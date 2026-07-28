from abc import ABC, abstractmethod

from client.control import SimulationDriver


class Frontend(ABC):
    """Presentation strategy over a SimulationDriver.

    A frontend owns the clock and the output device; it never owns the
    simulation. ``step()`` stays a pure "advance by one", so pacing,
    buffering and interaction are entirely a frontend concern.

    The parameter is the *interface*, not ``SimulationController``: with
    ``--log`` the driver is a ``RunCollector`` decorating that controller,
    and a frontend must not be able to tell the difference.
    """

    def __init__(self, controller: SimulationDriver) -> None:
        """Input: the controller to drive and display.
        Output: None.
        """
        self.controller = controller

    @abstractmethod
    def run(self, steps: int) -> None:
        """Input: how many steps to run (an upper bound; an interactive
        frontend may stop earlier).
        Output: None. Blocks until the frontend is done.
        """
        ...
