from dataclasses import dataclass


@dataclass(frozen=True)
class ScenarioConfig:
    """Declarative description of a scenario to build.

    Frozen on purpose: a config is a record of what was asked for, so a
    run stays reproducible from it plus its seed. Building the objects
    is ``factory.build()``'s job, not this class's.
    """

    width:  int = 15
    height: int = 15
    agents: int = 20
    obstacles: int = 0

    algo: str = "pibt"      # "pibt" | "random"
    mode: str = "mrta"      # "mrta" | "static"
    seed: int = 0

    # Task allocation strategy. "easiest" (nearest free agent, greedy) is
    # the default because it is both the sensible policy and a
    # deterministic one; "random" stays as the baseline to compare against.
    allocator: str = "easiest"   # "easiest" | "random"

    # Background task generation, on top of the interactive queue that is
    # always present in MRTA mode. "none" leaves the fleet idle until
    # something asks for work; "random" keeps it busy on its own.
    tasks: str = "none"     # "none" | "random"
    task_every: int = 5
    task_count: int = 2

    # MRTA watchdog tuning — see FleetManager.
    patience: int = 12
    max_attempts: int = 3

    # Named regions placed on the grid. Empty by default: a zone is a
    # scenario decision, not a property of the engine, so a run that was
    # never told about zones must behave exactly as it did before.
    zones: tuple = ()

    def __post_init__(self) -> None:
        """Input: none. Output: None. Rejects an unbuildable scenario
        early, where the message can still name the offending field.
        """
        if self.algo not in ("pibt", "random"):
            raise ValueError(f"Unknown algo {self.algo!r} (expected 'pibt' or 'random').")
        if self.mode not in ("mrta", "static"):
            raise ValueError(f"Unknown mode {self.mode!r} (expected 'mrta' or 'static').")
        if self.allocator not in ("easiest", "random"):
            raise ValueError(
                f"Unknown allocator {self.allocator!r} (expected 'easiest' or 'random')."
            )
        if self.tasks not in ("none", "random"):
            raise ValueError(f"Unknown tasks {self.tasks!r} (expected 'none' or 'random').")
        if self.agents + self.obstacles > self.width * self.height:
            raise ValueError(
                f"{self.agents} agents + {self.obstacles} obstacles do not fit "
                f"in a {self.width}x{self.height} grid."
            )
        # Caught here rather than by Grid.place: the offending zone can
        # still be named, which is the whole point of validating a config.
        for zone in self.zones:
            for cell in zone.cells:
                if not (0 <= cell.x < self.width and 0 <= cell.y < self.height):
                    raise ValueError(
                        f"Zone {zone.name!r} has cell {cell} outside the "
                        f"{self.width}x{self.height} grid."
                    )
