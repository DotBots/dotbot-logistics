# Level 0 — Run a PIBT to see how it works

The first level is the **algorithm alone**, on an abstract grid. There is no robot, no
controller, no radio — agents are dots that occupy cells, and PIBT decides where each one
moves next so that two of them never land on the same cell. This is the cheapest, fastest
level, and it establishes the *algorithmic ceiling*: if a scenario fails here, it's the
planner — not physics.

!!! info "What is PIBT?"
    PIBT (Priority Inheritance with Backtracking) is an iterative multi-agent path-finding
    algorithm. At every step each agent picks its best move toward its goal; when two agents
    want the same cell, the higher-priority one wins and the loser *inherits* priority to
    push others out of the way, backtracking if it gets stuck. The implementation in
    `simulation/algo/pibt.py` is an independent reimplementation inspired by
    **Okumura et al., *"Priority Inheritance with Backtracking for Iterative Multi-Agent
    Path Finding"*, Artificial Intelligence (2022)** —
    [arXiv:1901.11282](https://arxiv.org/abs/1901.11282).

## Watch it run — the interactive viewer

The `sim_pibt.py` script ships an interactive pygame viewer that animates PIBT on a small
grid and shows, at each step, the priority order, every agent's move, and the
priority-inheritance chains. The scenario (grid size, start positions, goals, priorities,
obstacles) is **edited directly in the file** — there are no command-line options.

```bash
python sim_pibt.py        # launch the interactive viewer
python sim_pibt.py -d     # debug mode (hides the pygame support prompt)
```

| Key | Action |
|-----|--------|
| `Space` | pause / play |
| `→` | step forward |
| `←` | step back |
| `Q` / `Esc` | quit |

A minimal, non-PIBT example (random-walk coordinator, useful as a template for your own
algorithm) lives in `simulation/main.py`:

```bash
python simulation/main.py
```

To plug in your own planner, subclass `Coordinator` and implement `plan()` — see
`simulation/algo/random_walk.py` for the smallest possible example, and the docstring at
the top of `sim_pibt.py` for the renderer options.

## Measure it — the headless benchmark

To turn "it works" into numbers, `sim_many_pibt.py` runs PIBT with **no pygame and no
hardware**, sweeping grid resolution × number of robots × random seeds and writing one CSV
row per instance.

```bash
python sim_many_pibt.py                  # full sweep, 30 seeds
python sim_many_pibt.py --seeds 5        # quick smoke-test
python sim_many_pibt.py --out my.csv     # custom output file (default: l0_results.csv)
```

The sweep fixes a **2000 × 2000 mm arena** and varies the cell size, which is the core
experimental question — *how small can the cells get before the plan stops working?*

| Grid | Cell size |
|------|-----------|
| 4×4 | 500 mm |
| 5×5 | 400 mm |
| 8×8 | 250 mm |

For each grid it sweeps the robot count `N` up to the grid's capacity and reports success
rate against **occupancy ρ = N / cells**. Because the run is pure Python and finishes in
seconds, you can push `N` right up to each grid's limit to find the **PIBT breaking
point** — the occupancy at which congestion forces long priority-inheritance chains and
some agents never reach their goal within the step cap.

Metrics written to the CSV include success rate, makespan (last arrival step), flowtime,
detour ratio, per-step planning time, and the deadlock count.

!!! note "Why this matters for the later levels"
    On the abstract grid PIBT is near-optimal, so success stays high at low-to-moderate
    density. That is the point: it proves that the failures you'll see on real hardware at
    [Level 2](level-2-real.md) come from *physics* (turning radius, overshoot), not from the
    algorithm.

Next: [Level 1 — Plug it to fake bots](level-1-simulator.md).
