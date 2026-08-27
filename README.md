# dotbot-logistics

**MRTA mode for a [DotBot][pydotbot-doc] swarm** — click a robot and a point in the DotBot web
console, and PIBT (Priority Inheritance with Backtracking) drives that robot there one grid cell
at a time while routing around every other robot. Collision-free multi-robot navigation, driven
by an operator, on top of the DotBot simulator (or real hardware).

This repo is the **bridge**: it wires the [MAPF_Simulation][mapf] PIBT engine to the DotBot
controller's REST + WebSocket API. The planning engine itself is a separate package
(`mapf-simulation`, installed automatically). The DotBot side (`pydotbot`) is also separate.

> **Scope note.** The only thing you run here is **MRTA mode**, via `mrta_server.py`. The older
> Level 0/1/2 batch and demo scripts were removed on 2026-08-27; three unported ones are parked
> in `test_scripts/` for reference. See [`AGENT.md`](AGENT.md) for the full project map.

---

## What it does

1. You run a DotBot swarm (simulated or real) and this repo's `mrta_server.py` next to it.
2. In the DotBot web console you flip the **MRTA** pill to **ON**.
3. You select a bot, click a point on the map, and hit **Apply waypoints** — the console's own
   existing gesture, nothing new to learn.
4. `mrta_server.py` catches that click, snaps it to the nearest grid cell, and hands it to PIBT.
   The bot walks there one cell per tick, and PIBT bends its path around every other bot you've
   sent somewhere. Bots nobody clicked stay parked.
5. Flip the pill to **OFF** and every bot stops where it stands.

Re-clicking a bot that's still moving redirects it immediately. Sending the console's **Stop
nav** (an empty waypoint list) cancels that bot's target.

---

## What you need

| Piece | Why | How you get it |
|---|---|---|
| Python 3.12 + a virtualenv | runs `mrta_server.py` | you make it (below) |
| `mapf-simulation` (`core` + `pibt`) | the PIBT planning engine | pulled by `requirements.txt` from git |
| `pydotbot` | the DotBot controller, simulator and web console | pulled by `requirements.txt` |
| PyDotBot's `/mrta/*` proxy | lets the console's MRTA pill reach `mrta_server.py` | **only** on the `feat/mrta-mode-toggle` branch — editable install, below |

If you skip the proxy you can still run `mrta_server.py --dry-run` (a wiring check) and reuse
`mrta_mode/` as a library, but the console pill will read **MRTA N/A**.

---

## Install

```bash
git clone https://github.com/DotBots/dotbot-logistics.git
cd dotbot-logistics

python3.12 -m venv venv
source venv/bin/activate          # bash/zsh   —   fish: source venv/bin/activate.fish

pip install -r requirements.txt
```

Then, to drive it from the console, replace the released `pydotbot` with the branch that carries
the `/mrta/*` proxy:

```bash
pip install -e ../dotbot-workspace/repos/PyDotBot   # branch feat/mrta-mode-toggle
```

`venv/` is gitignored; there is no committed environment.

---

## Run it

Three things run side by side. Use three terminals (all with the venv activated).

### 1 — the DotBot swarm

The simulator needs an init-state TOML describing at least two bots. This repo no longer ships
one; the PyDotBot checkout has a sample, or point `--simulator-init-state` at your own.

```bash
dotbot run simulator --map-size 2000x2000 \
    --simulator-init-state ../dotbot-workspace/repos/PyDotBot/simulator_init_state.toml \
    --mrta-url http://localhost:8002
```

`--mrta-url` (equivalently `[run.controller] mrta_url` in the pydotbot config, or the
`DOTBOT_MRTA_URL` env var) tells the controller's `/mrta/*` proxy where `mrta_server.py` listens.

### 2 — the MRTA server

```bash
python mrta_server.py             # serves 0.0.0.0:8002
```

### 3 — the console

Open <http://localhost:8000/PyDotBot/>. The **MRTA** pill in the top bar should read **OFF**.
(If it reads **MRTA N/A**, terminal 2 isn't running or `--mrta-url` doesn't point at it.)

Flip it **ON** — it blinks amber while the server snapshots the fleet, then settles on **ON**
with the bot count in its tooltip. Now drive bots as described in *What it does*. `Ctrl+C` in
terminal 2 to shut the server down.

> The fleet is snapshotted when you flip ON. To pick up a bot that joined later, flip **OFF then
> ON** again.

---

## `mrta_server.py` options

`python mrta_server.py --help` for the full list. The ones you're likely to touch:

| Option | Default | Meaning |
|---|---|---|
| `--dry-run` | off | Build the session and tick, but never send waypoints or wait — a startup/wiring smoke test |
| `--mrta-port N` | `8002` | Port this server listens on (must match the controller's `--mrta-url`) |
| `--mrta-host H` | `0.0.0.0` | Bind address |
| `--base URL` | `http://localhost:8000` | The DotBot controller |
| `--map-cells N` | `5` | Grid resolution N×N — `5` → 400 mm cells, `8` → 250 mm, on a 2000×2000 map |
| `--cell-mm N` | derived | Cell size in mm (overrides `--map-cells`) |
| `--threshold N` | `100` | How close (mm) a bot must get to a cell centre to count as "arrived" |
| `--step-timeout S` | `4.0` | Max seconds to wait for all bots to finish a step before moving on |
| `--settle S` | `0.3` | Pause after each step to let bots come to rest |
| `--min-bots N` | `2` | Refuse to turn ON until at least this many localised bots are present |
| `--ws-url URL` | from `--base` | Controller WebSocket status URL |
| `--reconcile-interval S` | `2.0` | How often to fall back to a REST poll if the WebSocket misses a click or position |

---

## How it works (short version)

- **Detecting the click.** Every `PUT .../waypoints` the console sends triggers a broadcast on
  the controller's `ws://…/controller/ws/status` channel. `mrta_server.py` listens there — the
  same channel the frontend itself uses — and tells a real operator click apart from the echo of
  a `PUT` it just sent itself.
- **Planning.** The click's cell goes to `pibt.LifelongGoalOrchestrator.set_target(agent_id,
  cell)` — one target slot per bot, always overwriting. PIBT then advances the whole world one
  step, and every driven bot gets its next cell.
- **Moving.** One waypoint per bot per step, then a **synchronisation barrier**: the server waits
  (on live WebSocket positions, with a REST poll as backup) until every bot has actually arrived
  before planning the next step. That barrier is what makes PIBT's collision-avoidance hold on
  asynchronous hardware — it is not skippable.
- **No console changes.** The operator uses the stock DotBot web UI. The only change on the
  PyDotBot side is the `/mrta/*` proxy — one URL, no MRTA logic.

Grid ↔ millimetre mapping:

```
cell (gx, gy)  →  centre in mm = (gx·cell_mm + cell_mm/2,  gy·cell_mm + cell_mm/2)
position (x, y) mm  →  cell     = (⌊x / cell_mm⌋,  ⌊y / cell_mm⌋)
```

For the design in detail, read `diagrammes/sim_dotbot_mrta_ws_target_class_diagram.puml` and
[`AGENT.md`](AGENT.md).

---

## What's in the repo

| Path | What it is |
|---|---|
| `mrta_server.py` | The entry point — CLI that serves the console-toggle HTTP API (`GET /status`, `POST /mode`) |
| `mrta_mode/` | The MRTA-mode classes, one per file: `MRTASession`, the WS listener, the click translator, the position store, the REST clients, and `server.py`'s `MrtaMode` state machine. Self-contained — reusable without the rest of this repo. |
| `diagrammes/` | PlantUML design diagrams |
| `docs/` | MkDocs site (`mkdocs serve`) — three-level guides. **Partly stale**: still describes the removed batch scripts. |
| `test_scripts/` | `sim_dotbot_pibt.py`, `sim_dotbot_right_left.py`, `sim_many_pibt.py` — archived, currently broken (they import the removed vendored engine), kept only as a porting reference. |
| `log/` | Experiment outputs from past runs |
| [`AGENT.md`](AGENT.md) | Full project map, install/reuse guide for agents, contributing conventions, roadmap |

---

## Troubleshooting

**The pill reads `MRTA N/A`.** The console can't reach `mrta_server.py`. Check terminal 2 is
running, and that the controller was started with `--mrta-url http://localhost:8002` (or the
config-file / env-var equivalent) pointing at the right port.

**Toggling ON blinks amber then falls back to OFF.** `connect()` couldn't find `--min-bots`
localised bots within ~10 s. Check the simulator is running with a valid init-state TOML and that
bots have LH2 positions; lower `--min-bots` if you're testing with one bot.

**WSL isn't detecting the TTY** (real hardware, `usbipd` attach done but no `/dev/ttyUSB0` /
`/dev/ttyACM0`):

1. Install usbipd on Windows (PowerShell as Admin): `winget install --source winget dorssel.usbipd-win`
2. `usbipd list`
3. `usbipd bind --busid <BUSID>` (Admin)
4. `usbipd attach --wsl --busid <BUSID>`

---

## License

[BSD 3-Clause](LICENSE)

[pydotbot-doc]: https://pydotbot.readthedocs.io/en/latest/
[mapf]: https://github.com/RasdaCorentin/MAPF_Simulation
