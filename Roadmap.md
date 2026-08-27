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

## 0. Reconnect to the external MAPF_Simulation engine (blocking prerequisite — premise re-checked 2026-08-27, was stale)

`simulation/` here is a vendored snapshot of `~/3A/projets/MAPF_Simulation`
(`git@github.com:RasdaCorentin/MAPF_Simulation`), not a submodule or an installed package — it was
copied in once and has evolved independently on both sides since. The eventual goal is still to
reconnect this bridge to the upstream repo instead of maintaining a second, drifting copy — but the
shape that reconnection takes, described below until 2026-08-27, was never actually checked against
the upstream checkout and turned out to be wrong.

**What this section used to claim, and what is actually there.** It described upstream as having
done three deliberate `refactor!` removals (`client/`+`report/`, `algo/`, `mrta/` all gone) and
landed a new `pibt/` package (`PIBTPlanner` fed via `AssignmentManifest`/`StepOutcome`) plus an
`export/` CSV package, with `core/` still built around `Objective`. None of that holds. As of
2026-08-27, `/home/dok/MAPF_Simulation` (branch `MRTA` — same branch name as this repo, not a
coincidence) still has `algo/`, `client/`, `mrta/`, `report/`, with the **same class names** this
repo's vendored copy uses (`PIBTCoordinator`, `DispatchIntent`, `FleetManager`, `QueueTaskSource`,
`EasiestAllocator`, ...). There is no `pibt/` package anywhere in that checkout, no `export/`, no
`LifelongGoalOrchestrator`, no `AssignmentManifest`. Upstream instead **added** things since the
snapshot — `LaCAMCoordinator`, `PIBTPlusCoordinator`, `pibt_core.py`, `push_and_swap.py`, LaCAM/
PIBT+ benchmark scripts — and modified `pibt_coordinator.py`, `client/control/{controller,factory,
config,driver}.py`, `report/collector.py`, the pygame frontend, `main.py`, without changing the
package shape. It is not pip-installable and not on `sys.path` — no packaging exists on either
side yet.

Consequence: the `TaskManifestAdapter`/`LifelongGoalOrchestrator` design sketched in
`diagrammes/sim_dotbot_mrta_ws_target_class_diagram.puml`'s `mrta_mode (local)` package targets an
architecture that does not exist upstream — that diagram's second target is invalidated, not just
outdated (see the note added to the `.puml` itself). `FleetManager`, `QueueTaskSource`, `Task`,
`EasiestAllocator` do **not** need a local home inside `mrta_mode/`: they are still importable from
upstream `algo`/`mrta`, same names, same rough shape as `simulation/`'s copy.

What a real reconnection would actually require, once undertaken: diffing the drifted files
(`pibt_coordinator.py`, `controller.py`, `factory.py`, `config.py`, `driver.py`, `collector.py`,
the frontends) file-by-file against the vendored copy to see what API surface changed underneath
the unchanged names, deciding how this repo depends on the upstream checkout (path insert against
a local clone, editable install, git submodule — none set up today), and only then retiring
`simulation/`. **Deliberately not started** — see the 2026-08-27 conversation that caught this
premise before any of §1 or the rest of this file was built on top of it; the corrected version of
this section, if reconnection is picked back up, needs its own re-verification pass rather than
trusting this fix to still hold.

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
│   ├── Task allocation model (FleetManager, Task, EasiestAllocator)
│   └── Bridge scripts (sim_dotbot_mrta.py / real_dotbot_mrta.py once ported)
├── Contributing
│   ├── Architecture (mm↔cell, core engine, PIBT — MRTA detail moves out, see above)
│   └── Improvement                ← this roadmap, or a summary of it
└── Appendix
```

This is a nav restructuring, not new technical content — the underlying architecture pages
(`docs/contributing/architecture.md` Detail B/C/D, `docs/level-1-simulator.md`,
`docs/index.md`) were already written accurately against the current code on the branch that got
reset; they need re-adding (cherry-picked, not re-derived) before this restructuring, since they
describe things that still exist (`simulation/mrta/`, `sim_dotbot_mrta.py`'s click-to-target mode)
independently of the abandoned real-hardware work.

## 3. Open questions for the 1000-bot target

Not yet scoped as concrete tasks — flagged here so the next planning pass starts from these instead
of rediscovering them:

- Does `wait_until_all_arrived()`'s synchronous, all-bots barrier (load-bearing for PIBT's
  collision guarantee, see `AGENT.md`'s "Rules and invariants") remain viable at 1000 bots, or does
  it need spatial partitioning (bots far apart don't need to wait on each other)?
- `GridStateManager.resolve_conflicts()`'s collision-nudge pass and the REST poll it runs on: what
  is its actual complexity, and at what bot count does it stop being negligible?
- Click-driven MRTA assumes a human operator per click; 1000 bots need either a much higher
  operator-to-bot ratio (batch/zone task assignment) or a non-manual task source
  (`QueueTaskSource`'s automated sibling) — this is a `simulation/mrta/` question, not a bridge-layer
  one, but the bridge's click-watch module (§1) is where any batch-assignment UI would plug in.
