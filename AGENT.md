# AGENT.md

> Project map for coding agents working in `dotbot-logistics`. Read this before touching any
> root-level script. `simulation/` is its own sub-project with its own
> `CLAUDE.md`/`AGENT.md`/`CONVENTION.md` — read those when you cross into `simulation/`; this
> file does not repeat them.

## What this project is

`dotbot-logistics` is the **bridge** between the `simulation/` PIBT/MRTA engine and the DotBot
environment. `simulation/` owns the algorithm (grid, agents, PIBT, task allocation) and exposes it
as a Python API; the root-level scripts in this repo consume that API and wire it to whatever
DotBot environment is actually available — the DotBot simulator today, real hardware over
LH2/MQTT tomorrow — adapting the connection layer to each target. The DotBot side (`pydotbot`,
the controller, the hardware stack) is **under active restructuring** and evolves independently
of `simulation/`; treat this bridge layer as a moving target, not a settled one, and re-verify
against the code rather than trusting a stale description — including this one.

Three levels, pure algorithm to real hardware:

- **L0** — pure Python, no hardware: `sim_pibt.py`, `sim_many_pibt.py`, the whole `simulation/`
  package.
- **L1** — drives the DotBot **simulator** through its REST controller API: `sim_dotbot_pibt.py`.
- **L2** — drives **real** DotBots over LH2/MQTT: `real_dotbot_pibt.py`,
  `real_dotbot_pibt_batch.py`.

Multi-Robot Task Allocation (online task stream + dynamic priority, on top of one-shot PIBT) is
implemented in `simulation/mrta/` — read `simulation/mrta/AGENT.md` before touching goal/priority
assignment. The design roadmap that preceded the implementation (`RoadmapMRTA.md`) has been
removed now that the code is the source of truth; if you need the original rationale, it is in
git history (`git log --all --full-history -- RoadmapMRTA.md`).

## Bridge-scripts migration history (2026-07-23)

`simulation/` was refactored: `core/` split into `entities/`/`environment/`/`engine/`,
`Objective` removed in favour of `Zone`, `algo/pibt.py` replaced by
`algo/coordination/pibt_coordinator.py`'s `PIBTCoordinator`, and goals/priorities are now
injected per tick via a `DispatchIntent` instead of the old `PIBT(goals=..., initial_priorities=...)`
constructor. All five root-level bridge scripts (`sim_pibt.py`, `sim_many_pibt.py`,
`sim_dotbot_pibt.py`, `real_dotbot_pibt.py`, `real_dotbot_pibt_batch.py`) initially missed this
and failed at import; all five have since been migrated onto `PIBTCoordinator` +
`StaticDispatcher`, following the `simulation/demo_pibt.py` pattern — goals and priorities are
now keyed by `agent_id` (int), not `Agent` objects. Two things worth knowing if you touch them
again:

- **`sim_pibt.py`'s old `Objective` obstacle** (a collectible, owner-able entity) was dropped
  rather than replaced — that entity type has no post-refactor equivalent (`Zone` is never
  collectible).
- **`real_dotbot_pibt_batch.py`'s `resync_simulation()`** used to reach into
  `sim.coordinator.priorities` (Agent-keyed) to un-stick an agent PIBT had demoted to `-inf`
  after "reaching its goal", in case the LH2 resync showed it hadn't really arrived. That hack
  was dropped, not migrated: `PIBTCoordinator` has no public `priorities` attribute, and doesn't
  need the poke either — `plan()` re-checks `position == goal` at the start of every step and
  restores the demoted base priority itself as soon as the state stops holding (the "`-inf`
  demotion is reversible" invariant, `simulation/AGENT.md`).

**Two `sim_many_pibt.py` still exist and are not interchangeable**: the root one (L0 sweep over
grid × N × seed, writes `l0_results.csv`) and `simulation/sim_many_pibt.py` (same idea, own
scope, writes `sim_results.csv`). Both now target the current engine — check which directory
you're in before running or editing either.

*(If `simulation/`'s engine changes again in a way that breaks these scripts, update this section
in the same commit — an agent map that lies is worse than no map.)*

## Layout

```
.
├── AGENT.md                    — this file
├── CLAUDE.md                   — pointer that imports AGENT.md
├── CONVENTION.md                — git/branch/commit/issue conventions (repo-wide)
├── README.md                    — human-facing overview, install, script reference
├── requirements.txt             — pydotbot[calibrate], requests, pygame
├── dotbot.toml                  — pydotbot CLI config (MQTT broker, swarm id)
├── mosquitto.conf               — local MQTT broker config for L2
├── mkdocs.yml                   — config for the docs/ site
├── simulator_init_state.toml    — L1 simulator seed, 5x5 grid (400 mm cells)
├── simulator_init_state_8x8.toml— L1 simulator seed, 8x8 grid (250 mm cells)
├── docs/                        — MkDocs site: level-0/1/2 guides, installation, contributing, inria/
├── simulation/                  — PIBT/MRTA engine, own CLAUDE.md/AGENT.md/CONVENTION.md
├── log/                         — experiment outputs (raw_logs/, *_per_run.csv, *_summary.csv)
├── sim_pibt.py                  — L0 interactive PIBT viewer
├── sim_many_pibt.py             — L0 headless benchmark sweep
├── sim_dotbot_pibt.py           — L1: drives the DotBot simulator
├── real_dotbot_pibt.py          — L2: drives real DotBots
├── real_dotbot_pibt_batch.py    — L2: batch harness (N bots x M runs)
└── run_metrics.py               — CSV metrics helper for the L2 batch harness
```

`simulation/` is added to `sys.path` by each top-level script at import time — no install needed,
no package boundary to cross other than the Python import itself.

## The bridge pattern (L1/L2 scripts)

`sim_dotbot_pibt.py`, `real_dotbot_pibt.py` and `real_dotbot_pibt_batch.py` all share the same
three-part shape — this is the pattern to preserve when migrating or extending them:

1. **`GridStateManager`** — fetches bot state from `GET /controller/dotbots`, converts mm ↔ grid
   cell, resolves collisions when two bots land on the same cell (nudges one to a free
   neighbouring cell).
2. **`build_pibt()`** — builds a `Grid` + `Agent` list from the measured start cells, assigns
   goals, and returns a ready `Simulation` wired to a PIBT coordinator.
3. **`run_pibt_live()`** — the step loop: `sim.step()` → send waypoints → `wait_until_all_arrived()`
   (the synchronisation barrier, polling real/simulated LH2 positions).

**sim vs real differences:**
- `sim_dotbot_pibt.py` — sends waypoints in parallel (`ThreadPoolExecutor`), pre-computes the next
  PIBT step while bots travel (pipelining), adaptive poll back-off (50 ms → 500 ms).
- `real_dotbot_pibt.py` — serial send (one bot at a time), no pipelining, fixed 200 ms poll.
- `real_dotbot_pibt_batch.py` — adds `resync_simulation()` (corrects agent positions from LH2
  after each step, since real hardware drifts from the plan), records `RunMetrics`, writes CSVs
  via `run_metrics.py`.

### Grid ↔ mm mapping

```
cell (gx, gy)  →  centre mm = (gx*cell_mm + cell_mm//2, gy*cell_mm + cell_mm//2)
pos (x, y) mm  →  cell      = (int(x/cell_mm), int(y/cell_mm))
```

Default: `--map-cells 5` on a 2000×2000 mm map → `cell_mm = 400`, 5×5 grid.
Alternative: `--map-cells 8` → `cell_mm = 250`, 8×8 grid (use `simulator_init_state_8x8.toml`).

### REST API consumed (controller side)

```
GET  /controller/dotbots                     → list of bots (filter: lh2_position present, status != 2)
GET  /controller/map_size                    → { width, height } in mm
PUT  /controller/dotbots/{addr}/0/waypoints  → { threshold, waypoints: [{x, y}] }
```

This is the seam that changes as the DotBot environment is restructured — if the controller API
shape changes, `GridStateManager` and `send_waypoints()` are what need updating, in each of the
three scripts that duplicate them.

### Configuration

`dotbot.toml` configures the pydotbot CLI (MQTT broker `localhost:1883`, swarm `1234`). MQTT
credentials go in env vars `DOTBOT_MQTT_USER` / `DOTBOT_MQTT_PASS`.

## Rules and invariants

- **1 action = 1 commit**: each logically distinct change (fix, migration, doc batch) is its own
  commit — see `CONVENTION.md`.
- **No push without explicit user request** in the same message.
- **Class-diagram-based development**: any change to `simulation/`'s engine must be shown and
  validated through its class diagram (`simulation/diagrammes/_model.iuml`) — see
  `simulation/AGENT.md` for the full rule and the regeneration commands.
- **Dependency direction inside `simulation/`** (`core` never imports `client`/`algo`/`mrta`,
  `algo` never imports `client`, etc.) is `simulation/`'s own contract — see
  `simulation/AGENT.md`, not restated here.
- **The sync barrier (`wait_until_all_arrived`) is load-bearing**: it is what gives PIBT its
  collision-avoidance guarantee on async, real hardware. Removing it or racing ahead of it can
  make two bots collide — it is not an optimisation to cut for latency.
- **`GridStateManager.resolve_conflicts()` is what keeps two bots from aliasing to the same
  cell** when LH2 noise puts them close together — do not bypass it when reading bot state.
