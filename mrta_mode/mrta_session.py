"""The activatable MRTA mode: owns the PIBT/MRTA simulation plus every
collaborator needed to drive it from manual clicks on the DotBot web UI.

start()/stop()/handle_click()/tick() let a caller other than a blocking CLI
while-loop -- a frontend -- drive it one step at a time; run() wraps tick()
in that while-loop for standalone CLI use.
"""

import time

import requests

from core import Simulation, Agent, Grid, Position
from algo import PIBTCoordinator, EasiestAllocator
from mrta import FleetManager, QueueTaskSource, Task, TaskState

from .click_event import ClickEvent
from .controller_status_listener import ControllerStatusListener
from .grid_state_manager import GridStateManager
from .live_position_store import LivePositionStore
from .manual_click_translator import ManualClickTranslator
from .waypoint_command_client import WaypointCommandClient


class MRTAConnectionError(RuntimeError):
    """Raised by MRTASession.connect() when the controller cannot be reached
    or too few dotbots are localised at startup."""


def _derive_ws_url(base_url: str) -> str:
    if base_url.startswith("https://"):
        return "wss://" + base_url[len("https://"):] + "/controller/ws/status"
    if base_url.startswith("http://"):
        return "ws://" + base_url[len("http://"):] + "/controller/ws/status"
    return base_url.rstrip("/") + "/controller/ws/status"


def _fetch_grid_state_with_retry(
    gsm: GridStateManager, min_bots: int, attempts: int = 10, delay: float = 1.0
) -> dict[str, Position]:
    state: dict[str, Position] = {}
    for _ in range(attempts):
        state = gsm.get_grid_state()
        if len(state) >= min_bots:
            return state
        print(f"  ... {len(state)} bot(s) with LH2 position, waiting for >= {min_bots}...")
        time.sleep(delay)
    return state


class MRTASession:
    def __init__(
        self,
        gsm: GridStateManager,
        listener: ControllerStatusListener,
        position_store: LivePositionStore,
        translator: ManualClickTranslator,
        command_client: WaypointCommandClient,
        sim: Simulation,
        agents: list[Agent],
        addresses: list[str],
        queue_source: QueueTaskSource,
        fleet: FleetManager,
        threshold: int,
        step_timeout: float,
        settle_s: float,
        dry_run: bool,
        idle_sleep: float,
        reconcile_interval: float,
    ) -> None:
        self.gsm = gsm
        self.listener = listener
        self.position_store = position_store
        self.translator = translator
        self.command_client = command_client
        self.sim = sim
        self.agents = agents
        self.addresses = addresses
        self.queue_source = queue_source
        self.fleet = fleet
        self.threshold = threshold
        self.step_timeout = step_timeout
        self.settle_s = settle_s
        self.dry_run = dry_run
        self.idle_sleep = idle_sleep
        self.reconcile_interval = reconcile_interval

        self._agent_by_addr = {addr: agents[i] for i, addr in enumerate(addresses)}
        self._prev = {addr: agents[i].position for i, addr in enumerate(addresses)}
        self._step = 0
        self._last_reconcile = 0.0
        self._unknown_addresses: set[str] = set()

    @classmethod
    def connect(
        cls,
        base_url: str,
        cell_mm: int | None,
        map_cells: int,
        min_bots: int,
        threshold: int,
        step_timeout: float,
        settle_s: float,
        dry_run: bool,
        idle_sleep: float,
        reconcile_interval: float,
        ws_url: str | None = None,
    ) -> "MRTASession":
        gsm = GridStateManager(base_url, cell_mm, map_cells)
        print(f"Connecting to {base_url}...")
        try:
            width_mm, height_mm = gsm.fetch_map_size()
            gsm.set_map_size(width_mm, height_mm)
            grid_state = _fetch_grid_state_with_retry(gsm, min_bots)
            dotbots_raw = gsm.fetch_dotbots()
        except requests.RequestException as e:
            raise MRTAConnectionError(f"cannot reach the controller ({e})") from e

        if len(grid_state) < min_bots:
            raise MRTAConnectionError(
                f"only {len(grid_state)} DotBot(s) localised (min: {min_bots}). "
                f"Check LH2 coverage."
            )

        pos_by_addr = {b["address"]: b["lh2_position"] for b in dotbots_raw}
        print(f"\n{len(grid_state)} DotBot(s) detected:")
        for addr, cell in grid_state.items():
            p = pos_by_addr.get(addr, {})
            print(f"  {addr[:8]}...  pos=({p.get('x', '?'):.0f}, {p.get('y', '?'):.0f}) mm  cell={cell}")

        grid = Grid(width=gsm.map_cells_x, height=gsm.map_cells_y)
        addresses = list(grid_state.keys())
        agents = [Agent(agent_id=i, position=grid_state[addr]) for i, addr in enumerate(addresses)]
        queue_source = QueueTaskSource()
        fleet = FleetManager(source=queue_source, allocator=EasiestAllocator())
        sim = Simulation(grid, coordinator=PIBTCoordinator(), dispatcher=fleet)
        for agent in agents:
            sim.add_agent(agent)

        translator = ManualClickTranslator(gsm)
        translator.seed_commanded(dotbots_raw)

        position_store = LivePositionStore(gsm)
        for bot in dotbots_raw:
            p = bot.get("lh2_position")
            if p:
                position_store.update(bot["address"], p["x"], p["y"])

        resolved_ws_url = ws_url or _derive_ws_url(base_url)
        listener = ControllerStatusListener(resolved_ws_url, position_store)
        command_client = WaypointCommandClient(base_url, threshold)

        print(f"\nGrid {gsm.map_cells_x}x{gsm.map_cells_y} cells "
              f"({width_mm}x{height_mm} mm, cell={gsm.cell_mm} mm).")
        print("MRTA mode: in the controller UI, select a bot, click a map point, "
              "\"Apply waypoints\" — PIBT takes it from there.")
        print(f"Listening on {resolved_ws_url} ...")

        return cls(
            gsm, listener, position_store, translator, command_client,
            sim, agents, addresses, queue_source, fleet,
            threshold=threshold,
            step_timeout=step_timeout,
            settle_s=settle_s,
            dry_run=dry_run,
            idle_sleep=idle_sleep,
            reconcile_interval=reconcile_interval,
        )

    def start(self) -> None:
        self.listener.start()

    def stop(self) -> None:
        self.listener.stop()

    def handle_click(self, event: ClickEvent) -> None:
        address = event.address
        if address not in self._agent_by_addr:
            if address not in self._unknown_addresses:
                print(f"  ⚠ waypoint on unknown bot {address[:8]}... (not present at "
                      f"startup) — ignored.")
                self._unknown_addresses.add(address)
            return
        if event.source == "ws" and self.translator.is_self_commanded(event):
            return  # our own PIBT-sent waypoint, echoed back

        agent = self._agent_by_addr[address]
        cells = self.translator.translate(event.waypoints_mm, agent.position)
        if not cells:
            return
        self._cancel_agent_tasks(agent.agent_id)
        self.queue_source.push_many([
            Task(task_id=0, target=c, eligible=frozenset({agent.agent_id}), created_step=self._step)
            for c in cells
        ])
        print(f"  -> manual target(s) for {address[:8]}...: {cells}")

    def tick(self) -> None:
        """Runs one step: drain click events, plan, send, wait for arrival.

        No pipelining (a manual click can land mid-travel and must be
        reflected in the very next sim.step(), so pre-computing ahead would
        either miss it or be thrown away).
        """
        self._step += 1
        events = self.listener.drain_clicks()
        now = time.time()
        if now - self._last_reconcile >= self.reconcile_interval:
            events += self.translator.reconcile()
            self._last_reconcile = now

        for event in events:
            self.handle_click(event)

        if not self.fleet.tasks and not events:
            time.sleep(self.idle_sleep)
            return

        try:
            self.sim.step()
        except ValueError as e:
            print(f"  ⚠ planning error, skipping tick: {e}")
            time.sleep(self.idle_sleep)
            return

        targets = {addr: self.agents[i].position for i, addr in enumerate(self.addresses)}
        moved = {addr: cell for addr, cell in targets.items() if cell != self._prev[addr]}

        if not moved:
            time.sleep(self.idle_sleep)
            self._prev = targets
            return

        print(f"\n── Tick {self._step} ──")
        for addr, cell in moved.items():
            x, y = self.gsm.cell_to_mm(cell)
            print(f"  {addr[:8]}... -> cell {cell} = ({x:.0f}, {y:.0f}) mm")

        if not self.dry_run:
            self.command_client.send_all_parallel(
                {addr: self.gsm.cell_to_mm(cell) for addr, cell in moved.items()}
            )
            for addr, cell in moved.items():
                self.translator.record_commanded(addr, cell)
            self.position_store.wait_until_all_arrived(
                targets, self.threshold, self.step_timeout, self.settle_s
            )

        self._prev = targets

    def run(self) -> None:
        """Blocking loop for standalone CLI use: ticks until Ctrl+C."""
        print("Ctrl+C to stop.\n")
        try:
            while True:
                self.tick()
        except KeyboardInterrupt:
            print("\nStopping (Ctrl+C)...")

    def _cancel_agent_tasks(self, agent_id: int) -> None:
        """Fails (not drops) that agent's pending/assigned tasks, so a
        re-click overrides in-flight navigation instead of queuing behind
        it -- matching the browser's own PUT, which already overwrites the
        bot's waypoint list unconditionally the instant it lands."""
        for task in self.fleet.tasks:
            if task.state not in (TaskState.PENDING, TaskState.ASSIGNED):
                continue
            targets_this_agent = (
                task.eligible == frozenset({agent_id})
                or (task.assignee is not None and task.assignee.agent_id == agent_id)
            )
            if targets_this_agent:
                task.state = TaskState.FAILED
                task.assignee = None
