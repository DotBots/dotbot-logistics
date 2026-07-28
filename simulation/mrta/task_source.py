from abc import ABC, abstractmethod

from .task import Task


class TaskSource(ABC):
    """Strategy interface for producing new tasks over time.

    Polled once per dispatch cycle by FleetManager; implementations
    decide which new tasks (if any) become available at the given
    simulation step (e.g. reading a schedule, a queue, or user input).
    """

    @abstractmethod
    def poll(self, current_step: int) -> list[Task]:
        """Input: the current simulation step.
        Output: newly available tasks at this step (possibly empty).
        """
        ...
