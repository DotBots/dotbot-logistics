"""Pure simulation engine — no rendering or algorithm dependencies."""

from .entities import Position, WorldEntity, Agent, Zone
from .environment import Grid
from .engine import (
    Coordinator, PlanResult, DispatchIntent,
    Dispatcher, StaticDispatcher, Simulation,
)

__all__ = [
    "Position", "WorldEntity", "Agent", "Zone",
    "Grid", "Simulation",
    "Coordinator", "PlanResult", "DispatchIntent",
    "Dispatcher", "StaticDispatcher",
]
