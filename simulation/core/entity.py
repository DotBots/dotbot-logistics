from .position import Position


class WorldEntity:
    """Base commune à toute entité placée sur la grille."""

    def __init__(
        self,
        entity_id: int,
        position: Position,
        appear_at: int = 0,
        blocks_movement: bool = False,
    ) -> None:
        self.entity_id = entity_id
        self.position = position
        self.appear_at = appear_at
        self.blocks_movement = blocks_movement

    @property
    def active(self) -> bool:
        return True
