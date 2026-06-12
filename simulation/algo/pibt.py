"""
PIBT — Priority Inheritance with Backtracking
Okumura et al., 2022.

Usage via coordinator hook:
    a0 = Agent(0, Position(0,0))
    a1 = Agent(1, Position(9,9))
    goals             = {a0: Position(9,9), a1: Position(0,0)}
    initial_priorities = {a0: 5.0, a1: 3.0}   # optional
    pibt = PIBT(goals=goals, initial_priorities=initial_priorities)
    sim  = Simulation(grid, coordinator=pibt)
    sim.add_agent(a0); sim.add_agent(a1)
    pibt.run(sim, steps=30, pause=0.5)

After each plan(), tracking attributes are available for external rendering:
    pibt._last_order       : list[Agent]                        — agents in priority order
    pibt._last_moves       : dict[Agent, (Position, Position)]  — (before, after) per agent
    pibt._last_inheritance : list[(Agent, Agent)]               — (pusher, pushed) successful inheritances
"""

from __future__ import annotations

from typing import Optional

from core.position import Position
from core.coordinator import Coordinator
from core.agent import Agent
from core.grid import Grid

DIRS    = [Position(0, -1), Position(0, 1), Position(-1, 0), Position(1, 0)]
EPSILON = 1e-3


class PIBT(Coordinator):
    """
    PIBT coordinator — implements the Coordinator interface.

    Plugged into Simulation.coordinator, replaces per-agent movement computation
    with a single coordinated planning pass.

    Parameters
    ----------
    goals :
        Dict Agent -> target Position. Keys are Agent objects directly.
    initial_priorities :
        Optional initial priorities (dict Agent -> float). Default:
        insertion index (last added = highest priority).
    """

    def __init__(
        self,
        goals: dict[Agent, Position],
        initial_priorities: Optional[dict[Agent, float]] = None,
    ) -> None:
        self.goals: dict[Agent, Position] = goals
        self.priorities: dict[Agent, float] = (
            initial_priorities.copy() if initial_priorities is not None else {}
        )

        # Internal state for one step (reset at each plan())
        self._next:      dict[Agent, Position] = {}
        self._processed: set[Agent]            = set()
        self._grid:      Optional[Grid]        = None

        # Tracking exposed to renderers — updated at each plan()
        self._last_order:       list[Agent]                          = []
        self._last_moves:       dict[Agent, tuple[Position, Position]] = {}
        self._last_inheritance: list[tuple[Agent, Agent]]            = []

    def _init_priorities_if_needed(self, agents: list[Agent]) -> None:
        for i, agent in enumerate(agents):
            if agent not in self.priorities:
                self.priorities[agent] = float(i)

    # ── Heuristique ───────────────────────────────────────────────────────────

    def _h(self, pos: Position, agent: Agent) -> int:
        g = self.goals[agent]
        return abs(pos.x - g.x) + abs(pos.y - g.y)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _reserving_agent(self, pos: Position) -> Optional[Agent]:
        for agent, p in self._next.items():
            if p == pos:
                return agent
        return None

    # ── Recursive PIBT algorithm (Algorithm 1) ───────────────────────────────

    def _pibt(self, agent: Agent, parent: Optional[Agent]) -> bool:
        grid = self._grid

        candidates: list[Position] = []
        for d in DIRS:
            v = agent.position + d
            if grid.is_valid(v) and not any(
                e.blocks_movement and e.active
                for e in grid.get_entities_at(v)
                if not isinstance(e, Agent)
            ):
                candidates.append(v)
        candidates.sort(key=lambda v: self._h(v, agent))

        # An agent already at its goal prefers to stay in place
        if agent.position == self.goals.get(agent):
            candidates.insert(0, agent.position)

        if parent is not None:
            candidates = [v for v in candidates if v != parent.position]

        for v in candidates:
            # Staying in place: always valid if no other agent has reserved the cell
            if v == agent.position:
                reserving = self._reserving_agent(v)
                if reserving is None or reserving == agent:
                    self._next[agent] = v
                    return True
                continue

            reserving = self._reserving_agent(v)
            if reserving is not None and reserving != agent:
                continue

            occupant = grid.get_agent_at(v)

            # Anti-recursion guard: only recurse into an occupant if σ(occupant)
            # is still undefined (occupant not yet in _next). An occupant already
            # in _next has reserved its target cell -> it will free its current one.
            # Checking _processed here (updated only AFTER return) re-enters agents
            # still on the stack -> infinite recursion on cycles (rotations).
            if occupant is not None and occupant not in self._next:
                self._next[agent] = v
                self.priorities[occupant] = self.priorities[agent] + EPSILON
                if not self._pibt(occupant, agent):
                    del self._next[agent]
                    continue
                self._processed.add(occupant)
                self._last_inheritance.append((agent, occupant))
                return True

            if occupant is None or occupant in self._next:
                self._next[agent] = v
                return True

        self._next[agent] = agent.position
        return False

    # ── Interface Coordinator ─────────────────────────────────────────────────

    def plan(self, agents: list[Agent], grid: Grid) -> dict[int, Position]:
        """Computes next positions for all agents (one coordinated pass)."""
        self._grid = grid
        self._init_priorities_if_needed(agents)

        for agent in self.priorities:
            self.priorities[agent] -= 1

        for agent in agents:
            if agent.position == self.goals.get(agent):
                self.priorities[agent] = float("-inf")

        self._next.clear()
        self._processed.clear()
        self._last_inheritance.clear()

        ordered = sorted(agents, key=lambda a: -self.priorities[a])
        self._last_order = list(ordered)

        for agent in ordered:
            if agent not in self._processed:
                self._pibt(agent, None)
                self._processed.add(agent)

        result = {a.agent_id: self._next.get(a, a.position) for a in agents}
        self._last_moves = {a: (a.position, result[a.agent_id]) for a in agents}
        return result

