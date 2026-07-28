from core import Agent, Grid, Position
from mrta import Task, Allocator


class EasiestAllocator(Allocator):
    """Greedy allocator: each task takes the free agent nearest to it.

    "Easiest" is the cheapest *visible* match, not the optimal one. The
    tasks are served in priority order and each takes the closest free
    agent still available; an earlier, more urgent task may therefore
    take an agent that a later one would have used better. Proving a
    globally optimal assignment is a different algorithm (Hungarian, or
    the KD-tree variant still stubbed out next door) and a different
    cost — this is the sensible default, not the last word.

    Distance is Manhattan, not path length: the grid is 4-connected, so
    it is exact in the absence of obstacles and a lower bound otherwise.
    Consulting the planner for a true distance would make allocation
    depend on navigation, which is the coupling ``DispatchIntent`` exists
    to prevent.

    Unlike ``RandomAllocator`` it draws no random numbers at all, so a
    run is reproducible from its seed — which is what makes a logged
    ``RunRecord`` worth comparing against another.
    """

    def allocate(self, pending: list[Task], free: list[Agent], grid: Grid) -> dict[Task, Agent]:
        """Input: pending tasks, free agents, and the grid (unused).
        Output: a one-to-one matching, tasks served most-urgent first,
        each taking the nearest agent still unclaimed.
        """
        available = list(free)
        matched: dict[Task, Agent] = {}

        # Ties broken by task_id then agent_id: an allocator that shuffles
        # under the hood makes two runs of one seed disagree, and there is
        # no reading a benchmark whose baseline moves.
        for task in sorted(pending, key=lambda t: (-t.priority, t.task_id)):
            if not available:
                break
            agent = min(
                available,
                key=lambda a: (self._manhattan(a.position, task.target), a.agent_id),
            )
            available.remove(agent)
            matched[task] = agent
        return matched

    @staticmethod
    def _manhattan(a: Position, b: Position) -> int:
        """Input: two positions.
        Output: their Manhattan distance.
        """
        return abs(a.x - b.x) + abs(a.y - b.y)
