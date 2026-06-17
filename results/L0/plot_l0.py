import csv
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import numpy as np
from collections import defaultdict

CSV = "l0_pibt_grid4x4_5x5_8x8_30seeds_100steps.csv"

rows = []
with open(CSV) as f:
    for r in csv.DictReader(f):
        rows.append(r)

gw, gh = 5, 5
cells = gw * gh
TARGET_RHO = 0.60

grouped = defaultdict(list)
for r in rows:
    if int(r["grid_w"]) == gw and int(r["grid_h"]) == gh:
        grouped[int(r["n_agents"])].append(r)

ns    = sorted(grouped.keys())
rho_a = np.array([n / cells for n in ns])

cost_per_agent = np.array([
    np.mean([float(r["flowtime"]) for r in grouped[n]]) / n
    for n in ns
])
makespan = np.array([
    np.mean([float(r["makespan"]) for r in grouped[n] if r["makespan"]])
    for n in ns
])

# knee fixed at rho = 0.60 (N=15 for 5×5)
knee_idx = int(np.argmin(np.abs(rho_a - TARGET_RHO)))
knee_rho = rho_a[knee_idx]
knee_n   = ns[knee_idx]

cell_mm = int(rows[[i for i, r in enumerate(rows)
                     if int(r["grid_w"]) == gw][0]]["cell_mm"])

fig, ax1 = plt.subplots(figsize=(9, 5))

color_cpa = "#2563eb"
color_mk  = "#dc2626"

# efficient zone shading
ax1.axvspan(0, knee_rho, alpha=0.07, color="#16a34a", zorder=0,
            label=f"Efficient zone  ρ ≤ {knee_rho:.2f}  (N ≤ {knee_n})")
ax1.axvline(knee_rho, color="#16a34a", linewidth=1.4, linestyle=":", zorder=1)

# cost per agent
ax1.plot(rho_a, cost_per_agent, color=color_cpa, linewidth=2,
         marker="o", markersize=4, label="Cost per agent  (flowtime / N)", zorder=3)
ax1.set_xlabel("Occupancy  ρ = N / cells", fontsize=11)
ax1.set_ylabel("Cost per agent (steps)", color=color_cpa, fontsize=11)
ax1.tick_params(axis="y", labelcolor=color_cpa)

# makespan
ax2 = ax1.twinx()
ax2.plot(rho_a, makespan, color=color_mk, linewidth=2, linestyle="--",
         marker="s", markersize=4, label="Mean makespan (steps)", zorder=3)
ax2.set_ylabel("Mean makespan (steps)", color=color_mk, fontsize=11)
ax2.tick_params(axis="y", labelcolor=color_mk)

# legend
h1, l1 = ax1.get_legend_handles_labels()
h2, l2 = ax2.get_legend_handles_labels()
ax1.legend(h1 + h2, l1 + l2, loc="upper left", fontsize=8.5)

plt.title(
    "Cost per agent and mean makespan vs. occupancy ρ"
    f" — both metrics accelerate past ρ = {TARGET_RHO}"
    f" (5×5 grid, {cell_mm} mm cells, 30 seeds)",
    fontsize=10,
)
plt.tight_layout(rect=[0, 0.0, 1, 1])

out = f"l0_pibt_{gw}x{gh}.pdf"
plt.savefig(out, format="pdf")
plt.close()
print(f"Saved {out}")
