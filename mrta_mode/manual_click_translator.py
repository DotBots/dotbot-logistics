"""Translates raw waypoint payloads (WS click events or REST reconciliation)
into grid cells, and tells apart a manual click from the echo of a waypoint
this script sent itself.
"""

import requests

from core import Position

from .click_event import ClickEvent
from .grid_state_manager import GridStateManager


class ManualClickTranslator:
    def __init__(self, gsm: GridStateManager):
        self._gsm = gsm
        self._commanded: dict[str, Position] = {}

    def seed_commanded(self, dotbots_raw: list[dict]) -> None:
        """Seeds `commanded` from each bot's live REST waypoints so leftovers
        from a previous session aren't misread as a fresh manual click on the
        first tick."""
        for bot in dotbots_raw:
            cells = self._waypoints_to_cells(bot.get("waypoints") or [])
            if cells:
                self._commanded[bot["address"]] = cells[-1]

    def record_commanded(self, address: str, cell: Position) -> None:
        self._commanded[address] = cell

    def translate(self, waypoints_mm: list[dict], current: Position) -> list[Position]:
        """Converts a waypoint chain to cells and drops adjacent duplicates
        and a leading no-op -- trims the one wasted dispatch tick an
        mm-rounding collision would cost."""
        result: list[Position] = []
        prev = current
        for cell in self._waypoints_to_cells(waypoints_mm):
            if cell != prev:
                result.append(cell)
            prev = cell
        return result

    def is_self_commanded(self, event: ClickEvent) -> bool:
        """True if this event is just the echo of a waypoint we sent ourselves."""
        last = self._commanded.get(event.address)
        if last is None:
            return False
        cells = self._waypoints_to_cells(event.waypoints_mm)
        return bool(cells) and cells[-1] == last

    def reconcile(self) -> list[ClickEvent]:
        """Safety net for clicks made while the WS listener was disconnected:
        compares each bot's REST-reported waypoints against what we last
        commanded."""
        try:
            bots = self._gsm.fetch_dotbots()
        except requests.RequestException:
            return []
        events = []
        for bot in bots:
            address = bot["address"]
            waypoints = bot.get("waypoints") or []
            if not waypoints:
                continue
            cells = self._waypoints_to_cells(waypoints)
            if cells and cells[-1] != self._commanded.get(address):
                events.append(ClickEvent(address=address, waypoints_mm=waypoints, source="reconcile"))
        return events

    def _waypoints_to_cells(self, waypoints_mm: list[dict]) -> list[Position]:
        return [
            self._gsm.mm_to_cell(wp["x"], wp["y"])
            for wp in waypoints_mm
            if "x" in wp and "y" in wp
        ]
