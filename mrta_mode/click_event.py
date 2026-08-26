"""DTO for a single manual-click-to-target event."""

from dataclasses import dataclass


@dataclass
class ClickEvent:
    """A waypoint-set event for one bot, from the WS status channel (source
    "ws") or from the REST reconciliation safety net (source "reconcile").
    """

    address: str
    waypoints_mm: list[dict]
    source: str
