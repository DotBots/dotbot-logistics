#!/usr/bin/env python3
"""
sim_dotbot_mrta.py — Manual click-to-cell MRTA driving on the DotBot simulator.

Runs indefinitely (Ctrl+C to stop). Uses the existing, unmodified PyDotBot web UI as the
operator's interface: select a DotBot, click a point on the map, click "Apply waypoints" — the
existing flow. Instead of that raw waypoint going straight to hardware, this script detects it,
snaps it to the nearest grid cell, and hands it to PIBT as an MRTA Task restricted to that one
bot, so it navigates there step by step while avoiding every other bot being driven the same way.
Bots nobody has clicked simply stay parked.

Detection: every PUT .../waypoints call (browser or this script) triggers a broadcast on the
controller's ws://<base>/controller/ws/status channel — the same one the frontend itself already
connects to. A background thread listens there and forwards manual clicks (waypoints this script
did not itself just send) into the main loop. A periodic REST-based reconciliation pass recovers
any click made while that socket was down.

No changes to the PyDotBot controller: only its existing REST + WebSocket surface is used.

Prerequisites:
    dotbot run simulator \\
        --map-size 2000x2000 \\
        --simulator-init-state simulator_init_state.toml

Usage:
    python sim_dotbot_mrta.py              # persistent run, click-to-target via the web UI
    python sim_dotbot_mrta.py --dry-run    # connect and build the grid, send/wait nothing
    python sim_dotbot_mrta.py --map-cells 8  # 8x8 grid on 2000x2000 (250 mm cells)

Grid <-> mm mapping:
    cell (gx, gy) -> centre mm = (gx*cell_mm + cell_mm//2, gy*cell_mm + cell_mm//2)
    pos (x_mm, y_mm) -> cell   = (int(x/cell_mm), int(y/cell_mm))
"""

import sys
import os
import math
import time
import json
import queue
import asyncio
import threading
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
import websockets

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "simulation"))

from core import Simulation, Agent, Grid, Position
from algo import PIBTCoordinator, EasiestAllocator
from mrta import FleetManager, QueueTaskSource, Task, TaskState

DEFAULT_BASE_URL = "http://localhost:8000"
DEFAULT_CELL_MM = None      # cell size in mm; if None, derived from map_size / map_cells
DEFAULT_MAP_CELLS = 5       # grid resolution NxN (5 -> 400 mm cells, 8 -> 250 mm on 2000x2000)
DEFAULT_THRESHOLD = 100     # mm — bot considered "arrived" when distance < threshold.
                            # 100 mm: < half-cell (200 mm), > LH2 noise (~20 mm).
DEFAULT_STEP_TIMEOUT = 8.0  # s — max wait per PIBT step
DEFAULT_SETTLE = 0.3        # s — pause after arrival to let bots stop moving
DEFAULT_IDLE_SLEEP = 0.2    # s — pace of the idle/no-movement backoff loop
DEFAULT_RECONCILE_INTERVAL = 2.0  # s — period of the REST-based WS-outage safety net


# ── GridStateManager ──────────────────────────────────────────────────────────
# Identical to sim_dotbot_pibt.py — see that file; duplicated rather than shared,
# matching this codebase's existing convention across the L1/L2 scripts.

class GridStateManager:
    """Fetches DotBot state from the REST API and converts it to PIBT grid positions."""

    def __init__(self, base_url: str, cell_mm: int | None, map_cells: int):
        self.base_url = base_url
        self.cell_mm = cell_mm          # None -> derived from map size in set_map_size()
        self.map_cells = map_cells      # requested NxN resolution (used when cell_mm is None)
        self.map_cells_x = map_cells
        self.map_cells_y = map_cells

    def set_map_size(self, width_mm: int, height_mm: int) -> None:
        if self.cell_mm is None:
            # Derive square cells from the requested NxN grid resolution.
            self.cell_mm = max(1, width_mm // self.map_cells)
        if width_mm % self.cell_mm or height_mm % self.cell_mm:
            print(f"  ⚠ cell_mm={self.cell_mm} does not divide map "
                  f"{width_mm}x{height_mm} mm — grid will be truncated.")
        self.map_cells_x = max(1, width_mm // self.cell_mm)
        self.map_cells_y = max(1, height_mm // self.cell_mm)

    def fetch_dotbots(self) -> list[dict]:
        r = requests.get(f"{self.base_url}/controller/dotbots", timeout=5)
        r.raise_for_status()
        return [b for b in r.json() if b.get("lh2_position") and b.get("status") != 2]

    def fetch_map_size(self) -> tuple[int, int]:
        r = requests.get(f"{self.base_url}/controller/map_size", timeout=5)
        r.raise_for_status()
        data = r.json()
        return data["width"], data["height"]

    def mm_to_cell(self, x_mm: float, y_mm: float) -> Position:
        gx = max(0, min(self.map_cells_x - 1, int(x_mm / self.cell_mm)))
        gy = max(0, min(self.map_cells_y - 1, int(y_mm / self.cell_mm)))
        return Position(gx, gy)

    def cell_to_mm(self, pos: Position) -> tuple[float, float]:
        return (pos.x * self.cell_mm + self.cell_mm // 2,
                pos.y * self.cell_mm + self.cell_mm // 2)

    def get_grid_state(self) -> dict[str, Position]:
        dotbots = self.fetch_dotbots()
        raw: dict[str, Position] = {}
        for bot in dotbots:
            p = bot["lh2_position"]
            raw[bot["address"]] = self.mm_to_cell(p["x"], p["y"])
        return self.resolve_conflicts(raw)

    def resolve_conflicts(self, positions: dict[str, Position]) -> dict[str, Position]:
        occupied: dict[Position, str] = {}
        result: dict[str, Position] = {}
        for address, pos in positions.items():
            if pos not in occupied:
                occupied[pos] = address
                result[address] = pos
            else:
                candidates = [
                    Position(pos.x + dx, pos.y + dy)
                    for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1),
                                   (1, 1), (-1, 1), (1, -1), (-1, -1)]
                    if 0 <= pos.x + dx < self.map_cells_x and 0 <= pos.y + dy < self.map_cells_y
                ]
                free = next((c for c in candidates if c not in occupied), pos)
                occupied[free] = address
                result[address] = free
        return result


# ── MRTA planning ─────────────────────────────────────────────────────────────

def build_mrta(
    grid_state: dict[str, Position],
    cells_x: int,
    cells_y: int,
):
    """Builds a Simulation driven by FleetManager/QueueTaskSource instead of fixed goals.

    No goals at startup: FleetManager._build_intent() only emits a goal for an
    ASSIGNED task, and PIBTCoordinator falls back to an agent's own position
    when it has none — every bot stays parked until its first manual click.
    """
    grid = Grid(width=cells_x, height=cells_y)
    addresses = list(grid_state.keys())
    agents = [Agent(agent_id=i, position=grid_state[addr]) for i, addr in enumerate(addresses)]
    queue_source = QueueTaskSource()
    fleet = FleetManager(source=queue_source, allocator=EasiestAllocator())
    sim = Simulation(grid, coordinator=PIBTCoordinator(), dispatcher=fleet)
    for agent in agents:
        sim.add_agent(agent)
    return sim, agents, addresses, queue_source, fleet


def _cancel_agent_tasks(fleet: FleetManager, agent_id: int) -> None:
    """Input: the fleet manager and an agent id.
    Output: None. Fails (not drops) that agent's pending/assigned tasks, so a
    re-click overrides in-flight navigation instead of queuing behind it —
    matching the browser's own PUT, which already overwrites the bot's
    waypoint list unconditionally the instant it lands.
    """
    for task in fleet.tasks:
        if task.state not in (TaskState.PENDING, TaskState.ASSIGNED):
            continue
        targets_this_agent = (
            task.eligible == frozenset({agent_id})
            or (task.assignee is not None and task.assignee.agent_id == agent_id)
        )
        if targets_this_agent:
            task.state = TaskState.FAILED
            task.assignee = None


# ── Manual-click detection ─────────────────────────────────────────────────────

def _derive_ws_url(base_url: str) -> str:
    if base_url.startswith("https://"):
        return "wss://" + base_url[len("https://"):] + "/controller/ws/status"
    if base_url.startswith("http://"):
        return "ws://" + base_url[len("http://"):] + "/controller/ws/status"
    return base_url.rstrip("/") + "/controller/ws/status"


def _waypoints_to_cells(waypoints_mm: list[dict], gsm: GridStateManager) -> list[Position]:
    return [
        gsm.mm_to_cell(wp["x"], wp["y"])
        for wp in waypoints_mm
        if "x" in wp and "y" in wp
    ]


def _dedupe_consecutive(cells: list[Position], current: Position | None) -> list[Position]:
    """Input: a target cell chain and the agent's current cell.
    Output: the chain with adjacent duplicates and a leading no-op dropped —
    trims the one wasted dispatch tick an mm-rounding collision would cost.
    """
    result: list[Position] = []
    prev = current
    for cell in cells:
        if cell != prev:
            result.append(cell)
        prev = cell
    return result


def _is_self_commanded(ev: dict, commanded: dict[str, Position], gsm: GridStateManager) -> bool:
    """True if this WS event is just the echo of a waypoint we sent ourselves."""
    last = commanded.get(ev["address"])
    if last is None:
        return False
    cells = _waypoints_to_cells(ev["waypoints_mm"], gsm)
    return bool(cells) and cells[-1] == last


def _reconcile_from_rest(gsm: GridStateManager, commanded: dict[str, Position]) -> list[dict]:
    """Safety net for clicks made while the WS listener was disconnected: compares
    each bot's REST-reported waypoints against what we last commanded.
    """
    try:
        bots = gsm.fetch_dotbots()
    except requests.RequestException:
        return []
    events = []
    for bot in bots:
        address = bot["address"]
        waypoints = bot.get("waypoints") or []
        if not waypoints:
            continue
        cells = _waypoints_to_cells(waypoints, gsm)
        if cells and cells[-1] != commanded.get(address):
            events.append({"address": address, "waypoints_mm": waypoints, "source": "reconcile"})
    return events


class WaypointWatcher:
    """Background WS listener: forwards every waypoints-set broadcast into a queue.

    Connects to /controller/ws/status — the controller's broadcast channel (the
    one the frontend itself already uses), NOT /controller/ws/dotbots, which is
    a separate, bidirectional command-relay channel that never receives
    notify_clients() broadcasts. Retries forever with exponential backoff: the
    controller may not be up yet at script start, or may restart mid-session,
    and this is meant to run indefinitely.
    """

    def __init__(self, ws_url: str, out_queue: "queue.Queue[dict]") -> None:
        self.ws_url = ws_url
        self.out_queue = out_queue
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        asyncio.run(self._listen_forever())

    async def _listen_forever(self) -> None:
        backoff = 1.0
        while not self._stop.is_set():
            try:
                async with websockets.connect(self.ws_url, open_timeout=5) as ws:
                    print(f"  [ws] connected to {self.ws_url}")
                    backoff = 1.0
                    async for raw in ws:
                        self._handle_raw(raw)
            except (OSError, websockets.exceptions.WebSocketException) as e:
                print(f"  [ws] disconnected ({e}); retrying in {backoff:.0f}s")
            if self._stop.is_set():
                break
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 10.0)

    def _handle_raw(self, raw: str) -> None:
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            return
        if msg.get("cmd") != 2:  # DotBotNotificationCommand.UPDATE
            return
        data = msg.get("data") or {}
        address = data.get("address")
        waypoints = data.get("lh2_waypoints")
        if not address or not waypoints:
            return
        self.out_queue.put({"address": address, "waypoints_mm": waypoints, "source": "ws"})


def _drain_ws_queue(q: "queue.Queue[dict]") -> list[dict]:
    events = []
    while True:
        try:
            events.append(q.get_nowait())
        except queue.Empty:
            break
    return events


# ── DotBot navigation ─────────────────────────────────────────────────────────
# Identical to sim_dotbot_pibt.py.

def send_waypoints(
    base_url: str,
    address: str,
    waypoints_mm: list[tuple[float, float]],
    threshold: int,
) -> None:
    payload = {
        "threshold": threshold,
        "waypoints": [{"x": float(x), "y": float(y)} for x, y in waypoints_mm],
    }
    r = requests.put(
        f"{base_url}/controller/dotbots/{address}/0/waypoints",
        json=payload,
        timeout=5,
    )
    r.raise_for_status()


def _send_all_parallel(
    base_url: str,
    moved_mm: dict[str, tuple[float, float]],
    threshold: int,
) -> None:
    if not moved_mm:
        return
    with ThreadPoolExecutor(max_workers=len(moved_mm)) as executor:
        futures = {
            executor.submit(send_waypoints, base_url, addr, [wp_mm], threshold): addr
            for addr, wp_mm in moved_mm.items()
        }
        for future in as_completed(futures):
            addr = futures[future]
            try:
                future.result()
            except requests.RequestException as e:
                print(f"    -> Send error {addr[:8]}...: {e}")


def wait_until_all_arrived(
    gsm: GridStateManager,
    targets: dict[str, Position],
    threshold: int,
    step_timeout: float,
    settle_s: float,
) -> set[str]:
    target_mm = {addr: gsm.cell_to_mm(cell) for addr, cell in targets.items()}
    deadline = time.time() + step_timeout
    arrived: set[str] = set()
    poll_interval = 0.05  # starts at 50 ms, exponential back-off up to 500 ms
    while time.time() < deadline:
        try:
            bots = {b["address"]: b["lh2_position"] for b in gsm.fetch_dotbots()}
        except requests.RequestException:
            time.sleep(poll_interval)
            continue
        arrived = {
            addr
            for addr, (tx, ty) in target_mm.items()
            if (p := bots.get(addr)) and math.hypot(p["x"] - tx, p["y"] - ty) < threshold
        }
        if len(arrived) == len(target_mm):
            break
        time.sleep(poll_interval)
        poll_interval = min(poll_interval * 1.5, 0.5)

    missing = set(target_mm) - arrived
    if missing:
        print(f"    ⚠ not arrived before timeout {step_timeout}s: "
              f"{', '.join(a[:8] + '...' for a in missing)}")
    if settle_s:
        time.sleep(settle_s)
    return arrived


def fetch_grid_state_with_retry(
    gsm: GridStateManager,
    min_bots: int,
    attempts: int = 10,
    delay: float = 1.0,
) -> dict[str, Position]:
    state: dict[str, Position] = {}
    for _ in range(attempts):
        state = gsm.get_grid_state()
        if len(state) >= min_bots:
            return state
        print(f"  ... {len(state)} bot(s) with LH2 position, waiting for >= {min_bots}...")
        time.sleep(delay)
    return state


# ── Persistent execution ────────────────────────────────────────────────────

def run_mrta_live(
    gsm: GridStateManager,
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
    raw_queue: "queue.Queue[dict]",
    commanded: dict[str, Position],
) -> None:
    """Runs until Ctrl+C. No pipelining (a manual click can land mid-travel and
    must be reflected in the very next sim.step(), so pre-computing ahead would
    either miss it or be thrown away) — step, send, wait, like real_dotbot_pibt.py.
    """
    agent_by_addr = {addr: agents[i] for i, addr in enumerate(addresses)}
    prev = {addr: agents[i].position for i, addr in enumerate(addresses)}
    step = 0
    last_reconcile = 0.0
    unknown_addresses: set[str] = set()

    try:
        while True:
            step += 1
            events = _drain_ws_queue(raw_queue)
            now = time.time()
            if now - last_reconcile >= reconcile_interval:
                events += _reconcile_from_rest(gsm, commanded)
                last_reconcile = now

            for ev in events:
                address = ev["address"]
                if address not in agent_by_addr:
                    if address not in unknown_addresses:
                        print(f"  ⚠ waypoint on unknown bot {address[:8]}... (not present at "
                              f"startup) — ignored.")
                        unknown_addresses.add(address)
                    continue
                if ev["source"] == "ws" and _is_self_commanded(ev, commanded, gsm):
                    continue  # our own PIBT-sent waypoint, echoed back

                agent = agent_by_addr[address]
                cells = _dedupe_consecutive(
                    _waypoints_to_cells(ev["waypoints_mm"], gsm), agent.position
                )
                if not cells:
                    continue
                _cancel_agent_tasks(fleet, agent.agent_id)
                queue_source.push_many([
                    Task(task_id=0, target=c, eligible=frozenset({agent.agent_id}), created_step=step)
                    for c in cells
                ])
                print(f"  -> manual target(s) for {address[:8]}...: {cells}")

            if not fleet.tasks and not events:
                time.sleep(idle_sleep)
                continue

            try:
                sim.step()
            except ValueError as e:
                print(f"  ⚠ planning error, skipping tick: {e}")
                time.sleep(idle_sleep)
                continue

            targets = {addr: agents[i].position for i, addr in enumerate(addresses)}
            moved = {addr: cell for addr, cell in targets.items() if cell != prev[addr]}

            if not moved:
                time.sleep(idle_sleep)
                prev = targets
                continue

            print(f"\n── Tick {step} ──")
            for addr, cell in moved.items():
                x, y = gsm.cell_to_mm(cell)
                print(f"  {addr[:8]}... -> cell {cell} = ({x:.0f}, {y:.0f}) mm")

            if not dry_run:
                _send_all_parallel(
                    gsm.base_url,
                    {addr: gsm.cell_to_mm(cell) for addr, cell in moved.items()},
                    threshold,
                )
                for addr, cell in moved.items():
                    commanded[addr] = cell
                wait_until_all_arrived(gsm, targets, threshold, step_timeout, settle_s)

            prev = targets
    except KeyboardInterrupt:
        print("\nStopping (Ctrl+C)...")


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="PIBT -> DotBot simulator MRTA demo (persistent, click-to-target via the web UI)"
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Connect and build the grid without sending or waiting "
                             "(mainly a startup/wiring smoke test — nothing moves without a "
                             "live click)")
    parser.add_argument("--cell-mm", type=int, default=DEFAULT_CELL_MM,
                        help="Cell size in mm (default: derived from map_size / --map-cells)")
    parser.add_argument("--map-cells", type=int, default=DEFAULT_MAP_CELLS,
                        help=f"Grid resolution NxN (default: {DEFAULT_MAP_CELLS}; "
                             f"5 -> 400 mm cells, 8 -> 250 mm on a 2000x2000 map)")
    parser.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD,
                        help=f"Arrival radius per cell in mm (default: {DEFAULT_THRESHOLD})")
    parser.add_argument("--step-timeout", type=float, default=DEFAULT_STEP_TIMEOUT,
                        help=f"Max wait (s) per step (default: {DEFAULT_STEP_TIMEOUT})")
    parser.add_argument("--settle", type=float, default=DEFAULT_SETTLE,
                        help=f"Pause (s) after arrival per step (default: {DEFAULT_SETTLE})")
    parser.add_argument("--min-bots", type=int, default=2,
                        help="Minimum localised bots required at startup (default: 2)")
    parser.add_argument("--base", default=DEFAULT_BASE_URL,
                        help=f"Controller URL (default: {DEFAULT_BASE_URL})")
    parser.add_argument("--ws-url", default=None,
                        help="Controller WebSocket status URL (default: derived from --base)")
    parser.add_argument("--idle-sleep", type=float, default=DEFAULT_IDLE_SLEEP,
                        help=f"Pause (s) between idle ticks with nothing to do "
                             f"(default: {DEFAULT_IDLE_SLEEP})")
    parser.add_argument("--reconcile-interval", type=float, default=DEFAULT_RECONCILE_INTERVAL,
                        help=f"Period (s) of the REST-based WS-outage safety net "
                             f"(default: {DEFAULT_RECONCILE_INTERVAL})")
    args = parser.parse_args()

    gsm = GridStateManager(args.base, args.cell_mm, args.map_cells)

    print(f"Connecting to {args.base}...")
    try:
        width_mm, height_mm = gsm.fetch_map_size()
        gsm.set_map_size(width_mm, height_mm)
        grid_state = fetch_grid_state_with_retry(gsm, args.min_bots)
        dotbots_raw = gsm.fetch_dotbots()
    except requests.RequestException as e:
        print(f"Error: cannot reach the controller ({e})")
        print("  -> dotbot run simulator --map-size 2000x2000 --simulator-init-state simulator_init_state.toml")
        sys.exit(1)

    if len(grid_state) < args.min_bots:
        print(f"Only {len(grid_state)} DotBot(s) localised (min: {args.min_bots}). Check LH2 coverage.")
        sys.exit(1)

    pos_by_addr = {b["address"]: b["lh2_position"] for b in dotbots_raw}
    print(f"\n{len(grid_state)} DotBot(s) detected:")
    for addr, cell in grid_state.items():
        p = pos_by_addr.get(addr, {})
        print(f"  {addr[:8]}...  pos=({p.get('x', '?'):.0f}, {p.get('y', '?'):.0f}) mm  cell={cell}")

    sim, agents, addresses, queue_source, fleet = build_mrta(
        grid_state, gsm.map_cells_x, gsm.map_cells_y
    )

    # Seed `commanded` from each bot's live REST waypoints so leftovers from a
    # previous session aren't misread as a fresh manual click on tick 1.
    commanded: dict[str, Position] = {}
    for bot in dotbots_raw:
        cells = _waypoints_to_cells(bot.get("waypoints") or [], gsm)
        if cells:
            commanded[bot["address"]] = cells[-1]

    ws_url = args.ws_url or _derive_ws_url(args.base)
    raw_queue: "queue.Queue[dict]" = queue.Queue()
    watcher = WaypointWatcher(ws_url, raw_queue)

    print(f"\nGrid {gsm.map_cells_x}x{gsm.map_cells_y} cells "
          f"({width_mm}x{height_mm} mm, cell={gsm.cell_mm} mm).")
    print("MRTA mode: in the controller UI, select a bot, click a map point, "
          "\"Apply waypoints\" — PIBT takes it from there.")
    print(f"Listening on {ws_url} ...")
    print("Ctrl+C to stop.\n")

    watcher.start()
    try:
        run_mrta_live(
            gsm, sim, agents, addresses, queue_source, fleet,
            threshold=args.threshold,
            step_timeout=args.step_timeout,
            settle_s=args.settle,
            dry_run=args.dry_run,
            idle_sleep=args.idle_sleep,
            reconcile_interval=args.reconcile_interval,
            raw_queue=raw_queue,
            commanded=commanded,
        )
    finally:
        watcher.stop()


if __name__ == "__main__":
    main()
