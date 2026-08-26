"""Classes behind the click-to-target MRTA mode: manual clicks on the
DotBot web UI drive PIBT-planned navigation on the DotBot simulator, with
arrival detected from the controller's live WS position stream.

Adds `simulation/` to sys.path (same convention as every root-level bridge
script) so submodules can import `core`/`algo`/`mrta` without each caller
having to repeat the sys.path.insert() dance.
"""

import os
import sys

_SIMULATION_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "simulation"
)
if _SIMULATION_DIR not in sys.path:
    sys.path.insert(0, _SIMULATION_DIR)

from .click_event import ClickEvent
from .controller_status_listener import ControllerStatusListener
from .grid_state_manager import GridStateManager
from .live_position_store import LivePositionStore
from .manual_click_translator import ManualClickTranslator
from .mrta_session import MRTAConnectionError, MRTASession
from .waypoint_command_client import WaypointCommandClient

__all__ = [
    "ClickEvent",
    "ControllerStatusListener",
    "GridStateManager",
    "LivePositionStore",
    "ManualClickTranslator",
    "MRTAConnectionError",
    "MRTASession",
    "WaypointCommandClient",
]
