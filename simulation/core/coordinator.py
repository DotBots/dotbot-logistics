from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .agent import Agent
    from .grid import Grid
    from .position import Position


class Coordinator(ABC):
    """
    Interface for multi-agent coordination algorithms (MAPF).

    Receives the full list of agents and the grid, returns next positions
    for all agents in a single coordinated pass.
    Plugged into Simulation via the `coordinator` attribute.
    """

    @abstractmethod
    def plan(self, agents: list["Agent"], grid: "Grid") -> dict[int, "Position"]:
        """Returns a dict agent_id -> next Position for each agent."""
        ...
