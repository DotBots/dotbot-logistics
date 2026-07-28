from dataclasses import dataclass
from typing import Optional

from core import Position
from mrta import Task, TaskState


@dataclass(frozen=True)
class TaskView:
    """Frozen projection of a Task, safe to archive in a snapshot.

    A ``Task`` is mutable and owned by ``FleetManager``, which keeps
    mutating it (ASSIGNED -> DONE) and eventually prunes it. Storing the
    task itself in a snapshot would let an archived frame rewrite its own
    past — and ``task.assignee.position`` (live) would contradict
    ``result.positions[id]`` (frozen) *inside the same snapshot*.

    So the assignee is reduced to its ``agent_id``: identity, not a
    reference. This is the rule ``PlanResult`` already applies by keying
    on ``agent_id`` rather than exposing ``Agent``.

    ``created_step`` is copied for the same reason the rest is: it is
    what a reader of the frame needs to say how long a task waited, and
    the fleet prunes the task that knows it on the tick it ends.

    Importing ``TaskState`` is a dependency on a *value*, not on
    behaviour — the frontends never see FleetManager, Allocator or
    TaskSource. Duplicating the enum client-side would reintroduce
    drift; typing it as ``str`` would lose the safety.
    """

    task_id: int
    target: Position
    state: TaskState
    priority: float
    assignee_id: Optional[int]
    attempts: int
    created_step: int = 0

    @classmethod
    def of(cls, task: Task) -> "TaskView":
        """Input: a live Task.
        Output: a frozen projection built by copying values — never
        holding the task or its assignee.
        """
        return cls(
            task_id=task.task_id,
            target=task.target,
            state=task.state,
            priority=task.priority,
            assignee_id=task.assignee.agent_id if task.assignee is not None else None,
            attempts=task.attempts,
            created_step=task.created_step,
        )
