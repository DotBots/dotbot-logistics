from typing import Optional, TYPE_CHECKING

from ..entities.position import Position
from .dispatch_intent import DispatchIntent
from .dispatcher import Dispatcher

if TYPE_CHECKING:
    from ..entities.agent import Agent
    from ..environment.grid import Grid


class StaticDispatcher(Dispatcher):
    """Trivial dispatcher: always returns the same fixed intent.

    Fallback for scenarios that do not need task allocation (MRTA): fixed
    goals and optional priorities are configured once at construction, and
    the same immutable ``DispatchIntent`` is returned on every tick.
    """

    def __init__(
        self,
        goals: dict[int, Position],
        priorities: Optional[dict[int, float]] = None,
    ) -> None:
        """Input: fixed goals (agent_id -> Position) and optional fixed
        priorities (agent_id -> float).
        Output: None.
        """
        self._intent = DispatchIntent(
            goals=dict(goals),
            priorities=dict(priorities) if priorities is not None else {},
        )

    def dispatch(self, agents: "list[Agent]", grid: "Grid", step: int) -> DispatchIntent:
        """Input: agents, grid, step (all ignored).
        Output: the same fixed DispatchIntent, every tick.
        """
        return self._intent
