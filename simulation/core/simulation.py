from .grid import Grid
from .agent import Agent
from .entity import WorldEntity
from .objective import Objective
from .coordinator import Coordinator


class Simulation:
    def __init__(self, grid: Grid, coordinator: Coordinator) -> None:
        self.grid = grid
        self.agents: list[Agent] = []
        self.entities: list[WorldEntity] = []
        self._pending: list[WorldEntity] = []
        self.current_step = 0
        self.coordinator = coordinator

    def add_agent(self, agent: Agent) -> None:
        self.grid.place(agent)
        self.agents.append(agent)

    def add_object(self, entity: WorldEntity) -> None:
        self.entities.append(entity)
        if entity.appear_at <= self.current_step:
            self.grid.place(entity)
        else:
            self._pending.append(entity)

    def step(self) -> None:
        self.current_step += 1

        # 1. Spawn pending entities whose appear_at step has been reached
        due = [e for e in self._pending if e.appear_at <= self.current_step]
        for entity in due:
            self.grid.place(entity)
            self._pending.remove(entity)

        # 2. Coordinator computes all next positions (global plan)
        next_positions = self.coordinator.plan(self.agents, self.grid)

        # 3. Lift phase: remove moving agents from the grid first
        # so they do not artificially block each other
        moving_agents = []
        for agent in self.agents:
            target_pos = next_positions.get(agent.agent_id, agent.position)
            if target_pos != agent.position:
                moving_agents.append((agent, target_pos))
                self.grid.remove(agent)  # agent leaves its current cell

        # 4. Place phase: apply movement and put agents back on the grid
        for agent, target_pos in moving_agents:
            agent.move_to(target_pos)
            self.grid.place(agent)  # will raise cleanly if cell is already occupied

        # 5. Collect objectives
        for agent in self.agents:
            for obj in self.grid.get_entities_at(agent.position, Objective):
                if obj.owner is None or obj.owner is agent:
                    obj.collected = True
                    self.grid.remove(obj)

    def __repr__(self) -> str:
        return f"Simulation(grid={self.grid}, agents={len(self.agents)}, step={self.current_step})"
