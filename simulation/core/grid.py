from typing import Optional, Type, TypeVar
from .position import Position
from .entity import WorldEntity
from .agent import Agent

E = TypeVar("E", bound=WorldEntity)


class Grid:
    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        self._agents: dict[Position, Agent] = {}
        self._static: dict[Position, list[WorldEntity]] = {}

    def is_valid(self, position: Position) -> bool:
        return 0 <= position.x < self.width and 0 <= position.y < self.height

    def is_blocked(self, position: Position) -> bool:
        """True if the cell contains an agent or an active blocking entity."""
        if position in self._agents:
            return True
        return any(
            e.blocks_movement and e.active
            for e in self._static.get(position, [])
        )

    def place(self, entity: WorldEntity) -> None:
        if not self.is_valid(entity.position):
            raise ValueError(f"Position {entity.position} out of bounds.")
        if isinstance(entity, Agent):
            if entity.position in self._agents:
                raise ValueError(f"Cell {entity.position} already occupied by an agent.")
            self._agents[entity.position] = entity
        else:
            self._static.setdefault(entity.position, []).append(entity)

    def remove(self, entity: WorldEntity) -> None:
        if isinstance(entity, Agent):
            self._agents.pop(entity.position, None)
        else:
            bucket = self._static.get(entity.position, [])
            if entity in bucket:
                bucket.remove(entity)
            if not bucket:
                self._static.pop(entity.position, None)

    def move(self, agent: Agent, new_position: Position) -> bool:
        if not self.is_valid(new_position) or self.is_blocked(new_position):
            return False
        self.remove(agent)
        agent.move_to(new_position)
        self._agents[new_position] = agent
        return True

    def get_agent_at(self, position: Position) -> Optional[Agent]:
        return self._agents.get(position)

    def get_entities_at(self, position: Position, kind: Optional[Type[E]] = None) -> list:
        agents = [self._agents[position]] if position in self._agents else []
        static = [e for e in self._static.get(position, []) if e.active]
        all_entities = agents + static
        if kind is not None:
            return [e for e in all_entities if isinstance(e, kind)]
        return all_entities

    def get_all(self, kind: Optional[Type[E]] = None) -> list:
        agents = list(self._agents.values())
        static = [e for bucket in self._static.values() for e in bucket]
        all_entities = agents + static
        if kind is not None:
            return [e for e in all_entities if isinstance(e, kind)]
        return all_entities

    def __repr__(self) -> str:
        return f"Grid({self.width}x{self.height}, agents={len(self._agents)})"
