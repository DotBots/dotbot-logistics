import random
from typing import Optional

from core import Agent, Grid
from mrta import Task, Allocator


class RandomAllocator(Allocator):
    """Baseline allocator: pairs pending tasks with free agents at random.

    No notion of distance or cost — useful as a reference/baseline when
    comparing smarter allocation strategies.

    The RNG is **owned**, not the ``random`` module's global one. Drawing
    from the global instance made two runs of the same ``--seed``
    disagree: the scenario was reproducible, the allocation was not, and
    a ``RunRecord`` storing the seed promised a reproducibility it could
    not deliver. Passing ``seed=None`` restores the old behaviour
    explicitly, for whoever actually wants an unseeded baseline.
    """

    def __init__(self, seed: Optional[int] = None) -> None:
        """Input: the RNG seed (None draws from the OS entropy pool).
        Output: None.
        """
        self._rng = random.Random(seed)

    def allocate(self, pending: list[Task], free: list[Agent], grid: Grid) -> dict[Task, Agent]:
        """Input: pending tasks, free agents, and the grid (unused).
        Output: a random one-to-one matching, limited by whichever of
        pending/free is shorter; leftover tasks or agents are unmatched.
        """
        tasks = list(pending)
        agents = list(free)
        self._rng.shuffle(tasks)
        self._rng.shuffle(agents)
        return dict(zip(tasks, agents))
