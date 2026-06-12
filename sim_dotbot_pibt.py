#!/usr/bin/env python3
"""
sim_dotbot_pibt.py — SIMULATOR version (bulk waypoint dispatch).

Computes PIBT trajectories and sends them as waypoint lists to DotBots.
Each bot receives its entire path at once and follows it at its own pace.
Suited for the simulator (clean physics, sparse grid). For real asynchronous
hardware, prefer real_dotbot_pibt.py (synchronised step-by-step execution).

Prerequisites:
    dotbot run simulator \\
        --map-size 4000x4000 \\
        --init-state simulator_init_state.toml

Usage:
    python sim_dotbot_pibt.py              # fetch positions + send waypoints
    python sim_dotbot_pibt.py --dry-run    # simulate without sending commands
    python sim_dotbot_pibt.py --steps 40   # number of PIBT steps (default: 30)
    python sim_dotbot_pibt.py --map-cells 8 --cell-mm 500  # 8x8 grid (default)

Grid <-> mm mapping:
    cell (gx, gy) -> centre mm = (gx*cell_mm + cell_mm//2, gy*cell_mm + cell_mm//2)
    pos (x_mm, y_mm) -> cell   = (int(x/cell_mm), int(y/cell_mm))
"""

import sys
import os
import argparse
import random
import requests

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "simulation"))

from core import Simulation, Agent, Grid, Position
from algo.pibt import PIBT

DEFAULT_BASE_URL = "http://localhost:8000"
DEFAULT_CELL_MM = 500     # cell size (fixed in DotBotsMap.tsx:256)
DEFAULT_MAP_CELLS = 8     # 8x8 grid = 4000x4000 mm
DEFAULT_STEPS = 30
DEFAULT_THRESHOLD = 50    # mm — bot stops when distance < threshold
                          # 50 mm is enough: speed reduction starts at 100 mm


# ── GridStateManager ──────────────────────────────────────────────────────────

class GridStateManager:
    """
    Fetches the current DotBot state from the REST API and converts it
    to positions on the PIBT grid. Main tool for reading state at
    minimal cost (one REST call, zero simulation).
    """

    def __init__(self, base_url: str, cell_mm: int, map_cells: int):
        self.base_url = base_url
        self.cell_mm = cell_mm
        # Grid dimensions in cells (per axis). Initialised to the fallback
        # square; overridden by set_map_size() once the API responds.
        self.map_cells_x = map_cells
        self.map_cells_y = map_cells

    def set_map_size(self, width_mm: int, height_mm: int) -> None:
        """Derives grid dimensions (in cells) from the real map size."""
        if width_mm % self.cell_mm or height_mm % self.cell_mm:
            print(f"  ⚠ cell_mm={self.cell_mm} does not divide map "
                  f"{width_mm}x{height_mm} mm — grid will be truncated.")
        self.map_cells_x = max(1, width_mm // self.cell_mm)
        self.map_cells_y = max(1, height_mm // self.cell_mm)

    # ── API reads ──────────────────────────────────────────────────────────────

    def fetch_dotbots(self) -> list[dict]:
        """GET /controller/dotbots — returns bots with a valid LH2 position and not lost."""
        r = requests.get(f"{self.base_url}/controller/dotbots", timeout=5)
        r.raise_for_status()
        return [b for b in r.json() if b.get("lh2_position") and b.get("status") != 2]

    def fetch_map_size(self) -> tuple[int, int]:
        """GET /controller/map_size -> (width_mm, height_mm)."""
        r = requests.get(f"{self.base_url}/controller/map_size", timeout=5)
        r.raise_for_status()
        data = r.json()
        return data["width"], data["height"]

    # ── Conversion ─────────────────────────────────────────────────────────────

    def mm_to_cell(self, x_mm: float, y_mm: float) -> Position:
        """mm coordinates -> grid cell (clamped per axis to [0, map_cells_*-1])."""
        gx = max(0, min(self.map_cells_x - 1, int(x_mm / self.cell_mm)))
        gy = max(0, min(self.map_cells_y - 1, int(y_mm / self.cell_mm)))
        return Position(gx, gy)

    def cell_to_mm(self, pos: Position) -> tuple[float, float]:
        """Centre of the cell in mm."""
        return (pos.x * self.cell_mm + self.cell_mm // 2,
                pos.y * self.cell_mm + self.cell_mm // 2)

    # ── Grid state ────────────────────────────────────────────────────────────

    def get_grid_state(self) -> dict[str, Position]:
        """
        Returns address -> current cell for all active bots.
        Cost: a single REST call.
        """
        dotbots = self.fetch_dotbots()
        raw: dict[str, Position] = {}
        for bot in dotbots:
            p = bot["lh2_position"]
            raw[bot["address"]] = self.mm_to_cell(p["x"], p["y"])
        return self.resolve_conflicts(raw)

    def resolve_conflicts(self, positions: dict[str, Position]) -> dict[str, Position]:
        """
        If two bots land on the same cell, shifts the second to a free adjacent cell.
        Preserves insertion order (first bot keeps its cell).
        """
        occupied: dict[Position, str] = {}
        result: dict[str, Position] = {}
        for address, pos in positions.items():
            if pos not in occupied:
                occupied[pos] = address
                result[address] = pos
            else:
                candidates = [
                    Position(pos.x + dx, pos.y + dy)
                    for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1),
                                   (1, 1), (-1, 1), (1, -1), (-1, -1)]
                    if 0 <= pos.x + dx < self.map_cells_x and 0 <= pos.y + dy < self.map_cells_y
                ]
                free = next((c for c in candidates if c not in occupied), pos)
                occupied[free] = address
                result[address] = free
        return result


# ── PIBT planning ─────────────────────────────────────────────────────────────

def _assign_random_goals(
    agents: list[Agent],
    grid: Grid,
    rng: random.Random,
) -> dict[Agent, Position]:
    """Random goals: each agent receives a distinct cell drawn at random from the grid."""
    all_cells = [Position(x, y) for x in range(grid.width) for y in range(grid.height)]
    chosen = rng.sample(all_cells, len(agents))
    return {agent: cell for agent, cell in zip(agents, chosen)}


def run_pibt(
    grid_state: dict[str, Position],
    cells_x: int,
    cells_y: int,
    steps: int,
    rng: random.Random,
) -> tuple[dict[str, list[Position]], dict[str, Position]]:
    """
    Runs the PIBT simulation and returns:
      paths  : address -> list of grid Position (including start)
      goals  : address -> target grid Position
    """
    grid = Grid(width=cells_x, height=cells_y)

    addresses = list(grid_state.keys())
    agents = [Agent(agent_id=i, position=grid_state[addr]) for i, addr in enumerate(addresses)]
    goals_by_agent = _assign_random_goals(agents, grid, rng)

    pibt = PIBT(goals=goals_by_agent)
    sim = Simulation(grid, coordinator=pibt)
    for agent in agents:
        sim.add_agent(agent)

    paths: dict[str, list[Position]] = {addr: [agents[i].position] for i, addr in enumerate(addresses)}

    for _ in range(steps):
        sim.step()
        for agent in sim.agents:
            addr = addresses[agent.agent_id]
            if agent.position != paths[addr][-1]:
                paths[addr].append(agent.position)

    goals_by_address = {addresses[i]: goals_by_agent[agents[i]] for i in range(len(agents))}
    return paths, goals_by_address


# ── DotBot navigation ─────────────────────────────────────────────────────────

def send_waypoints(
    base_url: str,
    address: str,
    waypoints_mm: list[tuple[float, float]],
    threshold: int,
) -> None:
    payload = {
        "threshold": threshold,
        "waypoints": [{"x": float(x), "y": float(y)} for x, y in waypoints_mm],
    }
    r = requests.put(
        f"{base_url}/controller/dotbots/{address}/0/waypoints",
        json=payload,
        timeout=5,
    )
    r.raise_for_status()


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="PIBT -> DotBot waypoints demo (simulator, bulk dispatch)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print waypoints without sending them")
    parser.add_argument("--steps", type=int, default=DEFAULT_STEPS,
                        help=f"Number of PIBT steps (default: {DEFAULT_STEPS})")
    parser.add_argument("--cell-mm", type=int, default=DEFAULT_CELL_MM,
                        help=f"Cell size in mm (default: {DEFAULT_CELL_MM})")
    parser.add_argument("--map-cells", type=int, default=DEFAULT_MAP_CELLS,
                        help=f"Fallback NxN grid dimension if the API does not respond "
                             f"(default: {DEFAULT_MAP_CELLS}; normally derived from map_size)")
    parser.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD,
                        help=f"Arrival radius per waypoint in mm (default: {DEFAULT_THRESHOLD})")
    parser.add_argument("--base", default=DEFAULT_BASE_URL,
                        help=f"Controller URL (default: {DEFAULT_BASE_URL})")
    parser.add_argument("--seed", type=int, default=None,
                        help="RNG seed for reproducible random goals (default: random)")
    args = parser.parse_args()

    rng = random.Random(args.seed)
    gsm = GridStateManager(args.base, args.cell_mm, args.map_cells)

    print(f"Connecting to {args.base}...")
    try:
        width_mm, height_mm = gsm.fetch_map_size()
        gsm.set_map_size(width_mm, height_mm)  # derive grid from real map size
        grid_state = gsm.get_grid_state()
        dotbots_raw = gsm.fetch_dotbots()
    except requests.RequestException as e:
        print(f"Error: cannot reach the controller ({e})")
        print("  -> dotbot run simulator --map-size 4000x4000 --init-state simulator_init_state.toml")
        sys.exit(1)

    if not grid_state:
        print("No DotBot with a valid LH2 position available.")
        sys.exit(1)

    # Display real positions fetched from the API
    pos_by_addr = {b["address"]: b["lh2_position"] for b in dotbots_raw}
    print(f"\n{len(grid_state)} DotBot(s) detected:")
    for addr, cell in grid_state.items():
        p = pos_by_addr.get(addr, {})
        print(f"  {addr[:8]}...  pos=({p.get('x', '?'):.0f}, {p.get('y', '?'):.0f}) mm  cell={cell}")

    print(f"\nPIBT planning — grid {gsm.map_cells_x}x{gsm.map_cells_y} cells "
          f"(derived from map {width_mm}x{height_mm} mm, cell={args.cell_mm} mm), "
          f"{args.steps} steps...")

    paths, goals = run_pibt(grid_state, gsm.map_cells_x, gsm.map_cells_y, args.steps, rng)

    print()
    any_sent = False
    for addr, cell in grid_state.items():
        path = paths.get(addr, [])
        waypoints_cells = path[1:]  # exclude start position (already the current position)
        waypoints_mm = [gsm.cell_to_mm(p) for p in waypoints_cells]

        print(f"  Bot {addr[:8]}...  start={cell}  goal={goals.get(addr)}")
        if not waypoints_mm:
            print(f"    -> already at goal, no waypoints to send")
            continue
        for x, y in waypoints_mm:
            print(f"    ({x:.0f}, {y:.0f}) mm", end="")
        print()

        if not args.dry_run:
            try:
                send_waypoints(args.base, addr, waypoints_mm, args.threshold)
                print(f"    -> {len(waypoints_mm)} waypoint(s) sent (threshold={args.threshold} mm)")
                any_sent = True
            except requests.RequestException as e:
                print(f"    -> Error: {e}")
        else:
            print(f"    -> [dry-run] not sent")

    if args.dry_run:
        print("\n[dry-run] No commands sent.")
    elif any_sent:
        print("\nNavigation started. Open http://localhost:8000 to visualise.")


if __name__ == "__main__":
    main()
