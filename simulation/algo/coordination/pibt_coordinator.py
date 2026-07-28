"""
PIBTCoordinator — Priority Inheritance with Backtracking
Okumura et al., 2022.

PIBT is split into focused classes: reservations live in
ReservationTable, priorities in PriorityManager. The recursive core
(_pibt / _h) receives `grid` as an argument instead of storing it, so
no per-step grid state lives on the coordinator.

Goals and base priorities are read from the tick's DispatchIntent
(passed to plan()), never set by external mutation. The coordinator is
stateless about allocation but keeps its own navigation state across
ticks (dynamic priority drift, reservations).

Usage:
    pibt = PIBTCoordinator()
    intent = DispatchIntent(goals={0: Position(9, 9)}, priorities={0: 5.0})
    sim = Simulation(grid, coordinator=pibt, dispatcher=StaticDispatcher(intent.goals, intent.priorities))
    sim.add_agent(Agent(0, Position(0, 0)))

plan() returns a PlanResult DTO carrying next positions plus PIBT
diagnostics (priority order, moves, priority inheritances).
"""

from __future__ import annotations

from typing import Optional

from core import Position, Coordinator, Agent, Grid, PlanResult, DispatchIntent

from .reservation_table import ReservationTable
from .priority_manager import PriorityManager

DIRS    = [Position(0, -1), Position(0, 1), Position(-1, 0), Position(1, 0)]
EPSILON = 1e-3


class PIBTCoordinator(Coordinator):
    """PIBT coordinator — implements the Coordinator interface.

    Plugged into Simulation.coordinator, replaces per-agent movement
    computation with a single coordinated planning pass driven by agent
    priorities (Priority Inheritance with Backtracking).
    """

    def __init__(self) -> None:
        """Input: none.
        Output: None. Goals/priorities arrive per tick via the intent.
        """
        self.goals: dict[Agent, Position] = {}
        self._reservations = ReservationTable()
        self._priorities = PriorityManager()
        self._processed: set[Agent] = set()
        self._inheritance: list[tuple[Agent, Agent]] = []
        # Last (goal, priority) seen per agent_id — used to re-seed the base
        # priority ONLY when the allocation intent actually changes, so the
        # dynamic priority drift (anti-starvation) is never clobbered.
        self._last_intent: dict[int, tuple[Optional[Position], Optional[float]]] = {}
        # Base priority overwritten by the goal-reached -inf demotion, kept so
        # the demotion can be undone when the agent is no longer at its goal.
        self._demoted: dict[Agent, float] = {}
        # Base priority overwritten by a priority-inheritance boost this tick,
        # kept so it can be undone once this tick's cascade is resolved.
        self._inherited: dict[Agent, float] = {}

    # ── Heuristic ────────────────────────────────────────────────────────────

    def _h(self, pos: Position, agent: Agent, grid: Grid) -> int:
        """Input: a candidate position, the agent it is evaluated for,
        and the grid.
        Output: Manhattan distance from pos to the agent's goal.
        """
        g = self.goals[agent]
        return abs(pos.x - g.x) + abs(pos.y - g.y)

    # ── Recursive PIBT algorithm (Algorithm 1) ───────────────────────────────

    def _pibt(self, agent: Agent, parent: Optional[Agent], grid: Grid) -> bool:
        """Input: the agent being placed, its pusher (None at top level),
        and the grid.
        Output: True if a valid next cell was reserved for the agent.
        """
        candidates: list[Position] = []
        for d in DIRS:
            v = agent.position + d
            if grid.is_valid(v) and not any(
                e.blocks_movement and e.active
                for e in grid.get_entities_at(v)
                if not isinstance(e, Agent)
            ):
                candidates.append(v)
        candidates.sort(key=lambda v: self._h(v, agent, grid))

        # An agent already at its goal prefers to stay in place
        if agent.position == self.goals.get(agent):
            candidates.insert(0, agent.position)

        if parent is not None:
            candidates = [v for v in candidates if v != parent.position]

        for v in candidates:
            # Staying in place: always valid if no other agent has reserved the cell
            if v == agent.position:
                reserving = self._reservations.get_reserving_agent(v)
                if reserving is None or reserving == agent:
                    self._reservations.reserve(agent, v)
                    return True
                continue

            reserving = self._reservations.get_reserving_agent(v)
            if reserving is not None and reserving != agent:
                continue

            occupant = grid.get_agent_at(v)

            # Anti-recursion guard: only recurse into an occupant if sigma(occupant)
            # is still undefined (occupant has not reserved a cell yet). An
            # occupant that already reserved a cell will free its current one.
            # Checking _processed here (updated only AFTER return) would
            # re-enter agents still on the call stack -> infinite recursion
            # on cycles (rotations).
            if occupant is not None and self._reservations.get_reservation(occupant) is None:
                self._reservations.reserve(agent, v)
                self._inherited.setdefault(occupant, self._priorities.get_base(occupant))
                self._priorities.set_base(occupant, self._priorities.get_priority(agent) + EPSILON)
                if not self._pibt(occupant, agent, grid):
                    self._reservations.release(agent)
                    continue
                self._processed.add(occupant)
                self._inheritance.append((agent, occupant))
                return True

            if occupant is None or self._reservations.get_reservation(occupant) is not None:
                self._reservations.reserve(agent, v)
                return True

        self._reservations.reserve(agent, agent.position)
        return False

    # ── Interface Coordinator ─────────────────────────────────────────────────

    def _apply_intent(self, agents: list[Agent], intent: DispatchIntent) -> None:
        """Input: the agents and this tick's intent.
        Output: None. Rebuilds ``self.goals`` (fallback: stay in place) and
        re-seeds a base priority ONLY when an agent's goal changed or its
        business priority is strictly different from the previous tick —
        never otherwise, to preserve the dynamic priority drift.
        """
        self.goals = {a: intent.goals.get(a.agent_id, a.position) for a in agents}

        for agent in agents:
            aid = agent.agent_id
            prio = intent.priorities.get(aid)
            if prio is None:
                continue
            key = (intent.goals.get(aid), prio)
            if self._last_intent.get(aid) != key:
                self._priorities.set_base(agent, prio)
                # A freshly seeded base wins over any pending restore.
                self._demoted.pop(agent, None)
            self._last_intent[aid] = key

    def plan(self, agents: list[Agent], grid: Grid, intent: DispatchIntent) -> PlanResult:
        """Input: all simulated agents, the grid (read-only), and this
        tick's DispatchIntent (goals + optional priorities).
        Output: a PlanResult with next positions plus PIBT diagnostics
        (priority order, moves, priority inheritances, priorities).
        """
        # Seed goals + base priorities from the intent BEFORE decaying, so a
        # freshly-seeded base is decayed once this tick like every other.
        self._apply_intent(agents, intent)

        self._priorities.update(agents)

        # "At its goal" is a *state*, so the -inf demotion it triggers must be
        # undone as soon as the state stops holding — the goal moved, or the
        # agent was pushed off it by priority inheritance. Writing -inf into
        # the base without ever restoring it stranded the agent at the bottom
        # of the ranking for the rest of the run.
        for agent in agents:
            if agent.position == self.goals.get(agent):
                if agent not in self._demoted:
                    self._demoted[agent] = self._priorities.get_base(agent)
                    self._priorities.set_base(agent, float("-inf"))
            elif agent in self._demoted:
                self._priorities.set_base(agent, self._demoted.pop(agent))

        self._reservations.clear()
        self._processed.clear()
        self._inheritance.clear()
        self._inherited.clear()

        ordered = sorted(agents, key=lambda a: -self._priorities.get_priority(a))

        for agent in ordered:
            if agent not in self._processed:
                self._pibt(agent, None, grid)
                self._processed.add(agent)

        positions: dict[int, Position] = {}
        for a in agents:
            reservation = self._reservations.get_reservation(a)
            positions[a.agent_id] = reservation if reservation is not None else a.position

        result = PlanResult(
            positions=positions,
            moves={a.agent_id: (a.position, positions[a.agent_id]) for a in agents},
            order=[a.agent_id for a in ordered],
            inheritance=[(p.agent_id, q.agent_id) for p, q in self._inheritance],
            priorities={a.agent_id: self._priorities.get_priority(a) for a in agents},
        )

        # Inheritance boosts are scoped to this tick's cascade: undo them now
        # so an agent pushed once does not keep outranking its pusher forever.
        for agent, base in self._inherited.items():
            self._priorities.set_base(agent, base)

        return result
