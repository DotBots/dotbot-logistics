from dataclasses import dataclass

from core import Position, Zone


@dataclass(frozen=True)
class ZoneView:
    """Frozen projection of a Zone, safe to archive in a snapshot.

    Same rule as ``TaskView``: a snapshot copies values and never holds
    a live entity. A ``Zone`` can be deactivated or removed from the
    grid while a frontend is still replaying an old frame, and a frame
    that describes a zone must keep describing it.

    ``cells`` is what makes the projection useful rather than decorative:
    it is both what the frontend highlights on the board and what it
    hands back as ``send_batch_to(..., within=)``, so "send them to the
    loading station" lands in the station and nowhere else.
    """

    name: str
    cells: tuple

    @classmethod
    def of(cls, zone: Zone) -> "ZoneView":
        """Input: a live Zone.
        Output: a frozen projection built by copying values.
        """
        return cls(name=zone.name, cells=tuple(zone.cells))

    def contains(self, position: Position) -> bool:
        """Input: a position.
        Output: True if it falls inside this zone.

        Mirrors ``Zone.contains`` so a frontend can answer "which zone
        was clicked?" from the frame alone, without reaching into the
        engine for something the snapshot already carries.
        """
        return position in self.cells
