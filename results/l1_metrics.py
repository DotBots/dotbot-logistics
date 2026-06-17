#!/usr/bin/env python3
"""
l1_metrics.py — Shared CSV logging for the L1 hardware harness.

Imported by every test_real_dotbot_pibt_*bots_*runs.py script. Appends one row
per run to l1_per_run.csv and rewrites the per-(grid, N) aggregate in
l1_summary.csv. Column names are kept aligned with the L0 results CSV
(L0/l0_pibt_grid4x4_5x5_8x8_30seeds_100steps.csv) so the two levels can be
joined directly for the plan-to-real gap (Fig. 1 / Fig. 2).
"""

import csv
import math
import os
import time
from collections import defaultdict

PER_RUN_CSV = "l1_per_run.csv"
SUMMARY_CSV = "l1_summary.csv"

# Per-run schema. The first block mirrors the L0 CSV columns; the rest is
# hardware-specific (overshoot, throughput, timeouts).
PER_RUN_FIELDS = [
    "date", "script_name",
    "grid_w", "grid_h", "cell_mm", "n_agents", "occupancy", "seed", "run_id",
    "success_rate", "arrived", "total_bots", "all_reached",
    "steps_taken", "total_time_s", "step_timeouts",
    "throughput_per_min", "mean_overshoot_mm", "max_overshoot_mm",
    "total_conflict_moves", "total_free_moves", "conflict_ratio",
    "mean_step_time_free_s", "mean_step_time_conflict_s",
]

SUMMARY_FIELDS = [
    "script_name", "grid_w", "grid_h", "cell_mm", "n_agents", "occupancy",
    "num_runs", "success_rate_mean", "success_rate_ci95",
    "avg_steps", "avg_time_s", "avg_overshoot_mm",
    "timeout_rate", "avg_throughput_per_min",
    "avg_conflict_ratio", "avg_mean_step_time_free_s", "avg_mean_step_time_conflict_s",
]


def append_run(results_dir, row):
    """Append one run to l1_per_run.csv, writing the header if the file is new."""
    path = os.path.join(results_dir, PER_RUN_CSV)
    new_file = not os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=PER_RUN_FIELDS)
        if new_file:
            w.writeheader()
        w.writerow({k: row.get(k, "") for k in PER_RUN_FIELDS})
    return path


def _ci95(values):
    """95% confidence interval half-width of the mean (normal approx)."""
    n = len(values)
    if n < 2:
        return 0.0
    mean = sum(values) / n
    var = sum((v - mean) ** 2 for v in values) / (n - 1)
    return 1.96 * math.sqrt(var) / math.sqrt(n)


def write_summary(results_dir):
    """Rewrite l1_summary.csv as the per-(grid, N) aggregate of l1_per_run.csv."""
    per_run = os.path.join(results_dir, PER_RUN_CSV)
    if not os.path.exists(per_run):
        return None

    groups = defaultdict(list)
    with open(per_run, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            key = (r["script_name"], r["grid_w"], r["grid_h"],
                   r["cell_mm"], r["n_agents"], r["occupancy"])
            groups[key].append(r)

    path = os.path.join(results_dir, SUMMARY_CSV)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=SUMMARY_FIELDS)
        w.writeheader()
        for (script, gw, gh, cell, n, rho), rows in sorted(groups.items()):
            sr = [float(r["success_rate"]) for r in rows]
            steps = [float(r["steps_taken"]) for r in rows]
            tms = [float(r["total_time_s"]) for r in rows]
            ov = [float(r["mean_overshoot_mm"]) for r in rows]
            tout = [float(r["step_timeouts"]) for r in rows]
            thr  = [float(r["throughput_per_min"]) for r in rows]
            cratio  = [float(r.get("conflict_ratio") or 0) for r in rows]
            t_free  = [float(r.get("mean_step_time_free_s") or 0) for r in rows]
            t_conf  = [float(r.get("mean_step_time_conflict_s") or 0) for r in rows]
            k = len(rows)
            w.writerow({
                "script_name": script, "grid_w": gw, "grid_h": gh,
                "cell_mm": cell, "n_agents": n, "occupancy": rho,
                "num_runs": k,
                "success_rate_mean": round(sum(sr) / k, 4),
                "success_rate_ci95": round(_ci95(sr), 4),
                "avg_steps": round(sum(steps) / k, 2),
                "avg_time_s": round(sum(tms) / k, 2),
                "avg_overshoot_mm": round(sum(ov) / k, 2),
                "timeout_rate": round(sum(tout) / k, 3),
                "avg_throughput_per_min": round(sum(thr) / k, 2),
                "avg_conflict_ratio": round(sum(cratio) / k, 4),
                "avg_mean_step_time_free_s": round(sum(t_free) / k, 3),
                "avg_mean_step_time_conflict_s": round(sum(t_conf) / k, 3),
            })
    return path


def make_row(*, script_name, grid_w, grid_h, cell_mm, n_agents, seed, run_id,
             arrived, total_bots, all_reached, steps_taken, total_time_s,
             step_timeouts, mean_overshoot_mm, max_overshoot_mm,
             total_conflict_moves=0, total_free_moves=0,
             mean_step_time_free_s=0.0, mean_step_time_conflict_s=0.0):
    """Build a PER_RUN_FIELDS-shaped dict from a finished run's metrics."""
    cells = grid_w * grid_h
    throughput = (arrived / total_time_s * 60.0) if total_time_s else 0.0
    total_moves = total_conflict_moves + total_free_moves
    return {
        "date": time.strftime("%Y-%m-%d %H:%M:%S"),
        "script_name": script_name,
        "grid_w": grid_w, "grid_h": grid_h, "cell_mm": cell_mm,
        "n_agents": n_agents,
        "occupancy": round(n_agents / cells, 4) if cells else "",
        "seed": seed, "run_id": run_id,
        "success_rate": round(arrived / total_bots, 4) if total_bots else 0.0,
        "arrived": arrived, "total_bots": total_bots,
        "all_reached": int(bool(all_reached)),
        "steps_taken": steps_taken,
        "total_time_s": round(total_time_s, 2),
        "step_timeouts": step_timeouts,
        "throughput_per_min": round(throughput, 2),
        "mean_overshoot_mm": round(mean_overshoot_mm, 2),
        "max_overshoot_mm": round(max_overshoot_mm, 2),
        "total_conflict_moves": total_conflict_moves,
        "total_free_moves": total_free_moves,
        "conflict_ratio": round(total_conflict_moves / total_moves, 4) if total_moves else 0.0,
        "mean_step_time_free_s": round(mean_step_time_free_s, 3),
        "mean_step_time_conflict_s": round(mean_step_time_conflict_s, 3),
    }
