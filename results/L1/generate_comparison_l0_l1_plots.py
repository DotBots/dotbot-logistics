#!/usr/bin/env python3
"""
Generate two comparison PDFs: L0 (simulation, 30 seeds) vs L1 (real DotBots)
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
# PDF 1 — TABLE  (publication figure style)
# =============================================================================
FIG_W, FIG_H = 13.0, 5.8
fig = plt.figure(figsize=(FIG_W, FIG_H), facecolor='white')
ax  = fig.add_axes([0, 0, 1, 1], facecolor='white')
ax.set_xlim(0, 1)
ax.set_ylim(0, 1)
ax.axis('off')

# ── Geometry ──────────────────────────────────────────────────────────────────
# 8 comparable columns: n | occ | SR_L0 | Makespan_L0 | Deadlocks_L0 | SR_L1 | Steps_L1 | Timeouts_L1
L, R = 0.015, 0.985
W    = R - L

raw_w = [0.068, 0.068, 0.165, 0.165, 0.165, 0.165, 0.100]
total = sum(raw_w)
col_w = [w / total * W for w in raw_w]
col_x = [L]
for w in col_w[:-1]:
    col_x.append(col_x[-1] + w)
col_cx = [x + w / 2 for x, w in zip(col_x, col_w)]

# L0 group spans cols 2-3, L1 group spans cols 4-6
L0_x0 = col_x[2];  L0_x1 = col_x[3] + col_w[3]
L1_x0 = col_x[4];  L1_x1 = col_x[6] + col_w[6]
L0_cx  = (L0_x0 + L0_x1) / 2
L1_cx  = (L1_x0 + L1_x1) / 2

TOP  = 0.97
GH   = 0.085   # group header height
CH   = 0.095   # column header height
DH   = 0.082   # data row height
NCAP = 5       # caption lines

BOT_TABLE = TOP - GH - CH - len(data) * DH
CAP_TOP   = BOT_TABLE - 0.03

# ── Background fills (L0 blue / L1 orange) ────────────────────────────────────
for x0, x1, color in [(L0_x0, L0_x1, L0BG), (L1_x0, L1_x1, L1BG)]:
    ax.add_patch(patches.Rectangle(
        (x0, BOT_TABLE), x1 - x0, TOP - BOT_TABLE,
        color=color, zorder=0, lw=0))

# Alternating light-gray stripes on data rows (very subtle, on top of colored BG)
for i in range(len(data)):
    if i % 2 == 0:
        y = TOP - GH - CH - i * DH
        ax.add_patch(patches.Rectangle(
            (L, y - DH), W, DH,
            color='#00000008', zorder=1, lw=0))

# ── Booktabs-style rules ───────────────────────────────────────────────────────
def hrule(y, lw, ls='-'):
    ax.plot([L, R], [y, y], color='#111111', lw=lw, ls=ls,
            solid_capstyle='butt', zorder=10)

hrule(TOP, 1.6)
hrule(TOP - GH, 0.5)
hrule(TOP - GH - CH, 1.1)
hrule(BOT_TABLE, 1.6)

# ── Group header ──────────────────────────────────────────────────────────────
gh_y = TOP - GH / 2
for cx, label, color, x0, x1 in [
    (L0_cx, 'Simulation (L0 · 30 seeds)', L0C, L0_x0, L0_x1),
    (L1_cx, 'Real Robots (L1 · N runs)',   L1C, L1_x0, L1_x1),
]:
    ax.text(cx, gh_y + 0.010, label,
            ha='center', va='center', fontsize=9.5, fontweight='bold',
            color=color, zorder=11)
    ax.plot([x0 + 0.008, x1 - 0.008], [gh_y - 0.024, gh_y - 0.024],
            color=color, lw=0.9, zorder=11)

# ── Column headers ────────────────────────────────────────────────────────────
ch_y = TOP - GH - CH / 2
col_labels = [
    'Agents\n(n)',
    'Occ.',
    'Success Rate\n(mean ± std)',
    'Makespan\n(mean ± std)',
    'Succ. Rate†\n(mean ± std)',
    'Makespan\n(mean ± std)',
    'Runs\n(N)',
]
for cx, label in zip(col_cx, col_labels):
    ax.text(cx, ch_y, label,
            ha='center', va='center', fontsize=8.0, fontweight='bold',
            color='#111111', zorder=11, linespacing=1.4)

# ── Data rows ─────────────────────────────────────────────────────────────────
for i, d in enumerate(data):
    row_y = TOP - GH - CH - i * DH - DH / 2
    cells = [
        str(d['n']),
        f"{d['occ']:.2f}",
        f"{d['l0_sr_m']:.3f} ± {d['l0_sr_s']:.3f}",
        f"{d['l0_mk_m']:.1f} ± {d['l0_mk_s']:.1f}",
        f"{d['l1_sr_m']:.3f} ± {d['l1_sr_s']:.3f}",
        f"{d['l1_mk_m']:.1f} ± {d['l1_mk_s']:.1f}",
        str(d['l1_nr']),
    ]
    for cx, cell in zip(col_cx, cells):
        ax.text(cx, row_y, cell,
                ha='center', va='center', fontsize=8.5,
                color='#111111', zorder=11)

# ── Caption ───────────────────────────────────────────────────────────────────
caption_raw = (
    "Figure 2. PIBT scalability on a 5x5 grid (400 mm/cell, 25 cells): "
    "simulation L0 (30 random seeds per configuration, up to 100 steps) vs. real DotBot robots L1 (N physical runs). "
    "Success Rate : fraction of robots reaching their goal. "
    "Makespan : number of PIBT steps until the last robot arrives. "
    "Runs (N): total number of physical runs conducted for that agent count."
)
caption_wrapped = "\n".join(textwrap.wrap(caption_raw, width=155))
ax.text((L + R) / 2, CAP_TOP, caption_wrapped,
        ha='center', va='top', fontsize=7.2, style='italic',
        color='#333333', linespacing=1.5, zorder=11)

table_pdf = os.path.join(OUT_DIR,
    'comparison_pibt_l0_sim_30seeds_vs_l1_real_5x5_400mm_comparable_metrics_table.pdf')
plt.savefig(table_pdf, bbox_inches='tight', dpi=150, facecolor='white')
plt.close()
print(f'[TABLE] {table_pdf}')

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
    'PIBT on 5x5 Grid (400 mm/cell) — Simulation L0 (30 seeds) vs. Real DotBot Robots L1 (N runs)\n'
    'Comparison of Success Rate and Step Count vs. Occupancy',
    fontsize=12, fontweight='bold', y=1.005)

# ── Legend ────────────────────────────────────────────────────────────────────
legend_handles = [
    Line2D([0], [0], color=L0C, lw=2.2, linestyle='--',
           marker='o', markerfacecolor='white', markeredgecolor=L0C, markeredgewidth=2.2,
           label='L0 Simulation — blue dashed line, open circle marker, mean over 30 seeds'),
    mpatches.Patch(facecolor=L0C, alpha=0.25, edgecolor=L0C,
                   label='L0 Simulation — shaded blue area: ±1 std (30 seeds)'),
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
    'comparison_pibt_l0_sim_30seeds_vs_l1_real_5x5_400mm_success_rate_and_steps_vs_occupancy_plot.pdf')
plt.savefig(plot_pdf, bbox_inches='tight', dpi=150)
plt.close()
print(f'[PLOT]  {plot_pdf}')
