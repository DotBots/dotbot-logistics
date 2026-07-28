from collections import deque
from typing import Iterable, Optional

from core import Agent, Position, Simulation, PlanResult, Zone
from mrta import FleetManager, QueueTaskSource, Task

from client.view import StepSnapshot, TaskView, ZoneView

from .driver import SimulationDriver


class SimulationController(SimulationDriver):
    """Scripting API over a Simulation: step it, query it, task it.

    The single seam between a built scenario and whatever drives it — a
    pygame window, a terminal, a benchmark script. Frontends talk to this
    class through ``SimulationDriver`` and read ``StepSnapshot``; they
    never touch the coordinator, the fleet or the grid, which is what
    keeps them ignorant of ``algo`` and of mrta behaviour.

    ``sim``, ``fleet`` and ``queue`` stay here and are *not* on the ABC:
    they are how this class is built and observed from inside
    ``client.control``, not part of what it offers outward.

    ``step()`` stays a pure "advance by one": it owns no clock and no
    loop, so the caller decides the pacing.
    """

    def __init__(
        self,
        simulation: Simulation,
        fleet: Optional[FleetManager] = None,
        queue: Optional[QueueTaskSource] = None,
    ) -> None:
        """Input: the simulation, plus the fleet and task queue when the
        scenario runs in MRTA mode (both None in static mode).
        Output: None.
        """
        self._sim = simulation
        self._fleet = fleet
        self._queue = queue
        self._last_result = PlanResult(
            positions={a.agent_id: a.position for a in simulation.agents},
        )

    # ── The wrapped scenario (read-only: a controller does not re-target) ────

    @property
    def sim(self) -> Simulation:
        """The simulation being driven."""
        return self._sim

    @property
    def fleet(self) -> Optional[FleetManager]:
        """The fleet, in MRTA mode; None in static mode."""
        return self._fleet

    @property
    def queue(self) -> Optional[QueueTaskSource]:
        """The interactive task queue, in MRTA mode; None in static mode."""
        return self._queue

    # ── Driving ──────────────────────────────────────────────────────────────

    def step(self) -> StepSnapshot:
        """Input: none.
        Output: the snapshot of the step just executed.
        """
        self._last_result = self.sim.step()
        return self.snapshot()

    def run(self, steps: int) -> list[StepSnapshot]:
        """Input: a number of steps.
        Output: one snapshot per step, in order.
        """
        return [self.step() for _ in range(steps)]

    # ── Tasking ──────────────────────────────────────────────────────────────

    def send_batch_to(
        self,
        target: Position,
        agent_ids: Optional[Iterable[int]] = None,
        priority: float = 5.0,
        within: Optional[frozenset] = None,
    ) -> list[Task]:
        """Input: a destination, the agents to send there (all free
        agents if None), the tasks' priority, and optionally the cells
        the jobs are allowed to land on.
        Output: the tasks queued, one per agent, on ``target`` and the
        free cells around it.

        "Send this batch to B" *is* an allocation problem: we mint one
        task per destination cell and let the allocator distribute them.
        Nothing bypasses the planner, so the batch inherits collision
        avoidance for free — which is why there is no manual per-cell
        driving anywhere in this API.

        ``within`` bounds *where the jobs may land*, not where the search
        may go: "send them to the loading station" must mean the station
        itself, and stop rather than spill into the aisle once it is full.
        """
        if self.queue is None:
            raise RuntimeError("send_batch_to requires MRTA mode (no task queue attached).")

        ids = list(agent_ids) if agent_ids is not None else [a.agent_id for a in self.sim.agents]
        if not ids:
            return []

        cells = self._free_cells_around(target, len(ids), within)
        eligible = frozenset(ids)
        tasks = [
            # task_id is stamped by FleetManager at intake.
            Task(
                task_id=0,
                target=cell,
                priority=priority,
                created_step=self.sim.current_step,
                eligible=eligible,
            )
            for cell in cells
        ]
        self.queue.push_many(tasks)
        return tasks

    def _free_cells_around(
        self,
        target: Position,
        count: int,
        within: Optional[frozenset] = None,
    ) -> list[Position]:
        """Input: a centre, how many cells are wanted, and optionally the
        cells that may be collected.
        Output: up to ``count`` reachable cells, ``target`` first, then
        outwards in growing rings.

        A BFS rather than a radius scan: it follows connectivity, so it
        never hands back a cell that looks close but sits behind a wall.
        ``within`` filters what is *collected*, never what is *traversed*:
        a zone reached through a corridor outside it is still one zone,
        and bounding the walk instead would make it two.
        """
        grid = self.sim.grid
        found: list[Position] = []
        seen = {target}
        queue = deque([target])

        while queue and len(found) < count:
            current = queue.popleft()
            if (
                grid.is_valid(current)
                and not self._is_obstructed(current)
                and (within is None or current in within)
            ):
                found.append(current)
            for step in (Position(0, -1), Position(0, 1), Position(-1, 0), Position(1, 0)):
                nxt = current + step
                if nxt not in seen and grid.is_valid(nxt):
                    seen.add(nxt)
                    queue.append(nxt)
        return found

    def _is_obstructed(self, position: Position) -> bool:
        """Input: a position.
        Output: True if an active blocking entity (not an agent) sits
        there. Agents do not count: they move out of the way, so a cell
        merely occupied right now is still a valid destination.
        """
        return any(
            e.blocks_movement and e.active
            for e in self.sim.grid.get_entities_at(position)
            if not isinstance(e, Agent)
        )

    # ── Observing ────────────────────────────────────────────────────────────

    def snapshot(self) -> StepSnapshot:
        """Input: none.
        Output: a frozen StepSnapshot of the current state.

        Tasks are projected into ``TaskView`` by copying values — never
        the Task, never its assignee. A snapshot handed out here must
        still read identically after the engine has run on and pruned
        the tasks it describes.
        """
        tasks = tuple(TaskView.of(t) for t in self.fleet.tasks) if self.fleet else ()
        return StepSnapshot(
            step=self.sim.current_step,
            result=self._last_result,
            goals=dict(self.sim.last_intent.goals),
            objects=self._objects(),
            tasks=tasks,
            zones=self._zones(),
            width=self.sim.grid.width,
            height=self.sim.grid.height,
            accepts_tasks=self._queue is not None,
            completed=self.fleet.completed_count if self.fleet else 0,
            failed=self.fleet.failed_count if self.fleet else 0,
        )

    def _objects(self) -> tuple:
        """Input: none.
        Output: ((Position, kind), ...) for the active static entities.

        Zones are excluded: they are ground labels, not obstacles, and
        this tuple is what the board draws as walls. They travel in
        ``StepSnapshot.zones`` instead, where their name and full extent
        survive — neither of which fits a (position, kind) pair.
        """
        return tuple(
            (e.position, "obstacle")
            for e in self.sim.grid.get_all()
            if not isinstance(e, (Agent, Zone)) and e.active
        )

    def _zones(self) -> tuple:
        """Input: none.
        Output: a frozen ZoneView per active zone on the grid.
        """
        return tuple(
            ZoneView.of(z) for z in self.sim.grid.get_all(Zone) if z.active
        )
