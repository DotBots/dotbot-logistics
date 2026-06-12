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

        # 1. Apparition des entités en attente
        due = [e for e in self._pending if e.appear_at <= self.current_step]
        for entity in due:
            self.grid.place(entity)
            self._pending.remove(entity)

        # 2. PIBT calcule toutes les positions futures (plan global)
        next_positions = self.coordinator.plan(self.agents, self.grid)

        # 3. Phase de "Levée" : on retire de la grille ceux qui se déplacent
        # pour éviter qu'ils ne bloquent artificiellement les autres
        moving_agents = []
        for agent in self.agents:
            target_pos = next_positions.get(agent.agent_id, agent.position)
            if target_pos != agent.position:
                moving_agents.append((agent, target_pos))
                self.grid.remove(agent) # L'agent quitte son ancienne case

        # 4. Phase de "Pose" : on applique le déplacement interne et on replace sur la grille
        for agent, target_pos in moving_agents:
            agent.move_to(target_pos)
            self.grid.place(agent) # Plantera proprement si la case est déjà occupée !

        # 5. Résolution des objectifs (inchangé)
        for agent in self.agents:
            for obj in self.grid.get_entities_at(agent.position, Objective):
                if obj.owner is None or obj.owner is agent:
                    obj.collected = True
                    self.grid.remove(obj)

    def __repr__(self) -> str:
        return f"Simulation(grid={self.grid}, agents={len(self.agents)}, step={self.current_step})"
