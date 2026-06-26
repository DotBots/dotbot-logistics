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
| Contract Net Protocol (auction) | `MRTA15Khamis.md` §5.1.2 | Allocation = announce → submit (bid) → select (winner) → contract |
| Taxonomy placement | `MRTA15Khamis.md` §3 | Our configuration is **ST-SR-TA, online, centralized auctioneer** (single-task robots, single-robot tasks, time-extended/online assignment) |

---

## 3. Locked design decisions

- **Task model:** move-to only — `Task = (id, target Position, priority, state)`. No pickup/delivery.
- **Allocation:** **CNP auction** — announce a pending task to free robots, each bids its cost
  (= distance to target), award to the lowest bid (tie-break by `agent_id`).
- **Priority semantics:** dynamic task priority **reorders PIBT conflict resolution only**. The assigned
  agent's PIBT *base* priority follows the task priority. **No reassignment, no preemption.**
- **Task-creation tool:** an **independent component** (`TaskSource`) with its own structure, already
  placed in the class diagram. Its **transport** (HTTP endpoint vs pygame-interactive vs CLI/API) is
  **deferred** — to be confirmed after diagram review (see §9).

---

## 4. Architecture

New **independent package `simulation/mrta/`**, layered *above* `algo/`. It may import `core` + `algo`;
`core/` and `algo/` stay pure (they never import `mrta/`), preserving the repo's strict layering.

| Module | Responsibility |
|---|---|
| `mrta/task.py` | `Task` (id, `target: Position`, `priority: float`, `state`, `assignee`, `created_step`) + `TaskState` enum `{PENDING, ASSIGNED, DONE}` |
| `mrta/source.py` | `TaskSource` (ABC) — **the tool**: `poll(step) -> list[Task]`. Independent structure; transport pluggable (§9) |
| `mrta/auction.py` | `CNPAllocator` — `allocate(pending, free, grid)`; bid = Manhattan distance (BFS if obstacles), lowest wins, tie-break `agent_id` |
| `mrta/dispatcher.py` | `TaskDispatcher` — owns the task queue; each step: intake new tasks from `TaskSource`, run `CNPAllocator` over free agents, wire `pibt.goals[agent]` + base priority, detect completion, free agents; `set_priority(task_id, p)` for Feature B |

**PIBT change (`algo/pibt.py`), minimal.** Add a dispatcher-owned **base priority** per agent.
Effective priority = `base_priorities[agent]` (set from `task.priority`) **+** PIBT's existing aging term
(increment-while-not-at-goal, reset at goal). This keeps PIBT's starvation guarantee intact while letting
the dispatcher reorder agents instantly when a task priority changes. **Free agents** (no task) get
`goal = current cell` (stay put) and lowest priority.

> **Well-formedness caveat** (Flammini §F): idle robots staying on task cells can deadlock dense grids.
> Acceptable to *stay-put* on the 5×5 demo grid; parking/non-task endpoints are a later refinement.

**Diagram:** `Task`, `TaskState`, `TaskSource`, `CNPAllocator`, `TaskDispatcher` and their relations are
in `simulation/diagrammes/diagram.puml` (PNG regenerated). Keep in sync on every structural change.

---

## 5. Feature A — task-creation tool

`TaskSource` is the **independent** abstraction for "create a task". Contract:

```
class TaskSource(ABC):
    def poll(self, current_step: int) -> list[Task]: ...   # new tasks since last poll
```

The `TaskDispatcher` calls `source.poll()` once per step and enqueues returned tasks as `PENDING`.
Concrete transports are added per phase and decided in §9. The same `TaskSource` interface is what the
real **controller-side** tool implements in Phase 2/3.

---

## 6. Feature B — dynamic priority

`TaskDispatcher.set_priority(task_id, priority)` updates `task.priority`; on the next `dispatch()` the
dispatcher writes `pibt.base_priorities[assignee] = task.priority`. PIBT then serves agents in the new
order at the next `plan()` — the higher-priority task's robot wins vertex conflicts and moves first.
No re-auction, no goal change. This is the smallest change that makes PIBT *dynamic*.

---

## 7. Implementation phases

Progression is **pure simulation (L0) → simulator (L1) → real DotBots (L2)**.

### Phase 0 — engine groundwork (pure, headless)
- Add `mrta/` package: `Task`/`TaskState`, `TaskSource` ABC, `CNPAllocator`, `TaskDispatcher`.
- Add `base_priorities` + free-agent handling to `PIBT`.
- Headless unit tests: auction picks nearest free robot; completion frees the agent; `set_priority`
  reorders `pibt` order; free agent stays put.
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
- Same `TaskDispatcher` on `real_dotbot_pibt.py` / `real_dotbot_pibt_batch.py`: serial send, `resync` of
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

---

## 10. Conventions

- **1 action = 1 commit.** Each logically distinct change is its own commit.
- **No push without explicit user request** in the same message.
- `core/` never imports `algo/`/`client/`/`mrta/`; `algo/` never imports `client/`/`mrta/`;
  `mrta/` may import `core/` + `algo/` but never `client/`.
- Update `simulation/diagrammes/diagram.puml` + regenerate the PNG on every structural change.
