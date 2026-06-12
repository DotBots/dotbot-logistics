from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .agent import Agent
    from .grid import Grid
    from .position import Position


class Coordinator(ABC):
    """
    Interface pour les algorithmes de coordination multi-agents (MAPF).

    Reçoit la liste complète des agents et la grille, retourne les prochaines
    positions pour tous les agents en une seule passe coordonnée.
    Branché dans Simulation via l'attribut optionnel `coordinator`.
    """

    @abstractmethod
    def plan(self, agents: list["Agent"], grid: "Grid") -> dict[int, "Position"]:
        """Retourne un dict agent_id → prochaine Position pour chaque agent."""
        ...
