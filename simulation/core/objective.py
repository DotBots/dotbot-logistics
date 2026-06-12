from typing import Optional, TYPE_CHECKING
from .entity import WorldEntity
from .position import Position

if TYPE_CHECKING:
    from .agent import Agent


class Objective(WorldEntity):
    def __init__(
        self,
        entity_id: int,
        position: Position,
        appear_at: int = 0,
        owner: Optional["Agent"] = None,
    ) -> None:
        super().__init__(entity_id, position, appear_at)
        self.owner = owner
        self.collected = False

    @property
    def active(self) -> bool:
        return not self.collected

    def __repr__(self) -> str:
        return (
            f"Objective(id={self.entity_id}, pos={self.position}, "
            f"collected={self.collected})"
        )
