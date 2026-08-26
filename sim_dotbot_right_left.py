#!/usr/bin/env python3
"""
sim_dotbot_right_left.py — Simulator demo: all bots to the right edge, then all to the left.

Two MRTA phases, run back to back:
  1. one Task per rightmost cell is pushed with `eligible=None` (any free
     agent may take it) — a *mutual* objective for the fleet: the only
     condition is that every target cell ends up occupied, not which bot
     ends up on which. FleetManager + EasiestAllocator assign each task to
     whichever free bot is nearest it, so bots don't fight over a cell
     pre-assigned by a naive row/column sort;
  2. once every task has resolved (DONE, or FAILED past its retry budget),
     wait `--wait` seconds (default 5s);
  3. same, with cells packed against the left edge.

This mirrors sim_dotbot_mrta.py's build_mrta() (FleetManager + QueueTaskSource
+ EasiestAllocator as the Simulation's dispatcher) rather than
sim_dotbot_pibt.py's StaticDispatcher: a *fixed per-agent* goal is exactly the
assignment that was causing bots to struggle into position, since it forces a
specific bot onto a specific cell even when another bot is a much shorter,
uncontested path away. GridStateManager / send_waypoints /
wait_until_all_arrived are duplicated from the other bridge scripts rather
than imported, matching this repo's existing convention (see AGENT.md).

Prerequisites:
    dotbot run simulator \\
        --map-size 2000x2000 \\
        --simulator-init-state simulator_init_state.toml

Usage:
    python sim_dotbot_right_left.py                # right, wait 5s, left
    python sim_dotbot_right_left.py --dry-run       # print targets without sending
    python sim_dotbot_right_left.py --wait 10       # wait 10s between right and left
    python sim_dotbot_right_left.py --map-cells 8   # 8x8 grid on 2000x2000 (250 mm cells)

Grid <-> mm mapping:
    cell (gx, gy) -> centre mm = (gx*cell_mm + cell_mm//2, gy*cell_mm + cell_mm//2)
    pos (x_mm, y_mm) -> cell   = (int(x/cell_mm), int(y/cell_mm))
"""

import sys
import os
import math
import time
import argparse
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "simulation"))

from core import Simulation, Agent, Grid, Position
from algo import PIBTCoordinator, EasiestAllocator
from mrta import FleetManager, QueueTaskSource, Task

DEFAULT_BASE_URL = "http://localhost:8000"
DEFAULT_CELL_MM = None      # cell size in mm; if None, derived from map_size / map_cells
DEFAULT_MAP_CELLS = 5       # grid resolution NxN (5 -> 400 mm cells, 8 -> 250 mm on 2000x2000)
DEFAULT_STEPS = 30          # max PIBT steps per phase (right, then left)
DEFAULT_THRESHOLD = 100     # mm — bot considered "arrived" when distance < threshold.
                            # 100 mm: < half-cell (200 mm), > LH2 noise (~20 mm).
DEFAULT_STEP_TIMEOUT = 8.0  # s — max wait per PIBT step
DEFAULT_SETTLE = 0.3        # s — pause after arrival to let bots stop moving
DEFAULT_WAIT = 5.0          # s — pause between "all at right" and starting the left phase


# ── GridStateManager ──────────────────────────────────────────────────────────
# Identical to sim_dotbot_pibt.py — see that file; duplicated rather than shared,
# matching this codebase's existing convention across the L1/L2 scripts.

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

    def mm_to_cell(self, x_mm: float, y_mm: float) -> Position:
        gx = max(0, min(self.map_cells_x - 1, int(x_mm / self.cell_mm)))
        gy = max(0, min(self.map_cells_y - 1, int(y_mm / self.cell_mm)))
        return Position(gx, gy)

    def cell_to_mm(self, pos: Position) -> tuple[float, float]:
        return (pos.x * self.cell_mm + self.cell_mm // 2,
                pos.y * self.cell_mm + self.cell_mm // 2)

    def get_grid_state(self) -> dict[str, Position]:
        dotbots = self.fetch_dotbots()
        raw: dict[str, Position] = {}
        for bot in dotbots:
            p = bot["lh2_position"]
            raw[bot["address"]] = self.mm_to_cell(p["x"], p["y"])
        return self.resolve_conflicts(raw)

    def resolve_conflicts(self, positions: dict[str, Position]) -> dict[str, Position]:
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


# ── MRTA planning ─────────────────────────────────────────────────────────────

def _edge_cells(cells_x: int, cells_y: int, side: str, n: int) -> list[Position]:
    """Input: grid size, "left"/"right", and how many cells are needed.
    Output: the n cells closest to that edge, filling one full column at a
    time (edge column first) before moving inward — this is the *set* of
    cells the fleet must cover, not an assignment of any cell to any bot.
    """
    columns = range(cells_x - 1, -1, -1) if side == "right" else range(cells_x)
    cells: list[Position] = []
    for x in columns:
        for y in range(cells_y):
            cells.append(Position(x, y))
        if len(cells) >= n:
            break
    if len(cells) < n:
        raise ValueError(
            f"grid too small ({cells_x}x{cells_y} = {cells_x * cells_y} cells) "
            f"to place {n} agents on the {side} side"
        )
    return cells[:n]


def build_sim(grid_state: dict[str, Position], cells_x: int, cells_y: int):
    """Builds a Simulation driven by FleetManager/QueueTaskSource, same shape
    as sim_dotbot_mrta.py's build_mrta(): the dispatcher is a fleet of
    interchangeable tasks, not a fixed per-agent goal, so a phase's target
    cells are a *mutual* objective — any free bot may take any cell.
    """
    grid = Grid(width=cells_x, height=cells_y)
    addresses = list(grid_state.keys())
    agents = [Agent(agent_id=i, position=grid_state[addr]) for i, addr in enumerate(addresses)]
    queue_source = QueueTaskSource()
    fleet = FleetManager(source=queue_source, allocator=EasiestAllocator())
    sim = Simulation(grid, coordinator=PIBTCoordinator(), dispatcher=fleet)
    for agent in agents:
        sim.add_agent(agent)
    return sim, agents, addresses, queue_source, fleet


# ── Synchronisation / navigation ──────────────────────────────────────────────
# Identical to sim_dotbot_pibt.py.

def wait_until_all_arrived(
    gsm: GridStateManager,
    targets: dict[str, Position],
    threshold: int,
    step_timeout: float,
    settle_s: float,
) -> set[str]:
    target_mm = {addr: gsm.cell_to_mm(cell) for addr, cell in targets.items()}
    deadline = time.time() + step_timeout
    arrived: set[str] = set()
    poll_interval = 0.05  # starts at 50 ms, exponential back-off up to 500 ms
    while time.time() < deadline:
        try:
            bots = {b["address"]: b["lh2_position"] for b in gsm.fetch_dotbots()}
        except requests.RequestException:
            time.sleep(poll_interval)
            continue
        arrived = {
            addr
            for addr, (tx, ty) in target_mm.items()
            if (p := bots.get(addr)) and math.hypot(p["x"] - tx, p["y"] - ty) < threshold
        }
        if len(arrived) == len(target_mm):
            break
        time.sleep(poll_interval)
        poll_interval = min(poll_interval * 1.5, 0.5)

    missing = set(target_mm) - arrived
    if missing:
        print(f"    ⚠ not arrived before timeout {step_timeout}s: "
              f"{', '.join(a[:8] + '...' for a in missing)}")
    if settle_s:
        time.sleep(settle_s)
    return arrived


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


def _send_all_parallel(
    base_url: str,
    moved_mm: dict[str, tuple[float, float]],
    threshold: int,
) -> None:
    if not moved_mm:
        return
    with ThreadPoolExecutor(max_workers=len(moved_mm)) as executor:
        futures = {
            executor.submit(send_waypoints, base_url, addr, [wp_mm], threshold): addr
            for addr, wp_mm in moved_mm.items()
        }
        for future in as_completed(futures):
            addr = futures[future]
            try:
                future.result()
            except requests.RequestException as e:
                print(f"    -> Send error {addr[:8]}...: {e}")


def fetch_grid_state_with_retry(
    gsm: GridStateManager,
    min_bots: int,
    attempts: int = 10,
    delay: float = 1.0,
) -> dict[str, Position]:
    state: dict[str, Position] = {}
    for _ in range(attempts):
        state = gsm.get_grid_state()
        if len(state) >= min_bots:
            return state
        print(f"  ... {len(state)} bot(s) with LH2 position, waiting for >= {min_bots}...")
        time.sleep(delay)
    return state


# ── Step-by-step execution ────────────────────────────────────────────────────

def run_phase(
    gsm: GridStateManager,
    sim: Simulation,
    agents: list[Agent],
    addresses: list[str],
    queue_source: QueueTaskSource,
    fleet: FleetManager,
    target_cells: list[Position],
    threshold: int,
    max_steps: int,
    step_timeout: float,
    settle_s: float,
    dry_run: bool,
    phase_label: str,
) -> bool:
    """Pushes one Task per target cell (eligible=None -> any free agent may
    take it) and runs sim.step() until FleetManager has resolved every one
    of them (DONE or FAILED -> pruned out of fleet.tasks) or max_steps is
    exhausted. Which bot ends up on which cell is left entirely to
    EasiestAllocator; the only condition checked here is that the whole
    task batch has been resolved. Returns True iff every task completed
    (none failed).
    """
    queue_source.push_many([
        Task(task_id=0, target=cell, eligible=None, created_step=sim.current_step)
        for cell in target_cells
    ])
    completed_before, failed_before = fleet.completed_count, fleet.failed_count
    prev = {addr: agents[i].position for i, addr in enumerate(addresses)}

    for step in range(1, max_steps + 1):
        sim.step()
        targets = {addr: agents[i].position for i, addr in enumerate(addresses)}
        moved = {addr: cell for addr, cell in targets.items() if cell != prev[addr]}

        print(f"\n── [{phase_label}] Step {step} ──"
              f"  (pending/assigned: {len(fleet.tasks)})")
        for addr, cell in targets.items():
            x, y = gsm.cell_to_mm(cell)
            tag = "" if addr in moved else "  (stationary)"
            print(f"  {addr[:8]}... -> cell {cell} = ({x:.0f}, {y:.0f}) mm{tag}")

        if not dry_run:
            _send_all_parallel(
                gsm.base_url,
                {addr: gsm.cell_to_mm(cell) for addr, cell in moved.items()},
                threshold,
            )
            wait_until_all_arrived(gsm, targets, threshold, step_timeout, settle_s)

        prev = targets
        if not fleet.tasks:
            failed = fleet.failed_count - failed_before
            completed = fleet.completed_count - completed_before
            print(f"\n[{phase_label}] All {len(target_cells)} task(s) resolved at step {step} "
                  f"(completed={completed}, failed={failed}).")
            return failed == 0

    print(f"\n[{phase_label}] ⚠ max steps ({max_steps}) reached with "
          f"{len(fleet.tasks)} task(s) still unresolved.")
    return False


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="PIBT -> DotBot simulator demo: all bots right, wait, then all bots left"
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Print step-by-step targets without sending or waiting")
    parser.add_argument("--steps", type=int, default=DEFAULT_STEPS,
                        help=f"Max PIBT steps per phase (default: {DEFAULT_STEPS})")
    parser.add_argument("--wait", type=float, default=DEFAULT_WAIT,
                        help=f"Pause (s) between the right phase finishing and the left phase "
                             f"starting (default: {DEFAULT_WAIT})")
    parser.add_argument("--cell-mm", type=int, default=DEFAULT_CELL_MM,
                        help="Cell size in mm (default: derived from map_size / --map-cells)")
    parser.add_argument("--map-cells", type=int, default=DEFAULT_MAP_CELLS,
                        help=f"Grid resolution NxN (default: {DEFAULT_MAP_CELLS}; "
                             f"5 -> 400 mm cells, 8 -> 250 mm on a 2000x2000 map)")
    parser.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD,
                        help=f"Arrival radius per cell in mm (default: {DEFAULT_THRESHOLD})")
    parser.add_argument("--step-timeout", type=float, default=DEFAULT_STEP_TIMEOUT,
                        help=f"Max wait (s) per step (default: {DEFAULT_STEP_TIMEOUT})")
    parser.add_argument("--settle", type=float, default=DEFAULT_SETTLE,
                        help=f"Pause (s) after arrival per step (default: {DEFAULT_SETTLE})")
    parser.add_argument("--min-bots", type=int, default=2,
                        help="Minimum localised bots required at startup (default: 2)")
    parser.add_argument("--base", default=DEFAULT_BASE_URL,
                        help=f"Controller URL (default: {DEFAULT_BASE_URL})")
    args = parser.parse_args()

    gsm = GridStateManager(args.base, args.cell_mm, args.map_cells)

    print(f"Connecting to {args.base}...")
    try:
        width_mm, height_mm = gsm.fetch_map_size()
        gsm.set_map_size(width_mm, height_mm)
        grid_state = fetch_grid_state_with_retry(gsm, args.min_bots)
        dotbots_raw = gsm.fetch_dotbots()
    except requests.RequestException as e:
        print(f"Error: cannot reach the controller ({e})")
        print("  -> dotbot run simulator --map-size 2000x2000 --simulator-init-state simulator_init_state.toml")
        sys.exit(1)

    if len(grid_state) < args.min_bots:
        print(f"Only {len(grid_state)} DotBot(s) localised (min: {args.min_bots}). Check LH2 coverage.")
        sys.exit(1)

    pos_by_addr = {b["address"]: b["lh2_position"] for b in dotbots_raw}
    print(f"\n{len(grid_state)} DotBot(s) detected:")
    for addr, cell in grid_state.items():
        p = pos_by_addr.get(addr, {})
        print(f"  {addr[:8]}...  pos=({p.get('x', '?'):.0f}, {p.get('y', '?'):.0f}) mm  cell={cell}")

    sim, agents, addresses, queue_source, fleet = build_sim(
        grid_state, gsm.map_cells_x, gsm.map_cells_y
    )

    mode = "[dry-run] " if args.dry_run else ""
    print(f"\n{mode}Grid {gsm.map_cells_x}x{gsm.map_cells_y} cells "
          f"({width_mm}x{height_mm} mm, cell={gsm.cell_mm} mm).")

    # Phase 1: the fleet's mutual objective is the rightmost N cells — any
    # free bot may take any one of them, EasiestAllocator decides which.
    right_cells = _edge_cells(gsm.map_cells_x, gsm.map_cells_y, "right", len(agents))
    print(f"\nPhase 1 — RIGHT, mutual objective cells: {right_cells}")
    run_phase(
        gsm, sim, agents, addresses, queue_source, fleet, right_cells,
        threshold=args.threshold, max_steps=args.steps,
        step_timeout=args.step_timeout, settle_s=args.settle,
        dry_run=args.dry_run, phase_label="RIGHT",
    )

    print(f"\nWaiting {args.wait}s before sending everyone left...")
    if not args.dry_run:
        time.sleep(args.wait)

    # Phase 2: same, mutual objective is now the leftmost N cells.
    left_cells = _edge_cells(gsm.map_cells_x, gsm.map_cells_y, "left", len(agents))
    print(f"\nPhase 2 — LEFT, mutual objective cells: {left_cells}")
    run_phase(
        gsm, sim, agents, addresses, queue_source, fleet, left_cells,
        threshold=args.threshold, max_steps=args.steps,
        step_timeout=args.step_timeout, settle_s=args.settle,
        dry_run=args.dry_run, phase_label="LEFT",
    )

    if args.dry_run:
        print("\n[dry-run] No commands sent.")
    else:
        print(f"\nDone. Open {args.base} to visualise.")


if __name__ == "__main__":
    main()
