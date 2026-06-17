#!/usr/bin/env python3
"""
test_real_dotbot_pibt_15bots_5runs.py — Batch test: 15 bots, 5 runs.

Runs PIBT step-by-step on 15 real DotBots for 5 independent trials and
records per-run metrics and a summary to results/.
"""

import sys
import os
import math
import time
import random
import io as _io
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "simulation"))
from core import Simulation, Agent, Grid, Position
from algo.pibt import PIBT

import l1_metrics

# ── Batch parameters ───────────────────────────────────────────────────────────
NUM_AGENTS  = 15
NUM_RUNS    = 5
SCRIPT_NAME = "test_real_dotbot_pibt_15bots_5runs"

# ── Experiment parameters ──────────────────────────────────────────────────────
BASE_URL     = "http://localhost:8000"
CELL_MM      = 400
MAP_CELLS    = 5
STEPS        = 30
THRESHOLD    = 75
STEP_TIMEOUT = 8.0
SETTLE       = 0.3
RNG_SEED     = 0     # base seed; per-run seed = RNG_SEED + run_id (reproducible goals)

# ── Paths ──────────────────────────────────────────────────────────────────────
RESULTS_DIR = os.path.dirname(os.path.abspath(__file__))


# ── Tee: mirror stdout to log buffer ──────────────────────────────────────────
class _Tee:
    def __init__(self, real, buf):
        self._real = real
        self._buf  = buf

    def write(self, data):
        self._real.write(data)
        self._buf.write(data)

    def flush(self):
        self._real.flush()
        self._buf.flush()


# ── GridStateManager ──────────────────────────────────────────────────────────
class GridStateManager:
    def __init__(self, base_url, cell_mm, map_cells):
        self.base_url    = base_url
        self.cell_mm     = cell_mm
        self.map_cells_x = map_cells
        self.map_cells_y = map_cells

    def set_map_size(self, width_mm, height_mm):
        if width_mm % self.cell_mm or height_mm % self.cell_mm:
            print(f"  ⚠ cell_mm={self.cell_mm} does not divide map "
                  f"{width_mm}x{height_mm} mm — grid will be truncated.")
        self.map_cells_x = max(1, width_mm // self.cell_mm)
        self.map_cells_y = max(1, height_mm // self.cell_mm)

    def fetch_dotbots(self):
        r = requests.get(f"{self.base_url}/controller/dotbots", timeout=5)
        r.raise_for_status()
        return [b for b in r.json() if b.get("lh2_position") and b.get("status") != 2]

    def fetch_map_size(self):
        r = requests.get(f"{self.base_url}/controller/map_size", timeout=5)
        r.raise_for_status()
        data = r.json()
        return data["width"], data["height"]

    def mm_to_cell(self, x_mm, y_mm):
        gx = max(0, min(self.map_cells_x - 1, int(x_mm / self.cell_mm)))
        gy = max(0, min(self.map_cells_y - 1, int(y_mm / self.cell_mm)))
        return Position(gx, gy)

    def cell_to_mm(self, pos):
        return (pos.x * self.cell_mm + self.cell_mm // 2,
                pos.y * self.cell_mm + self.cell_mm // 2)

    def get_grid_state(self):
        dotbots = self.fetch_dotbots()
        raw = {}
        for bot in dotbots:
            p = bot["lh2_position"]
            raw[bot["address"]] = self.mm_to_cell(p["x"], p["y"])
        return self.resolve_conflicts(raw)

    def resolve_conflicts(self, positions):
        occupied = {}
        result   = {}
        for address, pos in positions.items():
            if pos not in occupied:
                occupied[pos] = address
                result[address] = pos
            else:
                candidates = [
                    Position(pos.x + dx, pos.y + dy)
                    for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1),
                                   (1, 1), (-1, 1), (1, -1), (-1, -1)]
                    if 0 <= pos.x + dx < self.map_cells_x
                    and 0 <= pos.y + dy < self.map_cells_y
                ]
                free = next((c for c in candidates if c not in occupied), pos)
                occupied[free] = address
                result[address] = free
        return result


# ── PIBT planning ──────────────────────────────────────────────────────────────
def _assign_random_goals(agents, grid, rng):
    all_cells = [Position(x, y) for x in range(grid.width) for y in range(grid.height)]
    chosen    = rng.sample(all_cells, len(agents))
    return {agent: cell for agent, cell in zip(agents, chosen)}


def build_pibt(grid_state, cells_x, cells_y, rng):
    grid      = Grid(width=cells_x, height=cells_y)
    addresses = list(grid_state.keys())
    agents    = [Agent(agent_id=i, position=grid_state[addr]) for i, addr in enumerate(addresses)]
    goals_by_agent = _assign_random_goals(agents, grid, rng)
    pibt = PIBT(goals=goals_by_agent)
    sim  = Simulation(grid, coordinator=pibt)
    for agent in agents:
        sim.add_agent(agent)
    goals_by_address = {addresses[i]: goals_by_agent[agents[i]] for i in range(len(agents))}
    return sim, agents, addresses, goals_by_agent, goals_by_address


# ── Synchronisation ────────────────────────────────────────────────────────────
def wait_until_all_arrived(gsm, targets, threshold, step_timeout, settle_s):
    target_mm     = {addr: gsm.cell_to_mm(cell) for addr, cell in targets.items()}
    deadline      = time.time() + step_timeout
    arrived       = set()
    last_seen     = {}
    poll_interval = 0.05
    while time.time() < deadline:
        try:
            bots = {b["address"]: b["lh2_position"] for b in gsm.fetch_dotbots()}
        except requests.RequestException:
            time.sleep(poll_interval)
            continue
        last_seen = bots
        arrived   = {
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
    # Final stop distance to target per bot (mm) → overshoot vs threshold.
    dist_mm = {
        addr: math.hypot(p["x"] - tx, p["y"] - ty)
        for addr, (tx, ty) in target_mm.items()
        if (p := last_seen.get(addr))
    }
    return arrived, last_seen, dist_mm


def _send_all_parallel(base_url, moved_mm, threshold):
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


# ── Closed-loop re-sync ────────────────────────────────────────────────────────
def resync_simulation(gsm, sim, agents, addresses, goals_by_agent, last_seen, fallback):
    raw = {}
    for addr in addresses:
        p        = last_seen.get(addr)
        raw[addr] = gsm.mm_to_cell(p["x"], p["y"]) if p else fallback[addr]
    real_cells = gsm.resolve_conflicts(raw)
    for agent in agents:
        sim.grid.remove(agent)
    priorities = getattr(sim.coordinator, "priorities", None)
    for i, addr in enumerate(addresses):
        agent          = agents[i]
        agent.position = real_cells[addr]
        sim.grid.place(agent)
        if (priorities is not None
                and agent.position != goals_by_agent[agent]
                and priorities.get(agent) == float("-inf")):
            priorities[agent] = float(i)
    return real_cells


# ── Per-run metrics ────────────────────────────────────────────────────────────
@dataclass
class RunMetrics:
    run_id:            int
    seed:              int
    steps_taken:       int
    bots_at_goal:      int
    total_bots:        int
    all_reached:       bool
    total_time_s:      float
    step_timeouts:     int
    mean_overshoot_mm: float
    max_overshoot_mm:  float


def run_pibt_live(gsm, sim, agents, addresses, goals_by_agent,
                  threshold, steps, step_timeout, settle_s, run_id, seed):
    prev          = {addr: agents[i].position for i, addr in enumerate(addresses)}
    step_timeouts = 0
    steps_taken   = 0
    overshoots    = []   # final stop distance (mm) per bot × moving step
    t0            = time.time()

    def all_at_goal():
        return all(
            agents[i].position == goals_by_agent[agents[i]]
            for i in range(len(agents))
        )

    for step in range(1, steps + 1):
        steps_taken = step
        sim.step()
        targets = {addr: agents[i].position for i, addr in enumerate(addresses)}
        moved   = {addr: cell for addr, cell in targets.items() if cell != prev[addr]}

        print(f"\n── Step {step} ──")
        for addr, cell in targets.items():
            x, y = gsm.cell_to_mm(cell)
            tag  = "" if addr in moved else "  (stationary)"
            print(f"  {addr[:8]}... -> cell {cell} = ({x:.0f}, {y:.0f}) mm{tag}")

        if not moved:
            if all_at_goal():
                print(f"\nAll bots reached their goal at step {step}.")
            else:
                print(f"\nNo movement planned at step {step} (livelock) — stopping.")
            break

        _send_all_parallel(
            gsm.base_url,
            {addr: gsm.cell_to_mm(cell) for addr, cell in moved.items()},
            threshold,
        )
        arrived, last_seen, dist_mm = wait_until_all_arrived(
            gsm, targets, threshold, step_timeout, settle_s
        )
        overshoots.extend(dist_mm.values())
        if len(arrived) < len(targets):
            step_timeouts += 1

        prev = resync_simulation(
            gsm, sim, agents, addresses, goals_by_agent, last_seen, fallback=targets
        )
        if all_at_goal():
            print(f"\nAll bots reached their goal at step {step} (verified from LH2).")
            break

    total_time   = time.time() - t0
    bots_at_goal = sum(
        1 for i in range(len(agents))
        if agents[i].position == goals_by_agent[agents[i]]
    )
    return RunMetrics(
        run_id=run_id,
        seed=seed,
        steps_taken=steps_taken,
        bots_at_goal=bots_at_goal,
        total_bots=len(agents),
        all_reached=all_at_goal(),
        total_time_s=round(total_time, 2),
        step_timeouts=step_timeouts,
        mean_overshoot_mm=(sum(overshoots) / len(overshoots)) if overshoots else 0.0,
        max_overshoot_mm=max(overshoots) if overshoots else 0.0,
    )
# ── DotBot navigation ──────────────────────────────────────────────────────────
def send_waypoints(base_url, address, waypoints_mm, threshold):
    payload = {
        "threshold": threshold,
        "waypoints": [{"x": float(x), "y": float(y)} for x, y in waypoints_mm],
    }
    url = f"{base_url}/controller/dotbots/{address}/0/waypoints"
    r = requests.put(url, json=payload, timeout=5)
    r.raise_for_status()
    time.sleep(0.5)
    r = requests.put(url, json=payload, timeout=5)
    r.raise_for_status()


def fetch_grid_state_with_retry(gsm, min_bots, attempts=10, delay=1.0):
    state = {}
    for _ in range(attempts):
        state = gsm.get_grid_state()
        if len(state) >= min_bots:
            return state
        print(f"  ... {len(state)} bot(s) with LH2 position, waiting for >= {min_bots}...")
        time.sleep(delay)
    return state


# ── Batch loop ─────────────────────────────────────────────────────────────────
def _run_batch():
    gsm = GridStateManager(BASE_URL, CELL_MM, MAP_CELLS)

    print(f"{'='*60}")
    print(f"Batch : {SCRIPT_NAME}")
    print(f"Config: {NUM_AGENTS} bots · {NUM_RUNS} runs · {STEPS} steps max")
    print(f"Grid  : {MAP_CELLS}×{MAP_CELLS} · cell={CELL_MM} mm · threshold={THRESHOLD} mm")
    print(f"{'='*60}")

    print(f"\nConnecting to {BASE_URL}...")
    try:
        width_mm, height_mm = gsm.fetch_map_size()
        gsm.set_map_size(width_mm, height_mm)
        print(f"Map: {width_mm}×{height_mm} mm  ->  grid {gsm.map_cells_x}×{gsm.map_cells_y}")
    except requests.RequestException as e:
        print(f"Error: cannot reach controller ({e})")
        sys.exit(1)

    all_metrics = []
    for run_id in range(1, NUM_RUNS + 1):
        run_seed = RNG_SEED + run_id          # reproducible goals per (N, run_id)
        rng      = random.Random(run_seed)
        print(f"\n{'='*60}")
        print(f"RUN {run_id}/{NUM_RUNS}  (seed={run_seed})")
        print(f"{'='*60}")

        grid_state = fetch_grid_state_with_retry(gsm, NUM_AGENTS)
        if len(grid_state) < NUM_AGENTS:
            print(f"  Only {len(grid_state)} bots localised (need {NUM_AGENTS}). Skipping.")
            continue

        dotbots_raw  = gsm.fetch_dotbots()
        pos_by_addr  = {b["address"]: b["lh2_position"] for b in dotbots_raw}
        print(f"\n{len(grid_state)} DotBot(s) detected:")
        for addr, cell in grid_state.items():
            p = pos_by_addr.get(addr, {})
            print(f"  {addr[:8]}...  pos=({p.get('x','?'):.0f}, {p.get('y','?'):.0f}) mm  cell={cell}")

        sim, agents, addresses, goals_by_agent, goals_by_address = build_pibt(
            grid_state, gsm.map_cells_x, gsm.map_cells_y, rng
        )
        print("Assigned goals:")
        for addr in addresses:
            print(f"  {addr[:8]}...  start={grid_state[addr]}  goal={goals_by_address[addr]}")

        m = run_pibt_live(
            gsm, sim, agents, addresses, goals_by_agent,
            threshold=THRESHOLD,
            steps=STEPS,
            step_timeout=STEP_TIMEOUT,
            settle_s=SETTLE,
            run_id=run_id,
            seed=run_seed,
        )
        all_metrics.append(m)
        print(f"\nRun {run_id}: {m.bots_at_goal}/{m.total_bots} at goal · "
              f"{m.steps_taken} steps · {m.total_time_s:.1f}s · {m.step_timeouts} timeout(s) · "
              f"overshoot mean {m.mean_overshoot_mm:.0f} / max {m.max_overshoot_mm:.0f} mm")

        l1_metrics.append_run(RESULTS_DIR, l1_metrics.make_row(
            script_name=SCRIPT_NAME,
            grid_w=gsm.map_cells_x, grid_h=gsm.map_cells_y, cell_mm=CELL_MM,
            n_agents=NUM_AGENTS, seed=m.seed, run_id=m.run_id,
            arrived=m.bots_at_goal, total_bots=m.total_bots,
            all_reached=m.all_reached, steps_taken=m.steps_taken,
            total_time_s=m.total_time_s, step_timeouts=m.step_timeouts,
            mean_overshoot_mm=m.mean_overshoot_mm,
            max_overshoot_mm=m.max_overshoot_mm,
        ))

        if run_id < NUM_RUNS:
            print("\nPausing 3 s before next run...")
            input("\nPress Enter to start next run...")

    # ── Final summary ──────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"SUMMARY — {SCRIPT_NAME}")
    print(f"{'='*60}")
    if not all_metrics:
        print("No runs completed.")
        return

    print(f"{'Run':>4}  {'Steps':>6}  {'At Goal':>8}  {'All?':>5}  {'Time(s)':>8}  {'Timeouts':>9}")
    for m in all_metrics:
        print(f"{m.run_id:>4}  {m.steps_taken:>6}  "
              f"{m.bots_at_goal}/{m.total_bots}       "
              f"{'Yes' if m.all_reached else 'No':>5}  "
              f"{m.total_time_s:>8.1f}  {m.step_timeouts:>9}")

    n        = len(all_metrics)
    sr       = 100 * sum(1 for m in all_metrics if m.all_reached) / n
    avg_steps = sum(m.steps_taken   for m in all_metrics) / n
    avg_time  = sum(m.total_time_s  for m in all_metrics) / n
    avg_bots  = sum(m.bots_at_goal  for m in all_metrics) / n
    print(f"\nSuccess rate : {sr:.0f}%")
    print(f"Avg steps    : {avg_steps:.1f}")
    print(f"Avg time     : {avg_time:.1f} s")
    print(f"Avg bots@goal: {avg_bots:.1f}/{NUM_AGENTS}")

    per_run = os.path.join(RESULTS_DIR, l1_metrics.PER_RUN_CSV)
    summary = l1_metrics.write_summary(RESULTS_DIR)
    print(f"\nCSV per-run → {per_run}")
    print(f"CSV summary → {summary}")



# ── Entry point ────────────────────────────────────────────────────────────────
def main():
    os.makedirs(RESULTS_DIR, exist_ok=True)
    timestamp   = time.strftime("%Y%m%d_%H%M%S")
    log_file    = os.path.join(RESULTS_DIR, f"{SCRIPT_NAME}_{timestamp}.txt")
    log_buf     = _io.StringIO()
    real_stdout = sys.stdout
    sys.stdout  = _Tee(real_stdout, log_buf)
    try:
        _run_batch()
    finally:
        sys.stdout = real_stdout
        with open(log_file, "w", encoding="utf-8") as f:
            f.write(log_buf.getvalue())
        print(f"Log saved → {log_file}")


if __name__ == "__main__":
    main()
