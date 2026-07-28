from dataclasses import dataclass, fields
from types import UnionType
from typing import Optional, Union, get_args, get_origin, get_type_hints

# Bump whenever a field is added, removed or given a new meaning. It is stored
# in every row, so a dataset assembled across code changes stays interpretable
# instead of silently mixing two definitions of the same column.
SCHEMA_VERSION = 2


@dataclass(frozen=True)
class RunRecord:
    """One experiment, flattened into one row.

    This is the schema — a CSV header and a SQL table are two renderings of
    it, which is why every field is a plain scalar (str, int, float or None)
    and nothing is nested. A list or a dict here would serialise fine to CSV
    and then have nowhere to go in a relational column.

    ``run_id`` is the natural primary key; ``git_rev`` and ``seed`` are what
    make a row reproducible after the fact.
    """

    # ── identity ─────────────────────────────────────────────────────────────
    run_id:         str
    timestamp:      str          # ISO-8601, UTC
    schema_version: int
    git_rev:        str          # short hash, "unknown" outside a repo
    label:          str          # free-text tag for the experiment

    # ── scenario ─────────────────────────────────────────────────────────────
    width:        int
    height:       int
    agents:       int
    obstacles:    int
    algo:         str
    mode:         str
    allocator:    str
    task_source:  str
    seed:         int
    patience:     int
    max_attempts: int
    zones:        int          # how many named regions were placed

    # ── run ──────────────────────────────────────────────────────────────────
    steps:        int            # steps actually executed
    wall_ms:      float
    step_ms_mean: float

    # ── task outcome (0/None in static mode: there is no fleet) ──────────────
    tasks_created:      int
    tasks_done:         int
    tasks_failed:       int
    tasks_unfinished:   int
    completion_rate:    Optional[float]
    failed_unreachable: int      # refused at intake: target invalid or blocked
    failed_stalled:     int      # gave up after max_attempts assignees
    reassignments:      int      # watchdog releases
    attempts_max:       int

    # ── latency, over completed tasks ────────────────────────────────────────
    wait_mean:    Optional[float]   # created -> assigned
    wait_max:     Optional[int]
    service_mean: Optional[float]   # assigned -> done
    service_max:  Optional[int]
    detour_mean:  Optional[float]   # service / Manhattan at assignment
    detour_max:   Optional[float]

    # ── formation drift: agents pushed off a target they had completed ───────
    drift_agents:     int
    drift_mean:       float
    drift_max:        int
    displaced_events: int
    goalless_frac:    float      # share of agent-ticks with no goal at all

    # ── fleet utilisation ────────────────────────────────────────────────────
    busy_frac: float
    idle_max:  int

    @classmethod
    def columns(cls) -> list[str]:
        """Input: none. Output: the field names, in declaration order."""
        return [f.name for f in fields(cls)]

    def as_row(self) -> dict:
        """Input: none. Output: the record as a flat dict, ready to write."""
        return {f.name: getattr(self, f.name) for f in fields(self)}

    @classmethod
    def sql_create_table(cls, table: str = "runs") -> str:
        """Input: a table name.
        Output: a CREATE TABLE statement matching this schema.

        Kept next to the dataclass so the relational shape cannot drift away
        from the record: if a field stops mapping to a column, it shows up
        here rather than at the first INSERT.
        """
        # Resolved through typing rather than by parsing the annotation's text:
        # field.type may be a class, a string or a typing construct depending
        # on the module, and guessing from its repr silently mistypes exactly
        # the Optional columns — the ones that most need to be nullable.
        sql_types = {int: "INTEGER", float: "REAL", str: "TEXT"}
        hints = get_type_hints(cls)
        lines = []

        for field in fields(cls):
            hint = hints[field.name]
            optional = False
            if get_origin(hint) in (Union, UnionType):
                args = get_args(hint)
                optional = type(None) in args
                remaining = [a for a in args if a is not type(None)]
                hint = remaining[0] if remaining else str

            column = sql_types.get(hint, "TEXT")
            null = "" if optional else " NOT NULL"
            key = " PRIMARY KEY" if field.name == "run_id" else ""
            lines.append(f"    {field.name} {column}{key}{null}")

        return f"CREATE TABLE IF NOT EXISTS {table} (\n" + ",\n".join(lines) + "\n);"
