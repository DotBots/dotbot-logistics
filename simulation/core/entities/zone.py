from typing import Iterable

from .entity import WorldEntity
from .position import Position


class Zone(WorldEntity):
    """A named region of the grid — "send the fleet to the loading station".

    A group of cells the operator addresses by name instead of by
    coordinates: loading station, working space, empty-rack area. Like
    any WorldEntity it can spawn late (``appear_at``) and go inactive;
    unlike the others it covers several cells, so the grid indexes it at
    each of them rather than at a single corner. Asking "what is here?"
    anywhere inside a zone therefore finds it.

    A zone never blocks movement: it labels ground, it does not occupy
    it. Robots cross it, park in it and work in it exactly as before,
    which is what lets it be added to a running scenario without
    touching the planner.

    It deliberately does **not** use ``WorldEntity.scale``. ``scale`` is
    reserved and unimplemented; making it work would mean an agent
    *footprint*, forcing ``Grid``, ``is_blocked``, ``Simulation._validate``
    and PIBT's candidate generation to change together. ``cells`` is an
    explicit list and touches none of that.
    """

    def __init__(
        self,
        entity_id: int,
        name: str,
        cells: Iterable[Position],
        appear_at: int = 0,
    ) -> None:
        """Input: unique id, the operator-facing name, the cells covered
        (at least one, duplicates dropped), and the spawn step.
        Output: None.
        """
        ordered = tuple(dict.fromkeys(cells))
        if not ordered:
            raise ValueError(f"Zone {name!r} must cover at least one cell.")
        # The inherited ``position`` is a nominal anchor, kept so a Zone is
        # a WorldEntity like any other; ``cells`` is what the grid indexes.
        super().__init__(entity_id, ordered[0], appear_at=appear_at, blocks_movement=False)
        self.name = name
        self._cells = ordered

    @property
    def cells(self) -> tuple:
        """Input: none.
        Output: the cells this zone covers, in declaration order and
        without duplicates.
        """
        return self._cells

    def contains(self, position: Position) -> bool:
        """Input: a position.
        Output: True if it falls inside this zone.
        """
        return position in self._cells

    def __repr__(self) -> str:
        return f"Zone({self.name!r}, {len(self._cells)} cells)"
