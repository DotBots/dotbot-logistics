# AGENT.md

> Project map for coding agents working in `dotbot-logistics`. Read this before touching any
> root-level script. Per-folder documentation rule (see "Rules and invariants" below): `simulation/`
> is its own sub-project with its own `CLAUDE.md`/`AGENT.md`/`CONVENTION.md` — read those when you
> cross into `simulation/`, and likewise for any other folder that grows its own `AGENT.md`
> (e.g. `simulation/mrta/AGENT.md`). This file does not repeat folder-local guides.

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
- **L1** — drives the DotBot **simulator** through its REST controller API: `sim_dotbot_pibt.py`
  (fixed-goal batch run), `sim_dotbot_mrta.py` (persistent, operator-driven via clicks in the
  existing web UI).
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
├── requirements.txt             — pydotbot[calibrate], requests, pygame, scipy, websockets
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
├── sim_dotbot_pibt.py           — L1: drives the DotBot simulator (fixed-goal batch run)
├── sim_dotbot_mrta.py           — L1: persistent, click-to-target via the web UI (see below)
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

### `sim_dotbot_mrta.py` — a different pattern (2026-07-23)

Not a fixed-goal batch run: it starts every bot **parked** (no goals) and runs **indefinitely**
(Ctrl+C to stop), waiting for an operator to drive it. It reuses `GridStateManager`,
`send_waypoints()`, `_send_all_parallel()` and `wait_until_all_arrived()` verbatim (same
duplication convention as the other bridge scripts), but replaces `build_pibt()` +
`StaticDispatcher` with `build_mrta()` wiring `mrta.FleetManager` + `mrta.QueueTaskSource` +
`algo.EasiestAllocator` as the `Simulation`'s dispatcher, and drops the pipelining
`run_pibt_live()` does (a manual click can land mid-travel and must be reflected in the very next
`sim.step()`, so pre-computing ahead would either miss it or be thrown away — this script always
does the plainer step → send → wait, like `real_dotbot_pibt.py`).

**The click path has no PyDotBot-side changes.** The operator uses the existing, unmodified web
UI exactly as it already works today: select a bot, click a map point, "Apply waypoints" — a
normal `PUT .../waypoints`. `sim_dotbot_mrta.py` detects that PUT via a `WaypointWatcher`
background thread listening on the controller's `ws://<base>/controller/ws/status` broadcast
channel (**not** `/controller/ws/dotbots`, which is a separate, bidirectional command-relay
channel that never receives broadcasts — confirmed by reading `dotbot/server.py` directly,
verify again if this behaviour matters and PyDotBot has moved on since), converts the waypoint's
target cell into an `mrta.Task` restricted to that one bot (`eligible=frozenset({agent_id})`),
and lets PIBT navigate it there while avoiding every other bot being driven the same way. A
periodic REST-based reconciliation pass (comparing `GET /controller/dotbots`' `waypoints` field
against what the script itself last sent) recovers a click made while the WS link was down. A
re-click on a bot already mid-route overrides the in-flight task rather than queuing behind it —
matching the fact that the browser's own PUT already overwrites the bot's waypoint list
unconditionally the instant it lands.

**Cross-repo dependency**: the WS message shape this script parses
(`{"cmd": 2, "data": {"address": ..., "lh2_waypoints": [...]}}`) is owned by
`/home/dok/Inria/PyDotBot` (a separate repo, not versioned here) — if that project changes its
notification schema, `WaypointWatcher._handle_raw()` is what needs updating.

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
WS   /controller/ws/status                   → broadcasts { cmd, data } on every state change
                                                (sim_dotbot_mrta.py only, cmd 2 = UPDATE)
```

This is the seam that changes as the DotBot environment is restructured — if the controller API
shape changes, `GridStateManager` and `send_waypoints()` are what need updating, in each of the
four scripts that duplicate them (plus `WaypointWatcher._handle_raw()` in `sim_dotbot_mrta.py` for
the WS shape specifically).

### Configuration

`dotbot.toml` configures the pydotbot CLI (MQTT broker `localhost:1883`, swarm `1234`). MQTT
credentials go in env vars `DOTBOT_MQTT_USER` / `DOTBOT_MQTT_PASS`.

## Rules and invariants

- **A folder with its own `AGENT.md` must have it read before working inside it.** Not just
  `simulation/` as a special case — this is the general rule `simulation/`'s own layout already
  follows one level down (`core/AGENT.md`, `algo/AGENT.md`, `mrta/AGENT.md`, `client/AGENT.md`,
  `report/AGENT.md`, each read on demand only when touching that specific package — see
  `simulation/AGENT.md`'s "Package guides" table). Any folder in this repo may grow its own
  `AGENT.md` the same way; check for one (`ls <folder>/AGENT.md`) before making changes inside a
  folder you have not worked in during this session, and do not assume this root file already
  covers it — a folder-local guide holds the detail this one deliberately does not repeat.
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
