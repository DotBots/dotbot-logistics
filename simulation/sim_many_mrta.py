#!/usr/bin/env python3
"""
sim_many_mrta.py — MRTA benchmark: allocation sweep, no pygame, no hardware.

The allocation counterpart of sim_many_pibt.py. That script answers "how
many robots can PIBT route before it deadlocks?"; this one answers "given
that they route, how much work does the fleet actually finish, and how
long does a job wait?" — which is the allocator's question, not the
planner's.

Sweeps grid × N agents × allocator × seeds and writes one row per run to
mrta_results.csv, then prints a per-allocator summary.

It deliberately goes through client.control.build() and report's
RunCollector rather than wiring a Simulation by hand: the metrics it
needs already exist in RunRecord, and a benchmark that measured the
engine its own way would drift from the one --log produces.

Usage:
    python sim_many_mrta.py                    # full sweep, 10 seeds
    python sim_many_mrta.py --seeds 2          # quick smoke-test
    python sim_many_mrta.py --zones            # same, with zones placed
    python sim_many_mrta.py --out my.csv
"""

import argparse
import csv
from collections import defaultdict

from client.control import ScenarioConfig, build, default_zones
from report import RunCollector

# ── Defaults ──────────────────────────────────────────────────────────────────

GRIDS      = [(10, 10), (15, 15), (20, 20)]
AGENT_FRAC = (0.05, 0.10, 0.20)      # share of the cells occupied by robots
ALLOCATORS = ("easiest", "random")
STEPS      = 120
N_SEEDS    = 10
OUTPUT     = "mrta_results.csv"

# Columns worth carrying over from RunRecord. The record has ~40 fields;
# a benchmark that dumped all of them would bury its own question.
COLUMNS = [
    "grid_w", "grid_h", "n_agents", "occupancy", "allocator", "zones", "seed",
    "steps", "tasks_created", "tasks_done", "tasks_failed", "completion_rate",
    "wait_mean", "service_mean", "step_ms_mean",
]

# ── Single instance ───────────────────────────────────────────────────────────


def run_instance(gw: int, gh: int, n: int, allocator: str, seed: int, zones: bool) -> dict:
    """Input: grid size, agent count, allocator name, seed, and whether to
    place the operational zones.
    Output: the selected RunRecord fields for that run, as a flat dict.
    """
    config = ScenarioConfig(
        width=gw, height=gh, agents=n,
        algo="pibt", mode="mrta", allocator=allocator,
        tasks="random", task_every=5, task_count=2,
        seed=seed,
        zones=default_zones(gw, gh) if zones else (),
    )
    collector = RunCollector(build(config), config, label="sim_many_mrta")
    collector.run(STEPS)
    record = collector.record()

    row = {
        "grid_w": gw,
        "grid_h": gh,
        "n_agents": n,
        "occupancy": round(n / (gw * gh), 4),
        "seed": seed,
    }
    row.update({c: getattr(record, c) for c in COLUMNS if c not in row})
    return row


# ── Sweep ─────────────────────────────────────────────────────────────────────


def run_sweep(seeds: list[int], output: str, zones: bool) -> None:
    """Input: the seeds to run, the output path, and the zones flag.
    Output: None. Writes the CSV and prints the summary.
    """
    rows = []

    for (gw, gh) in GRIDS:
        cells = gw * gh
        print(f"\n=== Grid {gw}x{gh}  ({cells} cells) ===")
        for frac in AGENT_FRAC:
            n = max(2, int(cells * frac))
            for allocator in ALLOCATORS:
                results = []
                for seed in seeds:
                    try:
                        row = run_instance(gw, gh, n, allocator, seed, zones)
                        results.append(row)
                        rows.append(row)
                    except Exception as exc:
                        print(f"  [{gw}x{gh}] N={n} {allocator} seed={seed} ERROR: {exc}")

                if results:
                    print(f"  N={n:3d}  rho={n/cells:.2f}  {allocator:<8}"
                          f"  done={_mean(results, 'tasks_done'):5.1f}"
                          f"  completion={_mean(results, 'completion_rate'):.2f}"
                          f"  wait={_mean(results, 'wait_mean'):5.2f}"
                          f"  service={_mean(results, 'service_mean'):5.2f}")

    if rows:
        with open(output, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
        print(f"\nResults written to {output}  ({len(rows)} rows)")

    _print_summary(rows)


def _mean(rows: list[dict], key: str) -> float:
    """Input: rows and a column.
    Output: its mean over the rows that have a value — None is "no
    completed task to measure", which is not the same as zero and must
    not be averaged in as one.
    """
    values = [r[key] for r in rows if r.get(key) is not None]
    return sum(values) / len(values) if values else float("nan")


# ── Summary ───────────────────────────────────────────────────────────────────


def _print_summary(rows: list[dict]) -> None:
    """Input: the collected rows.
    Output: None. Prints how the allocators compare, which is the whole
    point of running both.
    """
    print("\n=== Allocator summary (all grids, all densities) ===")
    grouped: dict[str, list] = defaultdict(list)
    for row in rows:
        grouped[row["allocator"]].append(row)

    for allocator in ALLOCATORS:
        group = grouped.get(allocator)
        if not group:
            continue
        print(f"  {allocator:<8}"
              f"  completion={_mean(group, 'completion_rate'):.3f}"
              f"  wait={_mean(group, 'wait_mean'):6.2f}"
              f"  service={_mean(group, 'service_mean'):6.2f}"
              f"  failed={_mean(group, 'tasks_failed'):.2f}"
              f"  step_ms={_mean(group, 'step_ms_mean'):.3f}")


# ── Entry point ───────────────────────────────────────────────────────────────


def _parse_args():
    parser = argparse.ArgumentParser(description="MRTA allocation benchmark sweep")
    parser.add_argument("--seeds", type=int, default=N_SEEDS,
                        help=f"number of seeds per cell (default: {N_SEEDS})")
    parser.add_argument("--out", type=str, default=OUTPUT,
                        help=f"output CSV file (default: {OUTPUT})")
    parser.add_argument("--zones", action="store_true",
                        help="place the three operational zones on the grid")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    seeds = list(range(args.seeds))
    print(f"MRTA sweep — {len(GRIDS)} grids, {len(ALLOCATORS)} allocators, "
          f"seeds 0...{args.seeds - 1}, {STEPS} steps")
    run_sweep(seeds, args.out, args.zones)
