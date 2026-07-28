from dataclasses import dataclass, fields
from typing import Optional


@dataclass(frozen=True)
class TaskEvent:
    """One task-lifecycle transition, flattened into one row.

    Where RunRecord answers "how did the run go", TaskEvent answers
    "what happened to task 7" — the question an aggregate count cannot.
    ``task_id`` is None only for an intake rejection: a task refused
    before it ever became visible in a StepSnapshot, so there is no id
    to attach the row to.

    ``event`` is one of: created, assigned, released, done, failed.
    ``reason`` is set only for a failure: "stalled_watchdog" (gave up
    after max_attempts assignees) or "unreachable_intake" (refused on
    arrival, target invalid or blocked).
    """

    run_id:    str
    step:      int
    task_id:   Optional[int]
    event:     str
    agent_id:  Optional[int]
    x:         Optional[int]
    y:         Optional[int]
    target_x:  Optional[int]
    target_y:  Optional[int]
    attempts:  int
    reason:    str = ""

    @classmethod
    def columns(cls) -> list[str]:
        """Input: none. Output: the field names, in declaration order."""
        return [f.name for f in fields(cls)]

    def as_row(self) -> dict:
        """Input: none. Output: the event as a flat dict, ready to write."""
        return {f.name: getattr(self, f.name) for f in fields(self)}
