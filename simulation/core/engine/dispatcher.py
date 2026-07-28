from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from .dispatch_intent import DispatchIntent

if TYPE_CHECKING:
    from ..entities.agent import Agent
    from ..environment.grid import Grid


class Dispatcher(ABC):
    """Pre-planning hook run by ``Simulation.step()`` before the coordinator plans.

    A dispatcher reads the world state at the current step and returns a
    ``DispatchIntent`` — the absolute goals/priorities wanted this tick. It
    never touches the coordinator: the intent is data, handed by Simulation
    to ``Coordinator.plan()``. Keeping this abstraction in ``core`` lets
    ``Simulation`` own the tick order (dispatch -> plan) without importing
    ``mrta`` — the same dependency-inversion seam as ``Coordinator``.
    ``FleetManager`` and ``StaticDispatcher`` are concrete dispatchers.
    """

    @abstractmethod
    def dispatch(self, agents: list["Agent"], grid: "Grid", step: int) -> DispatchIntent:
        """Input: all simulated agents, the grid, and the current step.
        Output: a DispatchIntent with the complete goals/priorities for
        this tick (no side effect on the coordinator).
        """
        ...
