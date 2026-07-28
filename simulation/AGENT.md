# AGENT.md

> **This is the project map for coding agents. Start here, then read the guide for the package
> you are about to touch. Do not re-explore the tree to answer structural questions.**

**Two companion files are binding and are *not* reproduced here:**
- **`CONVENTION.md`** — repository layout, branch naming, and Conventional Commits. Every commit,
  file name and new file must follow it. Read it before your first commit.
- **`README.md` / `GUIDE.md`** — human-facing overview and guided tour.

The reference for architecture is the class diagram: when this file, the code and the diagram
disagree, **the diagram arbitrates** — see *Rules and invariants*. It and the two object diagrams
are imported below so they are always in context; read them, do not re-derive them.

@diagrammes/_model.iuml

@diagrammes/Object_Diagram/object_diag_mrta.puml

@diagrammes/Object_Diagram/object_diag_static.puml

---

## Package guides — where the class-by-class detail lives

This file holds only what is **cross-cutting**: how to run the thing, the layout, the dependency
direction, the rules and the invariants. Everything about a specific class lives next to it.

| Guide | Covers |
|---|---|
| [`core/AGENT.md`](core/AGENT.md) | `Position`, `WorldEntity`, `Zone`, `Agent`, `Grid`, `PlanResult`, `DispatchIntent`, `Coordinator`, `Dispatcher`, `Simulation` — and the tick |
| [`algo/AGENT.md`](algo/AGENT.md) | PIBT (coordinator, reservations, priorities), random walk, the allocators, how to add a `Coordinator` |
| [`mrta/AGENT.md`](mrta/AGENT.md) | `Task` lifecycle, task sources, `FleetManager`, eligibility, the watchdog, domain vocabulary |
| [`client/AGENT.md`](client/AGENT.md) | `ScenarioConfig`, `build`, `SimulationDriver`, `SimulationController`, the frozen views, the frontends |
| [`report/AGENT.md`](report/AGENT.md) | `RunRecord` (the schema), sinks, `RunCollector` |

**Working on one package?** Root + that guide is enough. Changing a *seam* between two — an ABC,
a DTO, an import direction — read both guides and the rules below.

---

## Running the simulation

```bash
python main.py                                  # 15x15, 20 agents, PIBT + MRTA, interactive window
python main.py --tasks random                   # same, self-generating background work
python main.py --zones                          # same, with the three operational zones drawn
python main.py --algo random --mode static      # the historical random-walk demo
python demo_pibt.py                             # legacy PIBT demo (5x5, keyboard navigation)
python demo_pibt.py -d                          # same, debug mode: terminal print, zero pygame
python sim_many_pibt.py --seeds 2               # headless L0 benchmark sweep -> sim_results.csv
python sim_many_mrta.py --seeds 2               # allocation sweep -> mrta_results.csv
```

**Run logging is opt-in**: `--log runs.csv` appends one summary row per run (`.csv` only for now,
any other suffix is refused), plus a per-task event log at `runs.events.csv` and a per-step,
per-agent trace at `runs.trace.csv` — the detail the summary row cannot carry, for when a run
needs debugging rather than just measuring. `--label` tags the summary row. Without `--log`
nothing is measured and the frontend drives the `SimulationController` directly — see
[`report/AGENT.md`](report/AGENT.md).

`main.py` flags: `--width/--height` (15), `--agents` (20), `--obstacles`, `--algo {pibt,random}`,
`--allocator {easiest,random}`, `--mode {mrta,static}`, `--tasks {none,random}`, `--zones`,
`--frontend {pygame,headless}`, `--steps`, `--seed`, `--tick-ms`, `--log FILE.csv`, `--label`.

**In the window**: click an agent to toggle it, drag a rubber band to select several, then click a
cell to send the batch there — or a zone button in the sidebar to send it to a named region.
`Space` play/pause · `→` step · `←` replay backwards · `A`/`C` select all / clear · `Q` quit.

Dependencies: `pip install -r requirements.txt` — pygame is the only one, pinned `>=2.5`.
Everything except `client/frontends/pygame_frontend.py`, `sidebar.py` and the legacy renderer
runs without it.

**Fastest ways to exercise the code without a window** (use these to verify changes):
```bash
python main.py --frontend headless --tasks random --steps 20   # full MRTA path (easiest allocator)
python main.py --frontend headless --zones --tasks random --steps 20   # same, with zones
python main.py --frontend headless --mode static --algo random --steps 10
python demo_pibt.py -d
python sim_many_pibt.py --seeds 2                              # ~200 instances, a few seconds
python sim_many_mrta.py --seeds 2                              # 36 runs, ~1 minute
```
There is currently **no test suite** — these are the de-facto regression checks.

**MRTA runs are reproducible from `--seed` alone** — every allocator owns a seeded RNG rather
than the `random` module's global one. Two runs of the same command must produce identical
output; if they stop doing so, something has reached for global randomness again, and every
logged `RunRecord` becomes uncomparable with it.

---

## Layout

```
.
├── core/          — pure engine, zero rendering dependency        -> core/AGENT.md
│   ├── entities/  — position.py, entity.py, zone.py, agent.py
│   ├── environment/ — grid.py (spatial source of truth)
│   └── engine/    — plan_result, dispatch_intent, coordinator, dispatcher,
│                    static_dispatcher, simulation
│
├── client/        — presentation: scripting API, frozen views, frontends -> client/AGENT.md
│   ├── control/   — config, driver (the ABC), factory (COMPOSITION ROOT), controller
│   ├── view/      — task_view, zone_view, snapshot  (frozen value types)
│   ├── frontends/ — frontend (ABC), pygame_frontend, sidebar, headless_frontend
│   ├── palette.py — shared drawing colours (data, no pygame import)
│   └── pibt_interactive_renderer.py — LEGACY renderer, demo_pibt.py only
│
├── mrta/          — Multi-Robot Task Allocation, depends only on core   -> mrta/AGENT.md
│                    task, task_source (+ queue/random/scripted/composite),
│                    allocator, fleet_manager
│
├── algo/          — MAPF algorithms                                     -> algo/AGENT.md
│   ├── coordination/ — random_walk, reservation_table, priority_manager,
│   │                   pibt_coordinator
│   └── allocation/   — easiest_allocator (DEFAULT), random_allocator,
│                       kdtree_greedy_allocator (stub)
│
├── report/        — experiment log, OPT-IN behind --log                 -> report/AGENT.md
│                    run_record (THE schema), sink, collector
│
├── diagrammes/    — PlantUML sources + PNGs; script_perso.sh watches and regenerates
├── main.py            — CLI entry point (argparse -> client.control.build)
├── demo_pibt.py       — legacy interactive PIBT demo entry point
├── sim_many_pibt.py   — headless PIBT benchmark sweep -> sim_results.csv
├── sim_many_mrta.py   — headless allocation benchmark sweep -> mrta_results.csv
├── README.md · GUIDE.md · CONVENTION.md · CLAUDE.md · rapport_plan.md
└── requirements.txt · LICENSE
```

Every package carries an `__init__.py` re-exporting its public names; the package guide lists
them. `experiments.csv`, `sim_results.csv` and `mrta_results.csv` may sit at the root — all
gitignored outputs.

**Dependency direction** (strict, matches the class diagram):

```
mrta            -> core
algo            -> core, mrta
client.view     -> core, mrta (VALUE types only: Position, TaskState)
client.control  -> core, algo, mrta                     (composition root)
client.frontends-> core, client.view, client.control    (the ABC only)
report          -> core, mrta, client.control           (the ABC only)
```

`client/` cannot "depend only on core": picking the algorithm and wiring the fleet *is* the
scripting API's job. The rule that replaces it: **frontends know neither `algo` nor any mrta
*behaviour*** (`FleetManager`, `Allocator`, `TaskSource`) — they see frozen values only.
`TaskView.state` importing `TaskState` is a dependency on a *value*, not on behaviour;
duplicating the enum client-side would reintroduce drift, typing it `str` would lose the safety.

**The two `client.control` arrows are narrow on purpose.** `client/frontends/frontend.py` and
`report/collector.py` each import exactly one name — `SimulationDriver`, the ABC. Neither touches
`build()`, `ScenarioConfig` or any concrete wiring, so the composition root stays the only place
naming an algorithm. `SimulationDriver` is the project's one outward-facing interface; treat an
import of anything *else* from `client.control` by a frontend or by `report` as a layering bug.

---

## Rules and invariants

Two different things, kept apart on purpose. A **rule** constrains what you may write — breaking
one is a layering bug, and no amount of local convenience justifies it. An **invariant** is a
property the code already guarantees; your change does not have to restate it, but it must not
break it. When in doubt, the class diagram arbitrates.

### Hard rules — never violate these

- **`core/` must never import `client/`, `algo/`, or `mrta/`** — strictly one-directional dependency.
- **`mrta/` must never import `algo/` or `client/`** — it depends only on `core`.
- **`algo/` must never import `client/`** — algorithms are pure, no rendering.
- **`client/frontends/` must never import `algo/`, nor mrta *behaviour*** (`FleetManager`,
  `Allocator`, `TaskSource`). Allowed: `core`, the frozen types in `client/view/`, and
  `SimulationDriver` from `client.control` — **that one name only**. Value types (`Position`,
  `TaskState`) are fine. Composition belongs in `client/control/`.
- **A frontend never reads the engine at all.** Everything it draws *and* everything it resolves
  a click against comes from `StepSnapshot`; `SimulationDriver` hands out four verbs and no handle
  on a live object, so there is nothing to reach through. Do not put `sim`, `fleet` or `queue`
  back on that interface to make a frontend feature easier — extend the frame instead.
- **Hit-test the present, draw the cursor.** History is replayable, so the frame on screen may be
  many steps old. A click must be resolved against `history[-1]` (`PygameFrontend._present()`);
  resolving it against `history[cursor]` would order the robot that *used to* be in that cell.
  Geometry may come from the displayed frame — the board does not resize.
- **Visual/rendering changes -> `client/frontends/` only.**
- **Never call `SimulationController.step()` in a loop with a sleep** — a frontend owns the
  clock, and any real-time loop needs the `MAX_STEPS_PER_FRAME` clamp.
- **The class diagram is the reference.** When code and `_model.iuml` disagree, the default is to
  change the *code* so the diagram becomes true; amend the model only when it is genuinely wrong.
  The component and object diagrams follow the class diagram, never the reverse.
- **Diamonds follow one rule** (stated at the top of `_model.iuml`): filled for an immutable value
  or a mutable object with a single exclusive owner, hollow for a shared mutable instance.
- **`report/` stays out of the main diagram** — it has its own, and its only seams into the rest
  of the project are `SimulationDriver` and the `StepSnapshot` it measures.
- **Keep the diagrams in sync.** Five sources, each with its own scope:

  | Source | Scope | Regenerate with |
  |---|---|---|
  | `diagrammes/_model.iuml` | the architecture (via `diagrams.puml`) | `plantuml diagrammes/diagrams.puml` |
  | `diagrammes/component_diagram.puml` | packages and the seams between them | `plantuml diagrammes/component_diagram.puml` |
  | `diagrammes/report_diagram.puml` | `report/` alone | `plantuml diagrammes/report_diagram.puml` |
  | `diagrammes/Object_Diagram/object_diag_mrta.puml` | instances after one MRTA tick (French) | `plantuml diagrammes/Object_Diagram/object_diag_mrta.puml` |
  | `diagrammes/Object_Diagram/object_diag_static.puml` | same, static mode (French) | `plantuml diagrammes/Object_Diagram/object_diag_static.puml` |

  `diagrams.puml` renders `_model.iuml` twice — simple and annotated — driven by the `$ANNOTATED`
  preprocessor flag, so the two class diagrams cannot drift apart. Never edit the generated PNGs.
  There is no sequence diagram: `sequence_tick.puml` was dropped — the tick order it showed is
  stated on `Simulation` in the class diagram and in [`core/AGENT.md`](core/AGENT.md).

### Invariants — properties the code already maintains

| Constraint | Detail |
|---|---|
| One agent per cell | `Grid.place()` raises; `Simulation.step()` lifts all movers before placing them |
| `Position` is immutable | frozen dataclass, never mutated |
| `Agent` is hashable | via `agent_id`, usable as a dict key |
| Deferred spawn | `appear_at > 0` -> held in `_pending` until the right step |
| Coordinator is mandatory | `Simulation` refuses to run without one; a dispatcher is optional |
| Obstacle = WorldEntity | `WorldEntity(id, pos, blocks_movement=True)` suffices — no subclass |
| A zone labels ground | `Zone` never blocks movement and is indexed at every cell it covers; `get_all()` returns it once |
| Goal stability | PIBT inserts `loc(i)` first among candidates if `loc(i) == goal(i)` |
| Algorithms have no rendering | `algo/` never imports pygame — all rendering goes through `client/` |
| `PlanResult` is the universal contract | every `Coordinator.plan()` returns one; diagnostics are optional |
| `DispatchIntent` decouples allocation from navigation | goals/priorities flow only through the intent; no external mutation of the coordinator, so any Coordinator pairs with any Dispatcher |
| Single mover | only `Simulation.step()` moves agents (lift→`move_to`→place); `agent.move_to` alone must not be called |
| Plans are validated, not rolled back | `Simulation._validate()` rejects an inapplicable `PlanResult` **before** any mutation, so the lift/place transaction cannot fail partially |
| Task identity belongs to the registry | `FleetManager` stamps `task_id` at intake; sources propose tasks without one, so several sources cannot collide (`Task` hashes on `task_id`) |
| `-inf` demotion is reversible | "at its goal" is a *state*; `PIBTCoordinator` saves the overwritten base and restores it as soon as the state stops holding |
| Snapshots are projections | `TaskView`/`ZoneView`/`StepSnapshot` copy values and key on `agent_id`; a snapshot must read identically N steps later |
| Allocation stays inside the seed | `EasiestAllocator` draws no random numbers; `RandomAllocator` owns its RNG — a `RunRecord` storing a seed can deliver on it |
| No unreachable task consumes an agent | intake guard + progress watchdog release the assignee and end in `FAILED`, **counted** not dropped |

---

## Still to do on the diagrams

- **Split the class diagram in three** — *Frontend*, *Engine*, *Algo* — matching the component
  view. The single global rendering is too dense to be a first read. The dense version is
  archived as `diagrammes/_model_full.iuml` (+ `simulation_class_diagram_full_*.png`) and
  should be kept as the exhaustive reference, not as the one shown first.
- `Object_Diagram/object_diag_mrta.puml` does not show a `Zone` instance yet.
