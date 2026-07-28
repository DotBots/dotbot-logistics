import csv
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Iterable

from .record import Record


class ResultSink(ABC):
    """Where a row goes — a RunRecord, a TaskEvent or an AgentTrace alike.

    One method, so a CSV file and a database are interchangeable at the call
    site: ``main.py`` appends a record and never learns which sink it got. A
    SQL implementation is a subclass with the same signature — it needs no
    change anywhere else, which is the whole point of the seam. Generic over
    ``Record`` rather than tied to ``RunRecord``: the shape a sink needs is
    "columns() and as_row()", and TaskEvent/AgentTrace supply exactly that.
    """

    @abstractmethod
    def append(self, record: Record) -> None:
        """Input: one row.
        Output: None. Persists it. Must be safe to call on an existing store.
        """
        ...

    def append_all(self, records: Iterable[Record]) -> None:
        """Input: many rows of the same shape.
        Output: None. Appends each in turn — a sink that can do better
        (one file open instead of one per row) overrides this.
        """
        for record in records:
            self.append(record)


class CsvSink(ResultSink):
    """Appends rows to a CSV file, one sink per file.

    The header is written only when the file is created. On an existing file
    the stored header is compared against the record's fields and a mismatch
    **raises** instead of appending: a schema that gained a column mid-dataset
    would otherwise shift every later value one place to the left, producing a
    file that still parses and is quietly wrong. Failing here is the cheap
    outcome; discovering it during analysis is not.
    """

    def __init__(self, path: str | Path) -> None:
        """Input: the CSV path (created on first append).
        Output: None.
        """
        self.path = Path(path)

    def append(self, record: Record) -> None:
        """Input: one row.
        Output: None. Appends it, writing the header if the file is new.
        """
        self.append_all([record])

    def append_all(self, records: Iterable[Record]) -> None:
        """Input: many rows of the same shape.
        Output: None. Opens the file once and writes every row — the
        difference between one header check and one per row, which
        matters once a trace runs to thousands of them.
        """
        records = list(records)
        if not records:
            return

        columns = type(records[0]).columns()
        exists = self.path.exists() and self.path.stat().st_size > 0

        if exists:
            self._check_header(columns)

        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns)
            if not exists:
                writer.writeheader()
            for record in records:
                writer.writerow(record.as_row())

    def _check_header(self, columns: list[str]) -> None:
        """Input: the expected column names.
        Output: None. Raises ValueError if the file's header differs.
        """
        with self.path.open(newline="") as handle:
            stored = next(csv.reader(handle), [])
        if stored == columns:
            return

        missing = [c for c in columns if c not in stored]
        extra = [c for c in stored if c not in columns]
        raise ValueError(
            f"{self.path} was written with a different schema and appending "
            f"would misalign every column.\n"
            f"  new fields: {missing or 'none'}\n"
            f"  dropped   : {extra or 'none'}\n"
            f"Use --results with a new file, or migrate the existing one."
        )


class NullSink(ResultSink):
    """Discards records — for runs that should not be logged."""

    def append(self, record: Record) -> None:
        """Input: one row. Output: None. Does nothing."""

    def append_all(self, records: Iterable[Record]) -> None:
        """Input: many rows. Output: None. Does nothing."""
