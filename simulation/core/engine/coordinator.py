from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..entities.agent import Agent
    from ..environment.grid import Grid
    from .dispatch_intent import DispatchIntent
    from .plan_result import PlanResult


class Coordinator(ABC):
    """Strategy interface for multi-agent coordination algorithms (MAPF).

    Receives the full list of agents, the grid, and the tick's
    ``DispatchIntent`` (goals + optional priorities), and returns a
    ``PlanResult`` with the next position of every agent in a single
    coordinated pass. The intent is the *only* channel for goals and
    priorities — there is no external mutation of the coordinator, so
    the allocation layer and the navigation layer stay decoupled.
    Plugged into Simulation via the ``coordinator`` attribute.
    """

    @abstractmethod
    def plan(
        self,
        agents: list["Agent"],
        grid: "Grid",
        intent: "DispatchIntent",
    ) -> "PlanResult":
        """Input: all simulated agents, the grid (read-only), and this
        tick's DispatchIntent (goals + optional priorities).
        Output: a PlanResult with the next Position of every agent
        (``positions``/``moves`` filled; diagnostics optional). A
        priority-less coordinator simply ignores ``intent.priorities``.
        """
        ...
