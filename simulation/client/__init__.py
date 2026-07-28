"""Presentation layer: scripting API, frozen views, and frontends.

Subpackages and what each may import:

- ``client.control``   -> core, algo, mrta   (composition root)
- ``client.view``      -> core, mrta *value types only* (Position, TaskState)
- ``client.frontends`` -> core, client.view  (read-only)

The rule that matters: frontends know neither ``algo`` nor any mrta
*behaviour* (FleetManager, Allocator, TaskSource) — they see frozen
values and nothing else.

The pygame-backed names below are resolved lazily (PEP 562) so that
importing ``client.control`` or ``client.view`` never pulls pygame in.
Without this, every headless path — benchmarks, terminal runs, tests —
would pay for a display library it does not use.
"""

_LAZY = {
    "PIBTInteractiveRenderer":  ".pibt_interactive_renderer",
}
# ``StepSnapshot`` is deliberately NOT re-exported here. The legacy renderer
# defines its own, distinct from ``client.view.StepSnapshot``: exposing both
# under one package meant ``from client import StepSnapshot`` and
# ``from client.view import StepSnapshot`` silently returned different types.

__all__ = list(_LAZY)


def __getattr__(name: str):
    """Input: an attribute name.
    Output: the lazily imported renderer class it names.
    """
    if name not in _LAZY:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from importlib import import_module
    return getattr(import_module(_LAZY[name], __name__), name)


def __dir__() -> list[str]:
    """Input: none. Output: the lazily available names."""
    return sorted(__all__)
