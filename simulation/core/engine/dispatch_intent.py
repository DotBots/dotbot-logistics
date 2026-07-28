from dataclasses import dataclass, field

from ..entities.position import Position


@dataclass(frozen=True)
class DispatchIntent:
    """Immutable, absolute allocation state requested for the current tick.

    Produced by a ``Dispatcher`` and consumed by ``Coordinator.plan()``.
    It carries the *complete* desired state every tick (not deltas), so
    the coordinator never has to remember allocation across ticks:

    - ``goals``      : agent_id -> target Position;
    - ``priorities`` : agent_id -> allocation priority (float), optional
      per agent — a coordinator without priorities simply ignores it.

    Being frozen and agent_id-keyed, one intent is an auditable record of
    exactly what allocation asked for, before the planner alters anything.
    """

    goals:      dict[int, Position] = field(default_factory=dict)
    priorities: dict[int, float]    = field(default_factory=dict)
