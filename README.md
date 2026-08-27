# dotbot-pibt

PIBT (Priority Inheritance with Backtracking) demos for a [DotBot][pydotbot-doc] swarm —
collision-free multi-robot navigation on a discrete grid.

📖 **Documentation:** a three-level reproduction guide (algorithm → simulator → real
hardware) lives under [`docs/`](docs/index.md) and builds as a MkDocs site (`mkdocs serve`).

> ⚠️ **Every script below is currently broken.** The vendored PIBT/MRTA engine
> (`simulation/`) was removed on 2026-08-27; reconnecting to the real upstream engine is
> deliberate future work, not done yet. See `AGENT.md`'s "Current known inconsistencies" and
> `Roadmap.md` §0. None of the commands in this README will run until that lands.

## Contents

| Path | Level | Description |
|------|-------|-------------|
| `sim_pibt.py` | 0 | Interactive pygame viewer — animates PIBT on a small grid (edit-in-file scenario). |
| `sim_many_pibt.py` | 0 | Headless benchmark — PIBT sweep over grid resolution × N × seeds, writes a CSV. |
| `sim_dotbot_pibt.py` | 1 | Drives the DotBot **simulator** through the controller API (parallel + pipelined). |
| `sim_dotbot_mrta.py` | 1 | Persistent — click a bot then a cell in the existing web UI, PIBT drives it there while others carry on. |
| `real_dotbot_pibt.py` | 2 | Drives **real** DotBots, one waypoint per bot per step, sync barrier between steps. |
| `real_dotbot_pibt_batch.py` | 2 | Parametrised batch test (`--bots N --runs M`) writing L1 metrics. |
| `log/` | — | Experiment outputs — `raw_logs/` and metrics CSVs. |
| `docs/` | — | Documentation — roadmap, experiment reports, Inria hand-offs. |

## Installation

```bash
pip install -r requirements.txt
```

`requirements.txt` pulls `pydotbot[calibrate]`, `requests`, `pygame` (only used by the Level 0
viewer), `scipy` (only used by the still-stubbed `KDTreeGreedyAllocator`), and `websockets`
(only used by `sim_dotbot_mrta.py`'s click-detection listener). The PIBT/MRTA engine these scripts
depend on (formerly bundled at `simulation/`) is not currently installable at all — see the
warning at the top of this file.

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
python sim_dotbot_pibt.py --map-cells 8 # 8x8 grid (250 mm cells); default is 5x5 (400 mm)
python sim_dotbot_pibt.py --seed 42    # reproducible random goals
```

| Option | Default | Description |
|--------|---------|-------------|
| `--dry-run` | — | Print step-by-step targets without sending or waiting |
| `--steps N` | `30` | Number of PIBT steps |
| `--map-cells N` | `5` | Grid resolution N×N (5 → 400 mm cells, 8 → 250 mm on a 2000×2000 map) |
| `--cell-mm N` | derived | Cell size in mm (overrides `--map-cells`; default: `map_size / --map-cells`) |
| `--threshold N` | `100` | Arrival radius per cell in mm |
| `--step-timeout S` | `8.0` | Max wait (s) per step |
| `--settle S` | `0.3` | Pause (s) after arrival per step |
| `--min-bots N` | `2` | Minimum localised bots required at startup |
| `--base URL` | `http://localhost:8000` | Controller URL |
| `--seed N` | random | RNG seed for reproducible goals |

#### `sim_dotbot_mrta.py` — persistent, click-to-target

No fixed goals, no step limit: every bot starts parked and stays that way until an operator drives
it, using the **existing, unmodified** DotBot web UI at `http://localhost:8000/PyDotBot/` — no
frontend changes needed. Select a bot, click a point on the map, click "Apply waypoints" (the
UI's own existing flow). The script detects that click over the controller's WebSocket status
channel, snaps it to the nearest grid cell, and hands it to PIBT as a task restricted to that one
bot — it then navigates there step by step, avoiding every other bot being driven the same way.
Untouched bots simply stay put. Re-clicking a bot that's still mid-route redirects it immediately
instead of queuing behind the old target. Runs until `Ctrl+C`.

```bash
python sim_dotbot_mrta.py              # persistent run — click bots in the browser to drive them
python sim_dotbot_mrta.py --dry-run    # connect and build the grid, send/wait nothing (wiring check)
python sim_dotbot_mrta.py --map-cells 8  # 8x8 grid (250 mm cells); default is 5x5 (400 mm)
```

| Option | Default | Description |
|--------|---------|-------------|
| `--dry-run` | — | Connect and build the grid without sending or waiting |
| `--map-cells N` | `5` | Grid resolution N×N (5 → 400 mm cells, 8 → 250 mm on a 2000×2000 map) |
| `--cell-mm N` | derived | Cell size in mm (overrides `--map-cells`; default: `map_size / --map-cells`) |
| `--threshold N` | `100` | Arrival radius per cell in mm |
| `--step-timeout S` | `4.0` | Max wait (s) per step |
| `--settle S` | `0.3` | Pause (s) after arrival per step |
| `--min-bots N` | `2` | Minimum localised bots required at startup |
| `--base URL` | `http://localhost:8000` | Controller URL |
| `--ws-url URL` | derived from `--base` | Controller WebSocket status URL |
| `--idle-sleep S` | `0.2` | Pause (s) between idle ticks with nothing to do |
| `--reconcile-interval S` | `2.0` | Period (s) of the REST-based safety net that recovers a click made while the WebSocket link was down |

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
| `--map-cells N` | `5` | Grid resolution N×N (5 → 400 mm cells, 8 → 250 mm on a 2000×2000 map) |
| `--cell-mm N` | derived | Cell size in mm (overrides `--map-cells`; default: `map_size / --map-cells`) |
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
> a 5×5 grid, cell = 400 mm, map = 2000×2000 mm). For the 8×8 layout use
> `simulator_init_state_8x8.toml` together with `--map-cells 8`.
> See the [pydotbot documentation][pydotbot-doc] for an example.

### 2. Run the simulator demo

```bash
python sim_dotbot_pibt.py
python sim_dotbot_pibt.py --dry-run
```

### 2b. Or drive it manually via the web UI (MRTA mode)

```bash
python sim_dotbot_mrta.py
```

Then open `http://localhost:8000/PyDotBot/`, select a bot, click a point on the map, and click
"Apply waypoints" — PIBT takes it from there. `Ctrl+C` to stop.

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

With the default `--map-cells 5` and a `2000×2000 mm` map: `cell_mm=400`, 5×5 grid
(`--map-cells 8` gives `cell_mm=250`, 8×8).

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

#### Debug 
### Debugging: WSL Not Detecting TTY

If you have performed the `usbipd` attach command but your WSL instance is not detecting the device (e.g., no `/dev/ttyUSB0` or `/dev/ttyACM0` appears), follow these steps to troubleshoot:

## Initial Setup Checklist

Ensure the following commands have been executed correctly:

* **Install usbipd on Windows (PowerShell as Admin):**
```powershell
winget install --source winget dorssel.usbipd-win

```


* **List Devices (PowerShell):**
```powershell
usbipd list

```


* **Bind the Device (PowerShell as Admin):**
*This authorizes Windows to share the device with WSL.*
```powershell
usbipd bind --busid <BUSID>

```


* **Attach to WSL (PowerShell):**
```powershell
usbipd attach --wsl --busid <BUSID>

```
