# RoadmapMRTA.md — MRTA on top of PIBT

> Roadmap for adding **Multi-Robot Task Allocation (MRTA)** to the DotBot/PIBT stack.
> Status: **design approved, not yet implemented.** This document is the contract; code follows.

---

## 1. Objective & context

Today PIBT runs **one-shot**: goals are assigned once (random or hardcoded), the loop steps until
`all_at_goal`, then stops (`build_pibt()` / `run_pibt_live()` in `sim_dotbot_pibt.py`; the hardcoded
`goals` / `initial_priorities` in `sim_pibt.py`).

This roadmap turns that into **lifelong PIBT driven by an online task stream**, toward the experimental
article. Two **distinct** features are requested:

- **Feature A — task-creation tool (controller side).** Create a new **move-to task** ("go to cell X").
- **Feature B — dynamic priority.** Change a task's priority at runtime; the assigned robot's PIBT
  priority follows, **reordering conflict resolution**. This is what makes PIBT *dynamic*.

PIBT supports this natively: it repeats one-timestep planning with adaptive priorities, so goals and
priorities can change between steps (Okumura 2022 §2.3 "lifelong/online", §3.2 "MAPD").

---

## 2. Literature anchors

All under `~/Inria/Main/Documentation/SOA/stage/`:

| Topic | Source | What we take from it |
|---|---|---|
| Lifelong/online PIBT, MAPD model | `PIBT2022Okumura.md` §2.3, §3.2, Algo 1 | One-step planning; priority update rule (increment until goal, reset at goal); online task stream; *reachability* (not simultaneous-goal) is the right guarantee for task streams |
| Online task stream, service time | `MAPD2025Flammini.md` (§III-A, §F) | Tasks added online; free/occupied agents; **service time** metric; well-formedness / non-task endpoints (parking) for solvability |
| Centralized assignment (no auction) | `MRTA15Khamis.md` §5.1.2 | The auctioneer role (announce → bid → select) collapses to a direct computation: `FleetManager` has global state, so it computes the nearest-free-robot assignment itself — no message-passing rounds needed |
| Taxonomy placement | `MRTA15Khamis.md` §3 | Our configuration is **ST-SR-TA, online, centralized auctioneer** (single-task robots, single-robot tasks, time-extended/online assignment) — centralized in the *taxonomy* sense (one component decides), not implemented as a distributed protocol |

---

## 3. Locked design decisions

- **Task model:** move-to only — `Task = (id, target Position, priority, state)`. No pickup/delivery.
- **Allocation:** **centralized greedy assignment** via a pluggable `Allocator` — default
  `KDTreeGreedyAllocator` (nearest free robot, `scipy.spatial.cKDTree`, O(log n) lookup), tie-break by
  `agent_id`; `RandomAllocator` as a test baseline. No auction rounds — `FleetManager` has full state,
  so it computes the assignment directly instead of announcing/bidding.
- **Priority semantics:** dynamic task priority **reorders PIBT conflict resolution only**. The assigned
  agent's PIBT *base* priority follows the task priority. **No reassignment, no preemption.**
- **Task-creation tool:** an **independent component** (`TaskSource`) with its own structure, already
  placed in the class diagram. Its **transport** (HTTP endpoint vs pygame-interactive vs CLI/API) is
  **deferred** — to be confirmed after diagram review (see §9).
- **Coordinator boundary:** `FleetManager` depends only on `Coordinator`/`TaskSource`/`Allocator` — never
  on `PIBT` directly. `Coordinator` gains `set_goal(agent, target)` and `set_priority(agent, priority)`
  (concrete no-op defaults; `PIBT` overrides both). This is what makes `mrta/` swappable to any future
  algorithm without modification.

---

## 4. Architecture

New **independent package `simulation/mrta/`**. It depends only on `core/` (via the `Coordinator`
interface) — it does **not** import `algo/` at all, since allocation and goal/priority assignment go
through the abstraction, not a concrete algorithm. `core/` stays pure (never imports `mrta/`).

| Module | Responsibility |
|---|---|
| `mrta/task.py` | `Task` (id, `target: Position`, `priority: float`, `state`, `assignee`, `created_step`) + `TaskState` enum `{PENDING, ASSIGNED, DONE}` |
| `mrta/source.py` | `TaskSource` (ABC) — **the tool**: `poll(step) -> list[Task]`. Independent structure; transport pluggable (§9) |
| `mrta/allocator.py` | `Allocator` (ABC) — `allocate(pending, free, grid) -> dict[Task, Agent]`. `RandomAllocator` (test baseline) and `KDTreeGreedyAllocator` (default: nearest free robot via `scipy.spatial.cKDTree`, tie-break `agent_id`) both implement it |
| `mrta/fleet_manager.py` | `FleetManager` — owns the task queue; each step: intake new tasks from `TaskSource`, run the `Allocator` over free agents, wire `coordinator.set_goal(agent, task.target)` + `coordinator.set_priority(agent, task.priority)`, detect completion, free agents; `set_priority(task_id, p)` for Feature B |

**Coordinator change (`core/coordinator.py`), minimal.** Add `set_goal(agent, target)` and
`set_priority(agent, priority)` as concrete no-op default methods — any `Coordinator` that ignores
goals/priority (e.g. `RandomWalkCoordinator`) needs no changes.

**PIBT change (`algo/pibt.py`), minimal.** Override `set_goal`/`set_priority` to write `self.goals[agent]`
/ `self.base_priorities[agent]`. Effective priority = `base_priorities[agent]` (set from `task.priority`)
**+** PIBT's existing aging term (increment-while-not-at-goal, reset at goal). This keeps PIBT's starvation
guarantee intact while letting `FleetManager` reorder agents instantly when a task priority changes, without
knowing PIBT exists. **Free agents** (no task) get `goal = current cell` (stay put) and lowest priority.

> **Well-formedness caveat** (Flammini §F): idle robots staying on task cells can deadlock dense grids.
> Acceptable to *stay-put* on the 5×5 demo grid; parking/non-task endpoints are a later refinement.

**Diagram:** `Task`, `TaskState`, `TaskSource`, `Allocator`, `RandomAllocator`, `KDTreeGreedyAllocator`,
`FleetManager` and their relations are in `simulation/diagrammes/diagram.puml` (PNG regenerated). Keep in
sync on every structural change.

---

## 5. Feature A — task-creation tool

`TaskSource` is the **independent** abstraction for "create a task". Contract:

```
class TaskSource(ABC):
    def poll(self, current_step: int) -> list[Task]: ...   # new tasks since last poll
```

The `FleetManager` calls `source.poll()` once per step and enqueues returned tasks as `PENDING`.
Concrete transports are added per phase and decided in §9. The same `TaskSource` interface is what the
real **controller-side** tool implements in Phase 2/3.

---

## 6. Feature B — dynamic priority

`FleetManager.set_priority(task_id, priority)` updates `task.priority`; on the next `dispatch()` the
fleet manager calls `coordinator.set_priority(assignee, task.priority)` — never touching PIBT fields
directly. PIBT's override writes `base_priorities[assignee] = priority`, so agents are served in the new
order at the next `plan()` — the higher-priority task's robot wins vertex conflicts and moves first.
No re-allocation, no goal change. This is the smallest change that makes PIBT *dynamic*.

---

## 7. Implementation phases

Progression is **pure simulation (L0) → simulator (L1) → real DotBots (L2)**.

### Phase 0 — engine groundwork (pure, headless)
- Add `Coordinator.set_goal`/`set_priority` (no-op defaults) + `PIBT` overrides + `base_priorities`.
- Add `mrta/` package: `Task`/`TaskState`, `TaskSource` ABC, `Allocator` ABC, `RandomAllocator`,
  `KDTreeGreedyAllocator`, `FleetManager`.
- Headless unit tests: `KDTreeGreedyAllocator` picks the nearest free robot (verify against brute-force
  distance); `RandomAllocator` returns a valid assignment; completion frees the agent; `set_priority`
  reorders `pibt` order; free agent stays put; `FleetManager` imports `core` but never `algo`/`PIBT`.
- Diagram already updated.

### Phase 1 — L0 simulation
- Lifelong loop entry point (dedicated `sim_mrta.py`, or adapt `sim_pibt.py` — see §9): no auto-terminate;
  each step `dispatcher.dispatch()` then `sim.step()`.
- `TaskSource` transport for the demo (default candidate: pygame click to spawn a task + key to bump
  priority; plus a CLI/programmatic `TaskSource` for scripted runs).
- Render task targets + priorities (extend `client/`, never import pygame from `algo`/`mrta`).
- **Demonstrate**: spawn tasks online, bump a priority, observe PIBT reorder.

### Phase 2 — L1 simulator (controller REST)
- Controller-side task tool over REST implementing `TaskSource` (e.g. `POST /tasks`).
- Replace one-shot `build_pibt` / `run_pibt_live` with the lifelong dispatcher loop.
- Reuse `GridStateManager`, parallel waypoint send, and the `wait_until_all_arrived` sync barrier
  (critical for PIBT collision-avoidance on async hardware).

### Phase 3 — L2 real DotBots
- Same `FleetManager` on `real_dotbot_pibt.py` / `real_dotbot_pibt_batch.py`: serial send, `resync` of
  agent positions from LH2 after each step.
- Record **service time** per task (time from creation to delivery) via `run_metrics.py`; write CSVs.

---

## 8. Verification per phase

| Phase | How to verify |
|---|---|
| 0 | Headless pytest on `mrta/` + PIBT base-priority; no pygame, no hardware |
| 1 | `python sim_mrta.py` (or adapted `sim_pibt.py`): spawn tasks, bump priority, watch reorder |
| 2 | Simulator running; `--dry-run` then live; POST tasks; confirm bots service them collision-free |
| 3 | `real_dotbot_pibt_batch.py`; check `log/` CSVs for service-time metrics |

---

## 9. Deferred decisions (confirm before implementing the relevant phase)

- **`TaskSource` transport** — HTTP endpoint (mirrors the real controller, max sim→real continuity) vs
  pygame-interactive (best L0 demo) vs CLI/API (simplest). Confirm after reviewing the class diagram.
- **Phase 1 entry point** — new `sim_mrta.py` vs adapting `sim_pibt.py`.
- **`KDTreeGreedyAllocator` tie-break** — proposed default is `agent_id` (kept from the original CNP
  rule); confirm before Phase 0 implementation.

---

## 10. Conventions

- **1 action = 1 commit.** Each logically distinct change is its own commit.
- **No push without explicit user request** in the same message.
- `core/` never imports `algo/`/`client/`/`mrta/`; `algo/` never imports `client/`/`mrta/`;
  `mrta/` imports only `core/` (via `Coordinator`) — never `algo/` or `client/`.
- Update `simulation/diagrammes/diagram.puml` + regenerate the PNG on every structural change.
