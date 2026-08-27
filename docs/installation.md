# Installation

Nothing here is automated — there is no committed virtualenv and no install script. Do it by
hand, once.

## Prerequisites

- **Python 3.12** and `git`.
- **A working DotBot environment is a precondition** — specifically a PyDotBot on the
  `feat/mrta-mode-toggle` branch, which is the only one that carries the `/mrta/*` proxy the
  console toggle needs. Step 2 sets that up from a plain PyDotBot clone. If you want the whole
  DotBot testbed instead of PyDotBot alone, [`DotBots/dotbot-workspace`][workspace] is an
  agent-first setup (`/workspace-setup`) that clones every DotBot repo into one shared venv —
  use its `PyDotBot` checkout for step 2 and add this repo's `requirements.txt` to that venv.
- A machine that can run the DotBot **simulator** (`dotbot run simulator`) — no hardware
  needed for everything on this site.

[workspace]: https://github.com/DotBots/dotbot-workspace

## 1. The engine and the Python dependencies

```bash
git clone https://github.com/DotBots/dotbot-logistics.git
cd dotbot-logistics

python3.12 -m venv venv
source venv/bin/activate          # bash/zsh   —   fish: source venv/bin/activate.fish

pip install -r requirements.txt
```

`requirements.txt` pulls:

| Package | What it gives you |
|---|---|
| `pydotbot[calibrate]` | the DotBot controller, simulator, and web console |
| `mapf-simulation` | the PIBT engine — `core` + `pibt` — installed straight from `git+https://github.com/RasdaCorentin/MAPF_Simulation.git@develop`, no local checkout needed |
| `requests`, `websockets` | the controller REST client and the WebSocket click/position listener |

## 2. The `/mrta/*` proxy

The console's **MRTA** pill reaches `mrta_server.py` through a `/mrta/*` reverse-proxy in the
DotBot controller. That proxy currently exists **only on PyDotBot's `feat/mrta-mode-toggle`
branch**, so replace the released `pydotbot` in your venv with an editable checkout of it:

```bash
git clone https://github.com/DotBots/PyDotBot.git
git -C PyDotBot checkout feat/mrta-mode-toggle
pip install -e PyDotBot
```

Already have a PyDotBot checkout somewhere? Just `git checkout feat/mrta-mode-toggle` there
and `pip install -e` that path instead.

!!! tip "You can skip this step if…"
    …you only want the `mrta_server.py --dry-run` wiring check, or you are reusing
    `mrta_mode/` as a library. Without the proxy the console pill simply renders greyed out
    as **MRTA N/A** — the console stays fully usable, there is just no MRTA behind it.

## 3. The simulator seed

`dotbot run simulator` needs an **init-state TOML** describing at least two bots. This repo
no longer ships one; PyDotBot includes a sample (`simulator_init_state.toml` at the root of
its checkout), or write your own — any TOML with two or more `[[dotbots]]` entries carrying
`pos_x` / `pos_y` inside your `--map-size` works.

## Check it

```bash
python -c "import mrta_mode, core, pibt; print('imports ok')"
dotbot --help        # PyDotBot CLI is on PATH
```

If both succeed, the install is good. Next: **[Run MRTA mode](run.md)**.
