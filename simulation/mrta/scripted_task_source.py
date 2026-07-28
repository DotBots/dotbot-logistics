from .task import Task
from .task_source import TaskSource


class ScriptedTaskSource(TaskSource):
    """Replays a fixed schedule of tasks: ``{step: [Task, ...]}``.

    The deterministic counterpart of RandomTaskSource. Because both the
    arrival times and the targets are fixed up front, a scenario built
    on it is fully reproducible — which is what makes it the natural
    basis for regression scenarios.
    """

    def __init__(self, schedule: dict[int, list[Task]]) -> None:
        """Input: a mapping from simulation step to the tasks that
        become available at that step.
        Output: None.
        """
        self._schedule = {step: list(tasks) for step, tasks in schedule.items()}

    def poll(self, current_step: int) -> list[Task]:
        """Input: the current simulation step.
        Output: the tasks scheduled for this step, each delivered once.
        """
        return self._schedule.pop(current_step, [])
