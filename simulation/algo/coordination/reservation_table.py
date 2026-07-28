from typing import Optional

from core import Position, Agent


class ReservationTable:
    """Tracks which agent has reserved which cell for the next step.

    Used by PIBTCoordinator during its recursive planning pass to know
    whether a target cell is free, already claimed by the agent itself,
    or claimed by another agent (in which case the candidate is rejected).
    """

    def __init__(self) -> None:
        """Input: none. Output: None. Starts with no reservations."""
        self._reserved: dict[Position, Agent] = {}

    def reserve(self, agent: Agent, pos: Position) -> None:
        """Input: an agent and the cell it claims for the next step.
        Output: None. Releases any reservation previously held by this
        agent before recording the new one (an agent reserves at most
        one cell at a time).
        """
        self.release(agent)
        self._reserved[pos] = agent

    def release(self, agent: Agent) -> None:
        """Input: an agent.
        Output: None. Frees the cell currently reserved by this agent,
        if any. Used when PIBT backtracks on a failed candidate.
        """
        for pos, reserving in list(self._reserved.items()):
            if reserving == agent:
                del self._reserved[pos]

    def get_reserving_agent(self, pos: Position) -> Optional[Agent]:
        """Input: a grid cell.
        Output: the agent that has reserved it, or None.
        """
        return self._reserved.get(pos)

    def get_reservation(self, agent: Agent) -> Optional[Position]:
        """Input: an agent.
        Output: the cell it has reserved this step, or None if it has
        not reserved one yet.
        """
        for pos, reserving in self._reserved.items():
            if reserving == agent:
                return pos
        return None

    def clear(self) -> None:
        """Input: none.
        Output: None. Clears all reservations (called at the start of
        each planning step).
        """
        self._reserved.clear()
