from typing import Optional

from core import Agent, Grid, Position, DispatchIntent, Dispatcher

from .task import Task, TaskState
from .task_source import TaskSource
from .allocator import Allocator


class FleetManager(Dispatcher):
    """Control loop bridging task sources and allocation, as a Dispatcher.

    Pure with respect to the engine: ``dispatch()`` reads state, updates
    task assignments, and returns a ``DispatchIntent`` describing the
    complete goals/priorities of the active tasks — it never touches the
    coordinator.

    One cycle, in order:
        complete -> watchdog -> prune -> intake -> allocate -> intent

    The watchdog lives here because FleetManager is the only component
    that sees a task's life *across* ticks. Putting it in the coordinator
    would re-couple navigation with allocation semantics — exactly what
    DispatchIntent separated.
    """

    def __init__(
        self,
        source: TaskSource,
        allocator: Allocator,
        patience: int = 12,
        max_attempts: int = 3,
    ) -> None:
        """Input: the task source, the allocation strategy, how many
        steps an assignee may go without getting closer to its target
        before being released, and how many assignees a task may burn
        through before it is failed.
        Output: None.
        """
        self.source = source
        self.allocator = allocator
        self.patience = patience
        self.max_attempts = max_attempts
        self.tasks: list[Task] = []
        self.completed_count = 0
        self.failed_count = 0
        # Task identity is stamped here, not by the sources: Task hashes on
        # task_id and is used as a dict key by Allocator, so two sources
        # numbering from zero would silently collapse each other's tasks.
        # The registry owns identity within it.
        self._next_task_id = 0

    def dispatch(self, agents: list[Agent], grid: Grid, step: int) -> DispatchIntent:
        """Input: all simulated agents, the grid, and the current step.
        Output: the DispatchIntent (goals/priorities) for the active
        tasks after one full cycle.
        """
        self._complete(agents)
        self._watchdog(step)
        self._prune()
        self._intake(step, grid)
        self._allocate(agents, grid)
        return self._build_intent()

    def set_priority(self, task_id: int, priority: float) -> None:
        """Input: a task id and its new priority.
        Output: None. Updates the task; the new value reaches the
        coordinator through the next dispatch's intent.
        """
        for task in self.tasks:
            if task.task_id == task_id:
                task.priority = priority
                return

    # ── Cycle stages ─────────────────────────────────────────────────────────

    def _complete(self, agents: list[Agent]) -> None:
        """Input: all simulated agents.
        Output: None. Marks assigned tasks whose assignee stands on the
        target as DONE.

        Sampling ``agent.position`` is exact here, not an approximation:
        dispatch runs every tick and an agent advances at most one cell
        per tick, so no cell can be stepped over between two samples.
        """
        for task in self.tasks:
            if task.state is TaskState.ASSIGNED and task.assignee is not None:
                if task.assignee.position == task.target:
                    task.state = TaskState.DONE

    def _watchdog(self, step: int) -> None:
        """Input: the current simulation step.
        Output: None. Releases assignees that have stopped making
        progress, and fails tasks that burned through too many of them.

        We do not try to *prove* a target reachable — reachability is not
        static in a world with deferred spawns, and proving it would
        duplicate the planner. We observe the absence of progress
        instead: if the Manhattan distance to the target has not improved
        for ``patience`` steps, this pairing is going nowhere.
        """
        for task in self.tasks:
            if task.state is not TaskState.ASSIGNED or task.assignee is None:
                continue

            distance = self._manhattan(task.assignee.position, task.target)
            if task.best_distance is None or distance < task.best_distance:
                task.best_distance = distance
                task.last_improvement_step = step
                continue

            if step - task.last_improvement_step < self.patience:
                continue

            # Stalled: free the agent so it is not consumed forever.
            task.assignee = None
            task.attempts += 1
            task.best_distance = None
            task.last_improvement_step = step
            if task.attempts >= self.max_attempts:
                task.state = TaskState.FAILED
            else:
                task.state = TaskState.PENDING

    def _prune(self) -> None:
        """Input: none.
        Output: None. Drops terminal tasks, counting them on the way out
        so that finished and abandoned work stays observable after the
        task object is gone.
        """
        kept = []
        for task in self.tasks:
            if task.state is TaskState.DONE:
                self.completed_count += 1
            elif task.state is TaskState.FAILED:
                self.failed_count += 1
            else:
                kept.append(task)
        self.tasks = kept

    def _intake(self, step: int, grid: Grid) -> None:
        """Input: the current simulation step and the grid.
        Output: None. Polls the source and registers new tasks, failing
        immediately those whose target is off the grid or sits under a
        blocking entity — a task no agent could ever complete should not
        be allowed to consume one.
        """
        for task in self.source.poll(step):
            task.task_id = self._next_task_id
            self._next_task_id += 1
            if not grid.is_valid(task.target) or self._is_obstructed(task.target, grid):
                task.state = TaskState.FAILED
                self.failed_count += 1
                continue
            task.last_improvement_step = step
            self.tasks.append(task)

    def _allocate(self, agents: list[Agent], grid: Grid) -> None:
        """Input: all simulated agents and the grid.
        Output: None. Matches pending tasks to free agents through the
        allocator and records the assignments.

        Tasks are grouped by eligibility class and the allocator is
        called once per class, unrestricted tasks last, with matched
        agents removed from the pool between calls. Eligibility is thus
        enforced without the Allocator interface knowing about it: a
        restriction on *who may be asked* belongs to the request, while
        the allocator only decides *how to match*.
        """
        pending = [t for t in self.tasks if t.state is TaskState.PENDING]
        if not pending:
            return

        assigned_agent_ids = {
            t.assignee.agent_id for t in self.tasks
            if t.state is TaskState.ASSIGNED and t.assignee is not None
        }
        free = [a for a in agents if a.agent_id not in assigned_agent_ids]
        if not free:
            return

        for eligible, group in self._by_eligibility(pending):
            if not free:
                return
            pool = free if eligible is None else [a for a in free if a.agent_id in eligible]
            if not pool:
                continue

            matches = self.allocator.allocate(group, pool, grid)
            taken = set()
            for task, agent in matches.items():
                task.state = TaskState.ASSIGNED
                task.assignee = agent
                task.best_distance = None
                taken.add(agent.agent_id)
            free = [a for a in free if a.agent_id not in taken]

    def _build_intent(self) -> DispatchIntent:
        """Input: none.
        Output: a DispatchIntent with, for every ASSIGNED task, its
        assignee's goal and allocation priority.
        """
        goals: dict[int, Position] = {}
        priorities: dict[int, float] = {}
        for task in self.tasks:
            if task.state is TaskState.ASSIGNED and task.assignee is not None:
                aid = task.assignee.agent_id
                goals[aid] = task.target
                priorities[aid] = task.priority
        return DispatchIntent(goals=goals, priorities=priorities)

    # ── Helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _by_eligibility(pending: list[Task]) -> list[tuple[Optional[frozenset[int]], list[Task]]]:
        """Input: the pending tasks.
        Output: (eligibility, tasks) groups, restricted classes first so
        that a task naming specific agents is served before an
        unrestricted one can take them.
        """
        groups: dict[Optional[frozenset[int]], list[Task]] = {}
        for task in pending:
            groups.setdefault(task.eligible, []).append(task)
        ordered = [(k, v) for k, v in groups.items() if k is not None]
        if None in groups:
            ordered.append((None, groups[None]))
        return ordered

    @staticmethod
    def _is_obstructed(position: Position, grid: Grid) -> bool:
        """Input: a position and the grid.
        Output: True if an active blocking entity (not an agent) sits there.
        """
        return any(
            e.blocks_movement and e.active
            for e in grid.get_entities_at(position)
            if not isinstance(e, Agent)
        )

    @staticmethod
    def _manhattan(a: Position, b: Position) -> int:
        """Input: two positions. Output: their Manhattan distance."""
        return abs(a.x - b.x) + abs(a.y - b.y)
