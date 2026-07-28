import random
from typing import Optional

from core import Grid, Position

from .task import Task
from .task_source import TaskSource


class RandomTaskSource(TaskSource):
    """Emits random tasks on free cells, at a fixed rate.

    Drives autonomous runs (benchmarks, demos with no operator) where
    the fleet should stay busy without anyone clicking. Seeded through
    ``random.Random`` so a run is reproducible from its seed alone.

    The grid is captured at construction: the source needs it to pick a
    free target, and a TaskSource is polled with the step only.
    """

    def __init__(
        self,
        grid: Grid,
        every: int = 5,
        count: int = 1,
        seed: Optional[int] = None,
    ) -> None:
        """Input: the grid to sample targets from, the period in steps
        between emissions, how many tasks per emission, and the RNG seed.
        Output: None.
        """
        self._grid = grid
        self._every = max(1, every)
        self._count = count
        self._rng = random.Random(seed)

    def poll(self, current_step: int) -> list[Task]:
        """Input: the current simulation step.
        Output: ``count`` tasks on distinct free cells every ``every``
        steps, an empty list otherwise.
        """
        if current_step % self._every != 0:
            return []

        free = [
            Position(x, y)
            for x in range(self._grid.width)
            for y in range(self._grid.height)
            if not self._grid.is_blocked(Position(x, y))
        ]
        if not free:
            return []

        targets = self._rng.sample(free, min(self._count, len(free)))
        return [
            # task_id is a placeholder: FleetManager stamps a unique one
            # at intake, so sources never number into each other.
            Task(task_id=0, target=target, created_step=current_step,
                 last_improvement_step=current_step)
            for target in targets
        ]
