# DotBot Logistics

**MRTA mode for a [DotBot][pydotbot] swarm.** An operator clicks a robot and a point in the
DotBot web console; **PIBT** (Priority Inheritance with Backtracking) drives that robot there
one grid cell at a time, routing around every other robot on the floor. Collision-free
multi-robot navigation for warehouse-style intralogistics — driven by hand, one click at a
time.

<video controls muted playsinline preload="metadata"
       poster="assets/media/mrta-sim-demo.jpg"
       style="width:100%;max-width:960px;border-radius:8px;display:block;margin:1rem 0">
  <source src="assets/media/mrta-sim-demo.mp4" type="video/mp4">
  Your browser can't play this clip — <a href="assets/media/mrta-sim-demo.mp4">download it</a>.
</video>

*MRTA mode driving simulated DotBots through the reworked web console (2× speed).*

## What this repo is

`dotbot-logistics` is the **bridge** between a PIBT planning engine and the DotBot
environment. It holds neither of the two halves it connects:

| Half | Where it lives | Role |
|---|---|---|
| The planner | [`mapf-simulation`][mapf] (pip-installed) | `core` + `pibt` — the grid, the agents, PIBT, the lifelong goal orchestrator |
| The robots | [PyDotBot][pydotbot] (separate repo) | the DotBot controller, simulator, and web console |
| **The bridge** | **this repo** | turns a console click into a `set_target()` call, and a PIBT step into a waypoint the controller understands |

The one thing you run here is **`mrta_server.py`**, which sits behind the console's **MRTA**
toggle and does exactly that bridging.

!!! note "History"
    This project used to ship a vendored copy of the planning engine and a family of
    Level 0/1/2 batch scripts. On 2026-08-27 the vendored engine was removed (replaced by
    the `mapf-simulation` dependency) and the batch scripts were retired — three sit
    unported in `test_scripts/` for reference. The full account is in the repo's
    [`AGENT.md`](https://github.com/DotBots/dotbot-logistics/blob/develop/AGENT.md).
    Older versions of this site described the removed scripts; it has been rewritten around
    MRTA mode, the only live path.

## Where to go next

- **[Installation](installation.md)** — a virtualenv, the requirements, and the one PyDotBot
  branch that carries the `/mrta/*` proxy.
- **[Run MRTA mode](run.md)** — the three-terminal walkthrough and a worked two-robot
  example.
- **[How it works](how-it-works.md)** — click detection, the PIBT step, the synchronisation
  barrier, with the design diagrams.
- **[The console toggle](console-toggle.md)** — the ON/OFF pill, its four states, and what
  changes for an operator while it is on.
- **[Reference](reference.md)** — every `mrta_server.py` flag, the controller API consumed,
  and the grid ↔ millimetre mapping.
- **[Contributing](contributing.md)** — commit style, branch naming, and the
  class-diagram-first rule.

[pydotbot]: https://pydotbot.readthedocs.io/en/latest/
[mapf]: https://github.com/RasdaCorentin/MAPF_Simulation
