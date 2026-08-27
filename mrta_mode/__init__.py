"""Classes behind the click-to-target MRTA mode: manual clicks on the
DotBot web UI drive PIBT-planned navigation on the DotBot simulator, with
arrival detected from the controller's live WS position stream.

`core`/`pibt` come from the `mapf-simulation` package (pip-installed from
git@github.com:RasdaCorentin/MAPF_Simulation, branch develop) -- no
sys.path manipulation needed, unlike the removed vendored `simulation/`
copy this package used to add to sys.path for its submodules.
"""

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

# mrta_mode.server (the console-toggle HTTP surface) is intentionally not
# re-exported here: it pulls in fastapi/uvicorn, and the CLI (sim_dotbot_mrta.py)
# must import mrta_mode without that dependency. Import it as
# `from mrta_mode.server import serve` when you actually need it.
