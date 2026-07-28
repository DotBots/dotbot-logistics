# algo/ — MAPF algorithms

> **Package guide.** The general context — layout, dependency direction, hard rules,
> invariants and the diagrams — lives in the root [`AGENT.md`](../AGENT.md) and is **not**
> repeated here. Read it first.

`algo/` decides *how they move* (coordination) and, given a filtered set of candidates, *who
takes which job* (allocation). It depends on `core` and on `mrta`'s `Allocator`/`Task`, never
on `client` — **algorithms never render**, and `algo/` never imports pygame.

### `RandomWalkCoordinator` — `algo/coordination/random_walk.py`
```python
class RandomWalkCoordinator(Coordinator):
    def plan(agents, grid, intent) -> PlanResult  # per-agent random walk; ignores intent
```
Minimal coordinator: each agent tries random directions until it finds a valid, unblocked, not-yet-claimed cell (falls back to staying in place).

---

### PIBT decomposition — `algo/coordination/`

PIBT is split across three classes: `PIBTCoordinator` holds the algorithm, while reservations and priorities each live in their own class (`ReservationTable`, `PriorityManager`). `PIBTCoordinator` implements `Coordinator`. **Zero pygame dependency** — rendering lives in `client/`.

```python
class ReservationTable:            # algo/coordination/reservation_table.py
    _reserved: dict[Position, Agent]
    reserve(agent, pos)             # releases the agent's previous reservation first
    release(agent)                  # frees the agent's reservation (backtracking)
    get_reserving_agent(pos) -> Agent | None
    get_reservation(agent) -> Position | None
    clear()

class PriorityManager:             # algo/coordination/priority_manager.py
    __init__(initial_priorities: dict[Agent, float] | None = None)
    _base: dict[Agent, float]      # priorities set explicitly (intent re-seed, inheritance, goal-reached)
    _dynamic: dict[Agent, float]   # effective priorities used to rank agents
    update(agents)                  # inits missing agents, then decays every dynamic priority by 1
    get_priority(agent) -> float
    get_base(agent) -> float        # what set_base last wrote — read before the -inf demotion
    set_base(agent, p)              # writes both _base and _dynamic immediately

class PIBTCoordinator(Coordinator):   # algo/coordination/pibt_coordinator.py
    goals: dict[Agent, Position]     # public — rebuilt each tick from the intent; read by renderers
    _reservations: ReservationTable
    _priorities: PriorityManager
    _processed: set[Agent]
    _inheritance: list[tuple[Agent, Agent]]
    _last_intent: dict[int, tuple]   # last (goal, priority) per agent — for the re-seed guard
    _demoted: dict[Agent, float]     # base priority overwritten by the -inf demotion, kept to undo it

    plan(agents, grid, intent) -> PlanResult
    _apply_intent(agents, intent)          # rebuild goals; re-seed base priority only on change
    _pibt(agent, parent, grid) -> bool     # grid passed as an argument, no stored grid state
    _h(pos, agent, grid) -> int            # Manhattan distance heuristic
```

**Usage** — goals/priorities come from the intent, via a dispatcher:
```python
a0 = Agent(0, Position(0, 0))
a1 = Agent(1, Position(9, 9))

pibt = PIBTCoordinator()
dispatcher = StaticDispatcher(
    goals={0: Position(9, 9), 1: Position(0, 0)},
    priorities={0: 5.0, 1: 3.0},          # optional
)
sim = Simulation(grid, coordinator=pibt, dispatcher=dispatcher)
sim.add_agent(a0)
sim.add_agent(a1)

for _ in range(30):
    result = sim.step()      # PlanResult: positions + PIBT diagnostics
```
To *watch* it instead, go through the scripting API — `client.control.build(ScenarioConfig(...))`
then a `Frontend` — rather than driving `Simulation` by hand. This snippet exists to show the
coordinator/dispatcher wiring, not as the recommended entry point.

**Internal mechanics:**
- Goals are rebuilt each tick from `intent.goals` (an agent with no goal stays in place).
- **Re-seed guard**: the base priority is re-seeded from `intent.priorities` **only** when an agent's goal or business priority changed since last tick — otherwise the dynamic priority drift (anti-starvation) would be wiped. This is the crux of keeping the coordinator stateless about allocation while stateful about navigation.
- Dynamic priorities decay by 1 every step -> prevents starvation.
- An agent at its goal gets base priority `-inf` (processed last, prefers to stay). **The demotion
  is reversible**: "at its goal" is a *state*, so the overwritten base is saved in `_demoted` and
  restored the moment the state stops holding — the goal moved, or inheritance pushed the agent
  off it. Writing `-inf` without restoring it stranded the agent at the bottom of the ranking for
  the rest of the run.
- Priority Inheritance: if agent i wants k's cell, `set_base(k, get_priority(i) + EPSILON)` then `_pibt(k, i, grid)` recurses.
- Backtracking: if k cannot move, i tries another candidate cell (`ReservationTable.release`).
- Obstacles are detected via `entity.blocks_movement and entity.active` on the grid's static entities.

**Adding a new Coordinator:**
```python
# in algo/coordination/my_algo.py
from core import Coordinator, PlanResult

class MyAlgo(Coordinator):
    def plan(self, agents, grid, intent) -> PlanResult:
        positions = {a.agent_id: intent.goals.get(a.agent_id, a.position) for a in agents}
        return PlanResult(positions=positions, moves={...})
```
Plug it in with a dispatcher that supplies the goals, e.g. `Simulation(grid, coordinator=MyAlgo(), dispatcher=StaticDispatcher(goals={...}))`. For a dedicated overlay, create `client/my_algo_renderer.py` extending `Renderer`.

---

### `algo/allocation/`
```python
class EasiestAllocator(Allocator):         # THE DEFAULT — nearest free robot wins
class RandomAllocator(Allocator):          # baseline — RandomAllocator(seed=None)
class KDTreeGreedyAllocator(Allocator):    # design stub — raises NotImplementedError
```

**`EasiestAllocator`** serves tasks **highest priority first**, each taking the closest robot
still free. Three decisions worth keeping:

- **Greedy, not optimal.** An early task can strand a later one with a distant robot; a
  Hungarian assignment would avoid that at O(n³) and far more machinery. Allocation runs every
  tick and `FleetManager`'s watchdog already recovers from a bad pairing, so the trade is
  deliberate — it is the sensible default, not the last word.
- **Manhattan, not path length.** Exact on a 4-connected grid without obstacles, a lower bound
  otherwise. Consulting the planner for a true distance would make allocation depend on
  navigation — precisely the coupling `DispatchIntent` exists to prevent — and would give the
  allocator its own notion of *reachable*, rival to the planner's. The task lifecycle refuses
  that on purpose: it observes absence of progress instead of proving reachability up front.
- **Deterministic ties** (`(distance, agent_id)`, task order made total by `task_id`). It draws
  no random numbers at all, so allocation stays *inside* the seed and a logged `RunRecord` is
  worth comparing against another.

**`RandomAllocator`** is the distance-blind baseline, kept to compare against. Its RNG is
**owned** (`random.Random(seed)`), not the module-level global: drawing from the global one
made two runs of the same `--seed` disagree — the scenario was reproducible, the allocation was
not, and a `RunRecord` storing the seed promised a reproducibility it could not deliver.
`seed=None` restores the unseeded behaviour explicitly, for whoever actually wants it.

`KDTreeGreedyAllocator` is intentionally unimplemented: the indexing strategy (rebuild cost per
dispatch cycle, tie-breaking, distance metric on a discrete grid) needs discussion first. It is
the same *idea* as `EasiestAllocator` — nearest free robot — with a spatial index instead of a
linear scan, i.e. an optimisation of a class that now exists and costs O(tasks × agents) per
tick. Implement it when that scan is measured to matter, not before.

Neither allocator filters eligibility — `FleetManager` has already done that before calling
them; see [`../mrta/AGENT.md`](../mrta/AGENT.md).

`python sim_many_mrta.py` sweeps grid × agents × allocator × seeds and is the way to compare
them.
