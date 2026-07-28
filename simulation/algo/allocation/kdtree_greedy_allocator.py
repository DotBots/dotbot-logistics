from core import Agent, Grid
from mrta import Task, Allocator


class KDTreeGreedyAllocator(Allocator):
    """Greedy nearest-agent allocator backed by a KD-tree spatial index.

    Intended design: for each pending task (highest priority first),
    query a KD-tree built over free agent positions for the nearest
    agent, assign it, then remove both from further consideration.

    Design stub — not implemented yet. The indexing strategy (rebuild
    cost per dispatch cycle, tie-breaking, distance metric on a
    discrete grid) needs to be discussed before implementation.
    """

    def __init__(self) -> None:
        """Input: none.
        Output: None. ``_tree`` is left unset (placeholder for a KD-tree
        index, e.g. ``scipy.spatial.KDTree``), pending the design
        discussion.
        """
        self._tree = None

    def allocate(self, pending: list[Task], free: list[Agent], grid: Grid) -> dict[Task, Agent]:
        """Input: pending tasks, free agents, and the grid.
        Output: not implemented — see class docstring.
        """
        raise NotImplementedError(
            "KDTreeGreedyAllocator is a design stub; implementation "
            "pending discussion."
        )

    def _nearest_free(self, task: Task, free: list[Agent]) -> Agent:
        """Input: a task and the list of free agents.
        Output: not implemented — see class docstring.
        """
        raise NotImplementedError(
            "KDTreeGreedyAllocator is a design stub; implementation "
            "pending discussion."
        )
