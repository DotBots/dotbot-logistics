"""Experiment logging: measure a run, persist it, keep it queryable later.

    RunRecord   — one experiment, flat scalars only (the summary row)
    TaskEvent   — one task-lifecycle transition (created/assigned/done/failed)
    AgentTrace  — one agent, one step (replay-quality detail)
    ResultSink  — where a record goes (CsvSink now, a SQL sink later)
    RunCollector— decorates a SimulationController and measures it

Depends on ``core`` and ``mrta`` for value types; it observes a controller
through public attributes only, so the metrics can be reworked without the
engine or the fleet having to change.
"""

from .agent_trace import AgentTrace
from .run_record import RunRecord, SCHEMA_VERSION
from .sink import ResultSink, CsvSink, NullSink
from .task_event import TaskEvent
from .collector import RunCollector

__all__ = [
    "RunRecord", "SCHEMA_VERSION",
    "TaskEvent", "AgentTrace",
    "ResultSink", "CsvSink", "NullSink",
    "RunCollector",
]
