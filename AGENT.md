# AGENT.md

> Project map for coding agents working in `dotbot-logistics`. The only live code path is
> `mrta_mode/` + `mrta_server.py` (the console MRTA toggle). The old L0/L1/L2 bridge scripts
> were removed on 2026-08-27 — three are kept as unported reference under `test_scripts/`, the
> rest are gone (`git log --diff-filter=D --name-only` to see what). Read "Current known
> inconsistencies" below before trusting any older description in this file or in `docs/`.
> Per-folder documentation rule (see "Rules and invariants" below): any folder that grows its
> own `AGENT.md` gets read before you work inside it — this file does not repeat folder-local
> guides.

## Install this repo (to run it, or to reuse a piece of it)

If you are an agent picking this repo up — to run MRTA mode, extend it, or lift the `mrta_mode/`
click-to-target pattern into another project — this is the setup verified against a live
`dotbot run simulator`. There is no committed venv and none of this is automated; do it by hand.

### 1. The engine and the Python deps

```bash
git clone https://github.com/DotBots/dotbot-logistics.git
cd dotbot-logistics
python3.12 -m venv venv && source venv/bin/activate   # this repo has no venv of its own
pip install -r requirements.txt
```

`requirements.txt` pulls:

- `pydotbot[calibrate]` — the DotBot controller, simulator, and web console
- `mapf-simulation` — the PIBT engine (`core` + `pibt`), installed straight from
  `git+https://github.com/RasdaCorentin/MAPF_Simulation.git@develop`; no local checkout needed
  (see that repo's own `README.md`/`AGENT.md` for what each package exposes)
- `requests`, `websockets` — the controller REST client and the WS click/position listener

### 2. A PyDotBot environment on the `feat/mrta-mode-toggle` branch

`mrta_server.py` is reached by the DotBot web console's "MRTA" pill through a `/mrta/*` proxy
that currently exists only on PyDotBot's `feat/mrta-mode-toggle` branch. So a working PyDotBot
is a **prerequisite**, and it has to be that branch. Replace the released `pydotbot` in the venv
with an editable checkout of it:

```bash
git clone https://github.com/DotBots/PyDotBot.git
git -C PyDotBot checkout feat/mrta-mode-toggle
pip install -e PyDotBot
```

Already have a PyDotBot checkout? `git checkout feat/mrta-mode-toggle` in it and `pip install -e`
that path. For a full DotBot testbed rather than PyDotBot alone, follow
[`DotBots/dotbot-workspace`](https://github.com/DotBots/dotbot-workspace) — an agent-first setup
(`/workspace-setup`) that clones every DotBot repo into one shared venv with editable installs;
check `feat/mrta-mode-toggle` out in its `PyDotBot` and add this repo's `requirements.txt` to
that venv.

Skip this step if you only want the `--dry-run` wiring check, or if you are reusing `mrta_mode/`
as a library — the proxy is a console-integration convenience, not a dependency of the engine.

### 3. Run the smoke test

```bash
# terminal 1 — simulated swarm. Needs a seed TOML with >= 2 bots; PyDotBot ships a sample as
#              simulator_init_state.toml at the root of its checkout, or write your own. The
#              proxy target is set with --mrta-url (or [run.controller] mrta_url, or DOTBOT_MRTA_URL).
dotbot run simulator --map-size 2000x2000 \
    --simulator-init-state path/to/simulator_init_state.toml \
    --mrta-url http://localhost:8002

# terminal 2
python mrta_server.py            # serves 0.0.0.0:8002; add --dry-run to build without sending
```

Open `http://localhost:8000/PyDotBot/`, click the "MRTA" pill ON, then select a bot, click a map
point, "Apply waypoints" — PIBT drives it there while routing around every other bot. Toggle OFF
to stop every bot where it stands. `Ctrl+C` in terminal 2 shuts the server down.

### Reusing only `mrta_mode/`

`mrta_mode/` is self-contained: it depends on `core`/`pibt` (`pip install mapf-simulation`) and
the DotBot controller's REST/WS surface — nothing else in this repo.
`mrta_mode/mrta_session.py`'s `MRTASession` is the entry point
(`connect()` / `start()` / `handle_click()` / `tick()` / `stop()`); `mrta_mode/server.py`'s
`MrtaMode` wraps it in the ON/OFF state machine. Read
`diagrammes/sim_dotbot_mrta_ws_target_class_diagram.puml` before the code, per this repo's own
"class-diagram-based development" rule (see "Rules and invariants").

## What this project is

`dotbot-logistics` is the **bridge** between a PIBT/MRTA engine and the DotBot environment. Until
2026-08-27 that engine was vendored at `simulation/` — a drifted, git-history-only snapshot of the
external repo `MAPF_Simulation`, owning the algorithm (grid, agents, PIBT, task allocation) and
exposed as a Python API the root-level scripts here consumed and wired to whatever DotBot
environment is actually available — the DotBot simulator today, real hardware over LH2/MQTT
tomorrow. `simulation/` was **removed**, `mrta_mode/` was **reconnected** to the real upstream
engine, and on 2026-08-27 the whole family of L0/L1/L2 bridge scripts was **removed** (three kept
as unported reference under `test_scripts/`, the rest deleted): `mrta_mode/` + `mrta_server.py` is
now the only live code path. The DotBot side (`pydotbot`, the controller, the hardware stack) is
**under active restructuring** and evolves independently of this engine question; treat this
bridge layer as a moving target, not a settled one, and re-verify against the code rather than
trusting a stale description — including this one. (This file did exactly that wrong once already,
same day: an "engine reconnection is deliberately deferred" claim here briefly described a
fact-check against a stale second clone of `MAPF_Simulation` as if it were the real one — see the
"Roadmap" section's §0 for the full account of that mistake before trusting any claim about the
upstream engine's shape without re-deriving it from the actual clone in use.)

Where the three-level structure went (pure algorithm → simulator → real hardware):

- **L0** — pure Python, no hardware: `sim_pibt.py`, `sim_many_pibt.py`. `sim_pibt.py` deleted;
  `sim_many_pibt.py` archived in `test_scripts/`. Both still import the removed `simulation/`.
- **L1** — drove the DotBot **simulator** through its REST controller API. `sim_dotbot_pibt.py`
  (fixed-goal batch) archived in `test_scripts/`; `sim_dotbot_mrta.py` (persistent, click-to-target)
  **deleted** — its collaborators survive as `mrta_mode/`, driven now by `mrta_server.py`.
- **L2** — drove **real** DotBots over LH2/MQTT: `real_dotbot_pibt.py`, `real_dotbot_pibt_batch.py`,
  `run_metrics.py`, plus `dotbot.toml` / `mosquitto.conf`. All **deleted**.

Multi-Robot Task Allocation is now `pibt.LifelongGoalOrchestrator` (from the `mapf-simulation`
package, see below) — the online-task-stream/dynamic-priority `FleetManager`/`Task`/
`QueueTaskSource`/`EasiestAllocator` model that used to live in the now-removed
`simulation/mrta/` has no equivalent any more and was not ported: `LifelongGoalOrchestrator` is a
different, simpler design (one mutable target slot per agent, no queue, no cross-agent
eligibility — see `mrta_mode/mrta_session.py`'s `_advance_chain()` for what MRTASession now owns
locally to still support multi-hop waypoint chains). The design roadmap that preceded the removed
implementation (`RoadmapMRTA.md`) was deleted once that code existed; if you need the original
rationale, it is in git history (`git log --all --full-history -- RoadmapMRTA.md`). Same for
`ARCHITECTURE_REVIEW.md` (a one-time comparison against the League of Robot Runners start-kit,
written against the now-removed `simulation/` engine) and the former `CONVENTION.md`/`Roadmap.md`
(merged into "Contributing conventions"/"Roadmap" below, 2026-08-27) — all three are root-level
documentation files this repo no longer keeps separate; find any of them with
`git log --all --full-history -- <filename>`.

## Current known inconsistencies

**The old L0/L1/L2 bridge scripts are gone, as of 2026-08-27.** `sim_pibt.py`,
`real_dotbot_pibt.py`, `real_dotbot_pibt_batch.py`, `sim_dotbot_mrta.py`, `run_metrics.py`,
`generate_comparison_l0_l1_plots.py` and the `dotbot.toml` / `mosquitto.conf` /
`simulator_init_state*.toml` configs were **deleted**; `sim_dotbot_pibt.py`,
`sim_dotbot_right_left.py` and `sim_many_pibt.py` were **moved to `test_scripts/`** unchanged.
The three in `test_scripts/` are still broken — they import `algo`/`mrta` off a
`sys.path.insert(..., "simulation")` that resolves to nothing (`simulation/` was removed, commit
`d4e053b`) — and are kept only to port from: replace
`algo.PIBTCoordinator`/`core.Simulation`/`core.Grid`/`core.Position` with
`pibt.PIBTPlanner`/`core.WorldEngine`/`core.Grid2D`/`core.Coordinates2D`, the shape `mrta_mode/`
already uses. `git log --diff-filter=D --name-only -1 8154abf` lists exactly what was removed.

**`mrta_mode/` is reconnected** to the `mapf-simulation` package (`core` + `pibt`, pip-installed
as a git dependency from `git+https://github.com/RasdaCorentin/MAPF_Simulation.git@develop` — see
`requirements.txt`), not to the removed `simulation/`. `mrta_mode/mrta_session.py`'s `MRTASession`
owns a `core.WorldEngine` wired to `pibt.PIBTPlanner` + `pibt.LifelongGoalOrchestrator` instead of
the old `core.Simulation` + `mrta.FleetManager` + `mrta.QueueTaskSource` + `algo.EasiestAllocator`;
see `diagrammes/sim_dotbot_mrta_ws_target_class_diagram.puml` for the validated design and the
"Roadmap" section's §0, including the stale-clone mistake this correction follows.
**Verified end-to-end, 2026-08-27** (before `sim_dotbot_mrta.py` was deleted, via that CLI's
`--dry-run`; `mrta_server.py --dry-run` is the equivalent check now): against a real
`dotbot run simulator` (5×5 grid, 10 bots), a `PUT .../waypoints` click on one bot was detected
over the WS status channel, translated to a target cell, driven through
`orchestrator.set_target()` → `WorldEngine.advance_time_step()` → `PIBTPlanner`, and the bot
walked the Manhattan path to the target one cell per tick, waiting for real arrival at each step.
That run predated this repo's own venv: it borrowed `core`/`pibt` and `pydotbot` from separate
local checkouts via `PYTHONPATH`.

**The project-local venv now exists (2026-08-27).** `python3.12 -m venv venv && ./venv/bin/pip
install -r requirements.txt` — `mapf-simulation` builds and installs from its git URL (provides
`core`/`pibt`), alongside `pydotbot`, `fastapi`/`uvicorn`, `websockets`, `requests`. On top of
that, `./venv/bin/pip install -e <path-to-PyDotBot>` (branch `feat/mrta-mode-toggle`) replaces the
released `pydotbot` with an editable checkout so the same venv also carries the `/mrta/*` proxy.
`venv/` is gitignored. `./venv/bin/python mrta_server.py` runs with no `PYTHONPATH` trick.

**The MRTA mode button is now wired end to end (2026-08-27), not yet verified live.** All of
the "MRTA mode toggle" section's A/B/C/D shipped: the 3 restartability fixes (C.1 `ControllerStatusListener.stop()`
truly stops + joins the WS thread; C.2 `LivePositionStore.wait_until_all_arrived()` is
interruptible; C.3 an empty waypoint list cancels the agent's target via
`orchestrator.set_target(agent_id, agent.position)`), the HTTP server (`mrta_mode/server.py`'s
`MrtaMode` state machine + `mrta_server.py` CLI), the OFF sequence (D — `MRTASession.halt_all()` +
`WaypointCommandClient.send_stop()`, run in the stop-flag → wake-wait → join → PUT-[] order), and
the PyDotBot `/mrta/*` proxy (on PyDotBot's `feat/mrta-mode-toggle` branch, commit
"dotbot: proxy /mrta/* to the MRTA mode server"). Design:
`diagrammes/mrta_mode_button_architecture.puml` + `diagrammes/mrta_mode_button_state_machine.puml`.
Checked so far (in the new `venv/`): unit-level state-machine walk (off → connecting →
409-on-double-POST → off on connect failure), the proxy returning 502→"MRTA N/A" when nothing is
behind it, and PyDotBot's 79 console-web tests. **Not** checked: the live path ("The MRTA mode
toggle" § "How to verify" step 4 — two bots routed around each other, OFF mid-travel stops them
where they are). Still open: the drive-pad `move_raw`-vs-AUTO conflict from that section's "What
the button changes for everything else" (unaddressed — gate the pad or treat `move_raw` as a
per-bot cancel).

**Driving is per-bot**, unchanged by the button: select one bot, click a point, "Apply waypoints"
→ one `PUT` → `handle_click()` → `set_target()` for that one `agent_id`. To move two bots, do it
twice with two *different* targets; PIBT then routes both around each other. There is no
"select two bots + one point" gesture, and sending two agents to the *same* cell is a collision
`LifelongGoalOrchestrator` does not arbitrate (left to the caller — see the class-diagram note).

*(If this section goes stale — scripts fixed, the button verified or newly broken — update it in
the same commit that changes the fact: an agent map that lies is worse than no map.)*

## Layout

```
.
├── AGENT.md                    — this file (project map + install/reuse guide + conventions + roadmap)
├── CLAUDE.md                   — pointer that imports AGENT.md
├── README.md                   — human-facing usage guide for MRTA mode
├── requirements.txt            — pydotbot[calibrate], requests, websockets, mapf-simulation
├── mkdocs.yml                  — config for the docs/ site
├── mrta_server.py              — the live entry point: CLI that serves mrta_mode's MrtaMode
│                                  behind the console MRTA toggle (GET /status, POST /mode)
├── mrta_mode/                  — the MRTA-mode classes, one concrete class or DTO per file
│                                  (reconnected to mapf-simulation, see above).
│                                  mrta_mode/server.py = the console-toggle HTTP server (MrtaMode)
├── diagrammes/                 — PlantUML design diagrams (has its own AGENT.md)
├── docs/                       — MkDocs site: level-0/1/2 guides, installation, contributing
│                                  (partly stale — still describes the removed bridge scripts)
├── log/                        — experiment outputs (raw_logs/, *_per_run.csv, *_summary.csv)
└── test_scripts/               — sim_dotbot_pibt.py, sim_dotbot_right_left.py, sim_many_pibt.py:
                                   archived, still import the removed simulation/, kept to port from
```

Before the `simulation/` removal, that package was added to `sys.path` by each top-level script at
import time (`sys.path.insert(0, ".../simulation")`) — no install needed, no package boundary to
cross other than the Python import itself. The three archived scripts in `test_scripts/` still
carry that `sys.path.insert()` call, now resolving to nothing. `mrta_mode/` used to do the same
once, in its own `__init__.py`; since reconnection it has no `sys.path` manipulation at all —
`core`/`pibt` come from the pip-installed `mapf-simulation` package (`requirements.txt`), a real
install rather than a path trick. The archived scripts have not been ported to this pattern — see
"Current known inconsistencies".

## The bridge pattern (removed L1/L2 scripts)

Historical: the *shape* the removed `sim_dotbot_pibt.py` / `real_dotbot_pibt.py` /
`real_dotbot_pibt_batch.py` shared (`sim_dotbot_pibt.py` survives in `test_scripts/`; the other
two were deleted). Kept here because it is the pattern to reach for if the fixed-goal batch
driver is ever rebuilt on the `mapf-simulation` engine. All three shared the same three parts:

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

### `mrta_mode/` — a different pattern

Timeline: 2026-07-23 as `sim_dotbot_mrta.py`; split into `mrta_mode/` 2026-08-26; reconnected to
the real upstream engine 2026-08-27; CLI replaced by `mrta_server.py` 2026-08-27.

Not a fixed-goal batch run: every bot starts **parked** (no goals) and the session runs
**indefinitely**, waiting for an operator to drive it. The entry point is `mrta_server.py` (the
console-toggle HTTP server); the deleted `sim_dotbot_mrta.py` was the earlier Ctrl+C CLI over the
same collaborators. Those collaborators live in `mrta_mode/`, one concrete class or DTO per file,
per `diagrammes/sim_dotbot_mrta_ws_target_class_diagram.puml`:

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
  receives — `dotbot/controller.py:405-567` in an up-to-date PyDotBot checkout). The old
  `WaypointWatcher` kept only the waypoints half and
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
`DotBots/PyDotBot` (a separate repo, not versioned here) — if that project changes its
notification schema, `ControllerStatusListener._handle_raw()` is what needs updating.

### Grid ↔ mm mapping

```
cell (gx, gy)  →  centre mm = (gx*cell_mm + cell_mm//2, gy*cell_mm + cell_mm//2)
pos (x, y) mm  →  cell      = (int(x/cell_mm), int(y/cell_mm))
```

Default: `--map-cells 5` on a 2000×2000 mm map → `cell_mm = 400`, 5×5 grid.
Alternative: `--map-cells 8` → `cell_mm = 250`, 8×8 grid (seed the simulator with a matching
init-state TOML — this repo no longer ships one).

### REST API consumed (controller side)

```
GET  /controller/dotbots                     → list of bots (filter: lh2_position present, status != 2)
GET  /controller/map_size                    → { width, height } in mm
PUT  /controller/dotbots/{addr}/0/waypoints  → { threshold, waypoints: [{x, y}] }
WS   /controller/ws/status                   → broadcasts { cmd, data } on every state change
                                                (MRTA mode only, cmd 2 = UPDATE;
                                                 carries both lh2_waypoints and lh2_position)
```

This is the seam that changes as the DotBot environment is restructured — if the controller API
shape changes, what needs updating in the live path is `mrta_mode/grid_state_manager.py`'s
`GridStateManager`, `mrta_mode/waypoint_command_client.py`'s `WaypointCommandClient.send()`, and
`mrta_mode/controller_status_listener.py`'s `ControllerStatusListener._handle_raw()` for the WS
shape specifically. The archived `test_scripts/` copies each still duplicate their own inline
`GridStateManager` / `send_waypoints()`.

### Configuration

`mrta_server.py` takes all its configuration as CLI flags (see `--help`); there is no config
file. The controller side needs `--mrta-url http://localhost:8002` (or `[run.controller] mrta_url`,
or `DOTBOT_MRTA_URL`) so its `/mrta/*` proxy points at this server. The removed L2 scripts used a
`dotbot.toml` (MQTT broker, swarm id) and `DOTBOT_MQTT_USER` / `DOTBOT_MQTT_PASS` env vars — gone
with them; recover from git history if the real-hardware path is rebuilt.

## The MRTA mode toggle (console button)

Folded in from the former root-level `Button.md` (2026-08-27, per the rule that root
documentation in this repo lives in `AGENT.md` or `README.md` — nowhere else). Code comments in
`mrta_mode/*.py` and the `diagrammes/mrta_mode_button_*.puml` files still cite this as `Button.md`
and its four parts as **A/B/C/D**; those labels are kept below so the references resolve.

An ON/OFF pill in the DotBot web console that turns this repo's MRTA mode on and off. With no
server behind the proxy, `/mrta/status` returns 502/404, the console reads that as `unavailable`,
and the pill renders greyed out as `MRTA N/A` — the intended resting state, not a failure: the
console stays fully usable with no MRTA in the picture.

**Status (2026-08-27): A, B, C, D all implemented; the live end-to-end check is still pending.**

### The contract

Two routes, same-origin under `/mrta` (PyDotBot's proxy strips the prefix, so this server sees
`/status` and `/mode`):

- **`GET /mrta/status`** → `{ "state", "bots", "detail" }`.
  `state` is `off` | `connecting` | `on` | `stopping`. `bots` is the fleet size the running
  session snapshotted (`null` when not running). `detail` is one short tooltip line. A fifth
  value, `unavailable`, is **inferred by the console and must never be sent** — 404, 502 and an
  unreachable host all collapse into it.
- **`POST /mrta/mode`** `{ "on": bool }` → the same status object, `202`, returning the
  *transition* state (`connecting` / `stopping`), not the settled one. Refuse with a non-2xx
  while already transitioning — the console treats a refusal as "ask again next poll", which is
  what stops a double-click from starting a second session on the same bots.

The console polls status every 1.5 s. State lives in the MRTA process, never the browser: two
consoles on one testbed must agree, and closing one must change nothing.

### What was built (A–D, all shipped 2026-08-27)

- **A — the `/mrta/*` proxy in PyDotBot.** `mrta_url` (default `http://localhost:8002`,
  `--mrta-url` / `[run.controller] mrta_url` / `DOTBOT_MRTA_URL`) threaded through the controller;
  `mrta_proxy` in `dotbot/server.py` mirrors the existing `swarmit_proxy` minus the SSE/streaming
  machinery. On PyDotBot's `feat/mrta-mode-toggle` branch.
  This breaks the "no changes to the PyDotBot controller" invariant the CLI held — the smallest
  possible break: the controller learns one URL, nothing about MRTA.
- **B — the MRTA HTTP server, here.** `mrta_mode/server.py`: `MrtaMode` owns the state machine +
  session lifecycle (process-global under a `threading.Lock`); `build_app()` is a small FastAPI
  app; `serve()` runs it on uvicorn. `connect()` and the `tick()` loop run on a worker thread,
  never the serving loop. ON builds a *fresh* `MRTASession` (the fleet is snapshotted at
  `connect()`), so OFF/ON is how you pick up bots that joined late — there is no resume.
  `mrta_server.py` is the CLI. FastAPI/uvicorn are imported lazily so `mrta_mode/__init__.py`
  still imports without them.
- **C — three fixes that make `MRTASession` genuinely restartable** (a CLI starts one session; a
  toggle starts many):
  - **C.1** `ControllerStatusListener.stop()` truly stops the WS listener — it owns an explicit
    event loop, `stop()` races `recv()` against a stop `Event` and joins the thread (5 s). No
    more leaked thread + socket per OFF/ON.
  - **C.2** `LivePositionStore.wait_until_all_arrived()` is interruptible — `interrupt()` sets a
    flag and `notify_all()`s the `Condition` the wait parks on; OFF no longer takes ~4.3 s to
    begin.
  - **C.3** an empty waypoint list cancels instead of being ignored — `_handle_raw()` forwards
    `lh2_waypoints == []`, and `handle_click()` treats an empty payload as the operator's "Stop
    nav": `set_target(agent_id, agent.position)` + clear the pending chain. MRTA never sends an
    empty list, so an empty list is always the operator.
- **D — what OFF means: OFF stops the bots**, it does not let them coast to their last commanded
  cell. `MrtaMode._stop_session()` runs a load-bearing order: **set stop flag → wake the arrival
  wait (`session.stop()`) → join the tick thread → `PUT []` to every address in the snapshot**
  (`MRTASession.halt_all()` + `WaypointCommandClient.send_stop()`). Clearing waypoints before the
  join lets an in-flight parallel send re-arm the bots for one more cell. Clear exactly
  `session.addresses` — a bot that joined after `connect()` was never driven by MRTA.

### What the button changes for everything else

While MRTA is on, a map click means "PIBT will route you there", not "drive straight there" —
the one thing an operator must know; the tooltip says so. Two consequences, neither solved:

- **Still open — the drive pad.** It sends `move_raw`, which puts the firmware back in MANUAL
  while MRTA still believes it drives in AUTO; `agent.position` then diverges and PIBT plans on a
  stale world. Fix: gate the pad while MRTA is on, or treat a `move_raw` on an MRTA bot as a
  per-bot cancel.
- Waypoint *missions* (a queued chain) already work — the translator turns the chain into one
  target per cell via `MRTASession`'s `_pending_chain`.

### How to verify

1. `npm --prefix dotbot/console-web run typecheck && … run lint && … test` — 79 tests, 13 on the
   toggle's state machine.
2. `curl -o /dev/null -w '%{http_code}\n' localhost:8000/mrta/status` with nothing behind it →
   502/404 → pill reads `MRTA N/A`.
3. With A + B up: start `mrta_server.py`, reload the console, the pill reads `OFF`; toggle it and
   watch it sit on `connecting` for as long as `connect()` takes, then settle on `ON` with the
   bot count in the tooltip.
4. **Not yet done, and no unit test covers it:** with MRTA `ON`, drive two bots at each other
   from the console, confirm they route around one another; then hit OFF mid-travel and confirm
   they stop where they are rather than finishing their segment.

## Rules and invariants

- **A folder with its own `AGENT.md` must have it read before working inside it.** Any folder in
  this repo may grow its own `AGENT.md`; check for one (`ls <folder>/AGENT.md`) before making
  changes inside a folder you have not worked in during this session, and do not assume this root
  file already covers it — a folder-local guide holds the detail this one deliberately does not
  repeat. (`simulation/`'s own multi-level version of this rule — `core/AGENT.md`, `algo/AGENT.md`,
  `mrta/AGENT.md`, etc. — no longer applies now that `simulation/` is removed; it is the reference
  example if that package (or its replacement) comes back.)
- **1 action = 1 commit**: each logically distinct change (fix, migration, doc batch) is its own
  commit — see "Contributing conventions" below.
- **No push without explicit user request** in the same message.
- **Class-diagram-based development**: any change to the PIBT/MRTA engine's design should be shown
  and validated through a class diagram before code moves (the rule `simulation/AGENT.md` used to
  state for its own package) — still the intended practice, just without a live target to point at
  until reconnection is scoped; see the "Roadmap" section's §0.
- **The sync barrier (`wait_until_all_arrived`) is load-bearing**: it is what gives PIBT its
  collision-avoidance guarantee on async, real hardware. Removing it or racing ahead of it can
  make two bots collide — it is not an optimisation to cut for latency.
- **`GridStateManager.resolve_conflicts()` is what keeps two bots from aliasing to the same
  cell** when LH2 noise puts them close together — do not bypass it when reading bot state.

## Contributing conventions

Merged in from the former `CONVENTION.md` (2026-08-27, folded here per the rule that root-level
documentation in this repo lives in `AGENT.md` or `README.md` — nowhere else).
Folder and file names, code, docstrings, comments, commits, branches, and issues are all in
**English**.

### Branch naming

`prefix/suffix`, prefix in English:

- **Main branch**: `main`
- **Development branch**: `develop`
- **Feature branches**: `feat/{feature-name}`
- **Bug-fix branches**: `fix/{fix-name}`
- **Documentation branches**: `docs/{topic}`
- **Refactor branches**: `refactor/{topic}`
- **Project-management branches**: `pm/{name}`

### Commit rules

[Conventional Commits](https://www.conventionalcommits.org), English, imperative mood:

```
type(scope)!: subject
```

| Type       | Purpose                                             |
|:-----------|:----------------------------------------------------|
| `feat`     | a new feature                                       |
| `fix`      | a bug fix                                            |
| `refactor` | a change that neither fixes a bug nor adds a feature |
| `docs`     | documentation only                                  |
| `test`     | adding or fixing tests                              |
| `chore`    | tooling, dependencies, housekeeping                 |

`scope` (optional) is the affected area (`core`, `mrta_mode`, `mrta_mode/mrta_session`...); `!`
(optional) marks a breaking change, e.g. `refactor(core)!: ...`. **One logical change = one
commit** — do not bundle unrelated changes; split a distinct fix, rename, feature, or
documentation batch into its own commit with a clear message. A commit body (after a blank line)
may explain the *why* and any verification performed.

```
feat(core): add scale attribute to WorldEntity
fix: repair main.py import broken by the core subpackage split
docs: rewrite README for the current architecture
refactor(core)!: remove Objective entity
```

### Issue rules

Issues are written in English, each with an assignee and, when possible, a due date.

| Description            | Label               |
|:-----------------------|:--------------------|
| To do                  | `To Do`             |
| In progress            | `On-going`          |
| Bug fix                | `type: bug`         |
| Project management     | `type: PM`          |
| Feature addition       | `type: feature`     |
| Low priority           | `priority: low`     |
| Medium priority        | `priority: medium`  |
| High priority          | `priority: high`    |
| Critical priority      | `priority: critical`|

### Versioning

`Major.Minor.Fix`, starting at 0; trailing zeros may be omitted (`0.1.0` → `0.1`, `1.0.0` → `1`).
Each merge into `main` marks a new version and must be tagged; ideally the tag carries release
notes describing the changes since the previous version.

### Merge requests

Merge requests into `develop` and `main` must be approved by the majority of the development
team. Any required correction must be written down in the review comments for proper project
tracking.

## Roadmap

Merged in from the former `Roadmap.md` (2026-08-27, same reason as "Contributing conventions"
above). Forward-looking — what's next, not what already exists; for the current state of the code
and why the two attempts past `21a4580` were abandoned, see "What this project is" and "Current
known inconsistencies" above. Unrelated to the old `RoadmapMRTA.md` (removed once
`simulation/mrta/` was implemented, see "What this project is") — that one covered MRTA's own
design before it existed as code; this one covers what comes after the bridge layer that drives it.

**Goal**: manage on the order of **1000 DotBots without collision**, to simulate realistic
logistics environments (warehouse/depot-scale intralogistics), not just the current 2–8-bot
desk-scale experiments. Every item below is justified against that target, not against code taste
alone — a script that is merely "long" at 5 bots is a design that actively can't be reasoned
about, tested, or scaled at 1000.

### 0. Reconnect to the external MAPF_Simulation engine (DONE for `mrta_mode/`, 2026-08-27 — see the two false starts this section went through first)

`simulation/` here used to be a vendored snapshot of `MAPF_Simulation`
(`git@github.com:RasdaCorentin/MAPF_Simulation`), not a submodule or an installed package — copied
in once and evolved independently on both sides since. It has been removed
(dotbot-logistics `d4e053b`), and `mrta_mode/`/`sim_dotbot_mrta.py` are now reconnected to the
real upstream package instead of maintaining a second, drifting copy. Getting here took two wrong
turns, both worth keeping on record since the same mistake (trusting a description of the upstream
repo instead of the actual checkout in hand) produced both, hours apart:

**Wrong turn 1** (this section's original text): claimed upstream had done three `refactor!`
removals (`client/`+`report/`, `algo/`, `mrta/` all gone) and landed a new `pibt/` +
`AssignmentManifest`/`StepOutcome`-based package plus an `export/` CSV package. Never checked
against any real checkout.

**Wrong turn 2** (this section's text for most of 2026-08-27, after the first correction): checked
`/home/dok/MAPF_Simulation` (branch `MRTA`), found `algo/`, `client/`, `mrta/`, `report/` still
there with the old class names, no `pibt/`, no `export/` — and concluded wrong turn 1 was fiction.
That checkout was real, but **stale**: a second clone of the same remote, 78 commits behind. It was
never the clone `~/3A/projets/MAPF_Simulation` (this section's own path, from the start) actually
names — checking a same-named directory instead of the one referenced is not "re-verifying against
the code," it just relocates the trust problem.

**What's actually true**, confirmed against `~/3A/projets/MAPF_Simulation` (branch `develop`, tip
`736c757 "chore: expose core and pibt as an installable package"`, the clone the user actively
develops in): wrong turn 1 was closer to right than wrong turn 2 gave it credit for. `core/` +
`pibt/` + `export/` exist, no `algo/`/`client/`/`mrta/`/`report/`; `core/` is still built around
`Objective` (not the `Zone` this repo's old vendored copy had moved to); `pibt/` has `PIBTPlanner`
(`AssignmentManifest`/`StepOutcome`-based, confirmed) and `LifelongGoalOrchestrator` — written, per
its own docstring, *specifically* for `sim_dotbot_mrta.py`'s click-to-target use case
(`set_target(agent_id, position)`, one mutable slot per agent, no shared pool). A root
`pyproject.toml` (`name = "mapf-simulation"`, `include = ["core*", "pibt*"]`) makes it
pip-installable as a git dependency — `requirements.txt` now pulls it from
`git+https://github.com/RasdaCorentin/MAPF_Simulation.git@develop`.

`FleetManager`, `QueueTaskSource`, `Task`, `EasiestAllocator` have no home anywhere any more,
upstream or local — not ported, not needed. `LifelongGoalOrchestrator` replaces the whole
allocation layer with a materially simpler design (no task objects, no eligibility classes, no
queue); the one gap it leaves that `mrta_mode/mrta_session.py`'s `MRTASession` now closes locally
is multi-hop waypoint chains (a `_pending_chain` queue per agent, since the orchestrator's target
slot holds only one position). See
`diagrammes/sim_dotbot_mrta_ws_target_class_diagram.puml` for the validated design and "Current
known inconsistencies" above for exactly what shipped.

**Not done**: the other five broken bridge scripts (`sim_pibt.py`, `sim_many_pibt.py`,
`sim_dotbot_pibt.py`, `real_dotbot_pibt.py`, `real_dotbot_pibt_batch.py`) and
`sim_dotbot_right_left.py` were not part of this port — same `algo.PIBTCoordinator` →
`pibt.PIBTPlanner` / `core.Simulation` → `core.WorldEngine` swap would apply, just not done yet.
Verified end-to-end since (see "Current known inconsistencies" above) against a live simulator —
that verification happened after this section was first written, when `mapf-simulation`'s pip
install was still in progress upstream and this section's own claim of "not yet verified" was
still accurate.

### 1. Decompose the bridge scripts before scaling them

*Partly done.* `sim_dotbot_mrta.py` (668 lines) was split into `mrta_mode/` (2026-08-26, one class
per file) and then deleted (2026-08-27) — so the concern-separation this item asked for exists for
the live path. What remains open is everything below about scaling that decomposition to 1000 bots,
and the real-hardware modules (LED status, resync) that never got their own home. The historical
framing: `sim_dotbot_mrta.py` and its abandoned `real_dotbot_mrta.py` fork (958 lines) mixed six
orthogonal concerns — grid-state acquisition, MRTA planning, manual-click detection, navigation
primitives, the step loop, and CLI wiring — as flat private helpers with no module boundary:

- **`GridStateManager`** does one unbatched `GET /controller/dotbots` per poll and an O(n²)
  collision-nudge pass (`resolve_conflicts()`) — fine at single digits of bots, unknown at 1000.
  Extracting it to its own module is the prerequisite for profiling and optimizing that path in
  isolation, instead of inside a 668-line file where nothing else can be held constant.
- **Click detection (`CommandedStore`/`WaypointWatcher`)** is one background thread per script
  instance today; whatever click-routing model works for 1000 concurrently-driven bots (still one
  WS listener? sharded? per-zone operators?) needs a real module to be designed against, with an
  explicit, written cross-thread contract — see the halt-reflex postmortem (git history,
  `git log --all --grep=halt-reflex`) for what happens when that contract is implicit instead: a
  race invisible until live-hardware testing.
- **LED status and hardware resync** (from the discarded `real_dotbot_mrta.py`) are real-hardware
  concerns that must not re-inflate `sim_dotbot_mrta.py` the way they inflated its fork; they need
  their own modules from the start of the next attempt, not bolted on after the fact.

**Target layout** (composition root stays a minimal script: build the simulation, connect to the
DotBot controller, bridge the two):

```
bridge/
├── grid_state.py    — GridStateManager, mm↔cell helpers, retry-with-backoff
├── navigation.py    — send_waypoints, parallel send, wait_until_all_arrived
├── click_watch.py   — CommandedStore, WaypointWatcher, _reconcile_from_rest
├── led_status.py    — BotStatus, LedManager (real-hardware only)
└── resync.py        — resync_simulation (real-hardware only)
```

with `sim_dotbot_mrta.py` / `real_dotbot_mrta.py` reduced to `build_mrta()`, a thin
`run_mrta_live()` orchestrator, and `main()`. This also resolves, rather than trades off, the
duplication "The bridge pattern" section above currently accepts as a cost: `GridStateManager`
and `send_waypoints` are copy-pasted across four scripts today only because there is no shared
module to import instead.

**Once decomposed:** re-attempt the halt-reflex fix (properly synchronized `commanded.set()`
against the WS-echo read, this time against a module that states the invariant) and the
real-hardware LED/resync port, each as its own module from day one instead of inline growth.

### 2. Give MRTA its own place in the docs site

Recovered from an orphaned planning note (`docs/assets/docs_structure.puml`, on the branch reset
away with the rest of the abandoned work): the current mkdocs nav has no dedicated top-level entry
for MRTA — it's split across "Level 1" (as a mode of `sim_dotbot_mrta.py`) and "Contributing >
Architecture" (Detail D, one sub-section among core/PIBT/mm↔cell). As MRTA-driven simulation
becomes the actual product (1000-bot logistics scenarios, not one-off PIBT demos), that split
under-represents it. Planned nav shape:

```
DotBot Logistics docs
├── Home
├── Installation
├── Level 0 — Run a PIBT
├── Level 1 — Fake bots
│   ├── sim_dotbot_pibt.py (fixed-goal batch)
│   └── sim_dotbot_mrta.py (click-to-target)
├── Level 2 — Real bots
├── MRTA                          ← new top-level entry, not a Level-1 subsection
│   ├── Task allocation model (pibt.LifelongGoalOrchestrator, set_target())
│   └── Bridge scripts (sim_dotbot_mrta.py / real_dotbot_mrta.py once ported)
├── Contributing
│   ├── Architecture (mm↔cell, core engine, PIBT — MRTA detail moves out, see above)
│   └── Improvement                ← this roadmap, or a summary of it
└── Appendix
```

This is a nav restructuring, not new technical content — the underlying architecture pages
(`docs/contributing/architecture.md` Detail B/C/D, `docs/level-1-simulator.md`,
`docs/index.md`) were already written accurately against the current code on the branch that got
reset; they need re-adding (cherry-picked, not re-derived) before this restructuring. Their MRTA
allocation-model content will need a rewrite either way: it described `simulation/mrta/`'s
`FleetManager`/`Task` model, which no longer exists anywhere (`simulation/` removed, not ported —
§0), replaced by `pibt.LifelongGoalOrchestrator.set_target()`. `sim_dotbot_mrta.py`'s
click-to-target *mode* still describes the current behaviour, just not its old implementation.

### 3. Open questions for the 1000-bot target

Not yet scoped as concrete tasks — flagged here so the next planning pass starts from these
instead of rediscovering them:

- Does `wait_until_all_arrived()`'s synchronous, all-bots barrier (load-bearing for PIBT's
  collision guarantee, see "Rules and invariants" above) remain viable at 1000 bots, or does it
  need spatial partitioning (bots far apart don't need to wait on each other)?
- `GridStateManager.resolve_conflicts()`'s collision-nudge pass and the REST poll it runs on: what
  is its actual complexity, and at what bot count does it stop being negligible?
- Click-driven MRTA assumes a human operator per click; 1000 bots need either a much higher
  operator-to-bot ratio (batch/zone task assignment) or a non-manual, automated way to call
  `set_target()` — `LifelongGoalOrchestrator` itself has no opinion on where targets come from, so
  this is an `mrta_mode`/upstream-`pibt` question, not a bridge-layer one, but the bridge's
  click-watch module (§1) is where any batch-assignment UI would plug in.
