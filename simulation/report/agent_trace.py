from dataclasses import dataclass, fields
from typing import Optional


@dataclass(frozen=True)
class AgentTrace:
    """One agent, one step, flattened into one row.

    Replay-quality detail for the rare case a task event log is not
    enough to see *why* something happened — a deadlock or drift is a
    property of several agents over several ticks, not of one task.
    One row per agent per step is verbose by design: it is meant to be
    filtered (``agent_id == 7``) or diffed against the previous step,
    not read top to bottom.
    """

    run_id:      str
    step:        int
    agent_id:    int
    x:           int
    y:           int
    goal_x:      Optional[int]
    goal_y:      Optional[int]
    task_id:     Optional[int]
    task_state:  Optional[str]

    @classmethod
    def columns(cls) -> list[str]:
        """Input: none. Output: the field names, in declaration order."""
        return [f.name for f in fields(cls)]

    def as_row(self) -> dict:
        """Input: none. Output: the row as a flat dict, ready to write."""
        return {f.name: getattr(self, f.name) for f in fields(self)}
