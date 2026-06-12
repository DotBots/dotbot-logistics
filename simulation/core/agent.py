from .entity import WorldEntity
from .position import Position


class Agent(WorldEntity):
    def __init__(self, agent_id: int, position: Position) -> None:
        super().__init__(entity_id=agent_id, position=position, blocks_movement=True)
        self.steps_taken = 0

    @property
    def agent_id(self) -> int:
        return self.entity_id

    def move_to(self, new_position: Position) -> None:
        self.position = new_position
        self.steps_taken += 1

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Agent):
            return NotImplemented
        return self.agent_id == other.agent_id

    def __hash__(self) -> int:
        return hash(self.agent_id)

    def __repr__(self) -> str:
        return f"Agent(id={self.agent_id}, pos={self.position}, steps={self.steps_taken})"
