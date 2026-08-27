# Installation

This guide **continues from PyDotBot's installation.** Make sure you have a working
PyDotBot first, then add this project on top of it.

## Prerequisites: PyDotBot

Follow the [PyDotBot getting-started guide](https://pydotbot.readthedocs.io/en/0.29.1/)
and install the package with the calibration extra (needed for LH2 localisation at
[Level 2](level-2-real.md)):

```bash
pip install 'pydotbot[calibrate]'
```

Check it runs:

```bash
dotbot --help
```

!!! note "Python environment"
    Everything here is plain Python (the simulator and driving an existing swarm need
    nothing else). Building and cable-flashing firmware additionally needs SEGGER Embedded
    Studio and the nRF Command Line Tools — see PyDotBot's prerequisites. Use a virtual
    environment so PyDotBot and this project share the same interpreter.

## Get this project

```bash
git clone https://github.com/DotBots/dotbot-logistics.git
cd dotbot-logistics
pip install -r requirements.txt
```

`requirements.txt` pulls `pydotbot[calibrate]`, `requests`, and `pygame` (the last one is
only used by the Level 0 viewer).

!!! warning "Currently broken"
    The PIBT engine these scripts depend on (formerly bundled at `simulation/`) was removed
    on 2026-08-27 and has no replacement installed yet — see the root `AGENT.md`'s "Current
    known inconsistencies" and `Roadmap.md` §0. None of the scripts below will run.

## What's in the box

| Path | Used at | Purpose |
|------|---------|---------|
| `sim_pibt.py` | Level 0 | Interactive pygame viewer (edit-in-file scenario). |
| `sim_many_pibt.py` | Level 0 | Headless PIBT benchmark sweep. |
| `sim_dotbot_pibt.py` | Level 1 | Drives the DotBot **simulator** through the controller API. |
| `real_dotbot_pibt.py` | Level 2 | Drives **real** DotBots, step-by-step with a sync barrier. |
| `real_dotbot_pibt_batch.py` | Level 2 | Parametrised batch test harness (`--bots N`). |
| `simulator_init_state.toml` | Levels 1–2 | Initial simulated-bot positions for the controller. |
| `mosquitto.conf` | Level 2 | Local MQTT broker config. |
| `dotbot.toml` | Level 2 | Controller connection / swarm-id config. |

You're ready. Continue to [Level 0 — Run a PIBT](level-0-algorithm.md).
