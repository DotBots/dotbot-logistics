import random

from core import Agent, Grid, Position, Simulation, StaticDispatcher, WorldEntity, Zone
from algo import (
    PIBTCoordinator, RandomWalkCoordinator, EasiestAllocator, RandomAllocator,
)
from mrta import (
    CompositeTaskSource, FleetManager, QueueTaskSource, RandomTaskSource,
)

from .config import ScenarioConfig
from .controller import SimulationController

COORDINATORS = {
    "pibt":   PIBTCoordinator,
    "random": RandomWalkCoordinator,
}


def default_zones(width: int, height: int) -> tuple:
    """Input: the grid dimensions.
    Output: the three operational zones, as vertical bands.

    The vocabulary is the warehouse's, not the map's: a *rack* is the
    crate a robot carries, so the regions are named after what sits in
    them — the loading station, the working space, and the area where
    empty racks are parked.

    Derived from the grid rather than hard-coded, so ``--width 40``
    still yields three proportionate bands instead of three slivers
    against one wall.
    """
    band = max(1, width // 5)
    columns = {
        "loading station": range(0, band),
        "working space":   range(band, max(band + 1, width - band)),
        "empty-rack area": range(max(band + 1, width - band), width),
    }
    return tuple(
        Zone(i, name, [Position(x, y) for x in xs for y in range(height)])
        for i, (name, xs) in enumerate(columns.items())
        if len(xs) > 0
    )


def build(config: ScenarioConfig) -> SimulationController:
    """Input: a scenario description.
    Output: a ready-to-drive SimulationController.

    This is the composition root: the one place allowed to know both
    ``algo`` and ``mrta`` concretely. Everything downstream — the
    frontends — sees only the controller and its snapshots, which is
    what lets a new algorithm or allocator be swapped in here without
    touching a line of presentation code.
    """
    rng = random.Random(config.seed)
    grid = Grid(config.width, config.height)

    cells = [Position(x, y) for x in range(config.width) for y in range(config.height)]
    drawn = rng.sample(cells, config.agents + config.obstacles)
    agent_cells, obstacle_cells = drawn[:config.agents], drawn[config.agents:]

    coordinator = COORDINATORS[config.algo]()

    fleet = queue = None
    if config.mode == "mrta":
        # The interactive queue is always present so send_batch_to() works;
        # a background generator is composed alongside it when asked for.
        queue = QueueTaskSource()
        source = queue
        if config.tasks == "random":
            source = CompositeTaskSource(
                queue,
                RandomTaskSource(grid, every=config.task_every,
                                 count=config.task_count, seed=config.seed),
            )
        # The baseline allocator is seeded from the scenario, so "same
        # --seed, same run" holds for it too and not only for the layout.
        allocator = (
            EasiestAllocator() if config.allocator == "easiest"
            else RandomAllocator(seed=config.seed)
        )
        fleet = FleetManager(
            source=source,
            allocator=allocator,
            patience=config.patience,
            max_attempts=config.max_attempts,
        )
        dispatcher = fleet
    else:
        # Static mode: fixed goals drawn once, no allocation at all.
        goal_cells = rng.sample(cells, config.agents)
        dispatcher = StaticDispatcher(
            goals={i: goal_cells[i] for i in range(config.agents)}
        )

    sim = Simulation(grid, coordinator=coordinator, dispatcher=dispatcher)
    for i, cell in enumerate(agent_cells):
        sim.add_agent(Agent(i, cell))
    for n, cell in enumerate(obstacle_cells):
        sim.add_object(WorldEntity(n, cell, blocks_movement=True))
    # Zones label ground and block nothing, so they can be laid over the
    # agents and obstacles already drawn without contending for cells.
    for zone in config.zones:
        sim.add_object(zone)

    return SimulationController(sim, fleet=fleet, queue=queue)
