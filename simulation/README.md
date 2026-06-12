# MAPF Simulation — PIBT

A small **Multi-Agent Path Finding (MAPF)** simulator with a pluggable coordinator
interface and an interactive `pygame` viewer. The flagship coordinator implements
**PIBT** (Priority Inheritance with Backtracking).

![Class diagram](simulation_class_diagram.png)

## Inspiration & attribution

The PIBT coordinator in [`algo/pibt.py`](algo/pibt.py) is an **independent
reimplementation** inspired by the work of **Okumura et al.**:

> Keisuke Okumura, Manao Machida, Xavier Défago, Yasumasa Tamura.
> *"Priority Inheritance with Backtracking for Iterative Multi-Agent Path Finding."*
> Artificial Intelligence, 2022 (originally IJCAI 2019).
> [arXiv:1901.11282](https://arxiv.org/abs/1901.11282)

This repository is a learning/demo project and is **not** affiliated with the
original authors.

## Features

- **Pure simulation core** (`core/`) with zero rendering dependency.
- **Pluggable `Coordinator` interface** — drop in any MAPF algorithm.
- Two coordinators provided: **PIBT** and a minimal **random walk**.
- **Interactive step-by-step viewer**: priority order, per-agent moves, and
  priority-inheritance chains shown live, with free back/forward navigation.
- Deferred spawns, impassable obstacles, and collectible objectives.

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
python demo.py        # interactive PIBT demo (5×5 grid, navigable)
python demo.py -d     # terminal debug mode — prints each step, no pygame window
python main.py        # random-walk demo (10×10 grid)
```

### Interactive controls

| Key            | Action            |
| -------------- | ----------------- |
| `Space`        | play / pause      |
| `→`            | step forward      |
| `←`            | step back         |
| `Q` / `Esc`    | quit              |

## Project structure

```
core/      pure simulation engine (Position, Agent, Grid, Simulation, Coordinator, …)
algo/      MAPF algorithms (pibt.py, random_walk.py) — depends only on core/
client/    pygame rendering — depends only on core/
demo.py    interactive PIBT entry point
main.py    random-walk entry point
```

Dependencies are strictly one-directional: `core/` never imports `algo/` or
`client/`, and `algo/` never imports `client/`. See [`CLAUDE.md`](CLAUDE.md) for the
full architecture and contributor notes.

## Adding your own algorithm

Subclass `Coordinator` and implement `plan()`:

```python
from core.coordinator import Coordinator

class MyAlgo(Coordinator):
    def plan(self, agents, grid):
        # return {agent_id: next_Position, ...}
        return {a.agent_id: a.position for a in agents}
```

Then wire it in: `Simulation(grid, coordinator=MyAlgo())`. See
[`algo/random_walk.py`](algo/random_walk.py) for a minimal working example.

## License

[MIT](LICENSE) © 2026 Arcko5
