from dataclasses import dataclass, field

from core import Position, PlanResult

from .task_view import TaskView
from .zone_view import ZoneView


@dataclass(frozen=True)
class StepSnapshot:
    """Everything a frontend needs to draw one step, frozen.

    Produced by ``SimulationController``; the only thing frontends read.
    Every field is either immutable or a projection built by copying
    values, so a snapshot taken at step *n* still reads identically at
    step *n+50*. That is what makes it legitimate for a frontend to keep
    a history while the engine keeps running — the engine has no undo,
    so replaying the past is only sound if the past cannot change.

    It also carries what a frame needs to be *acted on*, not only drawn:
    the board size to turn a pixel into a cell, ``result.positions`` to
    turn a cell back into an agent, and ``accepts_tasks`` to know whether
    a click can dispatch anything at all. Without those a frontend has to
    reach into the live engine to resolve a click — which is how it ends
    up hit-testing the present against a frame that describes the past.
    """

    step:     int
    result:   PlanResult                                  # positions + diagnostics
    goals:    dict[int, Position] = field(default_factory=dict)
    objects:  tuple = ()                                  # ((Position, kind), ...)
    tasks:    tuple[TaskView, ...] = ()
    zones:    tuple[ZoneView, ...] = ()    # named regions, addressable by name
    width:    int = 0
    height:   int = 0
    accepts_tasks: bool = False                           # MRTA mode: a queue is attached
    completed: int = 0
    failed:    int = 0

    def counts(self) -> dict[str, int]:
        """Input: none.
        Output: task tallies for display — live tasks by state, plus the
        cumulative totals of pruned ones.
        """
        tally = {"pending": 0, "assigned": 0}
        for task in self.tasks:
            key = task.state.value
            if key in tally:
                tally[key] += 1
        tally["done"] = self.completed
        tally["failed"] = self.failed
        return tally
