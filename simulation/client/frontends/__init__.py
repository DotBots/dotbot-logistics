"""Frontends: presentation only.

Depend on ``core`` and ``client.view`` (frozen values) — never on
``algo``, never on mrta behaviour. PygameFrontend is imported lazily so
that using the headless one costs nothing.
"""

from .frontend import Frontend
from .headless_frontend import HeadlessFrontend

__all__ = ["Frontend", "HeadlessFrontend", "PygameFrontend"]


def __getattr__(name: str):
    """Input: an attribute name.
    Output: PygameFrontend, imported on first use (pygame is heavy and
    unavailable on headless machines).
    """
    if name == "PygameFrontend":
        from .pygame_frontend import PygameFrontend
        return PygameFrontend
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
