#!/usr/bin/env python3
"""
mrta_server.py — HTTP server that puts MRTA mode behind the console's toggle.

Same click-to-target behaviour as `sim_dotbot_mrta.py`, but instead of a
Ctrl+C CLI loop it exposes the two routes the DotBot web console's MRTA
pill calls (through PyDotBot's `/mrta/*` proxy):

    GET  /status              -> {"state", "bots", "detail"}
    POST /mode  {"on": bool}  -> 202 transition state / 409 while busy

See `Button.md` for the contract and `mrta_mode/server.py` for the state
machine. The MRTA session is (re)built fresh on every ON: the fleet is
snapshotted at connect() time, so OFF/ON is how you pick up bots that
joined late.

Prerequisites:
    dotbot run simulator \\
        --map-size 2000x2000 \\
        --simulator-init-state simulator_init_state.toml

    # PyDotBot controller started with --mrta-url http://localhost:8002
    # (or [run.controller] mrta_url, or DOTBOT_MRTA_URL) so /mrta/* proxies here.

Usage:
    python mrta_server.py                     # serve on 0.0.0.0:8002
    python mrta_server.py --mrta-port 9002
    python mrta_server.py --dry-run           # build the session, tick without sending
"""

import argparse

from mrta_mode.server import serve

# Mirrors sim_dotbot_mrta.py's defaults; a shared CLI is Roadmap item 1.
DEFAULT_BASE_URL = "http://localhost:8000"
DEFAULT_CELL_MM = None
DEFAULT_MAP_CELLS = 5
DEFAULT_THRESHOLD = 100
DEFAULT_STEP_TIMEOUT = 4.0
DEFAULT_SETTLE = 0.3
DEFAULT_IDLE_SLEEP = 0.2
DEFAULT_RECONCILE_INTERVAL = 2.0
DEFAULT_MRTA_HOST = "0.0.0.0"
DEFAULT_MRTA_PORT = 8002


def main() -> None:
    parser = argparse.ArgumentParser(
        description="MRTA mode HTTP server (drives sim_dotbot_mrta's MRTASession from the console toggle)"
    )
    parser.add_argument("--mrta-host", default=DEFAULT_MRTA_HOST,
                        help=f"Bind address for this server (default: {DEFAULT_MRTA_HOST})")
    parser.add_argument("--mrta-port", type=int, default=DEFAULT_MRTA_PORT,
                        help=f"Bind port for this server (default: {DEFAULT_MRTA_PORT})")
    parser.add_argument("--dry-run", action="store_true",
                        help="Build the session and tick without sending waypoints or waiting")
    parser.add_argument("--cell-mm", type=int, default=DEFAULT_CELL_MM,
                        help="Cell size in mm (default: derived from map_size / --map-cells)")
    parser.add_argument("--map-cells", type=int, default=DEFAULT_MAP_CELLS,
                        help=f"Grid resolution NxN (default: {DEFAULT_MAP_CELLS})")
    parser.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD,
                        help=f"Arrival radius per cell in mm (default: {DEFAULT_THRESHOLD})")
    parser.add_argument("--step-timeout", type=float, default=DEFAULT_STEP_TIMEOUT,
                        help=f"Max wait (s) per step (default: {DEFAULT_STEP_TIMEOUT})")
    parser.add_argument("--settle", type=float, default=DEFAULT_SETTLE,
                        help=f"Pause (s) after arrival per step (default: {DEFAULT_SETTLE})")
    parser.add_argument("--min-bots", type=int, default=2,
                        help="Minimum localised bots required to turn MRTA on (default: 2)")
    parser.add_argument("--base", default=DEFAULT_BASE_URL,
                        help=f"Controller URL (default: {DEFAULT_BASE_URL})")
    parser.add_argument("--ws-url", default=None,
                        help="Controller WebSocket status URL (default: derived from --base)")
    parser.add_argument("--idle-sleep", type=float, default=DEFAULT_IDLE_SLEEP,
                        help=f"Pause (s) between idle ticks (default: {DEFAULT_IDLE_SLEEP})")
    parser.add_argument("--reconcile-interval", type=float, default=DEFAULT_RECONCILE_INTERVAL,
                        help=f"Period (s) of the REST-based WS-outage safety net "
                             f"(default: {DEFAULT_RECONCILE_INTERVAL})")
    args = parser.parse_args()

    connect_kwargs = dict(
        base_url=args.base,
        cell_mm=args.cell_mm,
        map_cells=args.map_cells,
        min_bots=args.min_bots,
        threshold=args.threshold,
        step_timeout=args.step_timeout,
        settle_s=args.settle,
        dry_run=args.dry_run,
        idle_sleep=args.idle_sleep,
        reconcile_interval=args.reconcile_interval,
        ws_url=args.ws_url,
    )
    serve(connect_kwargs, host=args.mrta_host, port=args.mrta_port)


if __name__ == "__main__":
    main()
