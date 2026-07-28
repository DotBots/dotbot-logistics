from math import isinf
from typing import Optional

from core import Agent


class PriorityManager:
    """Tracks base and effective (dynamic) priorities of every agent.

    Base priorities are set explicitly — at initialization, or later via
    priority inheritance and goal-reached demotion — while dynamic
    priorities are the effective values used to rank agents each step.
    Every dynamic priority decays by 1 on every ``update()`` call to
    prevent starvation of low-priority agents.
    """

    def __init__(self, initial_priorities: Optional[dict[Agent, float]] = None) -> None:
        """Input: optional initial base priorities (Agent -> float).
        Output: None.
        """
        self._base: dict[Agent, float] = (
            initial_priorities.copy() if initial_priorities is not None else {}
        )
        self._dynamic: dict[Agent, float] = self._base.copy()

    def update(self, agents: list[Agent]) -> None:
        """Input: all simulated agents.
        Output: None. Assigns an insertion-order base priority to any
        agent seen for the first time, then decrements every dynamic
        priority by 1.
        """
        for i, agent in enumerate(agents):
            if agent not in self._base:
                self._base[agent] = float(i)
                self._dynamic[agent] = float(i)
        for agent in self._dynamic:
            self._dynamic[agent] -= 1

    def get_priority(self, agent: Agent) -> float:
        """Input: an agent.
        Output: its current effective (dynamic) priority.
        """
        return self._dynamic[agent]

    def get_base(self, agent: Agent) -> float:
        """Input: an agent.
        Output: its current base priority, undecayed — what a caller must
        save before overwriting the base if it intends to restore it.
        """
        return self._base[agent]

    def set_base(self, agent: Agent, p: float) -> None:
        """Input: an agent and its new base priority.
        Output: None. Also updates the effective priority immediately —
        used for the goal-reached ``-inf`` demotion and for priority
        inheritance boosts, both of which must take effect this step.

        The accumulated anti-starvation drift (``dynamic - base``) is
        carried over rather than flattened: an agent handed a new task
        must not lose the waiting credit it built up. Infinities are
        excluded from the arithmetic — ``-inf - -inf`` is ``nan``, which
        would corrupt the ranking in ``plan()`` without raising.
        """
        old_base = self._base.get(agent)
        if old_base is None or isinf(old_base) or isinf(p):
            drift = 0.0
        else:
            drift = self._dynamic[agent] - old_base
        self._base[agent] = p
        self._dynamic[agent] = p + drift
