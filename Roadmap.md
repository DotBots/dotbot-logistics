# Roadmap.md

> Forward-looking plan for `dotbot-logistics` — what's next, not what already exists. For the
> current state of the code and why the two attempts past `21a4580` were abandoned, see `AGENT.md`.
> This file is unrelated to the old `RoadmapMRTA.md` (removed once `simulation/mrta/` was
> implemented, see `AGENT.md`'s "What this project is" section) — that one covered MRTA's own
> design before it existed as code; this one covers what comes after the bridge layer that drives it.

## Goal

Manage on the order of **1000 DotBots without collision**, to simulate realistic logistics
environments (warehouse/depot-scale intralogistics), not just the current 2–8-bot desk-scale
experiments. Every item below is justified against that target, not against code taste alone —
a script that is merely "long" at 5 bots is a design that actively can't be reasoned about,
tested, or scaled at 1000.

## 0. Reconnect to the external MAPF_Simulation engine (DONE for mrta_mode/, 2026-08-27 — see the two false starts this section went through first)

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
`diagrammes/sim_dotbot_mrta_ws_target_class_diagram.puml` for the validated design and
`AGENT.md`'s "Current known inconsistencies" for exactly what shipped.

**Not done**: the other five broken bridge scripts (`sim_pibt.py`, `sim_many_pibt.py`,
`sim_dotbot_pibt.py`, `real_dotbot_pibt.py`, `real_dotbot_pibt_batch.py`) and
`sim_dotbot_right_left.py` were not part of this port — same `algo.PIBTCoordinator` →
`pibt.PIBTPlanner` / `core.Simulation` → `core.WorldEngine` swap would apply, just not done yet.
Also not verified: `mapf-simulation`'s pip install was still in progress upstream at the time of
this port, so the `mrta_mode` reconnection was checked by reading the real `core`/`pibt` source
and syntax-compiling, not by running it end-to-end against a live DotBot simulator.

## 1. Decompose the bridge scripts before scaling them

`sim_dotbot_mrta.py` (668 lines, see `AGENT.md`) and its abandoned `real_dotbot_mrta.py` fork
(958 lines) mix six orthogonal concerns — grid-state acquisition, MRTA planning, manual-click
detection, navigation primitives, the step loop, and CLI wiring — as flat, private helpers with no
module boundary between them. This was tolerable at desk scale; it is not a base to scale from:

- **`GridStateManager`** does one unbatched `GET /controller/dotbots` per poll and an O(n²)
  collision-nudge pass (`resolve_conflicts()`) — fine at single digits of bots, unknown at 1000.
  Extracting it to its own module is the prerequisite for profiling and optimizing that path in
  isolation, instead of inside a 668-line file where nothing else can be held constant.
- **Click detection (`CommandedStore`/`WaypointWatcher`)** is one background thread per script
  instance today; whatever click-routing model works for 1000 concurrently-driven bots (still one
  WS listener? sharded? per-zone operators?) needs a real module to be designed against, with an
  explicit, written cross-thread contract — see `AGENT.md`'s halt-reflex postmortem for what
  happens when that contract is implicit instead: a race invisible until live-hardware testing.
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
duplication `AGENT.md`'s "bridge pattern" section currently accepts as a cost: `GridStateManager`
and `send_waypoints` are copy-pasted across four scripts today only because there is no shared
module to import instead.

**Once decomposed:** re-attempt the halt-reflex fix (properly synchronized `commanded.set()`
against the WS-echo read, this time against a module that states the invariant) and the
real-hardware LED/resync port, each as its own module from day one instead of inline growth.

## 2. Give MRTA its own place in the docs site

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

## 3. Open questions for the 1000-bot target

Not yet scoped as concrete tasks — flagged here so the next planning pass starts from these instead
of rediscovering them:

- Does `wait_until_all_arrived()`'s synchronous, all-bots barrier (load-bearing for PIBT's
  collision guarantee, see `AGENT.md`'s "Rules and invariants") remain viable at 1000 bots, or does
  it need spatial partitioning (bots far apart don't need to wait on each other)?
- `GridStateManager.resolve_conflicts()`'s collision-nudge pass and the REST poll it runs on: what
  is its actual complexity, and at what bot count does it stop being negligible?
- Click-driven MRTA assumes a human operator per click; 1000 bots need either a much higher
  operator-to-bot ratio (batch/zone task assignment) or a non-manual, automated way to call
  `set_target()` — `LifelongGoalOrchestrator` itself has no opinion on where targets come from, so
  this is an `mrta_mode`/upstream-`pibt` question, not a bridge-layer one, but the bridge's
  click-watch module (§1) is where any batch-assignment UI would plug in.
