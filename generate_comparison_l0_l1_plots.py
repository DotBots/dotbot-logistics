#!/usr/bin/env python3
"""
Generate two comparison PDFs: L0 (simulation, 30 runs) vs L1 (real DotBots)
on the 5x5 grid (400 mm/cell), n_agents 4-10.
"""

import csv
import os
import textwrap
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.patches as patches
from matplotlib.lines import Line2D
from collections import defaultdict

OUT_DIR = os.path.dirname(os.path.abspath(__file__))
L0_CSV  = os.path.join(OUT_DIR, '../L0/l0_pibt_grid4x4_5x5_8x8_30seeds_100steps.csv')
L1_CSV  = os.path.join(OUT_DIR, 'l1_per_run.csv')

def load(path):
    with open(path, newline='') as f:
        return list(csv.DictReader(f))

l0 = [r for r in load(L0_CSV) if r['grid_w'] == '5' and r['grid_h'] == '5']
l1 = [r for r in load(L1_CSV) if r['grid_w'] == '5' and r['grid_h'] == '5']

l0_by_n = defaultdict(list)
for r in l0:
    l0_by_n[int(r['n_agents'])].append(r)

l1_by_n = defaultdict(list)
for r in l1:
    l1_by_n[int(r['n_agents'])].append(r)

def ms(rows, key):
    v = [float(r[key]) for r in rows]
    return np.mean(v), np.std(v), len(v)

agents = list(range(4, 11))
data   = []
for n in agents:
    occ = round(n / 25, 4)
    l0r = l0_by_n[n]
    l1r = l1_by_n[n]

    l0_sr_m, l0_sr_s, l0_nr = ms(l0r, 'success_rate')
    l0_mk_m, l0_mk_s, _     = ms(l0r, 'makespan')
    l0_dl_tot = sum(int(r['deadlocks']) for r in l0r)

    l1_sr_m,  l1_sr_s,  l1_nr = ms(l1r, 'success_rate')
    l1_mk_m,  l1_mk_s,  _     = ms(l1r, 'makespan')
    l1_to_tot = sum(int(r['step_timeouts']) for r in l1r)

    data.append(dict(
        n=n, occ=occ,
        l0_sr_m=l0_sr_m, l0_sr_s=l0_sr_s, l0_nr=int(l0_nr),
        l0_mk_m=l0_mk_m, l0_mk_s=l0_mk_s,
        l0_dl_tot=l0_dl_tot,
        l1_sr_m=l1_sr_m, l1_sr_s=l1_sr_s, l1_nr=int(l1_nr),
        l1_mk_m=l1_mk_m, l1_mk_s=l1_mk_s,
        l1_to_tot=l1_to_tot, l1_to_m=l1_to_tot / l1_nr,
    ))

L0C  = '#2563eb'
L1C  = '#ea580c'
L0BG = '#e8f2fc'
L1BG = '#fef0e4'

# =============================================================================
# PDF 1 — MAKESPAN PLOT  (L0 blue / L1 red)
# =============================================================================
MK_L0C  = '#2563eb'   # blue for L0
MK_L1C  = '#dc2626'   # red  for L1
MK_L0BG = '#e8f2fc'

fig1, ax1mk = plt.subplots(figsize=(8, 5.5))
fig1.patch.set_facecolor('white')
ax1mk.set_facecolor('#fdfdfd')

occs = [d['occ'] for d in data]
ns   = [d['n']   for d in data]
xticks_labels = [f"{o:.2f}\n(n={n})" for o, n in zip(occs, ns)]

l0_mk  = [d['l0_mk_m'] for d in data]
l0_mks = [d['l0_mk_s'] for d in data]
l1_mk  = [d['l1_mk_m'] for d in data]
l1_mks = [d['l1_mk_s'] for d in data]

ax1mk.fill_between(occs,
    [m - s for m, s in zip(l0_mk, l0_mks)],
    [m + s for m, s in zip(l0_mk, l0_mks)],
    color=MK_L0C, alpha=0.12, label='_nolegend_')
ax1mk.plot(occs, l0_mk, color=MK_L0C, linestyle='--', linewidth=2.2,
           marker='o', markersize=8, markerfacecolor='white',
           markeredgecolor=MK_L0C, markeredgewidth=2.2, zorder=3,
           label='L0 Simulation (mean ± std, 30 runs)')
ax1mk.errorbar(occs, l1_mk, yerr=l1_mks,
               color=MK_L1C, linestyle='-', linewidth=2.2,
               marker='s', markersize=8, markerfacecolor=MK_L1C,
               capsize=5, capthick=2, elinewidth=1.8, zorder=3,
               label='L1 Real Robots (mean ± std, N runs)')

ax1mk.set_title(
    'Makespan vs. Occupancy — 5×5 Grid (400 mm/cell)\n'
    'Simulation L0 (30 runs, blue) vs. Real DotBot Robots L1 (N runs, red)',
    fontsize=11, fontweight='bold', pad=10)
ax1mk.set_xlabel('Occupancy  (n_agents / 25 cells)', fontsize=10)
ax1mk.set_ylabel('Makespan  (PIBT steps)', fontsize=10)
ax1mk.set_xticks(occs)
ax1mk.set_xticklabels(xticks_labels, fontsize=8.5)
ax1mk.yaxis.grid(True, linestyle=':', alpha=0.45, color='#aaaaaa')
ax1mk.set_axisbelow(True)
for spine in ax1mk.spines.values():
    spine.set_linewidth(0.6)

ax1mk.legend(fontsize=9, framealpha=0.95, edgecolor='#cccccc', loc='upper left')

plt.tight_layout()
makespan_pdf = os.path.join(OUT_DIR,
    'comparison_pibt_sim_30runs_vs_real_5x5_400mm_makespan_plot.pdf')
plt.savefig(makespan_pdf, bbox_inches='tight', dpi=150, facecolor='white')
plt.close()
print(f'[MAKESPAN PLOT] {makespan_pdf}')

# =============================================================================
# PDF 2 — PLOT
# =============================================================================
fig, axes = plt.subplots(1, 2, figsize=(15, 6.5))
fig.patch.set_facecolor('#fafafa')

occs = [d['occ'] for d in data]
ns   = [d['n']   for d in data]
xticks_labels = [f"{o:.2f}\n(n={n})" for o, n in zip(occs, ns)]

def style_ax(ax, title, xlabel, ylabel):
    ax.set_title(title, fontsize=10.5, fontweight='bold', pad=8)
    ax.set_xlabel(xlabel, fontsize=9.5)
    ax.set_ylabel(ylabel, fontsize=9.5)
    ax.set_xticks(occs)
    ax.set_xticklabels(xticks_labels, fontsize=8)
    ax.yaxis.grid(True, linestyle=':', alpha=0.45, color='#aaaaaa')
    ax.set_axisbelow(True)
    ax.set_facecolor('#fdfdfd')
    for spine in ax.spines.values():
        spine.set_linewidth(0.6)

# ── Panel 1 : Success Rate ────────────────────────────────────────────────────
ax1 = axes[0]
l0_sr = [d['l0_sr_m'] for d in data]
l0_ss = [d['l0_sr_s'] for d in data]
l1_sr = [d['l1_sr_m'] for d in data]
l1_ss = [d['l1_sr_s'] for d in data]

ax1.fill_between(occs,
    [m - s for m, s in zip(l0_sr, l0_ss)],
    [m + s for m, s in zip(l0_sr, l0_ss)],
    color=L0C, alpha=0.12)
ax1.plot(occs, l0_sr, color=L0C, linestyle='--', linewidth=2.2,
         marker='o', markersize=8, markerfacecolor='white',
         markeredgecolor=L0C, markeredgewidth=2.2, zorder=3)
ax1.errorbar(occs, l1_sr, yerr=l1_ss,
             color=L1C, linestyle='-', linewidth=2.2,
             marker='s', markersize=8, markerfacecolor=L1C,
             capsize=5, capthick=2, elinewidth=1.8, zorder=3)
ax1.axhline(1.0, color='#aaaaaa', linewidth=0.8, linestyle=':', zorder=1)
ax1.set_ylim(-0.05, 1.18)

style_ax(ax1,
    'Success Rate vs. Occupancy\n(5x5 grid, 400 mm/cell)',
    'Occupancy  (n_agents / 25 cells)',
    'Success Rate')

# ── Panel 2 : Makespan / Steps ────────────────────────────────────────────────
ax2 = axes[1]
l0_mk  = [d['l0_mk_m'] for d in data]
l0_mks = [d['l0_mk_s'] for d in data]
l1_st  = [d['l1_mk_m'] for d in data]
l1_sts = [d['l1_mk_s'] for d in data]

ax2.fill_between(occs,
    [m - s for m, s in zip(l0_mk, l0_mks)],
    [m + s for m, s in zip(l0_mk, l0_mks)],
    color=L0C, alpha=0.12)
ax2.plot(occs, l0_mk, color=L0C, linestyle='--', linewidth=2.2,
         marker='o', markersize=8, markerfacecolor='white',
         markeredgecolor=L0C, markeredgewidth=2.2, zorder=3)
ax2.errorbar(occs, l1_st, yerr=l1_sts,
             color=L1C, linestyle='-', linewidth=2.2,
             marker='s', markersize=8, markerfacecolor=L1C,
             capsize=5, capthick=2, elinewidth=1.8, zorder=3)

style_ax(ax2,
    'Makespan vs. Occupancy\n(5x5 grid, 400 mm/cell)',
    'Occupancy  (n_agents / 25 cells)',
    'Makespan  (steps_taken - step_timeouts)')

# ── Global title ──────────────────────────────────────────────────────────────
fig.suptitle(
    'PIBT on 5x5 Grid (400 mm/cell) — Simulation L0 (30 runs) vs. Real DotBot Robots L1 (N runs)\n'
    'Comparison of Success Rate and Step Count vs. Occupancy',
    fontsize=12, fontweight='bold', y=1.005)

# ── Legend ────────────────────────────────────────────────────────────────────
legend_handles = [
    Line2D([0], [0], color=L0C, lw=2.2, linestyle='--',
           marker='o', markerfacecolor='white', markeredgecolor=L0C, markeredgewidth=2.2,
           label='L0 Simulation — blue dashed line, open circle marker, mean over 30 runs'),
    mpatches.Patch(facecolor=L0C, alpha=0.25, edgecolor=L0C,
                   label='L0 Simulation — shaded blue area: ±1 std (30 runs)'),
    Line2D([0], [0], color=L1C, lw=2.2, linestyle='-',
           marker='s', markerfacecolor=L1C,
           label='L1 Real Robots — orange solid line, filled square marker, mean over N runs (makespan = steps_taken - step_timeouts)'),
    Line2D([0], [0], color=L1C, lw=1.8, marker='|', markersize=10, markeredgewidth=2,
           label='L1 Real Robots — vertical error bars with caps: ±1 std (N runs)'),
    Line2D([0], [0], color='#aaaaaa', lw=0.9, linestyle=':',
           label='Reference line — perfect success rate (1.0)'),
]

fig.legend(
    handles=legend_handles,
    loc='lower center', ncol=2,
    fontsize=8.5, framealpha=0.95, edgecolor='#cccccc',
    bbox_to_anchor=(0.5, -0.18),
    title=(
        'Legend\n'
        'X-axis: occupancy = n_agents / 25 cells (5x5 grid)  ·  '
        'L1 success rate penalized: -0.25 if timeouts > 4, -0.25 if duration > 50 s'
    ),
    title_fontsize=8,
)

plt.tight_layout(rect=[0, 0, 1, 1])
plot_pdf = os.path.join(OUT_DIR,
    'comparison_pibt_l0_sim_30runs_vs_l1_real_5x5_400mm_success_rate_and_steps_vs_occupancy_plot.pdf')
plt.savefig(plot_pdf, bbox_inches='tight', dpi=150)
plt.close()
print(f'[PLOT]  {plot_pdf}')
