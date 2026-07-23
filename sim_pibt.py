"""
sim_pibt.py — Interactive PIBT demo on a 5x5 grid.

Controls:
    Space     pause / play
    ->        step forward
    <-        step back
    Q / Esc   quit

The footer bar shows the priority order, agent moves,
and priority inheritances at each step.

────────────────────────────────────────────────────────────────
To build your own demo:

  1. Pick a Coordinator (PIBTCoordinator, RandomWalkCoordinator, or your own).
  2. Provide goals/priorities through a Dispatcher — a StaticDispatcher for
     fixed targets, or a FleetManager (mrta) for task allocation.
  3. Build the simulation: Simulation(grid, coordinator=my_algo, dispatcher=d).
  4. Add agents and entities via sim.add_agent() / sim.add_object().
  5. Launch with:
       PIBTInteractiveRenderer(sim).run(steps=25)   # window, navigable
       PIBTInteractiveRenderer(sim).run_debug(20)   # terminal, no pygame

To add your own algorithm:
  -> see simulation/algo/coordination/random_walk.py as a minimal example.
  -> your class must inherit from Coordinator and implement
     plan(agents, grid, intent).
────────────────────────────────────────────────────────────────
"""

import sys
import os

DEBUG = "-d" in sys.argv
if DEBUG:
    os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "simulation"))

from core import Simulation, Agent, Grid, Position, StaticDispatcher, WorldEntity
from algo import PIBTCoordinator
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

# ── 3. PIBT goals: agent_id -> target Position ─────────────────────────────────
#    Modify these associations to change where each agent wants to go.
#    Keyed by agent_id (int), not Agent objects: goals/priorities now flow
#    through a Dispatcher's DispatchIntent, which is agent_id-keyed so it
#    stays an auditable, serialisable record of what allocation asked for.

goals = {
    agents[0].agent_id: Position(4, 4),
    agents[1].agent_id: Position(4, 1),
    agents[2].agent_id: Position(0, 4),
    agents[3].agent_id: Position(0, 0),
    agents[4].agent_id: Position(3, 4),
    agents[5].agent_id: Position(4, 3),
    agents[6].agent_id: Position(2, 2),
    agents[7].agent_id: Position(0, 2),
    agents[8].agent_id: Position(1, 1),
    agents[9].agent_id: Position(4, 2),
}

# ── 4. Initial priorities — higher value means the agent is served first ──────
#    Optional: if omitted, PIBTCoordinator assigns priorities by insertion order.
#    Fixed here via StaticDispatcher; for priorities that change at runtime,
#    use a Dispatcher that recomputes its DispatchIntent each tick instead
#    (e.g. mrta.FleetManager).

initial_priorities = {
    agents[0].agent_id: 20.0,
    agents[1].agent_id: 8.0,
    agents[2].agent_id: 7.0,
    agents[3].agent_id: 6.0,
    agents[4].agent_id: 5.0,
    agents[5].agent_id: 4.0,
    agents[6].agent_id: 3.0,
    agents[7].agent_id: 2.0,
    agents[8].agent_id: 1.0,
    agents[9].agent_id: 0.0,
}

# ── 5. Coordinator, dispatcher and simulation ──────────────────────────────────
#    To test another algorithm: replace PIBTCoordinator with your Coordinator.

pibt = PIBTCoordinator()
dispatcher = StaticDispatcher(goals=goals, priorities=initial_priorities)
sim = Simulation(grid, coordinator=pibt, dispatcher=dispatcher)

for agent in agents:
    sim.add_agent(agent)

# ── 6. World entities ─────────────────────────────────────────────────────────
#    Obstacles: WorldEntity with blocks_movement=True — no subclass needed.
#    (The collectible Objective entity used here previously was dropped in
#    the core refactor and has no replacement; Zone labels ground but is
#    never collectible.)
#
# sim.add_object(WorldEntity(entity_id=0, position=Position(2, 2), blocks_movement=True))

# ── 7. Launch ─────────────────────────────────────────────────────────────────
#    python sim_pibt.py       -> interactive window (<- -> Space Q)
#    python sim_pibt.py -d    -> debug mode: terminal print, no pygame

renderer = PIBTInteractiveRenderer(sim)
if DEBUG:
    renderer.run_debug(steps=20)
else:
    renderer.run(steps=30, auto_ms=500)
