from dataclasses import dataclass, field

from ..entities.position import Position


@dataclass(frozen=True)
class PlanResult:
    """Data Transfer Object returned by every ``Coordinator.plan()`` call.

    Uniform contract for comparing coordination algorithms:

    - ``positions`` / ``moves`` — universal contract (every coordinator
      fills them);
    - ``order`` / ``inheritance`` / ``priorities`` — optional diagnostics
      (left empty outside the PIBT family).

    Keys are ``agent_id`` integers so the DTO can cross the core→client
    boundary without exposing Agent objects, keeping renderers decoupled
    from the algo package.

    **Frozen**, like every other value that crosses that boundary
    (``Position``, ``DispatchIntent``, ``TaskView``). The same instance is
    referenced by ``SimulationController._last_result`` *and* archived in a
    ``StepSnapshot``; a snapshot is documented to read identically N steps
    later, and that guarantee has to rest on the type rather than on the
    convention that coordinators build the object in one go and no one
    writes to it afterwards.
    """

    positions:   dict[int, Position] = field(default_factory=dict)   # agent_id → next Position
    moves:       dict[int, tuple]    = field(default_factory=dict)   # agent_id → (from, to)
    order:       list[int]           = field(default_factory=list)   # agent_ids in priority order
    inheritance: list[tuple]         = field(default_factory=list)   # (pusher_id, pushed_id)
    priorities:  dict[int, float]    = field(default_factory=dict)   # agent_id → priority
