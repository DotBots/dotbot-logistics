"""Figure 2: two-panel — L0 cost (makespan + SoC/N) left, L1 per-instance success right."""
import csv, collections, math
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np

# ── L0 5×5 ────────────────────────────────────────────────────────────────────
l0_rows = []
with open("L0/l0_pibt_grid4x4_5x5_8x8_30seeds_100steps.csv") as f:
    for row in csv.DictReader(f):
        if int(row["grid_w"]) == 5 and int(row["grid_h"]) == 5:
            l0_rows.append(row)

l0_by_occ = collections.defaultdict(list)
for r in l0_rows:
    l0_by_occ[float(r["occupancy"])].append({
        "makespan": int(r["makespan"]),
        "soc_n":    int(r["flowtime"]) / int(r["n_agents"]),
    })

l0_occ  = sorted(l0_by_occ)
l0_mk   = [np.mean([v["makespan"] for v in l0_by_occ[o]]) for o in l0_occ]
l0_sn   = [np.mean([v["soc_n"]   for v in l0_by_occ[o]]) for o in l0_occ]
l0_mk_std = [np.std([v["makespan"] for v in l0_by_occ[o]], ddof=1) / math.sqrt(30) for o in l0_occ]
l0_sn_std = [np.std([v["soc_n"]   for v in l0_by_occ[o]], ddof=1) / math.sqrt(30) for o in l0_occ]

# ── L1 5×5 per-instance ───────────────────────────────────────────────────────
l1_by_occ = collections.defaultdict(list)
with open("l1_per_run.csv") as f:
    for row in csv.DictReader(f):
        if int(row["grid_w"]) == 5 and int(row["grid_h"]) == 5:
            l1_by_occ[float(row["occupancy"])].append(int(row["all_reached"]))

l1_occ  = sorted(l1_by_occ)
l1_rate = [sum(l1_by_occ[o]) / len(l1_by_occ[o]) * 100 for o in l1_occ]
l1_n    = [len(l1_by_occ[o]) for o in l1_occ]
def ci95(p, n):
    return 1.96 * math.sqrt(p/100 * (1 - p/100) / n) * 100 if n > 1 else 0
l1_err = [ci95(r, n) for r, n in zip(l1_rate, l1_n)]

# ── Figure ────────────────────────────────────────────────────────────────────
BLUE   = "#4477AA"
RED    = "#EE6677"
GREEN  = "#228833"
KNEE   = 0.60
REAL_CEIL = 0.30

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(7.0, 1.95))
fig.subplots_adjust(wspace=0.34)

# ── Left panel: L0 cost ───────────────────────────────────────────────────────
ax1b = ax1.twinx()

l1_mk, = ax1.plot(l0_occ, l0_mk, color=BLUE, lw=1.5, marker="s", ms=3, label="Makespan (steps)")
ax1.fill_between(l0_occ,
                 [m - e for m, e in zip(l0_mk, l0_mk_std)],
                 [m + e for m, e in zip(l0_mk, l0_mk_std)],
                 color=BLUE, alpha=0.15)

l2_sn, = ax1b.plot(l0_occ, l0_sn, color=GREEN, lw=1.5, ls="--", marker="^", ms=3,
                   label="SoC/N (steps/agent)")
ax1b.fill_between(l0_occ,
                  [s - e for s, e in zip(l0_sn, l0_sn_std)],
                  [s + e for s, e in zip(l0_sn, l0_sn_std)],
                  color=GREEN, alpha=0.12)

ax1.axvline(KNEE, color="#333333", lw=0.9, ls=":")
ax1.text(KNEE + 0.02, 24, r"cost knee", fontsize=5.5, va="top", color="#333333")

ax1.set_xlabel(r"Occupancy $\rho$", fontsize=7)
ax1.set_ylabel("Mean makespan (steps)", fontsize=7, color=BLUE)
ax1b.set_ylabel("Mean SoC/N (steps/agent)", fontsize=7, color=GREEN)
ax1.tick_params(axis="both", labelsize=6)
ax1b.tick_params(axis="y", labelsize=6, colors=GREEN)
ax1.tick_params(axis="y", colors=BLUE)
ax1.set_xlim(0.0, 1.05)
ax1.set_title("L0 — Simulation cost", fontsize=7, fontweight="bold")

lines = [l1_mk, l2_sn]
ax1.legend(lines, [l.get_label() for l in lines], fontsize=5.5, loc="upper left")
ax1.grid(axis="y", lw=0.4, alpha=0.35)

# ── Right panel: L1 per-instance ─────────────────────────────────────────────
bar_colors = [RED if r < 100 else "#AACCEE" for r in l1_rate]
bars = ax2.bar(l1_occ, l1_rate, width=0.025, color=bar_colors,
               edgecolor="white", linewidth=0.5, zorder=3)
ax2.errorbar(l1_occ, l1_rate, yerr=l1_err,
             fmt="none", color="#333333", capsize=2.5, lw=0.9, zorder=4)

ax2.axvline(REAL_CEIL, color=RED, lw=1.0, ls="--")
ax2.text(REAL_CEIL - 0.004, 55, "real ceiling\n" r"$\rho\!\approx\!0.30$",
         fontsize=5.5, ha="right", va="center", color=RED, linespacing=1.3)

# Label only degraded bars with run count
for occ, rate, n in zip(l1_occ, l1_rate, l1_n):
    if rate < 100:
        ax2.text(occ, rate + 3, f"n={n}", ha="center", fontsize=5, color="#333333")

ax2.set_xlabel(r"Occupancy $\rho$", fontsize=7)
ax2.set_ylabel("Per-instance success rate (%)", fontsize=7)
ax2.set_xlim(0.08, 0.50)
ax2.set_ylim(0, 115)
ax2.yaxis.set_major_locator(mticker.MultipleLocator(20))
ax2.tick_params(axis="both", labelsize=6)
ax2.set_title("L1 — Real DotBots reliability", fontsize=7, fontweight="bold")
ax2.grid(axis="y", lw=0.4, alpha=0.35, zorder=0)

fig.savefig("fig2_success_vs_occupancy.pdf", bbox_inches="tight")
fig.savefig("fig2_success_vs_occupancy.png", dpi=200, bbox_inches="tight")
print("Saved fig2_success_vs_occupancy.pdf + .png")
