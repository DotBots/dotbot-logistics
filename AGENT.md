# AGENT.md

> Project map for coding agents working in `dotbot-logistics`. Read this before touching any
> root-level script, and read the "Current known inconsistencies" section below first — every
> L0/L1/L2 script is currently broken (see why there). Per-folder documentation rule (see "Rules
> and invariants" below): any folder that grows its own `AGENT.md` gets read before you work
> inside it — this file does not repeat folder-local guides.

## What this project is

`dotbot-logistics` is the **bridge** between a PIBT/MRTA engine and the DotBot environment. Until
2026-08-27 that engine was vendored at `simulation/` — a drifted, git-history-only snapshot of the
external repo `MAPF_Simulation`, owning the algorithm (grid, agents, PIBT, task allocation) and
exposed as a Python API the root-level scripts here consumed and wired to whatever DotBot
environment is actually available — the DotBot simulator today, real hardware over LH2/MQTT
tomorrow. `simulation/` has been **removed** (see "Current known inconsistencies"); reconnecting
to the real upstream engine is deliberately deferred, not attempted blind — see `Roadmap.md` §0
for why the previous reconnection plan was itself wrong and what re-scoping it needs. The DotBot
side (`pydotbot`, the controller, the hardware stack) is **under active restructuring** and
evolves independently of this engine question; treat this bridge layer as a moving target, not a
settled one, and re-verify against the code rather than trusting a stale description — including
this one.

Three levels, pure algorithm to real hardware — **all three currently broken**, see below:

- **L0** — pure Python, no hardware: `sim_pibt.py`, `sim_many_pibt.py`.
- **L1** — drives the DotBot **simulator** through its REST controller API: `sim_dotbot_pibt.py`
  (fixed-goal batch run), `sim_dotbot_mrta.py` (persistent, operator-driven via clicks in the
  existing web UI).
- **L2** — drives **real** DotBots over LH2/MQTT: `real_dotbot_pibt.py`,
  `real_dotbot_pibt_batch.py`.

Multi-Robot Task Allocation (online task stream + dynamic priority, on top of one-shot PIBT) was
implemented in the now-removed `simulation/mrta/`. The design roadmap that preceded that
implementation (`RoadmapMRTA.md`) was removed once the code existed; if you need the original
rationale, it is in git history (`git log --all --full-history -- RoadmapMRTA.md`).

## Current known inconsistencies

**Every root-level L0/L1/L2 script and `mrta_mode/` is broken, as of 2026-08-27.** `simulation/`
was removed (commit `d4e053b`) without a replacement: reconnecting to the real upstream
`MAPF_Simulation` engine is deliberate future work (`Roadmap.md` §0), not done yet. Concretely,
every one of these fails at import time (`sys.path.insert(..., "simulation")` then
`from algo import PIBTCoordinator`, or the `mrta_mode` equivalent):

- `sim_pibt.py`, `sim_many_pibt.py`, `sim_dotbot_pibt.py`, `real_dotbot_pibt.py`,
  `real_dotbot_pibt_batch.py`, `sim_dotbot_right_left.py` — import `algo`/`mrta` off a
  `sys.path` entry that no longer resolves to anything.
- `mrta_mode/__init__.py` and `mrta_mode/mrta_session.py` — same import, plus
  `mrta_mode/mrta_session.py` builds a `mrta.FleetManager` + `mrta.QueueTaskSource` +
  `algo.EasiestAllocator` dispatcher that has no package to come from.
- `sim_dotbot_mrta.py` — broken transitively through `mrta_mode`.

None of this is a regression to silently patch around: don't re-vendor a copy of the engine to
make these importable again without reading `Roadmap.md` §0 first — the whole point of removing
`simulation/` was to stop maintaining a second, drifting copy of an engine that already exists
upstream. *(If this section goes stale — scripts fixed, or newly broken some other way — update it
in the same commit that changes the fact: an agent map that lies is worse than no map.)*

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
├── mrta_mode/                   — classes behind sim_dotbot_mrta.py's MRTA mode (see below;
│                                   one concrete class or DTO per file; currently broken, see above)
├── log/                         — experiment outputs (raw_logs/, *_per_run.csv, *_summary.csv)
├── sim_pibt.py                  — L0 interactive PIBT viewer (broken, see above)
├── sim_many_pibt.py             — L0 headless benchmark sweep (broken, see above)
├── sim_dotbot_pibt.py           — L1: drives the DotBot simulator (fixed-goal batch run, broken)
├── sim_dotbot_mrta.py           — L1: persistent, click-to-target via the web UI (see below, broken)
├── real_dotbot_pibt.py          — L2: drives real DotBots (broken, see above)
├── real_dotbot_pibt_batch.py    — L2: batch harness (N bots x M runs, broken)
└── run_metrics.py               — CSV metrics helper for the L2 batch harness
```

Before the `simulation/` removal, that package was added to `sys.path` by each top-level script at
import time (`sys.path.insert(0, ".../simulation")`, still present in the code, now resolving to
nothing) — no install needed, no package boundary to cross other than the Python import itself.
`mrta_mode/` was the one exception: it added `simulation/` to `sys.path` once, in its own
`__init__.py`, rather than requiring `sim_dotbot_mrta.py` to repeat the `sys.path.insert()` dance.
Whatever replaces this (path insert against a local `MAPF_Simulation` clone, an editable install,
a submodule) is an open question — see `Roadmap.md` §0.

## The bridge pattern (L1/L2 scripts)

Describes the still-current *shape* of these scripts — the classes and control flow below are
unchanged in the source — even though every one of them currently fails at import (see "Current
known inconsistencies"). This is the pattern to preserve once reconnection makes them importable
again, not a description of something that runs today.

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

### `sim_dotbot_mrta.py` — a different pattern (2026-07-23, split into `mrta_mode/` 2026-08-26)

Not a fixed-goal batch run: it starts every bot **parked** (no goals) and runs **indefinitely**
(Ctrl+C to stop), waiting for an operator to drive it. `sim_dotbot_mrta.py` itself is now a thin
CLI — argparse + wiring only, per `diagrammes/sim_dotbot_mrta_ws_target_class_diagram.puml`. The
collaborators live in `mrta_mode/`, one concrete class or DTO per file:

- **`GridStateManager`** (`mrta_mode/grid_state_manager.py`) — same shape as the other bridge
  scripts' inline copy, but bootstrap (initial bot list + map size) and WS-outage fallback only
  here, not the step-loop's position source (see `LivePositionStore` below).
- **`ControllerStatusListener`** (`mrta_mode/controller_status_listener.py`, replaces the old
  `WaypointWatcher`) — the one WS client, on `ws://<base>/controller/ws/status` (**not**
  `/controller/ws/dotbots`, a separate, bidirectional command-relay channel that never receives
  broadcasts — confirmed by reading `dotbot/server.py` directly, verify again if this behaviour
  matters and PyDotBot has moved on since). Every message is a `DotBotNotificationCommand`;
  `cmd=2` (`UPDATE`) carries *both* waypoint-set events (`data.lh2_waypoints`) and continuous LH2
  position updates (`data.lh2_position`, pushed on every advertisement frame the controller
  receives — `dotbot/controller.py:405-567` in the up-to-date PyDotBot checkout at
  `dotbot-workspace/repos/PyDotBot`). The old `WaypointWatcher` kept only the waypoints half and
  silently dropped the rest; `ControllerStatusListener` dispatches both — waypoint events to a
  click queue drained by `MRTASession.tick()`, position events straight into `LivePositionStore`.
- **`LivePositionStore`** (`mrta_mode/live_position_store.py`, new) — the arrival source. Where
  every other bridge script's `wait_until_all_arrived()` polls `GET /controller/dotbots` on a
  50 ms → 500 ms backoff, this one blocks on a `Condition` notified by
  `ControllerStatusListener`'s position events, and falls back to one REST poll only if no update
  arrives before the timeout (WS missed it, or is down) — same safety-net principle as
  `ManualClickTranslator.reconcile()` below.
- **`ManualClickTranslator`** (`mrta_mode/manual_click_translator.py`) — mm↔cell translation,
  dedup, self-echo detection (telling apart a manual click from the echo of a `PUT` this script
  itself just sent, arriving back on the same WS channel), and the REST reconciliation safety net
  (comparing `GET /controller/dotbots`' `waypoints` field against what the script itself last
  sent) for clicks made while the WS link was down.
- **`WaypointCommandClient`** (`mrta_mode/waypoint_command_client.py`) — write-path only:
  `PUT /controller/dotbots/{address}/0/waypoints`. The WS status channel is broadcast-only from
  the controller's side; commanding a bot to move always requires this `PUT` regardless of how
  arrival is detected — `ControllerStatusListener` cannot replace it, only `wait_until_all_arrived`
  moved off this class.
- **`MRTASession`** (`mrta_mode/mrta_session.py`) — the "activatable mode" object: owns the
  `Simulation` + `mrta.FleetManager` + `mrta.QueueTaskSource` + `algo.EasiestAllocator` dispatcher
  (`MRTASession.connect()` replaces the old `build_mrta()`), and exposes
  `start()`/`stop()`/`handle_click()`/`tick()` so a caller other than a blocking CLI while-loop —
  a future frontend — can drive it one step at a time; `run()` wraps `tick()` in the Ctrl+C
  while-loop for standalone CLI use. Drops the pipelining `run_pibt_live()` does (a manual click
  can land mid-travel and must be reflected in the very next `sim.step()`, so pre-computing ahead
  would either miss it or be thrown away — `tick()` always does the plainer step → send → wait,
  like `real_dotbot_pibt.py`).

**The click path has no PyDotBot-side changes.** The operator uses the existing, unmodified web
UI exactly as it already works today: select a bot, click a map point, "Apply waypoints" — a
normal `PUT .../waypoints`. `MRTASession.handle_click()` converts the waypoint's target cell into
an `mrta.Task` restricted to that one bot (`eligible=frozenset({agent_id})`), and lets PIBT
navigate it there while avoiding every other bot being driven the same way. A re-click on a bot
already mid-route overrides the in-flight task rather than queuing behind it — matching the fact
that the browser's own PUT already overwrites the bot's waypoint list unconditionally the instant
it lands.

**Cross-repo dependency**: the WS message shapes this script parses
(`{"cmd": 2, "data": {"address": ..., "lh2_waypoints": [...]}}` and
`{"cmd": 2, "data": {"address": ..., "lh2_position": {"x": ..., "y": ...}}}`) are owned by
`DotBots/PyDotBot` (a separate repo, checked out locally at `dotbot-workspace/repos/PyDotBot`, not
versioned here) — if that project changes its notification schema,
`ControllerStatusListener._handle_raw()` is what needs updating.

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
                                                (sim_dotbot_mrta.py only, cmd 2 = UPDATE;
                                                 carries both lh2_waypoints and lh2_position)
```

This is the seam that changes as the DotBot environment is restructured — if the controller API
shape changes, `GridStateManager` and `send_waypoints()` are what need updating in
`sim_dotbot_pibt.py`, `real_dotbot_pibt.py` and `real_dotbot_pibt_batch.py` (each still duplicates
its own inline copy); for `sim_dotbot_mrta.py` the equivalents are
`mrta_mode/grid_state_manager.py`'s `GridStateManager` and
`mrta_mode/waypoint_command_client.py`'s `WaypointCommandClient.send()`, plus
`mrta_mode/controller_status_listener.py`'s `ControllerStatusListener._handle_raw()` for the WS
shape specifically.

### Configuration

`dotbot.toml` configures the pydotbot CLI (MQTT broker `localhost:1883`, swarm `1234`). MQTT
credentials go in env vars `DOTBOT_MQTT_USER` / `DOTBOT_MQTT_PASS`.

## Rules and invariants

- **A folder with its own `AGENT.md` must have it read before working inside it.** Any folder in
  this repo may grow its own `AGENT.md`; check for one (`ls <folder>/AGENT.md`) before making
  changes inside a folder you have not worked in during this session, and do not assume this root
  file already covers it — a folder-local guide holds the detail this one deliberately does not
  repeat. (`simulation/`'s own multi-level version of this rule — `core/AGENT.md`, `algo/AGENT.md`,
  `mrta/AGENT.md`, etc. — no longer applies now that `simulation/` is removed; it is the reference
  example if that package (or its replacement) comes back.)
- **1 action = 1 commit**: each logically distinct change (fix, migration, doc batch) is its own
  commit — see `CONVENTION.md`.
- **No push without explicit user request** in the same message.
- **Class-diagram-based development**: any change to the PIBT/MRTA engine's design should be shown
  and validated through a class diagram before code moves (the rule `simulation/AGENT.md` used to
  state for its own package) — still the intended practice, just without a live target to point at
  until reconnection is scoped; see `Roadmap.md` §0.
- **The sync barrier (`wait_until_all_arrived`) is load-bearing**: it is what gives PIBT its
  collision-avoidance guarantee on async, real hardware. Removing it or racing ahead of it can
  make two bots collide — it is not an optimisation to cut for latency.
- **`GridStateManager.resolve_conflicts()` is what keeps two bots from aliasing to the same
  cell** when LH2 noise puts them close together — do not bypass it when reading bot state.
