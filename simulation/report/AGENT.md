# report/ — the experiment log

> **Package guide.** The general context — layout, dependency direction, hard rules,
> invariants and the diagrams — lives in the root [`AGENT.md`](../AGENT.md) and is **not**
> repeated here. Read it first.

`report/` turns a run into a summary row **and**, when the caller asks for it, into the detail
that row cannot carry. It is **opt-in**: without `main.py --log` no collector is built at all and
the frontend drives the `SimulationController` directly. Its only seams into the rest of the
project are `SimulationDriver` and the `StepSnapshot` it measures — it stays out of the main
class diagram and has [its own](../diagrammes/report_diagram.puml).

```python
@dataclass(frozen=True)
class RunRecord:                    # report/run_record.py — THE schema, one row per run
    run_id, timestamp, schema_version, git_rev, label      # identity
    width, height, agents, obstacles, algo, mode, task_source, seed,
    patience, max_attempts                                  # scenario
    steps, wall_ms, step_ms_mean                            # run
    tasks_created/done/failed/unfinished, completion_rate,
    failed_unreachable, failed_stalled, reassignments, attempts_max
    wait_mean/max, service_mean/max, detour_mean/max         # latency
    drift_agents, drift_mean, drift_max, displaced_events, goalless_frac
    busy_frac, idle_max
    columns() -> list[str] ; as_row() -> dict ; sql_create_table(table) -> str

@dataclass(frozen=True)
class TaskEvent:                    # report/task_event.py — one row per lifecycle transition
    run_id, step, task_id, event, agent_id, x, y, target_x, target_y, attempts, reason
    # event: created | assigned | released | done | failed
    # reason (failed only): stalled_watchdog | unreachable_intake
    columns() -> list[str] ; as_row() -> dict

@dataclass(frozen=True)
class AgentTrace:                   # report/agent_trace.py — one row per agent per step
    run_id, step, agent_id, x, y, goal_x, goal_y, task_id, task_state
    columns() -> list[str] ; as_row() -> dict

class Record(Protocol):             # report/record.py — what a sink needs, structurally
    columns() -> list[str] ; as_row() -> dict

class ResultSink(ABC):              # report/sink.py
    append(record: Record)
    append_all(records: Iterable[Record])   # default loops append(); CsvSink opens once
class CsvSink(ResultSink)           # appends; header written once, any Record shape
class NullSink(ResultSink)          # discards

class RunCollector(SimulationDriver):   # report/collector.py
    RunCollector(driver, config, label="")
    step() / run(steps)             # forwards to the wrapped driver, measuring
    snapshot() / send_batch_to()    # forwarded verbatim
    record(label=None) -> RunRecord
    events() -> list[TaskEvent]     # every task transition observed so far
    trace() -> list[AgentTrace]     # every agent, every step observed so far
```

- **Three renderings of the same observation, not three measurements.** `_observe_tasks` and
  `_observe_agents` already walk every field a `TaskEvent`/`AgentTrace` row needs in order to
  update the aggregate counters `record()` reads later; emitting the row is a few extra lines at
  the point of detection, not a second pass over the frame. `RunRecord` answers "how did the run
  go"; `TaskEvent` answers "what happened to task 7, and why"; `AgentTrace` answers "where was
  every agent, tick by tick" for the rare case even that is not enough. `main.py --log FILE.csv`
  writes all three: the summary at `FILE.csv`, one row per task transition at `FILE.events.csv`,
  one row per agent-tick at `FILE.trace.csv` — the last two only if there is anything to write
  (a static-mode run has no tasks, so no `.events.csv` is created, but agents still move, so
  `.trace.csv` still is).
- **`run_id` is generated at `RunCollector.__init__`, not at `record()`.** All three outputs must
  carry the same id so a `TaskEvent`/`AgentTrace` row can be joined back to the `RunRecord` that
  summarises it — generating it lazily at `record()` would let events observed earlier in the run
  belong to no id yet.

- **Every field is a plain scalar.** A CSV header and a SQL table are two renderings of the same
  record; anything nested would serialise to CSV and then have nowhere to go in a relational
  column. `sql_create_table()` lives next to the dataclass so the relational shape cannot drift
  from it, and resolves types through `typing.get_type_hints` rather than by parsing annotation
  text — guessing from the repr silently mistypes exactly the `Optional` columns.
- **`RunCollector` decorates the controller, it does not extend it** — but both implement
  `SimulationDriver` (`client/control/driver.py`), which is what makes the substitution a
  checked contract rather than `__getattr__` luck: a missing member now fails at instantiation
  instead of at the first click. It measures the **frame, not the engine**: every figure comes
  from the `StepSnapshot` that `step()` already returns, so the metrics can be reworked — and
  they will be — without the engine or the fleet changing. Reaching for the live `Simulation`
  and `FleetManager` would have been defensible (measuring is a stronger claim than drawing);
  it is simply not necessary, since a frame carries the task states, the goals and every
  agent's position.
- **`record()` reads the last *observed* frame**, not a fresh one. Every transition it reports
  was derived from that frame — `failed_unreachable` in particular is the part of `failed` no
  live task accounted for — so re-asking the driver would date the totals a tick later than the
  transitions explaining them, and the row would stop adding up.
- **Measurement is opt-in.** `report/` is still being validated, so it stays off the nominal
  path: without `--log` no collector is built and the frontend drives the controller itself.
  Either way the class diagram's `Frontend o-- SimulationDriver` holds.
- **Appending to a changed schema raises.** A new column would otherwise shift every later value
  one place left, producing a file that still parses and is quietly wrong. `schema_version` is
  stored on every row so a dataset spanning code changes stays interpretable; `git_rev` and
  `seed` are what make a row reproducible after the fact.
- **The run is logged in a `finally`**, so a window closed by hand or a Ctrl-C still records an
  observation; a logging failure is reported without masking the reason the run ended.

Swapping in SQL later means one new `ResultSink` subclass and nothing else — verified by loading
a `--log` CSV into sqlite with `sql_create_table()` unedited.

---
