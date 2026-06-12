import random
from core.coordinator import Coordinator
from core.position import Position
from core.agent import Agent
from core.grid import Grid

DIRECTIONS = [Position(0, 1), Position(0, -1), Position(-1, 0), Position(1, 0)]


class RandomWalkCoordinator(Coordinator):
    def plan(self, agents: list[Agent], grid: Grid) -> dict[int, Position]:
        return {a.agent_id: a.position + random.choice(DIRECTIONS) for a in agents}
