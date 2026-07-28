from typing import Protocol, runtime_checkable


@runtime_checkable
class Record(Protocol):
    """What a sink needs from a row: its columns and itself as a flat dict.

    RunRecord, TaskEvent and AgentTrace all satisfy this structurally —
    nothing here forces them into a shared base class, so each stays a
    plain frozen dataclass and a sink stays agnostic to which one it is
    writing.
    """

    @classmethod
    def columns(cls) -> list[str]: ...

    def as_row(self) -> dict: ...
