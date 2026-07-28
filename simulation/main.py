#!/usr/bin/env python3
"""
main.py — entry point for a MAPF scenario.

    python main.py                                     # 15x15, 20 agents, PIBT + MRTA, window
    python main.py --tasks random                      # same, with self-generated work
    python main.py --frontend headless --tasks random --steps 20
    python main.py --algo random --mode static         # the historical random-walk demo
    python main.py --agents 40 --width 25 --height 25 --obstacles 20

In the window: select agents (click, or drag a rubber band), then click
a cell to send the batch there. Space plays/pauses, arrows step and
replay, A/C select all or clear, Q quits.

Everything below is argument parsing: building the scenario is
client.control.build()'s job, and driving it is the frontend's.
"""

import argparse
from pathlib import Path

from client.control import ScenarioConfig, build, default_zones
from report import CsvSink, RunCollector


def parse_args() -> argparse.Namespace:
    """Input: none (reads sys.argv).
    Output: the parsed command-line arguments.
    """
    parser = argparse.ArgumentParser(description="Run a MAPF scenario.")
    parser.add_argument("--width",     type=int, default=15)
    parser.add_argument("--height",    type=int, default=15)
    parser.add_argument("--agents",    type=int, default=20)
    parser.add_argument("--obstacles", type=int, default=0)
    parser.add_argument("--algo",      choices=("pibt", "random"), default="pibt",
                        help="navigation algorithm (default: pibt)")
    parser.add_argument("--mode",      choices=("mrta", "static"), default="mrta",
                        help="mrta = task allocation, static = fixed goals")
    parser.add_argument("--allocator", choices=("easiest", "random"), default="easiest",
                        help="task allocation strategy (default: easiest — the "
                             "nearest free agent takes each task)")
    parser.add_argument("--tasks",     choices=("none", "random"), default="none",
                        help="background task generation on top of the "
                             "interactive queue (default: none)")
    parser.add_argument("--zones",     action="store_true",
                        help="lay the three operational zones over the grid "
                             "(loading station / working space / empty-rack area)")
    parser.add_argument("--frontend",  choices=("pygame", "headless"), default="pygame")
    parser.add_argument("--steps",     type=int, default=0,
                        help="step budget; 0 means run until quit (pygame only)")
    parser.add_argument("--seed",      type=int, default=0)
    parser.add_argument("--tick-ms",   type=int, default=350,
                        help="wall-clock duration of one step, pygame only")
    parser.add_argument("--log",       type=str, default=None, metavar="FILE.csv",
                        help="append one row per run to FILE (.csv only); "
                             "omit to run without logging")
    parser.add_argument("--label",     type=str, default="",
                        help="free-text tag stored with this run, --log only")
    args = parser.parse_args()

    # Only CSV for now. Refusing an unknown suffix here rather than writing
    # CSV into a file named .db is the difference between a clear error and a
    # dataset someone trusts for a week before opening it.
    if args.log is not None and not args.log.endswith(".csv"):
        parser.error(f"--log only supports .csv for now, got {args.log!r}")
    return args


def main() -> None:
    """Input: none. Output: None. Builds the scenario and runs it."""
    args = parse_args()

    config = ScenarioConfig(
        width=args.width,
        height=args.height,
        agents=args.agents,
        obstacles=args.obstacles,
        algo=args.algo,
        mode=args.mode,
        allocator=args.allocator,
        tasks=args.tasks,
        seed=args.seed,
        zones=default_zones(args.width, args.height) if args.zones else (),
    )

    # Measurement is opt-in. Without --log the frontend drives the controller
    # itself, which is the relation the class diagram states; with it, the
    # frontend drives a RunCollector decorating that controller. Both are
    # SimulationDriver, so the frontend cannot tell which it got.
    driver = build(config)
    collector = RunCollector(driver, config, label=args.label) if args.log else None

    try:
        if args.frontend == "headless":
            from client.frontends import HeadlessFrontend
            HeadlessFrontend(collector or driver).run(args.steps or 20)
        else:
            from client.frontends import PygameFrontend
            PygameFrontend(collector or driver, tick_ms=args.tick_ms).run(args.steps)
    finally:
        # Logged even on Ctrl-C or a closed window: a run that was interrupted
        # is still an observation, and losing it is how a session's worth of
        # experiments quietly goes missing.
        if collector is not None:
            record = collector.record()
            try:
                CsvSink(args.log).append(record)
                # Alongside the summary row: a per-task event log and a
                # per-step trace, one debugging aid a RunRecord's aggregate
                # counts cannot be — which task failed, which agent held it.
                log_path = Path(args.log)
                CsvSink(log_path.with_name(log_path.stem + ".events.csv")).append_all(
                    collector.events())
                CsvSink(log_path.with_name(log_path.stem + ".trace.csv")).append_all(
                    collector.trace())
                print(f"\nrun {record.run_id} ({record.steps} steps) -> "
                      f"{args.log} (+.events.csv, +.trace.csv)")
            except Exception as exc:
                # Never let a logging failure replace the reason the run ended
                # — if the run itself raised, that traceback is the useful one.
                print(f"\ncould not log run {record.run_id}: {exc}")


if __name__ == "__main__":
    main()
