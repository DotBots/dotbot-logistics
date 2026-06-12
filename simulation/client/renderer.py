import pygame
from core.simulation import Simulation
from core.agent import Agent
from core.objective import Objective

# Shared rendering constants (importable by PIBTRenderer)
AGENT_COLORS = [
    (31, 119, 180), (255, 127, 14), (44, 160, 44),  (214, 39, 40),
    (148, 103, 189), (140, 86, 75), (227, 119, 194), (127, 127, 127),
    (188, 189, 34),  (23, 190, 207),
]
OBJ_COLORS = {
    "objective": (255, 210, 0),
    "obstacle":  (180,  30, 30),
}
BG_A   = (240, 244, 255)
BG_B   = (255, 255, 255)
GRID_C = (200, 200, 200)
BLACK  = (0,   0,   0)
WHITE  = (255, 255, 255)
DARK   = (30,  30,  30)

CELL   = 60
MARGIN = 36


class Renderer:
    _caption = "Grid Simulation"
    # Longest possible header text — used to size the window so that
    # no text is clipped on small grids.
    _header_sample = "Step 9999  |  ◆ objective   ■ obstacle  |  close to quit"

    def __init__(self, simulation: Simulation) -> None:
        self.sim = simulation

    def run(self, steps: int, pause: float = 1.0) -> None:
        pause_ms = int(pause * 1000)
        pygame.init()
        font     = pygame.font.SysFont("monospace", 15, bold=True)
        font_sm  = pygame.font.SysFont("monospace", 11)
        font_hdr = pygame.font.SysFont("monospace", 13)
        grid_w = self.sim.grid.width * CELL
        w = max(grid_w, font_hdr.size(self._header_sample)[0] + 16)
        h = self.sim.grid.height * CELL + MARGIN
        screen = pygame.display.set_mode((w, h))
        pygame.display.set_caption(self._caption)
        clock    = pygame.time.Clock()

        self._draw(screen, font, font_sm, font_hdr, w, h)
        pygame.time.wait(pause_ms)

        for _ in range(steps):
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    return
            self.sim.step()
            self._draw(screen, font, font_sm, font_hdr, w, h)
            pygame.time.wait(pause_ms)

        while True:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    return
            clock.tick(30)

    def _draw(self, screen, font, font_sm, font_hdr, w, h) -> None:
        screen.fill(WHITE)

        for x in range(self.sim.grid.width):
            for y in range(self.sim.grid.height):
                bg = BG_A if (x + y) % 2 == 0 else BG_B
                pygame.draw.rect(screen, bg, (x * CELL, MARGIN + y * CELL, CELL, CELL))

        grid_w = self.sim.grid.width * CELL
        for x in range(self.sim.grid.width + 1):
            pygame.draw.line(screen, GRID_C, (x * CELL, MARGIN), (x * CELL, h))
        for y in range(self.sim.grid.height + 1):
            pygame.draw.line(screen, GRID_C, (0, MARGIN + y * CELL), (grid_w, MARGIN + y * CELL))

        for obj in self.sim.grid.get_all():
            if isinstance(obj, Agent) or not obj.active:
                continue
            ox = obj.position.x * CELL + CELL // 2
            oy = MARGIN + obj.position.y * CELL + CELL // 2
            is_obj = isinstance(obj, Objective)
            color = OBJ_COLORS["objective"] if is_obj else OBJ_COLORS["obstacle"]
            if is_obj:
                r = CELL // 2 - 10
                pts = [(ox, oy - r), (ox + r, oy), (ox, oy + r), (ox - r, oy)]
                pygame.draw.polygon(screen, color, pts)
                pygame.draw.polygon(screen, DARK, pts, 2)
            else:
                r = CELL // 2 - 10
                pygame.draw.rect(screen, color, (ox - r, oy - r, r * 2, r * 2))
                pygame.draw.rect(screen, DARK, (ox - r, oy - r, r * 2, r * 2), 2)
            lbl = font_sm.render("O" if is_obj else "X", True, DARK)
            screen.blit(lbl, lbl.get_rect(center=(ox, oy)))

        for agent in self.sim.agents:
            cx = agent.position.x * CELL + CELL // 2
            cy = MARGIN + agent.position.y * CELL + CELL // 2
            color = AGENT_COLORS[agent.agent_id % len(AGENT_COLORS)]
            pygame.draw.circle(screen, color, (cx, cy), CELL // 2 - 16)
            if agent.agent_id == 0:
                pygame.draw.circle(screen, BLACK, (cx, cy), CELL // 2 - 16, 2)
            lbl = font.render(str(agent.agent_id), True, WHITE)
            screen.blit(lbl, lbl.get_rect(center=(cx, cy)))

        step_label = "Initial" if self.sim.current_step == 0 else f"Step {self.sim.current_step}"
        hdr = font_hdr.render(
            f"{step_label}  |  ◆ objective   ■ obstacle  |  close to quit",
            True, DARK,
        )
        screen.blit(hdr, (8, 8))
        pygame.display.flip()
