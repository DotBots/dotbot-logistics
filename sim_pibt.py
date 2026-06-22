"""
sim_pibt.py — Interactive PIBT demo on a 10x10 grid.

Controls:
    Space     pause / play
    ->        step forward
    <-        step back
    Q / Esc   quit

The footer bar shows the priority order, agent moves,
and priority inheritances at each step.

────────────────────────────────────────────────────────────────
To build your own demo:

  1. Choose a Coordinator (PIBT, RandomWalkCoordinator, or your own).
  2. Create agents BEFORE the coordinator if it uses Agent objects
     as dict keys (as PIBT does for goals and priorities).
  3. Build the simulation: Simulation(grid, coordinator=my_algo).
  4. Add agents and entities via sim.add_agent() / sim.add_object().
  5. Launch with:
       PIBTInteractiveRenderer(sim, pibt).run(steps=25)  # with navigation
       PIBTRenderer(sim, pibt).run(steps=30, pause=0.3)  # read-only
       Renderer(sim).run(steps=30, pause=0.3)            # no PIBT rendering

To add your own algorithm:
  -> see simulation/algo/random_walk.py as a minimal example.
  -> your class must inherit from Coordinator and implement plan().
────────────────────────────────────────────────────────────────
"""

import sys
import os

DEBUG = "-d" in sys.argv
if DEBUG:
    os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "simulation"))

from core import Simulation, Agent, Grid, Position, Objective, WorldEntity
from algo.pibt import PIBT
if DEBUG:
    # Direct import — avoids loading pygame via client/__init__.py
    from client.pibt_interactive_renderer import PIBTInteractiveRenderer
else:
    from client import PIBTInteractiveRenderer

# ── 1. Grid ───────────────────────────────────────────────────────────────────

grid = Grid(width=5, height=5)

# ── 2. Agents — created before PIBT because they are used as keys in goals/priorities ─

start_positions = [
    Position(0, 0), Position(2, 1), Position(4, 3), Position(4, 0),
    Position(1, 0), Position(4, 4), Position(4, 2), Position(3, 4),
    Position(3, 0), Position(3, 3),
]
agents = [Agent(agent_id=i, position=pos) for i, pos in enumerate(start_positions)]

# ── 3. PIBT goals: Agent -> target Position ───────────────────────────────────
#    Modify these associations to change where each agent wants to go.

goals = {
    agents[0]: Position(4, 4),
    agents[1]: Position(4, 1),
    agents[2]: Position(0, 4),
    agents[3]: Position(0, 0),
    agents[4]: Position(3, 4),
    agents[5]: Position(4, 3),
    agents[6]: Position(2, 2),
    agents[7]: Position(0, 2),
    agents[8]: Position(1, 1),
    agents[9]: Position(4, 2),
}

# ── 4. Initial priorities — higher value means the agent is served first ──────
#    Optional: if omitted, PIBT assigns priorities by insertion order.
#    Can be changed here or during the simulation via pibt.priorities[agent] = x.

initial_priorities = {
    agents[0]: 20.0,
    agents[1]: 8.0,
    agents[2]: 7.0,
    agents[3]: 6.0,
    agents[4]: 5.0,
    agents[5]: 4.0,
    agents[6]: 3.0,
    agents[7]: 2.0,
    agents[8]: 1.0,
    agents[9]: 0.0,
}

# ── 5. Coordinator and simulation ─────────────────────────────────────────────
#    To test another algorithm: replace PIBT with your Coordinator
#    and use PIBTRenderer(sim, pibt) if applicable.

pibt = PIBT(goals=goals, initial_priorities=initial_priorities)
sim = Simulation(grid, coordinator=pibt)

for agent in agents:
    sim.add_agent(agent)

# ── 6. World entities ─────────────────────────────────────────────────────────

# Free objective (any agent can collect it — yellow diamond)
sim.add_object(Objective(entity_id=0, position=Position(3, 3)))
"""
# Reserved objective: only agents[0] can collect it
sim.add_object(Objective(entity_id=1, position=Position(8, 1), owner=agents[0]))

# Obstacles: WorldEntity with blocks_movement=True — no subclass needed
sim.add_object(WorldEntity(entity_id=2, position=Position(5, 5), blocks_movement=True))
sim.add_object(WorldEntity(entity_id=3, position=Position(5, 6), blocks_movement=True))

# Deferred objective: only appears on the grid from step 2 onwards
sim.add_object(Objective(entity_id=4, position=Position(1, 8), appear_at=2))
"""
# ── 7. Launch ─────────────────────────────────────────────────────────────────
#    python sim_pibt.py       -> interactive window (<- -> Space Q)
#    python sim_pibt.py -d    -> debug mode: terminal print, no pygame

renderer = PIBTInteractiveRenderer(sim, pibt)
if DEBUG:
    renderer.run_debug(steps=20)
else:
    renderer.run(steps=30, auto_ms=500)
