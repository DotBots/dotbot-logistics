#!/usr/bin/env python3
"""
real_dotbot_pibt.py — HARDENED version (synchronised step-by-step execution).

Computes PIBT trajectories and executes them step by step: at each step, one
waypoint per bot (its next cell), then waits for ALL bots to arrive before the
next step (synchronisation barrier). Preserves PIBT's collision-avoidance
guarantee on real asynchronous hardware. Also works with the simulator.
For the parallel + pipelined simulator version, see sim_dotbot_pibt.py.

Prerequisites (simulator):
    dotbot run simulator \\
        --map-size 2000x2000 \\
        --simulator-init-state simulator_init_state.toml

Prerequisites (real): gateway + controller connected to the swarm, bots localised (LH2).

Usage:
    python real_dotbot_pibt.py                 # synchronised step-by-step execution
    python real_dotbot_pibt.py --dry-run       # print targets without sending
    python real_dotbot_pibt.py --steps 40      # number of PIBT steps (default: 30)
    python real_dotbot_pibt.py --threshold 120 --step-timeout 10
    python real_dotbot_pibt.py --map-cells 8 --cell-mm 250  # 8x8 grid on 2000x2000 (default)

Grid <-> mm mapping:
    cell (gx, gy) -> centre mm = (gx*cell_mm + cell_mm//2, gy*cell_mm + cell_mm//2)
    pos (x_mm, y_mm) -> cell   = (int(x/cell_mm), int(y/cell_mm))
"""

import sys
import os
import math
import time
import argparse
import random
import requests

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "simulation"))

from core import Simulation, Agent, Grid, Position
from algo.pibt import PIBT

DEFAULT_BASE_URL = "http://localhost:8000"
DEFAULT_CELL_MM = 250     # cell size in mm (matches simulator_init_state.toml)
DEFAULT_MAP_CELLS = 8     # 8x8 grid = 2000x2000 mm
DEFAULT_STEPS = 30
DEFAULT_THRESHOLD = 100   # mm — a bot is considered "arrived" at its cell when
                          # distance < threshold. 100 mm: < half-cell (250 mm) to
                          # stay in the right cell, > LH2 noise (~20 mm) and real inertia.
DEFAULT_STEP_TIMEOUT = 8.0  # s — max wait for all bots to reach a PIBT step
DEFAULT_SETTLE = 0.3        # s — pause after arrival to let bots stop moving


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


def build_pibt(
    grid_state: dict[str, Position],
    cells_x: int,
    cells_y: int,
    rng: random.Random,
):
    """
    Builds the PIBT simulation from measured start cells and returns:
      sim             : ready Simulation (coordinator=PIBT)
      agents          : list of Agent (index = agent_id)
      addresses       : address of each agent (same index)
      goals_by_agent  : Agent -> target Position
      goals_by_address: address -> target Position
    """
    grid = Grid(width=cells_x, height=cells_y)

    addresses = list(grid_state.keys())
    agents = [Agent(agent_id=i, position=grid_state[addr]) for i, addr in enumerate(addresses)]
    goals_by_agent = _assign_random_goals(agents, grid, rng)

    pibt = PIBT(goals=goals_by_agent)
    sim = Simulation(grid, coordinator=pibt)
    for agent in agents:
        sim.add_agent(agent)

    goals_by_address = {addresses[i]: goals_by_agent[agents[i]] for i in range(len(agents))}
    return sim, agents, addresses, goals_by_agent, goals_by_address


def wait_until_all_arrived(
    gsm: "GridStateManager",
    targets: dict[str, Position],
    threshold: int,
    step_timeout: float,
    settle_s: float,
) -> set[str]:
    """
    Synchronisation barrier: polls the API until EVERY bot is within
    `threshold` mm of its target cell centre for the current step. Preserves
    the lock-step invariant of PIBT (without it, the collision-avoidance
    guarantee does not hold on asynchronous hardware). Returns arrived addresses;
    logs those that exceeded the timeout (execution continues — no deadlock
    if a bot stalls).
    """
    target_mm = {addr: gsm.cell_to_mm(cell) for addr, cell in targets.items()}
    deadline = time.time() + step_timeout
    arrived: set[str] = set()
    while time.time() < deadline:
        try:
            bots = {b["address"]: b["lh2_position"] for b in gsm.fetch_dotbots()}
        except requests.RequestException:
            time.sleep(0.2)
            continue
        arrived = {
            addr
            for addr, (tx, ty) in target_mm.items()
            if (p := bots.get(addr)) and math.hypot(p["x"] - tx, p["y"] - ty) < threshold
        }
        if len(arrived) == len(target_mm):
            break
        time.sleep(0.2)

    missing = set(target_mm) - arrived
    if missing:
        print(f"    ⚠ not arrived before timeout {step_timeout}s: "
              f"{', '.join(a[:8] + '...' for a in missing)}")
    if settle_s:
        time.sleep(settle_s)
    return arrived


def run_pibt_live(
    gsm: "GridStateManager",
    sim: Simulation,
    agents: list[Agent],
    addresses: list[str],
    goals_by_agent: dict[Agent, Position],
    threshold: int,
    steps: int,
    step_timeout: float,
    settle_s: float,
    dry_run: bool,
) -> None:
    """
    Executes PIBT step by step, synchronised on real bot movement:
      at each step -> compute next cell for each agent, send ONE waypoint per bot
      that changes cell, then wait for ALL to arrive before the next step.
    """
    prev = {addr: agents[i].position for i, addr in enumerate(addresses)}

    for step in range(1, steps + 1):
        sim.step()
        targets = {addr: agents[i].position for i, addr in enumerate(addresses)}
        moved = {addr: cell for addr, cell in targets.items() if cell != prev[addr]}

        print(f"\n── Step {step} ──")
        for addr, cell in targets.items():
            x, y = gsm.cell_to_mm(cell)
            tag = "" if addr in moved else "  (stationary)"
            print(f"  {addr[:8]}... -> cell {cell} = ({x:.0f}, {y:.0f}) mm{tag}")

        if not dry_run:
            for addr, cell in moved.items():
                try:
                    send_waypoints(gsm.base_url, addr, [gsm.cell_to_mm(cell)], threshold)
                except requests.RequestException as e:
                    print(f"    -> Send error {addr[:8]}...: {e}")
            wait_until_all_arrived(gsm, targets, threshold, step_timeout, settle_s)

        prev = targets
        if all(agents[i].position == goals_by_agent[agents[i]] for i in range(len(agents))):
            print(f"\nAll bots reached their goal at step {step}.")
            break


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

def fetch_grid_state_with_retry(
    gsm: GridStateManager,
    min_bots: int,
    attempts: int = 10,
    delay: float = 1.0,
) -> dict[str, Position]:
    """
    Waits until >= `min_bots` have a valid LH2 position. On real hardware, bots
    appear and localise progressively (LH2 coverage). Returns as soon as the
    threshold is met, or after `attempts` tries (last known state).
    """
    state: dict[str, Position] = {}
    for _ in range(attempts):
        state = gsm.get_grid_state()
        if len(state) >= min_bots:
            return state
        print(f"  ... {len(state)} bot(s) with LH2 position, waiting for >= {min_bots}...")
        time.sleep(delay)
    return state


def main() -> None:
    parser = argparse.ArgumentParser(description="PIBT -> DotBot waypoints demo (synchronised step-by-step)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print step-by-step targets without sending or waiting")
    parser.add_argument("--steps", type=int, default=DEFAULT_STEPS,
                        help=f"Number of PIBT steps (default: {DEFAULT_STEPS})")
    parser.add_argument("--cell-mm", type=int, default=DEFAULT_CELL_MM,
                        help=f"Cell size in mm (default: {DEFAULT_CELL_MM})")
    parser.add_argument("--map-cells", type=int, default=DEFAULT_MAP_CELLS,
                        help=f"Fallback NxN grid dimension if the API does not respond "
                             f"(default: {DEFAULT_MAP_CELLS}; normally derived from map_size)")
    parser.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD,
                        help=f"Arrival radius per cell in mm (default: {DEFAULT_THRESHOLD})")
    parser.add_argument("--step-timeout", type=float, default=DEFAULT_STEP_TIMEOUT,
                        help=f"Max wait (s) per step for all bots to arrive "
                             f"(default: {DEFAULT_STEP_TIMEOUT})")
    parser.add_argument("--settle", type=float, default=DEFAULT_SETTLE,
                        help=f"Pause (s) after arrival per step (default: {DEFAULT_SETTLE})")
    parser.add_argument("--min-bots", type=int, default=2,
                        help="Minimum number of localised bots required at startup (default: 2)")
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
        grid_state = fetch_grid_state_with_retry(gsm, args.min_bots)
        dotbots_raw = gsm.fetch_dotbots()
    except requests.RequestException as e:
        print(f"Error: cannot reach the controller ({e})")
        print("  -> start the real gateway + controller, or the simulator:")
        print("     dotbot run simulator --map-size 2000x2000 --simulator-init-state simulator_init_state.toml")
        sys.exit(1)

    if len(grid_state) < args.min_bots:
        print(f"Only {len(grid_state)} DotBot(s) with LH2 position "
              f"(min required: {args.min_bots}). Check LH2 coverage / power.")
        sys.exit(1)

    # Start positions: read live from the API (real, potentially random)
    pos_by_addr = {b["address"]: b["lh2_position"] for b in dotbots_raw}
    print(f"\n{len(grid_state)} DotBot(s) detected:")
    for addr, cell in grid_state.items():
        p = pos_by_addr.get(addr, {})
        print(f"  {addr[:8]}...  pos=({p.get('x', '?'):.0f}, {p.get('y', '?'):.0f}) mm  cell={cell}")

    print(f"\nPIBT planning — grid {gsm.map_cells_x}x{gsm.map_cells_y} cells "
          f"(derived from map {width_mm}x{height_mm} mm, cell={args.cell_mm} mm), "
          f"{args.steps} steps max...")

    sim, agents, addresses, goals_by_agent, goals_by_address = build_pibt(
        grid_state, gsm.map_cells_x, gsm.map_cells_y, rng
    )
    print("Assigned goals:")
    for addr in addresses:
        print(f"  {addr[:8]}...  start={grid_state[addr]}  goal={goals_by_address[addr]}")

    mode = "[dry-run] " if args.dry_run else ""
    print(f"\n{mode}Synchronised step-by-step execution "
          f"(threshold={args.threshold} mm, step-timeout={args.step_timeout}s)...")

    run_pibt_live(
        gsm, sim, agents, addresses, goals_by_agent,
        threshold=args.threshold,
        steps=args.steps,
        step_timeout=args.step_timeout,
        settle_s=args.settle,
        dry_run=args.dry_run,
    )

    if args.dry_run:
        print("\n[dry-run] No commands sent.")
    else:
        print(f"\nDone. Open {args.base} to visualise.")


if __name__ == "__main__":
    main()
