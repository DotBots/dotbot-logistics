from .position import Position


class WorldEntity:
    """Base class for any entity placed on the grid.

    Blocking obstacles do not need a dedicated subclass:
    ``WorldEntity(id, pos, blocks_movement=True)`` is enough.
    Entities with ``appear_at > 0`` are spawned later by the simulation.
    """

    def __init__(
        self,
        entity_id: int,
        position: Position,
        appear_at: int = 0,
        blocks_movement: bool = False,
        scale: int = 1,
    ) -> None:
        """Input: unique id, grid position, spawn step (0 = immediate),
        whether the entity blocks agent movement, and its footprint scale
        (in cells, default 1).
        Output: None.
        """
        self.entity_id = entity_id
        self.position = position
        self.appear_at = appear_at
        self.blocks_movement = blocks_movement
        self.scale = scale

    @property
    def cells(self) -> tuple:
        """Input: none.
        Output: every cell the entity occupies — just its position for
        everything except a ``Zone``, which covers several.

        This exists so ``Grid`` can index any entity without knowing
        which kinds span more than one cell. It is **not** ``scale``: it
        is an explicit list of cells for *indexing*, whereas ``scale``
        would be a movement footprint and would require the planner to
        change with it.
        """
        return (self.position,)

    @property
    def active(self) -> bool:
        """Input: none.
        Output: True while the entity takes part in the simulation
        (subclasses may override).
        """
        return True
