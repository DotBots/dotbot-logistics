from .task import Task
from .task_source import TaskSource


class CompositeTaskSource(TaskSource):
    """Merges several sources into one, polled in order.

    A FleetManager takes a single source, but work legitimately arrives
    from more than one place: an operator queueing a batch by hand *and*
    a generator producing background load. Composing them keeps that a
    property of the scenario rather than a special case inside
    FleetManager.
    """

    def __init__(self, *sources: TaskSource) -> None:
        """Input: the sources to merge, in polling order.
        Output: None.
        """
        self.sources = list(sources)

    def poll(self, current_step: int) -> list[Task]:
        """Input: the current simulation step.
        Output: the concatenation of every source's tasks for this step.
        """
        tasks: list[Task] = []
        for source in self.sources:
            tasks.extend(source.poll(current_step))
        return tasks
