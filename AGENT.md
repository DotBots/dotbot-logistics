# AGENT.md

> Project map for coding agents working in `dotbot-logistics`. Read this before touching any
> root-level script, and read the "Current known inconsistencies" section below first — most
> L0/L1/L2 scripts are currently broken, `mrta_mode`/`sim_dotbot_mrta.py` are not (see why there).
> Per-folder documentation rule (see "Rules and invariants" below): any folder that grows its own
> `AGENT.md` gets read before you work
> inside it — this file does not repeat folder-local guides.

## What this project is

`dotbot-logistics` is the **bridge** between a PIBT/MRTA engine and the DotBot environment. Until
2026-08-27 that engine was vendored at `simulation/` — a drifted, git-history-only snapshot of the
external repo `MAPF_Simulation`, owning the algorithm (grid, agents, PIBT, task allocation) and
exposed as a Python API the root-level scripts here consumed and wired to whatever DotBot
environment is actually available — the DotBot simulator today, real hardware over LH2/MQTT
tomorrow. `simulation/` was **removed**, and `mrta_mode/`/`sim_dotbot_mrta.py` have since been
**reconnected** to the real upstream engine (see "Current known inconsistencies" for exactly what
still isn't); the other L0/L1/L2 scripts have not. The DotBot side (`pydotbot`, the controller, the
hardware stack) is **under active restructuring** and evolves independently of this engine
question; treat this bridge layer as a moving target, not a settled one, and re-verify against the
code rather than trusting a stale description — including this one. (This file did exactly that
wrong once already, same day: an "engine reconnection is deliberately deferred" claim here briefly
described a fact-check against a stale second clone of `MAPF_Simulation` as if it were the real
one — see `Roadmap.md` §0's own account of that mistake before trusting any claim about the
upstream engine's shape without re-deriving it from the actual clone in use.)

Three levels, pure algorithm to real hardware:

- **L0** — pure Python, no hardware: `sim_pibt.py`, `sim_many_pibt.py`. **Broken.**
- **L1** — drives the DotBot **simulator** through its REST controller API: `sim_dotbot_pibt.py`
  (fixed-goal batch run, **broken**), `sim_dotbot_mrta.py` (persistent, operator-driven via clicks
  in the existing web UI, **reconnected**).
- **L2** — drives **real** DotBots over LH2/MQTT: `real_dotbot_pibt.py`,
  `real_dotbot_pibt_batch.py`. **Broken.**

Multi-Robot Task Allocation is now `pibt.LifelongGoalOrchestrator` (from the `mapf-simulation`
package, see below) — the online-task-stream/dynamic-priority `FleetManager`/`Task`/
`QueueTaskSource`/`EasiestAllocator` model that used to live in the now-removed
`simulation/mrta/` has no equivalent any more and was not ported: `LifelongGoalOrchestrator` is a
different, simpler design (one mutable target slot per agent, no queue, no cross-agent
eligibility — see `mrta_mode/mrta_session.py`'s `_advance_chain()` for what MRTASession now owns
locally to still support multi-hop waypoint chains). The design roadmap that preceded the removed
implementation (`RoadmapMRTA.md`) was deleted once that code existed; if you need the original
rationale, it is in git history (`git log --all --full-history -- RoadmapMRTA.md`).

## Current known inconsistencies

**`sim_pibt.py`, `sim_many_pibt.py`, `sim_dotbot_pibt.py`, `real_dotbot_pibt.py`,
`real_dotbot_pibt_batch.py`, `sim_dotbot_right_left.py` are still broken, as of 2026-08-27.** They
import `algo`/`mrta` off a `sys.path.insert(..., "simulation")` that no longer resolves to
anything — `simulation/` was removed (commit `d4e053b`) and these six scripts were not ported to
the real upstream engine (`mrta_mode`/`sim_dotbot_mrta.py` were, see below). Porting them means
replacing `algo.PIBTCoordinator`/`core.Simulation`/`core.Grid`/`core.Position` with
`pibt.PIBTPlanner`/`core.WorldEngine`/`core.Grid2D`/`core.Coordinates2D` — same shape as the
`mrta_mode` port, not yet done for these six.

**`mrta_mode/` and `sim_dotbot_mrta.py` are reconnected**, to the `mapf-simulation` package
(`core` + `pibt`, pip-installed as a git dependency from
`git+https://github.com/RasdaCorentin/MAPF_Simulation.git@develop` — see `requirements.txt`), not
to the removed `simulation/`. `mrta_mode/mrta_session.py`'s `MRTASession` now owns a
`core.WorldEngine` wired to `pibt.PIBTPlanner` + `pibt.LifelongGoalOrchestrator` instead of the old
`core.Simulation` + `mrta.FleetManager` + `mrta.QueueTaskSource` + `algo.EasiestAllocator`; see
`diagrammes/sim_dotbot_mrta_ws_target_class_diagram.puml` for the validated design and
`Roadmap.md` §0 for the full account, including the stale-clone mistake this correction follows.
**Verified end-to-end, 2026-08-27**: against a real `dotbot run simulator` (5×5 grid, 10 bots) and
`sim_dotbot_mrta.py --dry-run` (connects, lists bots, builds the grid, no errors), then live — a
`PUT .../waypoints` click on one bot was detected over the WS status channel, translated to a
target cell, driven through `orchestrator.set_target()` → `WorldEngine.advance_time_step()` →
`PIBTPlanner`, and the bot walked the Manhattan path to the target one cell per tick, waiting for
real arrival at each step before continuing. `mapf-simulation` itself is still not installed
anywhere in this project's own environment — this run borrowed `core`/`pibt` via `PYTHONPATH`
against the `~/3A/projets/MAPF_Simulation` checkout directly, and pydotbot from an unrelated
project's venv (`dotbot-workspace/.venv`) rather than a `dotbot-logistics`-local one, which still
does not exist. A durable local install (this project's own venv, `pip install -r
requirements.txt`) is still open work. Also not carried over on purpose: Button.md's fix C.3 (an
empty waypoint list — the operator's "Stop nav" — should cancel the agent's target, not be
ignored) is still unapplied; the new engine makes that fix trivial
(`orchestrator.set_target(agent_id, agent.position)`) but it is still a separate, undone change.

*(If this section goes stale — scripts fixed, or newly broken some other way — update it in the
same commit that changes the fact: an agent map that lies is worse than no map.)*

## Layout

```
.
├── AGENT.md                    — this file
├── CLAUDE.md                   — pointer that imports AGENT.md
├── CONVENTION.md                — git/branch/commit/issue conventions (repo-wide)
├── README.md                    — human-facing overview, install, script reference
├── requirements.txt             — pydotbot[calibrate], requests, pygame, websockets, mapf-simulation
├── dotbot.toml                  — pydotbot CLI config (MQTT broker, swarm id)
├── mosquitto.conf               — local MQTT broker config for L2
├── mkdocs.yml                   — config for the docs/ site
├── simulator_init_state.toml    — L1 simulator seed, 5x5 grid (400 mm cells)
├── simulator_init_state_8x8.toml— L1 simulator seed, 8x8 grid (250 mm cells)
├── docs/                        — MkDocs site: level-0/1/2 guides, installation, contributing, inria/
├── mrta_mode/                   — classes behind sim_dotbot_mrta.py's MRTA mode (see below;
│                                   one concrete class or DTO per file; reconnected, see above)
├── log/                         — experiment outputs (raw_logs/, *_per_run.csv, *_summary.csv)
├── sim_pibt.py                  — L0 interactive PIBT viewer (broken, see above)
├── sim_many_pibt.py             — L0 headless benchmark sweep (broken, see above)
├── sim_dotbot_pibt.py           — L1: drives the DotBot simulator (fixed-goal batch run, broken)
├── sim_dotbot_mrta.py           — L1: persistent, click-to-target via the web UI (see below, reconnected)
├── real_dotbot_pibt.py          — L2: drives real DotBots (broken, see above)
├── real_dotbot_pibt_batch.py    — L2: batch harness (N bots x M runs, broken)
└── run_metrics.py               — CSV metrics helper for the L2 batch harness
```

Before the `simulation/` removal, that package was added to `sys.path` by each top-level script at
import time (`sys.path.insert(0, ".../simulation")`) — no install needed, no package boundary to
cross other than the Python import itself. The six still-broken scripts listed above still have
that `sys.path.insert()` call, now resolving to nothing. `mrta_mode/` used to be the one exception
(it added `simulation/` to `sys.path` once, in its own `__init__.py`, rather than requiring
`sim_dotbot_mrta.py` to repeat the dance) — since reconnection, it has no `sys.path` manipulation
at all: `core`/`pibt` come from the pip-installed `mapf-simulation` package (`requirements.txt`),
a real install rather than a path trick. The six broken scripts have not been ported to this same
pattern yet — see "Current known inconsistencies".

## The bridge pattern (L1/L2 scripts)

Describes the still-current *shape* of `sim_dotbot_pibt.py`, `real_dotbot_pibt.py` and
`real_dotbot_pibt_batch.py` — the classes and control flow below are unchanged in the source —
even though all three currently fail at import (see "Current known inconsistencies"; unlike
`sim_dotbot_mrta.py`, they have not been reconnected to the real engine yet). All three share the
same three-part shape — this is the pattern to preserve once reconnection makes them importable
again:

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

### `sim_dotbot_mrta.py` — a different pattern (2026-07-23, split into `mrta_mode/` 2026-08-26,
reconnected to the real upstream engine 2026-08-27)

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
- **`MRTASession`** (`mrta_mode/mrta_session.py`) — the "activatable mode" object: owns a
  `core.WorldEngine` wired to `pibt.PIBTPlanner` + `pibt.LifelongGoalOrchestrator`
  (`MRTASession.connect()` replaces the old `build_mrta()`; as of 2026-08-27 this replaced the
  earlier `core.Simulation` + `mrta.FleetManager` + `mrta.QueueTaskSource` +
  `algo.EasiestAllocator` design — see `diagrammes/sim_dotbot_mrta_ws_target_class_diagram.puml`),
  and exposes `start()`/`stop()`/`handle_click()`/`tick()` so a caller other than a blocking CLI
  while-loop — a future frontend — can drive it one step at a time; `run()` wraps `tick()` in the
  Ctrl+C while-loop for standalone CLI use. Drops the pipelining `run_pibt_live()` does (a manual
  click can land mid-travel and must be reflected in the very next `advance_time_step()`, so
  pre-computing ahead would either miss it or be thrown away — `tick()` always does the plainer
  step → send → wait, like `real_dotbot_pibt.py`). Also owns a per-agent `_pending_chain` queue
  (a `deque[Coordinates2D]`) that `LifelongGoalOrchestrator` itself has no equivalent for: it
  holds one mutable target slot per agent, not a queue, so a multi-hop waypoint click's cells
  beyond the first are popped into `set_target()` one at a time as the agent arrives at each.

**The click path has no PyDotBot-side changes.** The operator uses the existing, unmodified web
UI exactly as it already works today: select a bot, click a map point, "Apply waypoints" — a
normal `PUT .../waypoints`. `MRTASession.handle_click()` calls
`orchestrator.set_target(agent_id, cell)` for that one bot, and lets PIBT navigate it there while
avoiding every other bot being driven the same way — eligibility is not a separate concept to
implement here, `set_target()` already takes an explicit `agent_id`. A re-click on a bot already
mid-route overrides the in-flight target rather than queuing behind it (`set_target()`'s own
contract: it always overwrites) — matching the fact that the browser's own PUT already overwrites
the bot's waypoint list unconditionally the instant it lands.

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
