# Level 1 — Plug it to fake bots

At Level 0 the agents were abstract dots. Now we connect the same PIBT plan to the
**DotBot simulator**: PyDotBot's controller drives a set of *simulated* bots, exposing the
exact same REST/WebSocket API as a real swarm — but with no hardware. Code you run here runs
**unchanged** against real DotBots at [Level 2](level-2-real.md); the only thing that changes
is what's on the other end of the API.

## 1. Start the simulator

In one terminal, launch the controller in simulator mode with the bundled initial state:

```bash
dotbot run simulator \
    --map-size 2000x2000 \
    --simulator-init-state simulator_init_state.toml
```

This serves the web UI at <http://localhost:8000/PyDotBot/> and creates the simulated bots
defined in `simulator_init_state.toml` (10 bots placed on grid-cell centres). Open the UI
to watch them on the map.

!!! warning "Option name"
    The flag is `--simulator-init-state` (not `--init-state`). The `--map-size` you pass
    here sets the arena the grid is mapped onto.

Check the bots are visible:

```bash
curl -s http://localhost:8000/controller/dotbots | python3 -m json.tool | head
```

You should see the addresses from the TOML (`BADCAFE1…`, `DEADBEEF…`, …), each with an
`lh2_position`.

## 2. Run the PIBT demo

In a second terminal:

```bash
python sim_dotbot_pibt.py              # step-by-step synchronised execution
python sim_dotbot_pibt.py --dry-run    # print the targets without sending anything
python sim_dotbot_pibt.py --steps 40   # cap the number of PIBT steps (default 30)
python sim_dotbot_pibt.py --seed 1     # reproducible random goals
```

The script auto-detects the bots over the REST API, computes PIBT trajectories, and sends
each bot one waypoint per step, waiting for **all** bots to arrive before issuing the next
step (a synchronisation barrier). It only talks to `http://localhost:8000`, so it is
independent of the transport underneath.

## Bulk vs. step-by-step

There are two ways to hand a plan to the bots, and the difference is the whole reason
Level 2 needs a hardened variant:

| | `sim_dotbot_pibt.py` (this page) | `real_dotbot_pibt.py` ([Level 2](level-2-real.md)) |
|---|---|---|
| Dispatch | One waypoint per bot per step | One waypoint per bot per step |
| Synchronisation | Sync barrier between steps | Sync barrier + per-step timeout |
| Target | Simulator (clean physics) | Real hardware **and** simulator |

Because the simulator has clean, instantaneous physics, the step barrier always closes; on
real hardware it may not, which is what the timeout and re-sync logic at Level 2 handle.

!!! tip "Why the simulator is not a measured level"
    The simulator is the fastest way to *see the plan drive bots through the real API*, but
    its "fidelity" is a moving target (how much physics you choose to model). For that reason
    it is used here for development and demonstration, not as a source of experimental
    metrics — those come from Level 0 (algorithm) and Level 2 (ground truth).

Next: [Level 2 — Vrrrm! Now it's real test time](level-2-real.md).
