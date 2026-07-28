"""Multi-Robot Task Allocation: tasks, sources, allocation and dispatch.

Depends only on core (Agent, Grid, Position, Dispatcher, DispatchIntent) —
never on algo or client.
"""

from .task import Task, TaskState
from .task_source import TaskSource
from .queue_task_source import QueueTaskSource
from .random_task_source import RandomTaskSource
from .scripted_task_source import ScriptedTaskSource
from .composite_task_source import CompositeTaskSource
from .allocator import Allocator
from .fleet_manager import FleetManager

__all__ = [
    "Task", "TaskState", "TaskSource", "QueueTaskSource",
    "RandomTaskSource", "ScriptedTaskSource", "CompositeTaskSource",
    "Allocator", "FleetManager",
]
