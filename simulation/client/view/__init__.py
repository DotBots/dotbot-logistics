"""Frozen value types shared by the control API and the frontends.

Depends on ``core`` and on ``mrta`` for *value* types only (Position,
TaskState) — never on mrta behaviour (FleetManager, Allocator,
TaskSource) and never on ``algo``.
"""

from .task_view import TaskView
from .zone_view import ZoneView
from .snapshot import StepSnapshot

__all__ = ["TaskView", "ZoneView", "StepSnapshot"]
