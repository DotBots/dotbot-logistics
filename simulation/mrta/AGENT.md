# mrta/ — Multi-Robot Task Allocation

> **Package guide.** The general context — layout, dependency direction, hard rules,
> invariants and the diagrams — lives in the root [`AGENT.md`](../AGENT.md) and is **not**
> repeated here. Read it first.

`mrta/` decides *who does what*. It sits on `core` alone and never imports `algo` or
`client`: allocation and navigation meet only through `DispatchIntent`, which is what lets
any allocator run under any coordinator.

```python
class TaskState(Enum):             # mrta/task.py
    PENDING, ASSIGNED, DONE, FAILED

class Task:                        # mrta/task.py — hashable via task_id
    task_id: int                   # stamped by FleetManager at intake, not by the source
    target: Position
    priority: float
    state: TaskState
    assignee: Agent | None
    created_step: int
    eligible: frozenset[int] | None    # agent_ids allowed to take it (None = anyone)
    attempts: int                      # assignees burned through so far
    best_distance: int | None          # best Manhattan distance ever reached
    last_improvement_step: int         # step at which best_distance last improved

class TaskSource(ABC):             # mrta/task_source.py
    poll(current_step) -> list[Task]

class QueueTaskSource(TaskSource):    # push / push_many, poll() drains and empties
class RandomTaskSource(TaskSource):   # (grid, every, count, seed)
class ScriptedTaskSource(TaskSource): # ({step: [Task]})
class CompositeTaskSource(TaskSource):# (*sources) — polled in order, concatenated

class Allocator(ABC):              # mrta/allocator.py
    allocate(pending, free, grid) -> dict[Task, Agent]

class FleetManager(Dispatcher):    # mrta/fleet_manager.py — concrete Dispatcher
    source: TaskSource
    allocator: Allocator
    patience: int                  # steps without progress before releasing an assignee
    max_attempts: int              # assignees a task may burn before it is FAILED
    tasks: list[Task]
    completed_count: int
    failed_count: int

    dispatch(agents, grid, step) -> DispatchIntent
    #   _complete -> _watchdog -> _prune -> _intake -> _allocate -> _build_intent
    set_priority(task_id, priority)
    _complete(agents)              # ASSIGNED -> DONE once the assignee stands on the target
    _watchdog(step)                # releases stalled assignees; FAILED past max_attempts
    _prune()                       # drops terminal tasks, counting them on the way out
    _intake(step, grid)            # stamps ids; FAILED at once if the target is unreachable
    _allocate(agents, grid)        # one allocator call per eligibility class, restricted first
    _build_intent() -> DispatchIntent  # goals/priorities of the ASSIGNED tasks
    _by_eligibility(pending)       # static — groups pending tasks, restricted classes FIRST
    _is_obstructed(pos, grid) / _manhattan(a, b)   # static helpers
```

**Task lifecycle** — `PENDING -> ASSIGNED -> DONE` is nominal; `FAILED` is terminal for
abandoned work. Two guards close the allocation deadlock a plain three-state lifecycle left open
(an unreachable target consumed its assignee *forever*, since `_allocate` excludes ASSIGNED
agents from the free pool — a fleet silently losing robots while looking healthy):

- **static, at intake** — a target off the grid or under a blocking entity is rejected outright;
- **dynamic, the watchdog** — an assignee that has not improved its Manhattan distance to the
  target for `patience` steps is released and the task retried; past `max_attempts` distinct
  assignees, the *target* is blamed and the task FAILED.

We deliberately do **not** try to *prove* a target reachable: reachability is not static in a
world with `appear_at`, and proving it would duplicate the planner with a rival notion of
"reachable". We observe the absence of progress instead. Terminal tasks are pruned but
**counted** — dropping work silently would hide the very deadlock this closes.

The watchdog belongs to `FleetManager` because it is the only component seeing a task *across*
ticks; in the coordinator it would re-couple navigation with allocation semantics, exactly what
`DispatchIntent` separated. Full rationale in `rapport_plan.md`.

**Eligibility** — `Task.eligible` restricts who may take a task, so a caller can send a
*specific* batch somewhere. `_allocate()` groups pending tasks by eligibility class and calls
the allocator once per class, **restricted classes first** (otherwise an unrestricted task could
steal a reserved agent), removing matched agents from the pool between calls. The constraint
lives on the *request*, not on the matching *strategy*, so the `Allocator` interface is
untouched and new allocators need no adaptation.

`FleetManager` holds **no coordinator reference**: it is pure w.r.t. the engine. It returns a `DispatchIntent`, and `Simulation.step()` passes it to `plan()`. `Simulation` owns the ordering: `Simulation(grid, coordinator, dispatcher=fleet)` and `step()` runs `dispatch()` before `plan()` every tick — the caller no longer sequences them by hand.

---

---

## Eligibility and the allocator contract

Neither allocator filters eligibility. `FleetManager._by_eligibility()` groups pending tasks
by eligibility class and calls the allocator once per class, **restricted classes first**, so
an unrestricted task cannot steal a reserved agent. The constraint lives on the *request*, not
on the matching *strategy* — which is why the `Allocator` interface never had to grow for it,
and why a new allocator needs no adaptation. See [`../algo/AGENT.md`](../algo/AGENT.md) for
the allocators themselves.

---

## Domain vocabulary — settles a naming mistake

A **rack** is the **crate a robot loads or does not load onto itself** — a payload, *not* a
region of the map. The three operational regions are therefore the *loading station*, the
*working space*, and the *empty-rack area* (where empty crates are parked): the last is named
after what sits in it, not after a kind of region. Those regions are modelled by
`core.Zone`, not by anything in this package.

Nothing in the code models a rack yet. A `Rack` entity carried by an `Agent` (load / unload,
`Agent.carrying: Rack | None`) is the obvious next step and would change the task lifecycle —
a job becomes "fetch a rack here, drop it there" rather than "stand on this cell". **Not in
scope now**; recorded so the vocabulary does not have to be un-learned later.
