"""REST client for the DotBot controller's bot/map read endpoints.

GET /controller/dotbots, GET /controller/map_size -- see AGENT.md's
"REST API consumed (controller side)" section. Bootstrap + WS-outage
fallback only in the WS-driven design: MRTASession.connect() calls these
once at startup, and LivePositionStore / ManualClickTranslator fall back to
fetch_dotbots() when the WS status channel misses an update.
"""

import requests

from core import Coordinates2D


class GridStateManager:
    """Fetches DotBot state from the REST API and converts it to PIBT grid positions."""

    def __init__(self, base_url: str, cell_mm: int | None, map_cells: int):
        self.base_url = base_url
        self.cell_mm = cell_mm          # None -> derived from map size in set_map_size()
        self.map_cells = map_cells      # requested NxN resolution (used when cell_mm is None)
        self.map_cells_x = map_cells
        self.map_cells_y = map_cells

    def set_map_size(self, width_mm: int, height_mm: int) -> None:
        if self.cell_mm is None:
            # Derive square cells from the requested NxN grid resolution.
            self.cell_mm = max(1, width_mm // self.map_cells)
        if width_mm % self.cell_mm or height_mm % self.cell_mm:
            print(f"  ⚠ cell_mm={self.cell_mm} does not divide map "
                  f"{width_mm}x{height_mm} mm — grid will be truncated.")
        self.map_cells_x = max(1, width_mm // self.cell_mm)
        self.map_cells_y = max(1, height_mm // self.cell_mm)

    def fetch_dotbots(self) -> list[dict]:
        r = requests.get(f"{self.base_url}/controller/dotbots", timeout=5)
        r.raise_for_status()
        return [b for b in r.json() if b.get("lh2_position") and b.get("status") != 2]

    def fetch_map_size(self) -> tuple[int, int]:
        r = requests.get(f"{self.base_url}/controller/map_size", timeout=5)
        r.raise_for_status()
        data = r.json()
        return data["width"], data["height"]

    def mm_to_cell(self, x_mm: float, y_mm: float) -> Coordinates2D:
        gx = max(0, min(self.map_cells_x - 1, int(x_mm / self.cell_mm)))
        gy = max(0, min(self.map_cells_y - 1, int(y_mm / self.cell_mm)))
        return Coordinates2D(gx, gy)

    def cell_to_mm(self, pos: Coordinates2D) -> tuple[float, float]:
        return (pos.x * self.cell_mm + self.cell_mm // 2,
                pos.y * self.cell_mm + self.cell_mm // 2)

    def get_grid_state(self) -> dict[str, Coordinates2D]:
        dotbots = self.fetch_dotbots()
        raw: dict[str, Coordinates2D] = {}
        for bot in dotbots:
            p = bot["lh2_position"]
            raw[bot["address"]] = self.mm_to_cell(p["x"], p["y"])
        return self.resolve_conflicts(raw)

    def resolve_conflicts(self, positions: dict[str, Coordinates2D]) -> dict[str, Coordinates2D]:
        occupied: dict[Coordinates2D, str] = {}
        result: dict[str, Coordinates2D] = {}
        for address, pos in positions.items():
            if pos not in occupied:
                occupied[pos] = address
                result[address] = pos
            else:
                candidates = [
                    Coordinates2D(pos.x + dx, pos.y + dy)
                    for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1),
                                   (1, 1), (-1, 1), (1, -1), (-1, -1)]
                    if 0 <= pos.x + dx < self.map_cells_x and 0 <= pos.y + dy < self.map_cells_y
                ]
                free = next((c for c in candidates if c not in occupied), pos)
                occupied[free] = address
                result[address] = free
        return result
