import subprocess
import time
import uuid
from datetime import datetime, timezone
from statistics import mean
from typing import Optional

from core import Position
from mrta import TaskState

from client.control import SimulationDriver

from .agent_trace import AgentTrace
from .run_record import RunRecord, SCHEMA_VERSION
from .task_event import TaskEvent


class RunCollector(SimulationDriver):
    """Wraps a SimulationDriver and measures the run as it happens.

    A decorator, not a subclass **of the controller**: it wraps one rather
    than extending it. Implementing SimulationDriver is what makes it a
    decorator in the proper sense — presenting the same face as the thing it
    wraps is precisely what allows a frontend to drive either one without
    knowing which it got.

    It measures the **frame, not the engine**: every figure below comes from
    the StepSnapshot that ``step()`` already returns. Reaching for the live
    Simulation and FleetManager would have been defensible — measuring is a
    stronger claim than drawing — but it is not necessary: a frame carries
    the task states, the goals and every agent's position, which is all of
    what is measured here. So the metrics can be reworked, and they will be,
    without the engine or the fleet having to care.
    """

    def __init__(self, driver, config, label: str = "") -> None:
        """Input: the driver to observe, the ScenarioConfig it was built
        from, and a free-text label for the experiment.
        Output: None.
        """
        self._driver = driver
        self._config = config
        self._label = label

        # Identity is fixed at construction, not at record(): events() and
        # trace() must carry the same run_id as the RunRecord produced at
        # the end, so the three can be joined back together.
        self._run_id = uuid.uuid4().hex[:12]

        # The starting frame: it fixes the fleet size and stands in for the
        # last observation until the first step produces one.
        self._last_snap = driver.snapshot()
        self._agents = len(self._last_snap.result.positions)

        self._steps = 0
        self._wall_ms = 0.0
        self._started = time.perf_counter()

        # Task observation. FleetManager prunes a task on the same tick it
        # ends, so assignment has to be caught live, tick by tick.
        self._assigned_at: dict[int, int] = {}
        self._assigned_from: dict[int, Position] = {}
        self._assignee_of: dict[int, int] = {}
        self._attempts_of: dict[int, int] = {}
        self._states: dict[int, TaskState] = {}
        self._targets: dict[int, Position] = {}
        self._waits: list[int] = []
        self._services: list[int] = []
        self._detours: list[float] = []
        self._attempts_max = 0
        self._reassignments = 0
        self._failed_stalled = 0
        self._failed_unreachable = 0
        self._last_failed_count = 0
        self._events: list[TaskEvent] = []
        self._trace: list[AgentTrace] = []

        # Drift observation: where an agent parked when it lost its goal, and
        # how far traffic has pushed it since.
        self._parked: dict[int, Position] = {}
        self._drift: dict[int, int] = {}
        self._displaced = 0
        self._goalless_ticks = 0
        self._busy_ticks = 0
        self._idle_max = 0

    # ── The decorated contract ───────────────────────────────────────────────
    # Forwarded explicitly rather than through __getattr__. A decorator that
    # forwards by catch-all is only substitutable by accident: a missing
    # member surfaces as an AttributeError at the first click, not at import.
    # Declaring SimulationDriver makes the substitution checked instead.

    def snapshot(self):
        """Input: none. Output: the wrapped driver's current snapshot."""
        return self._driver.snapshot()

    def send_batch_to(self, target, agent_ids=None, priority: float = 5.0, within=None):
        """Input: a destination, the eligible agents, a priority, and the
        cells the jobs may land on.
        Output: the tasks minted and queued by the wrapped driver.
        """
        return self._driver.send_batch_to(target, agent_ids, priority, within)

    def step(self):
        """Input: none.
        Output: the step's snapshot, after recording this tick.
        """
        t0 = time.perf_counter()
        snapshot = self._driver.step()
        self._wall_ms += (time.perf_counter() - t0) * 1e3
        self._steps += 1
        self._observe(snapshot)
        self._last_snap = snapshot
        return snapshot

    def run(self, steps: int) -> list:
        """Input: a number of steps. Output: one snapshot per step."""
        return [self.step() for _ in range(steps)]

    # ── Observation ──────────────────────────────────────────────────────────

    def _observe(self, snap) -> None:
        """Input: the frame just produced. Output: None. Records one tick."""
        self._observe_tasks(snap)
        self._observe_agents(snap)

    def _observe_tasks(self, snap) -> None:
        """Input: the frame just produced.
        Output: None. Tracks task transitions from outside the fleet.

        A task that disappears is terminal, but pruning has already removed it,
        so the transition is inferred from the state seen on the previous tick
        plus the frame's cumulative counters. Intake rejections never appear in
        ``snap.tasks`` at all — they show up only as a jump in ``failed`` that
        no live task accounts for.
        """
        step = snap.step
        live = {}
        newly_failed = 0

        for task in snap.tasks:
            live[task.task_id] = task.state
            self._targets.setdefault(task.task_id, task.target)
            self._attempts_max = max(self._attempts_max, task.attempts)
            self._attempts_of[task.task_id] = task.attempts

            previous = self._states.get(task.task_id)
            if previous is None:
                self._events.append(self._event(snap, task, "created"))

            if task.state is TaskState.ASSIGNED and task.task_id not in self._assigned_at:
                self._assigned_at[task.task_id] = step
                self._assigned_from[task.task_id] = snap.result.positions[task.assignee_id]
                self._waits.append(step - task.created_step)
                self._assignee_of[task.task_id] = task.assignee_id
                self._events.append(self._event(snap, task, "assigned", agent_id=task.assignee_id))
            elif previous is TaskState.ASSIGNED and task.state is not TaskState.ASSIGNED:
                # Released by the watchdog: it may retry or give up here.
                self._reassignments += 1
                self._assigned_at.pop(task.task_id, None)
                holder = self._assignee_of.pop(task.task_id, None)
                if task.state is TaskState.FAILED:
                    self._failed_stalled += 1
                    newly_failed += 1
                    self._events.append(self._event(
                        snap, task, "failed", agent_id=holder, reason="stalled_watchdog"))
                else:
                    self._events.append(self._event(snap, task, "released", agent_id=holder))

        for task_id, previous in self._states.items():
            if task_id in live:
                continue
            # Gone from the live list: pruned this tick.
            start = self._assigned_at.pop(task_id, None)
            origin = self._assigned_from.pop(task_id, None)
            holder = self._assignee_of.pop(task_id, None)
            attempts = self._attempts_of.pop(task_id, 0)
            if previous is TaskState.FAILED:
                newly_failed += 1
            elif start is not None:
                service = step - start
                self._services.append(service)
                target = self._targets.get(task_id)
                if origin is not None and target is not None:
                    optimal = self._manhattan(origin, target)
                    if optimal:
                        self._detours.append(service / optimal)
                self._events.append(self._done_event(snap, task_id, holder, target, attempts))

        # Whatever failed without a live task to explain it was rejected at
        # intake, before it was ever visible here.
        delta = snap.failed - self._last_failed_count
        unattributed = max(0, delta - newly_failed)
        self._failed_unreachable += unattributed
        if unattributed:
            self._events.append(TaskEvent(
                run_id=self._run_id, step=step, task_id=None, event="failed",
                agent_id=None, x=None, y=None, target_x=None, target_y=None,
                attempts=0, reason="unreachable_intake",
            ))
        self._last_failed_count = snap.failed

        self._states = live

    def _event(self, snap, task, kind: str, agent_id: Optional[int] = None,
               reason: str = "") -> TaskEvent:
        """Input: the frame, the task it concerns, the event kind, the agent
        holding it (if any), and a failure reason.
        Output: the TaskEvent — the agent's *current* position, since the
        agent still exists in the frame even once the task does not.
        """
        position = snap.result.positions.get(agent_id) if agent_id is not None else None
        return TaskEvent(
            run_id=self._run_id, step=snap.step, task_id=task.task_id, event=kind,
            agent_id=agent_id,
            x=position.x if position is not None else None,
            y=position.y if position is not None else None,
            target_x=task.target.x, target_y=task.target.y,
            attempts=task.attempts, reason=reason,
        )

    def _done_event(self, snap, task_id: int, agent_id: Optional[int],
                     target: Optional[Position], attempts: int) -> TaskEvent:
        """Input: the frame, a task just pruned as completed, its last known
        assignee, target and attempt count.
        Output: the "done" TaskEvent — built without a TaskView, since the
        task is already gone from the frame by the time this fires.
        """
        position = snap.result.positions.get(agent_id) if agent_id is not None else None
        return TaskEvent(
            run_id=self._run_id, step=snap.step, task_id=task_id, event="done",
            agent_id=agent_id,
            x=position.x if position is not None else None,
            y=position.y if position is not None else None,
            target_x=target.x if target is not None else None,
            target_y=target.y if target is not None else None,
            attempts=attempts, reason="",
        )

    def _observe_agents(self, snap) -> None:
        """Input: the frame just produced.
        Output: None. Splits agent-ticks into busy and goal-less, and measures
        how far a goal-less agent has been pushed from where it parked.
        """
        goals = snap.goals
        idle_now = 0
        task_by_agent = {
            task.assignee_id: (task.task_id, task.state.value)
            for task in snap.tasks
            if task.assignee_id is not None
        }

        for aid, position in snap.result.positions.items():
            goal = goals.get(aid)
            task_id, task_state = task_by_agent.get(aid, (None, None))
            self._trace.append(AgentTrace(
                run_id=self._run_id, step=snap.step, agent_id=aid,
                x=position.x, y=position.y,
                goal_x=goal.x if goal is not None else None,
                goal_y=goal.y if goal is not None else None,
                task_id=task_id, task_state=task_state,
            ))

            if aid in goals:
                self._busy_ticks += 1
                self._parked.pop(aid, None)     # working again: not parked
                continue

            idle_now += 1
            self._goalless_ticks += 1
            if aid not in self._parked:
                self._parked[aid] = position
            elif position != self._parked[aid]:
                self._displaced += 1
                self._drift[aid] = max(
                    self._drift.get(aid, 0),
                    self._manhattan(position, self._parked[aid]),
                )
        self._idle_max = max(self._idle_max, idle_now)

    @staticmethod
    def _manhattan(a: Position, b: Position) -> int:
        """Input: two positions. Output: their Manhattan distance."""
        return abs(a.x - b.x) + abs(a.y - b.y)

    # ── Result ───────────────────────────────────────────────────────────────

    def record(self, label: Optional[str] = None) -> RunRecord:
        """Input: an optional label overriding the one given at construction.
        Output: the RunRecord for the run so far.

        The totals are read from the **last observed frame**, not from a
        fresh one: ``_observe`` derived every transition below from that
        same frame, and ``failed_unreachable`` in particular is the part
        of ``failed`` that no live task accounted for. Re-asking the
        driver here would date the totals a tick later than the
        transitions explaining them, and the two would stop adding up.
        """
        snap = self._last_snap
        config = self._config
        agent_ticks = max(1, self._agents * self._steps)

        # In static mode there is no fleet: the frame reports no task and
        # zero counters, which is the honest record of a run with no work.
        done = snap.completed
        failed = snap.failed
        unfinished = len(snap.tasks)
        created = done + failed + unfinished
        drifts = list(self._drift.values())

        return RunRecord(
            run_id=self._run_id,
            timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            schema_version=SCHEMA_VERSION,
            git_rev=_git_rev(),
            label=label if label is not None else self._label,

            width=config.width,
            height=config.height,
            agents=config.agents,
            obstacles=config.obstacles,
            algo=config.algo,
            mode=config.mode,
            allocator=config.allocator,
            task_source=config.tasks,
            seed=config.seed,
            patience=config.patience,
            max_attempts=config.max_attempts,
            zones=len(config.zones),

            steps=self._steps,
            wall_ms=round(self._wall_ms, 3),
            step_ms_mean=round(self._wall_ms / self._steps, 5) if self._steps else 0.0,

            tasks_created=created,
            tasks_done=done,
            tasks_failed=failed,
            tasks_unfinished=unfinished,
            completion_rate=round(done / created, 4) if created else None,
            failed_unreachable=self._failed_unreachable,
            failed_stalled=self._failed_stalled,
            reassignments=self._reassignments,
            attempts_max=self._attempts_max,

            wait_mean=round(mean(self._waits), 2) if self._waits else None,
            wait_max=max(self._waits) if self._waits else None,
            service_mean=round(mean(self._services), 2) if self._services else None,
            service_max=max(self._services) if self._services else None,
            detour_mean=round(mean(self._detours), 3) if self._detours else None,
            detour_max=round(max(self._detours), 3) if self._detours else None,

            drift_agents=len(drifts),
            drift_mean=round(mean(drifts), 2) if drifts else 0.0,
            drift_max=max(drifts) if drifts else 0,
            displaced_events=self._displaced,
            goalless_frac=round(self._goalless_ticks / agent_ticks, 4),

            busy_frac=round(self._busy_ticks / agent_ticks, 4),
            idle_max=self._idle_max,
        )

    def events(self) -> list[TaskEvent]:
        """Input: none.
        Output: every task-lifecycle transition observed so far, in the
        order it happened — what a summary row cannot answer: which task,
        which agent, and why.
        """
        return list(self._events)

    def trace(self) -> list[AgentTrace]:
        """Input: none.
        Output: one row per agent per step observed so far. Heavier than
        events(); reach for it when a task event log does not explain a
        deadlock or drift by itself.
        """
        return list(self._trace)


def _git_rev() -> str:
    """Input: none.
    Output: the short git revision, or "unknown" outside a repository.

    Stored on every row so a result stays attributable to the code that
    produced it — without it, a dataset spanning a refactor is unreadable.
    """
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=2, check=True,
        )
        return out.stdout.strip() or "unknown"
    except Exception:
        return "unknown"
