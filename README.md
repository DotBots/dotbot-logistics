# dotbot-pibt

PIBT (Priority Inheritance with Backtracking) demos for a [DotBot][pydotbot-doc] swarm —
collision-free multi-robot navigation on a discrete grid.

📖 **Documentation:** a three-level reproduction guide (algorithm → simulator → real
hardware) lives under [`docs/`](docs/index.md) and builds as a MkDocs site (`mkdocs serve`).

## Contents

| Path | Level | Description |
|------|-------|-------------|
| `sim_pibt.py` | 0 | Interactive pygame viewer — animates PIBT on a small grid (edit-in-file scenario). |
| `sim_many_pibt.py` | 0 | Headless benchmark — PIBT sweep over grid resolution × N × seeds, writes a CSV. |
| `simulation/` | 0 | Standalone PIBT engine (`core/`, `algo/pibt.py`) + renderers. |
| `simulation/main.py` | 0 | Minimal non-PIBT template (random-walk coordinator). |
| `sim_dotbot_pibt.py` | 1 | Drives the DotBot **simulator** through the controller API (parallel + pipelined). |
| `real_dotbot_pibt.py` | 2 | Drives **real** DotBots, one waypoint per bot per step, sync barrier between steps. |
| `real_dotbot_pibt_batch.py` | 2 | Parametrised batch test (`--bots N --runs M`) writing L1 metrics. |
| `log/` | — | Experiment outputs — `raw_logs/` and metrics CSVs. |
| `docs/` | — | Documentation — roadmap, experiment reports, Inria hand-offs. |

### Simulation architecture

![Class diagram](simulation/diagrammes/simulation_class_diagram.png)

## Installation

```bash
pip install -r requirements.txt
```

`requirements.txt` pulls `pydotbot[calibrate]`, `requests`, and `pygame` (the last one is
only used by the Level 0 viewer). The bundled `simulation/` engine is added to `sys.path`
automatically by the scripts — no separate install needed.

---

## Scripts

### Level 0 — algorithm only

#### `sim_pibt.py` — interactive viewer

Animates PIBT on a small grid and shows, at each step, the priority order, every agent's
move, and the priority-inheritance chains. The scenario (grid size, start positions, goals,
priorities, obstacles) is **edited directly in the file** — there are no CLI options.

```bash
python sim_pibt.py        # launch the interactive viewer
python sim_pibt.py -d     # debug mode (hides the pygame support prompt)
```

| Key | Action |
|-----|--------|
| `Space` | pause / play |
| `→` | step forward |
| `←` | step back |
| `Q` / `Esc` | quit |

A minimal non-PIBT example (random-walk coordinator, a template for your own algorithm)
lives in `simulation/main.py` (`python simulation/main.py`).

#### `sim_many_pibt.py` — headless benchmark

Runs PIBT with no pygame and no hardware, sweeping grid resolution × number of robots ×
random seeds, and writes one CSV row per instance plus a breaking-point summary. The arena
is fixed at **2000 × 2000 mm** and the cell size varies: 4×4 (500 mm), 5×5 (400 mm),
8×8 (250 mm).

```bash
python sim_many_pibt.py                  # full sweep, 30 seeds
python sim_many_pibt.py --seeds 5        # quick smoke-test
python sim_many_pibt.py --out my.csv     # custom output file
```

| Option | Default | Description |
|--------|---------|-------------|
| `--seeds N` | `30` | Number of seeds per (grid, N) cell |
| `--out FILE` | `l0_results.csv` | Output CSV file |

### Level 1 — simulator

#### `sim_dotbot_pibt.py`

Drives the DotBot **simulator** through the controller's REST API. Sends one waypoint per
bot per step and waits for **all** bots to arrive (synchronisation barrier) before the next
step. Optimised for the simulator: waypoints are sent in parallel, and the next PIBT step is
pre-computed while the bots travel.

```bash
python sim_dotbot_pibt.py              # synchronised step-by-step run
python sim_dotbot_pibt.py --dry-run    # print targets without sending or waiting
python sim_dotbot_pibt.py --steps 40   # cap the number of PIBT steps
python sim_dotbot_pibt.py --map-cells 5 # 5x5 grid (400 mm cells); default is 8x8 (250 mm)
python sim_dotbot_pibt.py --seed 42    # reproducible random goals
```

| Option | Default | Description |
|--------|---------|-------------|
| `--dry-run` | — | Print step-by-step targets without sending or waiting |
| `--steps N` | `30` | Number of PIBT steps |
| `--map-cells N` | `8` | Grid resolution N×N (8 → 250 mm cells, 5 → 400 mm on a 2000×2000 map) |
| `--cell-mm N` | derived | Cell size in mm (overrides `--map-cells`; default: `map_size / --map-cells`) |
| `--threshold N` | `100` | Arrival radius per cell in mm |
| `--step-timeout S` | `8.0` | Max wait (s) per step |
| `--settle S` | `0.3` | Pause (s) after arrival per step |
| `--min-bots N` | `2` | Minimum localised bots required at startup |
| `--base URL` | `http://localhost:8000` | Controller URL |
| `--seed N` | random | RNG seed for reproducible goals |

### Level 2 — real hardware

#### `real_dotbot_pibt.py`

The conservative driver for **real** DotBots (also works against the simulator). Computes
one PIBT step, sends one waypoint per moved bot, then waits at a synchronisation barrier
that polls the bots' real LH2 positions until all have arrived. A bot that exceeds
`--step-timeout` is logged and skipped (no deadlock). Same options and defaults as
`sim_dotbot_pibt.py`.

```bash
python real_dotbot_pibt.py                              # real run
python real_dotbot_pibt.py --dry-run                    # print targets only
python real_dotbot_pibt.py --threshold 120 --step-timeout 10
python real_dotbot_pibt.py --min-bots 3
```

| Option | Default | Description |
|--------|---------|-------------|
| `--dry-run` | — | Print step-by-step targets without sending or waiting |
| `--steps N` | `30` | Number of PIBT steps |
| `--cell-mm N` | `250` | Cell size in mm |
| `--map-cells N` | `8` | Fallback N×N grid (normally derived from the API `map_size`) |
| `--threshold N` | `100` | Arrival radius per cell in mm |
| `--step-timeout S` | `8.0` | Max wait (s) per step; beyond it the bot is logged and skipped |
| `--settle S` | `0.3` | Pause (s) after arrival per step |
| `--min-bots N` | `2` | Minimum localised bots required at startup |
| `--base URL` | `http://localhost:8000` | Controller URL |
| `--seed N` | random | RNG seed for reproducible goals |

#### `real_dotbot_pibt_batch.py`

Batch test harness: runs PIBT step-by-step on `N` real DotBots for `M` independent trials
and records per-run metrics and a summary under `log/` (raw logs in `log/raw_logs/`).

```bash
python real_dotbot_pibt_batch.py --bots 8            # 8 bots, 5 runs (default)
python real_dotbot_pibt_batch.py --bots 4 --runs 10  # 4 bots, 10 runs
```

| Option | Default | Description |
|--------|---------|-------------|
| `--bots N` | `8` | Number of DotBots in the batch |
| `--runs M` | `5` | Number of independent runs |

---

## Quick start

### 1. Start the DotBot simulator

```bash
dotbot run simulator \
    --map-size 2000x2000 \
    --simulator-init-state simulator_init_state.toml
```

> `simulator_init_state.toml` defines the initial bot positions (10 bots on the centres of
> an 8×8 grid, cell = 250 mm, map = 2000×2000 mm).
> See the [pydotbot documentation][pydotbot-doc] for an example.

### 2. Run the simulator demo

```bash
python sim_dotbot_pibt.py
python sim_dotbot_pibt.py --dry-run
```

### 3. Run the real-hardware demo

See [Level 2](docs/level-2-real.md) for the full hardware bring-up (MQTT broker, gateway,
LH2 calibration), then:

```bash
python real_dotbot_pibt.py --dry-run --seed 1
python real_dotbot_pibt.py --seed 1 --steps 20
```

## Grid ↔ mm mapping

```
cell (gx, gy)  →  centre mm = (gx×cell_mm + cell_mm//2, gy×cell_mm + cell_mm//2)
pos (x, y) mm  →  cell      = (int(x/cell_mm), int(y/cell_mm))
```

With `cell_mm=250` and a `2000×2000 mm` map: 8×8 grid.

## sim vs real

```
sim_dotbot_pibt.py              real_dotbot_pibt.py
─────────────────────────────  ─────────────────────────────────
Simulator only                 Real hardware AND simulator
Sends waypoints in parallel    Sends one waypoint per bot
Pipelines next PIBT step       Compute → send → wait (serial)
─────────────────────────────  ─────────────────────────────────
Both: one waypoint/bot/step, sync barrier on real positions
with a per-step timeout, threshold = 100 mm
```

## License

[BSD 3-Clause](LICENSE)

[pydotbot-doc]: https://pydotbot.readthedocs.io/en/latest/
