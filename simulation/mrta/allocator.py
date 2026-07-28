from abc import ABC, abstractmethod

from core import Agent, Grid

from .task import Task


class Allocator(ABC):
    """Strategy interface for matching pending tasks to free agents."""

    @abstractmethod
    def allocate(self, pending: list[Task], free: list[Agent], grid: Grid) -> dict[Task, Agent]:
        """Input: pending tasks, free agents (no assigned task), and the
        grid (read-only, e.g. for distance-aware allocators).
        Output: a dict mapping each matched Task to its assigned Agent.
        Unmatched tasks or agents are simply absent from the result.
        """
        ...
