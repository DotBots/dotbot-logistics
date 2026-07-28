# client/ — presentation

> **Package guide.** The general context — layout, dependency direction, hard rules,
> invariants and the diagrams — lives in the root [`AGENT.md`](../AGENT.md) and is **not**
> repeated here. Read it first.

Three subpackages, documented together because the seam between them is the point:

| | role | may import |
|---|---|---|
| `control/` | scripting API and **composition root** — the only place naming a concrete algorithm | `core`, `algo`, `mrta` |
| `view/` | frozen value types crossing the seam (`TaskView`, `ZoneView`, `StepSnapshot`) | `core`, `mrta` **values** only |
| `frontends/` | presentation only — pygame window, terminal | `core`, `client.view`, and `SimulationDriver` — that one name |

**Frontends know neither `algo` nor any mrta *behaviour*** (`FleetManager`, `Allocator`,
`TaskSource`) and never touch the engine: they see frozen frames and four verbs. That rule is
the reason `view/` exists at all.

### `ScenarioConfig` — `client/control/config.py`
```python
@dataclass(frozen=True)
class ScenarioConfig:
    width: int = 15;  height: int = 15;  agents: int = 20;  obstacles: int = 0
    algo: str = "pibt"    # "pibt" | "random"
    allocator: str = "easiest"   # "easiest" | "random"  — MRTA mode only
    mode: str = "mrta"    # "mrta" | "static"
    seed: int = 0
    tasks: str = "none"   # "none" | "random"  — background generation
    task_every: int = 5;  task_count: int = 2
    patience: int = 12;   max_attempts: int = 3    # FleetManager watchdog tuning
    zones: tuple[Zone] = ()                        # named regions, empty by default
```
Frozen: a config is a record of what was asked for, so a run is reproducible from it plus its
seed. `__post_init__` rejects unknown algo/allocator/mode/tasks, a scenario that cannot fit, and a
zone whose cells fall off the grid — caught here rather than by `Grid.place` so the message can
still *name* the offending zone, which is the whole point of validating a config.

`zones` is empty by default: a zone is a scenario decision, not a property of the engine, so a
run never told about zones behaves exactly as it did before they existed.

### `build` — `client/control/factory.py`
```python
def build(config: ScenarioConfig) -> SimulationController
```
**The composition root** — the one place allowed to know `algo` and `mrta` concretely. Draws
collision-free starts with `random.Random(seed)`, picks the coordinator, and in MRTA mode always
attaches a `QueueTaskSource` (so `send_batch_to` works), composing a `RandomTaskSource` alongside
it when `tasks="random"`. Swapping in a new algorithm or allocator touches this file only.

### `SimulationDriver` — `client/control/driver.py`
```python
class SimulationDriver(ABC):
    {abstract} step() -> StepSnapshot
    {abstract} run(steps) -> list[StepSnapshot]
    {abstract} snapshot() -> StepSnapshot
    {abstract} send_batch_to(target, agent_ids=None, priority=5.0, within=None) -> list[Task]
```
**The seam a frontend depends on** — and the only thing that crosses the `client.control`
boundary outward. Two classes implement it: `SimulationController` normally, and `RunCollector`
(`report/`) when `main.py --log` wraps one to measure it. A frontend must not be able to tell
which it received.

Declaring the interface rather than relying on `__getattr__` forwarding is what makes that
substitution *checked*: a decorator missing a member now fails at instantiation instead of at the
first click. It is also what a decorator means — presenting the same face as the thing it wraps
is precisely what allows the substitution.

**Four verbs and no handles.** `sim`, `fleet` and `queue` were on this interface for as long as
`PygameFrontend` read `sim.grid` to hit-test clicks — and `queue` in particular handed presentation
a live `QueueTaskSource`, i.e. mrta *behaviour*, which the layering forbids. A `StepSnapshot` now
carries what a click needs to be resolved (`width`/`height`, and `result.positions` for the reverse
cell -> agent lookup), so nothing live crosses this line: what sits on the other side can be asked,
not steered. The handles stay on the concrete `SimulationController`, which nothing outside
`client.control` names.

### `SimulationController` — `client/control/controller.py`
```python
class SimulationController(SimulationDriver):
    sim: Simulation                 # read-only property
    fleet: FleetManager | None      # read-only property, MRTA mode only
    queue: QueueTaskSource | None   # read-only property, MRTA mode only

    step() -> StepSnapshot                    # pure "advance by one" — owns no clock
    run(steps) -> list[StepSnapshot]
    send_batch_to(target, agent_ids=None, priority=5.0, within=None) -> list[Task]
    snapshot() -> StepSnapshot
```
Read-only properties over `_sim`/`_fleet`/`_queue`: a controller never re-targets its scenario.
They are **not** on the ABC — they are how this class is built and observed from *inside*
`client.control`, not part of what it offers outward.

The single seam between a built scenario and whatever drives it. `send_batch_to` mints one task
per destination cell — `target` first, then outwards by BFS over free cells — with
`eligible=frozenset(agent_ids)`, and pushes them into the queue.

**"Send this batch to B" *is* an allocation problem**: nothing bypasses the planner, so a batch
move inherits collision avoidance for free. That is why there is no manual per-cell driving
anywhere in this API. The BFS follows connectivity rather than scanning a radius, so it never
returns a cell that looks near but sits behind a wall.

`within` bounds *where the jobs may land*, never where the search may go: "send them to the
loading station" must mean the station itself and stop rather than spill into the aisle once it
is full, yet a zone reached through a corridor outside it is still one zone — bounding the walk
instead of the collection would make it two.

### `TaskView` / `StepSnapshot` — `client/view/`
```python
@dataclass(frozen=True)
class TaskView:
    task_id: int;  target: Position;  state: TaskState
    priority: float;  assignee_id: int | None;  attempts: int
    created_step: int
    @classmethod
    def of(task: Task) -> TaskView       # copies VALUES — never holds the Task or its assignee

@dataclass(frozen=True)
class StepSnapshot:
    step: int
    result: PlanResult
    goals: dict[int, Position]           # from sim.last_intent, not from the coordinator
    objects: tuple                       # ((Position, kind), ...)
    tasks: tuple[TaskView, ...]
    zones: tuple[ZoneView, ...]          # named regions, addressable by name
    width: int;  height: int             # board size — a pixel becomes a cell
    accepts_tasks: bool                  # MRTA mode: a queue is attached
    completed: int;  failed: int
    def counts() -> dict[str, int]       # pending/assigned live + done/failed cumulative
```
**Why a projection and not the `Task`**: a `Task` is mutable and owned by `FleetManager`, which
keeps mutating it (ASSIGNED → DONE) then prunes it. Archiving the task itself would let a stored
frame rewrite its own past, and a live `task.assignee.position` would contradict the frozen
`result.positions[id]` *inside the same snapshot*. Reducing the assignee to its `agent_id` is
the rule `PlanResult` already applies. This is precisely what makes it sound for a frontend to
keep a history while the engine runs on.

**A frame is also what a click is resolved against**, not only what is drawn: `width`/`height`
turn a pixel into a cell, `result.positions` turns that cell back into an agent, and
`accepts_tasks` says whether a click can dispatch anything at all. Without them a frontend has
to reach into the live engine to answer a click — which is exactly how it ends up hit-testing
the present against a frame describing the past. `created_step` is on `TaskView` for the same
reason the rest is: it is what a reader needs to say how long a task waited, and the fleet prunes
the task that knows it on the tick it ends.


```python
@dataclass(frozen=True)
class ZoneView:
    name: str;  cells: tuple
    @classmethod
    def of(zone: Zone) -> ZoneView
    def contains(position) -> bool       # mirrors Zone.contains
```
`ZoneView` follows `TaskView`'s rule: copy values, never hold the live entity — a `Zone` can be
deactivated while a frontend is still replaying an old frame, and a frame that describes a zone
must keep describing it. `cells` is what makes the projection useful rather than decorative: it
is both what the board highlights and what the frontend hands back as
`send_batch_to(..., within=)`, so "send them to the loading station" lands in the station and
nowhere else. `contains()` lets a frontend answer "which zone was clicked?" from the frame alone.

### `Frontend` / `HeadlessFrontend` / `PygameFrontend` — `client/frontends/`
```python
class Frontend(ABC):
    controller: SimulationDriver     # the INTERFACE — may be a RunCollector
    def run(steps: int)

class HeadlessFrontend(Frontend):   # terminal, zero pygame
class PygameFrontend(Frontend):     # PygameFrontend(controller, tick_ms=350)
```
`PygameFrontend` holds one board-drawing routine (the three legacy renderers each carried a
near-identical copy), with **`CELL` derived** from grid size and a window budget instead of the
old hard-coded 60.

Mouse: click an agent to toggle · drag a rubber band to select · click a cell to dispatch the
batch. Keys: `Space` play/pause · `→` step · `←` replay back · `A`/`C` select all / clear · `Q`.

- **Fixed-step accumulator**: the frontend owns the clock, so `step()` stays a pure "advance by
  one". `MAX_STEPS_PER_FRAME` is **not optional** — once a tick costs more than `tick_duration`
  the backlog grows without bound and the window freezes (spiral of death). The clamp degrades
  to slow motion instead.
- **Backward navigation is replay only.** `Grid` and `PriorityManager` are destructive, so the
  engine has no undo: frozen snapshots make *looking* back safe, not *rewinding*. A deliberate
  regression against `PIBTInteractiveRenderer`, whose symmetry needs a pre-computed history and
  is therefore incompatible with interactivity.
- **No threads**: `Grid`/`Agent` are mutated while read, and PIBT is CPU-bound so the GIL
  cancels the gain. Concurrency buys nothing and costs correctness.

---

### Legacy renderer — `client/pibt_interactive_renderer.py` (`demo_pibt.py` only)

Kept as the pre-existing regression path. New work goes through `client/frontends/`.
It is re-exported lazily from `client/__init__.py` (PEP 562) so importing `client.control`
or `client.view` never pulls pygame in.

`Renderer` and `PIBTRenderer` **were removed** as dead code: nothing referenced them but the lazy
table and the docs advertising them. Their colour constants survived into `client/palette.py`
(plain tuples, no pygame import), which is what `PIBTInteractiveRenderer` actually used them for.

`client/__init__.py` deliberately does **not** re-export `StepSnapshot`: the legacy renderer
defines its own, distinct from `client.view.StepSnapshot`, and exposing both from one package
made `from client import StepSnapshot` silently return the wrong type.

```python
class PIBTInteractiveRenderer:
    sim: Simulation
    def run(steps: int = 30, auto_ms: int = 600)
    def run_debug(steps: int = 30)   # terminal print, no pygame

@dataclass
class StepSnapshot:
    step: int
    result: PlanResult     # the step's plan (positions + diagnostics)
    goals: dict
    objects: list
```
Usage: `PIBTInteractiveRenderer(sim).run(steps=80, auto_ms=500)`.

Keyboard: `Space` pause/play · `->` step forward · `<-` step back · `Q` quit.

The footer shows, for each step, the priority order, each agent's move, and any priority inheritances triggered — read from `snap.result` (a `PlanResult`), not from any `algo`-specific attribute.

---

---

## Notes parked for the frontend diagram

> These were deliberately left **out of the class diagram** to keep it readable. They are
> true and they matter, but each belongs in a diagram that does not exist yet.
> **Delete an entry the moment its diagram carries it.**

- `result.positions` is keyed by `agent_id` and filled for **every** agent by both
  `PIBTCoordinator` and `RandomWalkCoordinator`. That completeness is what makes the reverse
  lookup ("which robot is in this cell?") sound rather than partial — the whole basis for
  hit-testing without the engine.
- Sidebar buttons are keyed `zone:<name>` and laid out from `snap.zones`, so a fourth zone
  declared in a scenario yields a fourth button with no change in the sidebar.
- `MAX_STEPS_PER_FRAME` is not optional: without the clamp a slow tick lets the accumulator
  outrun the frame and the window freezes (spiral of death).
