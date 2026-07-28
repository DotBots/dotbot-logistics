import random

from core import Coordinator, Position, Agent, Grid, PlanResult, DispatchIntent

DIRECTIONS = [Position(0, 1), Position(0, -1), Position(-1, 0), Position(1, 0)]


class RandomWalkCoordinator(Coordinator):
    """Minimal coordinator: each agent walks to a random free neighbour.

    Reference implementation of the Coordinator interface — it ignores
    the intent entirely (no goals, no priorities). Cells that are invalid,
    blocked, or already targeted by another agent this step are skipped;
    with no candidate left the agent stays in place.
    """

    def plan(self, agents: list[Agent], grid: Grid, intent: DispatchIntent) -> PlanResult:
        """Input: all simulated agents, the grid (read-only), and the
        tick's DispatchIntent (ignored — this coordinator is goal-less).
        Output: a PlanResult with ``positions`` and ``moves`` filled;
        diagnostics fields are left empty.
        """
        taken: set[Position] = set()
        positions: dict[int, Position] = {}
        for agent in agents:
            candidates = [
                agent.position + d
                for d in random.sample(DIRECTIONS, len(DIRECTIONS))
            ]
            target = agent.position
            for v in candidates:
                if grid.is_valid(v) and not grid.is_blocked(v) and v not in taken:
                    target = v
                    break
            taken.add(target)
            positions[agent.agent_id] = target

        return PlanResult(
            positions=positions,
            moves={a.agent_id: (a.position, positions[a.agent_id]) for a in agents},
        )
