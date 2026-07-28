"""Scripting API: build a scenario and drive it. No pygame anywhere.

This is the composition root — the only part of ``client`` allowed to
import ``algo`` and mrta behaviour, because choosing the algorithm and
wiring the fleet is precisely its job. Frontends depend on ``client.view``
instead, and stay ignorant of both.
"""

from .config import ScenarioConfig
from .driver import SimulationDriver
from .controller import SimulationController
from .factory import build, default_zones

__all__ = [
    "ScenarioConfig", "SimulationDriver", "SimulationController",
    "build", "default_zones",
]
