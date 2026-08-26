#!/usr/bin/env python3
"""
sim_dotbot_mrta.py — Manual click-to-cell MRTA driving on the DotBot simulator.

Thin CLI: argparse + wiring only. All the collaborators (REST/WS clients,
click translation, live position tracking, the simulation itself) live in
the mrta_mode package as MRTASession -- see mrta_mode/AGENT.md-equivalent
docs in diagrammes/sim_dotbot_mrta_ws_target_class_diagram.puml for the
class breakdown and rationale.

Runs indefinitely (Ctrl+C to stop). Uses the existing, unmodified PyDotBot
web UI as the operator's interface: select a DotBot, click a point on the
map, click "Apply waypoints" — the existing flow. Instead of that raw
waypoint going straight to hardware, this script detects it, snaps it to the
nearest grid cell, and hands it to PIBT as an MRTA Task restricted to that
one bot, so it navigates there step by step while avoiding every other bot
being driven the same way. Bots nobody has clicked simply stay parked.

Detection: every PUT .../waypoints call (browser or this script) triggers a
broadcast on the controller's ws://<base>/controller/ws/status channel — the
same one the frontend itself already connects to. That same channel also
carries continuous LH2 position updates, which MRTASession's
LivePositionStore uses to detect arrival instead of REST polling. A
periodic REST-based reconciliation pass recovers any click or missed
position update made while that socket was down.

No changes to the PyDotBot controller: only its existing REST + WebSocket
surface is used.

Prerequisites:
    dotbot run simulator \\
        --map-size 2000x2000 \\
        --simulator-init-state simulator_init_state.toml

Usage:
    python sim_dotbot_mrta.py              # persistent run, click-to-target via the web UI
    python sim_dotbot_mrta.py --dry-run    # connect and build the grid, send/wait nothing
    python sim_dotbot_mrta.py --map-cells 8  # 8x8 grid on 2000x2000 (250 mm cells)

Grid <-> mm mapping:
    cell (gx, gy) -> centre mm = (gx*cell_mm + cell_mm//2, gy*cell_mm + cell_mm//2)
    pos (x_mm, y_mm) -> cell   = (int(x/cell_mm), int(y/cell_mm))
"""

import argparse
import sys

from mrta_mode import MRTAConnectionError, MRTASession

DEFAULT_BASE_URL = "http://localhost:8000"
DEFAULT_CELL_MM = None      # cell size in mm; if None, derived from map_size / map_cells
DEFAULT_MAP_CELLS = 5       # grid resolution NxN (5 -> 400 mm cells, 8 -> 250 mm on 2000x2000)
DEFAULT_THRESHOLD = 100     # mm — bot considered "arrived" when distance < threshold.
                            # 100 mm: < half-cell (200 mm), > LH2 noise (~20 mm).
DEFAULT_STEP_TIMEOUT = 4.0  # s — max wait per PIBT step
DEFAULT_SETTLE = 0.3        # s — pause after arrival to let bots stop moving
DEFAULT_IDLE_SLEEP = 0.2    # s — pace of the idle/no-movement backoff loop
DEFAULT_RECONCILE_INTERVAL = 2.0  # s — period of the REST-based WS-outage safety net


def main() -> None:
    parser = argparse.ArgumentParser(
        description="PIBT -> DotBot simulator MRTA demo (persistent, click-to-target via the web UI)"
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Connect and build the grid without sending or waiting "
                             "(mainly a startup/wiring smoke test — nothing moves without a "
                             "live click)")
    parser.add_argument("--cell-mm", type=int, default=DEFAULT_CELL_MM,
                        help="Cell size in mm (default: derived from map_size / --map-cells)")
    parser.add_argument("--map-cells", type=int, default=DEFAULT_MAP_CELLS,
                        help=f"Grid resolution NxN (default: {DEFAULT_MAP_CELLS}; "
                             f"5 -> 400 mm cells, 8 -> 250 mm on a 2000x2000 map)")
    parser.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD,
                        help=f"Arrival radius per cell in mm (default: {DEFAULT_THRESHOLD})")
    parser.add_argument("--step-timeout", type=float, default=DEFAULT_STEP_TIMEOUT,
                        help=f"Max wait (s) per step (default: {DEFAULT_STEP_TIMEOUT})")
    parser.add_argument("--settle", type=float, default=DEFAULT_SETTLE,
                        help=f"Pause (s) after arrival per step (default: {DEFAULT_SETTLE})")
    parser.add_argument("--min-bots", type=int, default=2,
                        help="Minimum localised bots required at startup (default: 2)")
    parser.add_argument("--base", default=DEFAULT_BASE_URL,
                        help=f"Controller URL (default: {DEFAULT_BASE_URL})")
    parser.add_argument("--ws-url", default=None,
                        help="Controller WebSocket status URL (default: derived from --base)")
    parser.add_argument("--idle-sleep", type=float, default=DEFAULT_IDLE_SLEEP,
                        help=f"Pause (s) between idle ticks with nothing to do "
                             f"(default: {DEFAULT_IDLE_SLEEP})")
    parser.add_argument("--reconcile-interval", type=float, default=DEFAULT_RECONCILE_INTERVAL,
                        help=f"Period (s) of the REST-based WS-outage safety net "
                             f"(default: {DEFAULT_RECONCILE_INTERVAL})")
    args = parser.parse_args()

    try:
        session = MRTASession.connect(
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
    except MRTAConnectionError as e:
        print(f"Error: {e}")
        print("  -> dotbot run simulator --map-size 2000x2000 --simulator-init-state simulator_init_state.toml")
        sys.exit(1)

    session.start()
    try:
        session.run()
    finally:
        session.stop()


if __name__ == "__main__":
    main()
