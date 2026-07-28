# MAPF Simulation — PIBT

A small **Multi-Agent Path Finding (MAPF)** simulator with a pluggable coordinator
interface and an interactive `pygame` viewer. The flagship coordinator implements
**PIBT** (Priority Inheritance with Backtracking).

![Class diagram](diagrammes/simulation_class_diagram_commente.png)

## Inspiration & attribution

The PIBT coordinator in
[`algo/coordination/pibt_coordinator.py`](algo/coordination/pibt_coordinator.py) is an
**independent reimplementation** inspired by the work of **Okumura et al.**:

> Keisuke Okumura, Manao Machida, Xavier Défago, Yasumasa Tamura.
> *"Priority Inheritance with Backtracking for Iterative Multi-Agent Path Finding."*
> Artificial Intelligence, 2022 (originally IJCAI 2019).
> [arXiv:1901.11282](https://arxiv.org/abs/1901.11282)

This repository is a learning/demo project and is **not** affiliated with the
original authors.

## Features

- **Pure simulation core** (`core/`) with zero rendering dependency.
- **Pluggable `Coordinator` interface** — drop in any MAPF algorithm; every `plan()`
  returns a uniform `PlanResult` DTO.
- Two coordinators provided: **PIBT** and a minimal **random walk**.
- **Task allocation** (`mrta/`): tasks with a full lifecycle (including failure and a
  progress watchdog), several task sources, an allocator interface, and a fleet
  manager that dispatches goals to the shared coordinator.
- **Interactive fleet control**: select agents with the mouse and send a batch to a
  destination — routed through task allocation, so it inherits collision avoidance
  from the planner.
- **Scripting API** (`client/control/`): build and drive a scenario in a few lines,
  with no pygame involved.
- Deferred spawns and impassable obstacles.

## Requirements

- Python 3.10+ (developed on 3.14)
- [pygame](https://www.pygame.org/) (see `requirements.txt`)

## Installation

```bash
# (optional) create a virtual environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

## Running the demos

Run from the repository root:

```bash
python main.py                                  # 15×15, 20 agents, PIBT + task allocation
python main.py --tasks random                   # same, self-generating background work
python main.py --frontend headless --steps 20   # terminal output, no window
python main.py --algo random --mode static      # the historical random-walk demo
python demo_pibt.py                             # legacy PIBT demo (5×5 grid, navigable)
python demo_pibt.py -d                          # terminal debug mode, no pygame window
```

Useful flags: `--width/--height`, `--agents`, `--obstacles`, `--algo {pibt,random}`,
`--mode {mrta,static}`, `--tasks {none,random}`, `--seed`, `--tick-ms`.

### Interactive controls

Select agents, then click a destination — the batch is turned into tasks, allocated,
and routed by the planner.

| Input                  | Action                          |
| ---------------------- | ------------------------------- |
| click an agent         | toggle its selection            |
| drag                   | rubber-band selection           |
| click a cell           | send the selected batch there   |
| `Space`                | play / pause                    |
| `→`                    | step forward                    |
| `←`                    | replay backwards                |
| `A` / `C`              | select all / clear selection    |
| `Q` / `Esc`            | quit                            |

## Project structure

```
core/      pure simulation engine — entities/ (Position, WorldEntity, Agent),
           environment/ (Grid), engine/ (Simulation, Coordinator, PlanResult)
algo/      MAPF algorithms — coordination/ (PIBT, random walk), allocation/
mrta/      Multi-Robot Task Allocation (Task, TaskSource, Allocator, FleetManager)
client/    presentation — control/ (scripting API), view/ (frozen DTOs),
           frontends/ (pygame, headless)
diagrammes/ PlantUML class diagram sources + generated PNGs
main.py     CLI entry point
demo_pibt.py legacy interactive PIBT entry point
```

Dependencies are strictly one-directional:

```
mrta             → core
algo             → core, mrta
client.view      → core, mrta (value types only)
client.control   → core, algo, mrta      (composition root)
client.frontends → core, client.view     (read-only)
```

`core/` never imports the others, and frontends never see an algorithm or any task-allocation
behaviour — only frozen values. See [`GUIDE.md`](GUIDE.md) for a human tour of the project and
[`AGENT.md`](AGENT.md) for the full architecture reference.

## Adding your own algorithm

Subclass `Coordinator` and implement `plan()`, returning a `PlanResult`. Goals and
priorities arrive through the tick's `DispatchIntent`:

```python
from core import Coordinator, PlanResult

class MyAlgo(Coordinator):
    def plan(self, agents, grid, intent) -> PlanResult:
        positions = {a.agent_id: intent.goals.get(a.agent_id, a.position) for a in agents}
        moves = {a.agent_id: (a.position, positions[a.agent_id]) for a in agents}
        return PlanResult(positions=positions, moves=moves)
```

Wire it in with a dispatcher that supplies the goals — a `StaticDispatcher` for fixed
targets, or a `FleetManager` (mrta) for task allocation:
`Simulation(grid, coordinator=MyAlgo(), dispatcher=StaticDispatcher(goals={...}))`. See
[`algo/coordination/random_walk.py`](algo/coordination/random_walk.py) for a minimal
working example.

## License

[MIT](LICENSE) © 2026 Arcko5
