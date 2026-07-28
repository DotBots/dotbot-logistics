from dataclasses import dataclass
from enum import Enum
from typing import Optional

from core import Agent, Position


class TaskState(Enum):
    """Lifecycle of a Task.

    PENDING -> ASSIGNED -> DONE is the nominal path. FAILED is the
    terminal state for work the fleet gave up on: a target that was
    unreachable from the start (rejected at intake), or one no assignee
    made progress towards after ``max_attempts`` tries. Failing a task
    visibly is the point — silently dropping it would hide an
    allocation deadlock behind a fleet that looks healthy.
    """

    PENDING = "pending"
    ASSIGNED = "assigned"
    DONE = "done"
    FAILED = "failed"


@dataclass(eq=False)
class Task:
    """A unit of work to be carried out by some agent: reach `target`.

    Created by a TaskSource, matched to an agent by an Allocator, then
    tracked by FleetManager through PENDING -> ASSIGNED -> DONE.
    Hashable via ``task_id`` (immutable), so it can be used as a dict
    key in ``Allocator.allocate()`` results.
    """

    task_id: int
    target: Position
    priority: float = 0.0
    state: TaskState = TaskState.PENDING
    assignee: Optional[Agent] = None
    created_step: int = 0

    # Restrict which agents may be assigned this task (agent_ids). None
    # means "any free agent". Set when a caller asks for a *specific*
    # batch of agents: eligibility is a property of the request, not of
    # the matching strategy, so Allocators stay unaware of it.
    eligible: Optional[frozenset[int]] = None

    # Progress bookkeeping, owned by FleetManager's watchdog.
    attempts: int = 0
    best_distance: Optional[int] = None
    last_improvement_step: int = 0

    def __eq__(self, other: object) -> bool:
        """Input: another object. Output: equality based on task_id."""
        if not isinstance(other, Task):
            return NotImplemented
        return self.task_id == other.task_id

    def __hash__(self) -> int:
        """Input: none. Output: hash based on the immutable task_id."""
        return hash(self.task_id)
