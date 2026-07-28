from abc import ABC, abstractmethod
from typing import Iterable, Optional

from core import Position
from mrta import Task

from client.view import StepSnapshot


class SimulationDriver(ABC):
    """What a frontend is allowed to drive.

    ``SimulationController`` is the ordinary implementation; ``RunCollector``
    (in ``report``) is a decorator that wraps one and measures it. Both are
    handed to frontends interchangeably, so the thing a frontend depends on
    is this interface, not the controller class.

    **Why an interface rather than duck typing.** A decorator is only a
    decorator if it presents the same face as what it wraps — that is what
    makes it substitutable. Without a declared contract the substitution
    rested on ``__getattr__`` forwarding, which no one checks: a collector
    that forgot a method would fail at the first click in the window rather
    than at import. Declaring the contract also lets the class diagram say
    what is actually true, in both the measured and unmeasured cases.

    **Four verbs and no handles.** ``sim``, ``fleet`` and ``queue`` used to
    be on this interface because ``PygameFrontend`` read ``sim.grid`` to
    hit-test clicks — and ``queue`` in particular handed presentation a live
    ``QueueTaskSource``, mrta *behaviour*, which the layering forbids. A
    frame now carries what a click needs to be resolved (the board size, and
    ``result.positions`` for the reverse cell -> agent lookup), so nothing
    live has to cross this line. What sits on the other side can no longer
    be steered, only asked.
    """

    # ── Driving ──────────────────────────────────────────────────────────────

    @abstractmethod
    def step(self) -> StepSnapshot:
        """Input: none. Output: the snapshot of the step just executed."""
        ...

    @abstractmethod
    def run(self, steps: int) -> list[StepSnapshot]:
        """Input: a number of steps. Output: one snapshot per step."""
        ...

    @abstractmethod
    def snapshot(self) -> StepSnapshot:
        """Input: none. Output: a snapshot of the current state."""
        ...

    # ── Tasking ──────────────────────────────────────────────────────────────

    @abstractmethod
    def send_batch_to(
        self,
        target: Position,
        agent_ids: Optional[Iterable[int]] = None,
        priority: float = 5.0,
        within: Optional[frozenset] = None,
    ) -> list[Task]:
        """Input: a destination, the agents allowed to serve it, a priority,
        and optionally the cells the jobs may land on.
        Output: the tasks minted and queued.
        """
        ...
