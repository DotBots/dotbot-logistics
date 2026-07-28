# core/ — the engine

> **Package guide.** The general context — layout, dependency direction, hard rules,
> invariants and the diagrams — lives in the root [`AGENT.md`](../AGENT.md) and is **not**
> repeated here. Read it first.

`core/` is the pure simulation engine: entities, the grid they live on, and the tick that
moves them. It imports **nothing** from `client/`, `algo/` or `mrta/` — the dependency is
strictly one-directional, which is what lets an algorithm or an allocator be swapped without
the engine noticing.

### `Position` — `core/entities/position.py`
```python
@dataclass(frozen=True)
class Position:
    x: int
    y: int
    def __add__(self, other: Position) -> Position  # vector addition
```
Hashable (frozen). Used as a dict key in `Grid._agents` and `Grid._static`.

---

### `WorldEntity` — `core/entities/entity.py`
```python
class WorldEntity:
    entity_id:       int
    position:        Position
    appear_at:       int   # step at which the entity spawns (0 = immediate)
    blocks_movement: bool  # True -> cell impassable for agents
    scale:           int   # RESERVED — stored, never read (see below)
    cells:           tuple # property, the cells occupied — (position,) unless overridden
    active:          bool  # property, True by default
```
Common base for any entity placed on the grid. Blocking obstacles are created with `WorldEntity(id, pos, blocks_movement=True)` — **no dedicated subclass needed**.

**`cells` is what `Grid` indexes**, so the grid can place any entity without knowing which kinds
span more than one cell. The base returns `(position,)`; only `Zone` overrides it.

⚠ **`cells` is not `scale`, and `scale` is still reserved.** `cells` is an explicit list for
*indexing* — "where do I find this entity?". `scale` would be a movement *footprint* — "how much
room does it need to move?" — and would force `Grid`, `is_blocked`, `Simulation._validate` and
PIBT's candidate generation to change together. `scale` is assigned in `__init__` and read
nowhere in the repo: do not write code that assumes it works.

---

### `Zone` — `core/entities/zone.py`
```python
class Zone(WorldEntity):
    name:  str
    cells: tuple[Position]              # read-only, declaration order, de-duplicated
    def contains(position) -> bool
    Zone(entity_id, name, cells, appear_at=0)   # raises on an empty cell list
```
A named region an operator addresses by name instead of by coordinates — loading station,
working space, empty-rack area. Like any `WorldEntity` it can spawn late and go inactive.

**It never blocks movement**: a zone labels ground, it does not occupy it. Robots cross it and
park in it exactly as before, which is what lets zones be added to a running scenario without
the planner changing at all.

**Indexed at *each* of its cells**, not at one anchor, so "what is here?" finds it anywhere
inside. The inherited `position` is a nominal anchor kept only so a `Zone` is a `WorldEntity`
like any other; `cells` is what `Grid` indexes.

It deliberately does **not** use `WorldEntity.scale` — see the warning above. `cells` is an
explicit list and forces nothing else to change.

---

### `Agent` — `core/entities/agent.py`
```python
class Agent(WorldEntity):
    agent_id:    int        # alias of entity_id
    steps_taken: int
    blocks_movement = True  # (passed to super().__init__)
    def move_to(new_position: Position)   # updates position + steps_taken
    def __eq__ / __hash__                 # based on agent_id — hashable, usable as a dict key
```
`agent_id` is immutable -> stable hash. Used as a dict key in `PIBTCoordinator.goals` and internally in `PriorityManager`/`ReservationTable`.
Constructor: `Agent(agent_id, position)` — no strategy of its own, movement is always delegated to the `Coordinator`.

---

### `Grid` — `core/environment/grid.py`
```python
class Grid:
    width: int
    height: int
    _agents: dict[Position, Agent]
    _static: dict[Position, list[WorldEntity]]

    is_valid(position) -> bool
    is_blocked(position) -> bool        # True if an agent OR an active blocking entity occupies it
    place(entity: WorldEntity)          # indexes it at EVERY entity.cells; raises if invalid
                                        # or if an agent cell is already taken
    remove(entity: WorldEntity)
    get_agent_at(position) -> Agent | None
    get_entities_at(position, kind=None) -> list[WorldEntity]   # filters active=True on _static
    get_all(kind=None) -> list[WorldEntity]
```

---

### `PlanResult` — `core/engine/plan_result.py`
```python
@dataclass(frozen=True)
class PlanResult:
    positions:   dict[int, Position]   # agent_id -> next Position (universal contract)
    moves:       dict[int, tuple]      # agent_id -> (from, to)     (universal contract)
    order:       list[int]             # agent_ids in priority order   (optional diagnostic)
    inheritance: list[tuple]           # (pusher_id, pushed_id)        (optional diagnostic)
    priorities:  dict[int, float]      # agent_id -> priority          (optional diagnostic)
```
DTO returned by every `Coordinator.plan()` call. `positions`/`moves` are the contract every coordinator fills; the rest are diagnostics, left empty outside the PIBT family. Keys are `agent_id` integers so it can cross the core -> client boundary without exposing `Agent` objects.

**Frozen**, like every value crossing that boundary. The same instance is referenced by
`SimulationController._last_result` *and* archived in a `StepSnapshot`; a snapshot is documented
to read identically N steps later, so the guarantee rests on the type rather than on the
convention that coordinators build the object whole and nobody writes to it afterwards. The
contained dicts are not deep-frozen — this is a guard, not a proof.

---

### `DispatchIntent` — `core/engine/dispatch_intent.py`
```python
@dataclass(frozen=True)
class DispatchIntent:
    goals:      dict[int, Position]   # agent_id -> target (absolute, this tick)
    priorities: dict[int, float]      # agent_id -> allocation priority (optional per agent)
```
Immutable, `agent_id`-keyed carrier of the **absolute** allocation state for one tick (complete state, not deltas). Produced by a `Dispatcher`, consumed by `Coordinator.plan()`. It is the *only* channel for goals/priorities — there is no external mutation of the coordinator, which keeps allocation (`mrta`) and navigation (`algo`) decoupled and gives an auditable per-tick record.

---

### `Coordinator` — `core/engine/coordinator.py`
```python
class Coordinator(ABC):
    @abstractmethod
    def plan(self, agents: list[Agent], grid: Grid, intent: DispatchIntent) -> PlanResult: ...
```
The single-method interface for every MAPF algorithm. Goals and priorities arrive only through `intent`; a priority-less coordinator (e.g. random walk) simply ignores `intent.priorities`. Any `Coordinator` can therefore be paired with any `Dispatcher`.

---

### `Dispatcher` / `StaticDispatcher` — `core/engine/dispatcher.py`, `static_dispatcher.py`
```python
class Dispatcher(ABC):
    @abstractmethod
    def dispatch(self, agents: list[Agent], grid: Grid, step: int) -> DispatchIntent: ...

class StaticDispatcher(Dispatcher):
    def __init__(self, goals: dict[int, Position], priorities: dict[int, float] | None = None): ...
    def dispatch(self, agents, grid, step) -> DispatchIntent   # same fixed intent every tick
```
Pre-planning hook: `Simulation.step()` runs the dispatcher (if attached) **before** `plan()` and passes the returned intent to it, so goals are never stale by construction. It never touches the coordinator. Living in `core` lets `Simulation` own the tick order (dispatch → plan) **without importing `mrta`** — the same dependency-inversion seam as `Coordinator`. `FleetManager` (`mrta`) and `StaticDispatcher` are the concrete dispatchers; use `StaticDispatcher` for fixed-goal scenarios that need no task allocation.

---

### `Simulation` — `core/engine/simulation.py`
```python
class Simulation:
    grid:         Grid
    agents:       list[Agent]
    entities:     list[WorldEntity]
    _pending:     list[WorldEntity]
    current_step: int
    coordinator:  Coordinator            # mandatory — no per-agent fallback
    dispatcher:   Dispatcher | None       # optional — produces this tick's intent
    last_intent:  DispatchIntent          # the intent used by the last step (auditable)

    __init__(grid, coordinator, dispatcher=None)
    add_agent(agent)         # place + append
    add_object(entity)       # append + place immediately if appear_at <= current_step
    step() -> PlanResult     # spawn -> dispatch -> plan -> validate -> lift -> place
    _validate(result)        # rejects an inapplicable plan BEFORE any mutation
```

**`step()` logic** — `current_step += 1` runs **first**, so `appear_at` is compared against the
already-incremented step (an entity with `appear_at=1` spawns on the first `step()`):
```python
# 1. Spawn deferred entities whose appear_at step has been reached
# 2. Dispatch: intent = self.dispatcher.dispatch(...) if dispatcher else DispatchIntent()  (empty)
#    stored in self.last_intent
# 3. Coordinated planning (mandatory): result = self.coordinator.plan(self.agents, self.grid, intent)
# 4. Validate: self._validate(result) — raises before the grid is touched
# 5. Lift:  grid.remove(agent) for every agent whose target differs from its position
# 6. Place: agent.move_to(target) then grid.place(agent)
#    Return result — clients read diagnostics from it without importing algo
```
The `dispatch → plan` order is owned by `step()`, so a caller cannot plan on stale goals. Movement is applied by `step()` itself (lift-then-place) to handle simultaneous swaps — `agent.move_to` is never called outside this transaction, so `Agent.position` and the grid index stay in sync.

**`_validate()` rejects three things**, before any mutation, so the lift/place transaction cannot
fail halfway and strand agents off the grid:
1. **two agents claiming one cell** — checked for *every* agent, stationary ones included, so a
   mover cannot target a cell a stationary agent is keeping;
2. **a target off the grid** (`not grid.is_valid`);
3. **a target under an active blocking entity**.

Checks 2 and 3 are **deliberately skipped for agents that do not move**. An obstacle spawning via
`appear_at` onto an already-occupied cell would otherwise be reported as a planning error, which
it is not — the planner never proposed that overlap.

---

---

## Notes parked for the engine diagram

> These were deliberately left **out of the class diagram** to keep it readable. They are
> true and they matter, but each belongs in a diagram that does not exist yet.
> **Delete an entry the moment its diagram carries it.**

- `Grid.get_all()` **de-duplicates** — a zone eight cells wide is indexed eight times but
  returned once, so a caller cannot draw or count it eight times. The key is **object
  identity, not `entity_id`**: ids are unique per family (agents, obstacles and zones each
  number from 0), so keying on the id would silently merge an obstacle with a zone.
- `Simulation._validate()` skips the off-grid and blocked-cell checks for agents that do not
  move, so an obstacle spawning via `appear_at` onto an occupied cell is not reported as a
  planning error.
- `Grid.get_entities_at` / `get_all` and `Simulation._validate` were dropped from the class
  diagram as secondary; they remain part of the API.
