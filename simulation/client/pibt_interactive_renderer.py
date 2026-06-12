"""
PIBTInteractiveRenderer — PIBT renderer with keyboard navigation.

Pre-computes all steps then allows free navigation through history:
  Space     pause / play
  ->        step forward
  <-        step back
  Q / Esc   quit

The footer bar shows for each step the priority order,
each agent's move, and any priority inheritances triggered.

Usage:
    from client import PIBTInteractiveRenderer
    PIBTInteractiveRenderer(sim, pibt).run(steps=80, auto_ms=500)
"""

from dataclasses import dataclass, field

from core.simulation import Simulation
from core.agent import Agent
from core.objective import Objective
from algo.pibt import PIBT

MUTED      = ( 90,  90, 110)
SEP        = (150, 150, 180)
HDR_BG     = (230, 234, 250)

CELL       = 60
MARGIN     = 38   # header height
FOOTER_HDR = 22   # ligne titre du pied de page
FOOTER_ROW = 20   # hauteur par ligne d'agent dans le pied de page


@dataclass
class StepSnapshot:
    step:        int
    positions:   dict = field(default_factory=dict)   # agent_id → Position
    priorities:  dict = field(default_factory=dict)   # agent_id → float
    order:       list = field(default_factory=list)   # [agent_id, ...] prio desc.
    moves:       dict = field(default_factory=dict)   # agent_id → (Position, Position)
    inheritance: list = field(default_factory=list)   # [(pusher_id, pushed_id), ...]
    objects:     list = field(default_factory=list)   # [(Position, "objective"|"obstacle")]
    goals:       dict = field(default_factory=dict)   # agent_id → Position


class PIBTInteractiveRenderer:
    """Interactive PIBT renderer: pre-computes history, navigates with keyboard."""

    def __init__(self, simulation: Simulation, pibt: PIBT) -> None:
        self.sim  = simulation
        self.pibt = pibt

    # ── Public API ────────────────────────────────────────────────────────────

    def run(self, steps: int = 30, auto_ms: int = 600) -> None:
        """Pre-computes `steps` steps then opens the interactive window."""
        history = self._build_history(steps)
        self._run_loop(history, auto_ms)

    def run_debug(self, steps: int = 30) -> None:
        """Debug mode: prints each step to the terminal, no pygame window."""
        history = self._build_history(steps)
        total   = len(history) - 1
        for snap in history:
            self._print_snapshot(snap, total)

    def _print_snapshot(self, snap: "StepSnapshot", total: int) -> None:
        label = "Initial" if snap.step == 0 else f"Step {snap.step} / {total}"
        print(f"\n{'═' * 50}")
        print(f"  {label}")
        print(f"{'═' * 50}")

        if snap.step == 0:
            for aid, pos in sorted(snap.positions.items()):
                goal = snap.goals.get(aid)
                goal_str = f"  goal: ({goal.x},{goal.y})" if goal else ""
                print(f"  Agent {aid}  pos: ({pos.x},{pos.y}){goal_str}")
        else:
            forced_by = {pushed: pusher for pusher, pushed in snap.inheritance}
            forces    = {pusher: pushed for pusher, pushed in snap.inheritance}
            order     = snap.order if snap.order else sorted(snap.positions)

            for rank, aid in enumerate(order):
                prio = snap.priorities.get(aid, 0)
                prio_str = "-inf" if prio == float("-inf") else f"{prio:+.0f}"

                if aid in snap.moves:
                    from_p, to_p = snap.moves[aid]
                    if prio == float("-inf"):
                        action = f"goal reached ({to_p.x},{to_p.y})"
                    elif from_p == to_p:
                        action = f"stays        ({from_p.x},{from_p.y})"
                    else:
                        action = f"({from_p.x},{from_p.y}) → ({to_p.x},{to_p.y})"
                else:
                    action = "—"

                inherit = ""
                if aid in forces:
                    inherit = f"  ↓ inherits Agent {forces[aid]}"
                elif aid in forced_by:
                    inherit = f"  ↑ forced by Agent {forced_by[aid]}"

                print(f"  #{rank+1:2}  Agent {aid}  prio: {prio_str:>5}  {action}{inherit}")

        if snap.objects:
            obj_str = "  ".join(
                f"{'◆' if k == 'objective' else '■'}({p.x},{p.y})"
                for p, k in snap.objects
            )
            print(f"  objects: {obj_str}")

    # ── History building ──────────────────────────────────────────────────────

    def _build_history(self, total_steps: int) -> list[StepSnapshot]:
        goals_by_id = {a.agent_id: pos for a, pos in self.pibt.goals.items()}
        history = [StepSnapshot(
            step=0,
            positions={a.agent_id: a.position for a in self.sim.agents},
            objects=self._snapshot_objects(),
            goals=goals_by_id,
        )]
        for _ in range(total_steps):
            self.sim.step()
            history.append(StepSnapshot(
                step=self.sim.current_step,
                positions={a.agent_id: a.position for a in self.sim.agents},
                priorities={a.agent_id: p for a, p in self.pibt.priorities.items()},
                order=[a.agent_id for a in self.pibt._last_order],
                moves={a.agent_id: (f, t) for a, (f, t) in self.pibt._last_moves.items()},
                inheritance=[(p.agent_id, q.agent_id) for p, q in self.pibt._last_inheritance],
                objects=self._snapshot_objects(),
                goals=goals_by_id,
            ))
        return history

    def _snapshot_objects(self) -> list[tuple]:
        result = []
        for e in self.sim.grid.get_all():
            if isinstance(e, Agent) or not e.active:
                continue
            kind = "objective" if isinstance(e, Objective) else "obstacle"
            result.append((e.position, kind))
        return result

    # ── Interactive pygame loop ───────────────────────────────────────────────

    def _run_loop(self, history: list[StepSnapshot], auto_ms: int) -> None:
        import pygame
        from client.renderer import AGENT_COLORS, OBJ_COLORS, BG_A, BG_B, GRID_C, BLACK, WHITE, DARK

        n_agents = len(history[0].positions)
        total    = len(history) - 1
        h = MARGIN + self.sim.grid.height * CELL + FOOTER_HDR + n_agents * FOOTER_ROW + 10

        pygame.init()
        font     = pygame.font.SysFont("monospace", 15, bold=True)
        font_sm  = pygame.font.SysFont("monospace", 11)
        font_hdr = pygame.font.SysFont("monospace", 13)

        # Window width: wide enough for the longest text (header +
        # footer lines), otherwise display is clipped on a small grid.
        w = max(self.sim.grid.width * CELL,
                self._required_text_width(history, total, font_hdr, font_sm))

        screen = pygame.display.set_mode((w, h))
        pygame.display.set_caption("PIBT — interactive navigation")
        clock    = pygame.time.Clock()

        idx          = 0
        playing      = False
        last_advance = pygame.time.get_ticks()

        def render() -> None:
            screen.fill(WHITE)
            snap = history[idx]
            self._draw_header(screen, snap, total, playing, font_hdr, w)
            self._draw_grid(screen, snap, font, font_sm)
            self._draw_footer(screen, snap, font_sm, font_hdr, w,
                              MARGIN + self.sim.grid.height * CELL)
            pygame.display.flip()

        render()

        while True:
            now = pygame.time.get_ticks()

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    return
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_SPACE:
                        playing = not playing
                        last_advance = now
                        render()
                    elif event.key == pygame.K_RIGHT and idx < total:
                        idx += 1
                        render()
                    elif event.key == pygame.K_LEFT and idx > 0:
                        idx -= 1
                        render()
                    elif event.key in (pygame.K_q, pygame.K_ESCAPE):
                        pygame.quit()
                        return

            if playing and now - last_advance >= auto_ms:
                if idx < total:
                    idx += 1
                    last_advance = now
                    render()
                else:
                    playing = False
                    render()

            clock.tick(60)

    # ── Sizing ────────────────────────────────────────────────────────────────

    def _required_text_width(self, history: list[StepSnapshot], total: int,
                             font_hdr, font_sm) -> int:
        """Pixel width of the longest text (header + footer lines).

        Reproduces the strings built in `_draw_header` / `_draw_footer`
        to measure exactly what will be drawn, including indents.
        """
        widest = 0

        # Header (font_hdr, indent x=10) — "⏸ pause" is longer than "▶ play".
        for step in (total,):
            label = f"Step {step} / {total}"
            text  = f"{label}   ⏸ pause   Space=pause   ← →=navigate   Q=quit"
            widest = max(widest, 10 + font_hdr.size(text)[0])

        # Footer lines (font_sm, indent x=30).
        for snap in history:
            if snap.step == 0:
                continue
            forced_by = {pushed: pusher for pusher, pushed in snap.inheritance}
            forces    = {pusher: pushed for pusher, pushed in snap.inheritance}
            order     = snap.order if snap.order else sorted(snap.positions)
            for rank, aid in enumerate(order):
                prio = snap.priorities.get(aid, 0)
                prio_str = "−∞" if prio == float("-inf") else f"{prio:+.0f}"
                if aid in snap.moves:
                    from_p, to_p = snap.moves[aid]
                    if prio == float("-inf"):
                        action = f"goal reached  ({to_p.x},{to_p.y})"
                    elif from_p == to_p:
                        action = f"stays  ({from_p.x},{from_p.y})"
                    else:
                        action = f"({from_p.x},{from_p.y}) → ({to_p.x},{to_p.y})"
                else:
                    action = "—"
                inherit_note = ""
                if aid in forces:
                    inherit_note = f"   ↓ inherits Agent {forces[aid]}"
                elif aid in forced_by:
                    inherit_note = f"   ↑ forced by Agent {forced_by[aid]}"
                text = f"#{rank+1}  Agent {aid}  |  prio: {prio_str}  |  {action}{inherit_note}"
                widest = max(widest, 30 + font_sm.size(text)[0])

        return widest + 16   # marge droite

    # ── Drawing ───────────────────────────────────────────────────────────────

    def _draw_header(self, screen, snap: StepSnapshot, total: int,
                     playing: bool, font_hdr, w: int) -> None:
        import pygame
        from client.renderer import DARK
        pygame.draw.rect(screen, HDR_BG, (0, 0, w, MARGIN))
        label  = "Initial" if snap.step == 0 else f"Step {snap.step} / {total}"
        status = "▶ play" if playing else "⏸ pause"
        lbl = font_hdr.render(
            f"{label}   {status}   Space=pause   ← →=navigate   Q=quit",
            True, DARK,
        )
        screen.blit(lbl, (10, (MARGIN - lbl.get_height()) // 2))

    def _draw_grid(self, screen, snap: StepSnapshot, font, font_sm) -> None:
        import pygame
        from client.renderer import AGENT_COLORS, OBJ_COLORS, BG_A, BG_B, GRID_C, BLACK, WHITE, DARK
        n_cols, n_rows = self.sim.grid.width, self.sim.grid.height

        for x in range(n_cols):
            for y in range(n_rows):
                bg = BG_A if (x + y) % 2 == 0 else BG_B
                pygame.draw.rect(screen, bg, (x * CELL, MARGIN + y * CELL, CELL, CELL))
        for x in range(n_cols + 1):
            pygame.draw.line(screen, GRID_C,
                             (x * CELL, MARGIN), (x * CELL, MARGIN + n_rows * CELL))
        for y in range(n_rows + 1):
            pygame.draw.line(screen, GRID_C,
                             (0, MARGIN + y * CELL), (n_cols * CELL, MARGIN + y * CELL))

        for aid, goal in snap.goals.items():
            color = AGENT_COLORS[aid % len(AGENT_COLORS)]
            pygame.draw.rect(screen, color,
                             (goal.x * CELL + 3, MARGIN + goal.y * CELL + 3, CELL - 6, CELL - 6), 2)

        for pos, kind in snap.objects:
            ox = pos.x * CELL + CELL // 2
            oy = MARGIN + pos.y * CELL + CELL // 2
            color = OBJ_COLORS.get(kind, (128, 128, 128))
            r = CELL // 2 - 10
            if kind == "objective":
                pts = [(ox, oy - r), (ox + r, oy), (ox, oy + r), (ox - r, oy)]
                pygame.draw.polygon(screen, color, pts)
                pygame.draw.polygon(screen, DARK, pts, 2)
            else:
                pygame.draw.rect(screen, color, (ox - r, oy - r, r * 2, r * 2))
                pygame.draw.rect(screen, DARK,  (ox - r, oy - r, r * 2, r * 2), 2)
            screen.blit(
                font_sm.render("O" if kind == "objective" else "X", True, DARK),
                font_sm.render("O", True, DARK).get_rect(center=(ox, oy)),
            )

        for aid, pos in snap.positions.items():
            cx = pos.x * CELL + CELL // 2
            cy = MARGIN + pos.y * CELL + CELL // 2
            color = AGENT_COLORS[aid % len(AGENT_COLORS)]
            r = CELL // 2 - 14
            pygame.draw.circle(screen, color, (cx, cy), r)
            pygame.draw.circle(screen, BLACK, (cx, cy), r, 1)
            screen.blit(font.render(str(aid), True, WHITE),
                        font.render(str(aid), True, WHITE).get_rect(center=(cx, cy)))
            prio = snap.priorities.get(aid)
            if prio is not None:
                pstr = "−∞" if prio == float("-inf") else f"{prio:.0f}"
                screen.blit(font_sm.render(pstr, True, DARK),
                            (pos.x * CELL + 2, MARGIN + pos.y * CELL + 2))

    def _draw_footer(self, screen, snap: StepSnapshot, font_sm, font_hdr,
                     w: int, footer_top: int) -> None:
        import pygame
        from client.renderer import AGENT_COLORS, DARK
        pygame.draw.line(screen, SEP, (0, footer_top), (w, footer_top), 1)

        if snap.step == 0:
            screen.blit(font_hdr.render("— Initial state —", True, MUTED), (12, footer_top + 6))
            return

        screen.blit(
            font_hdr.render(
                f"Step {snap.step} — priority order  |  □ goal   ■ obstacle",
                True, MUTED,
            ),
            (12, footer_top + 4),
        )

        forced_by = {pushed: pusher for pusher, pushed in snap.inheritance}
        forces    = {pusher: pushed for pusher, pushed in snap.inheritance}
        order     = snap.order if snap.order else sorted(snap.positions)

        for rank, aid in enumerate(order):
            row_y = footer_top + FOOTER_HDR + rank * FOOTER_ROW + 2
            color = AGENT_COLORS[aid % len(AGENT_COLORS)]
            badge_cy = row_y + FOOTER_ROW // 2
            pygame.draw.circle(screen, color, (14, badge_cy), 8)
            pygame.draw.circle(screen, DARK,  (14, badge_cy), 8, 1)

            prio = snap.priorities.get(aid, 0)
            prio_str = "−∞" if prio == float("-inf") else f"{prio:+.0f}"

            if aid in snap.moves:
                from_p, to_p = snap.moves[aid]
                if prio == float("-inf"):
                    action = f"goal reached  ({to_p.x},{to_p.y})"
                elif from_p == to_p:
                    action = f"stays  ({from_p.x},{from_p.y})"
                else:
                    action = f"({from_p.x},{from_p.y}) → ({to_p.x},{to_p.y})"
            else:
                action = "—"

            inherit_note = ""
            if aid in forces:
                inherit_note = f"   ↓ inherits Agent {forces[aid]}"
            elif aid in forced_by:
                inherit_note = f"   ↑ forced by Agent {forced_by[aid]}"

            lbl = font_sm.render(
                f"#{rank+1}  Agent {aid}  |  prio: {prio_str}  |  {action}{inherit_note}",
                True, DARK,
            )
            screen.blit(lbl, (30, row_y + (FOOTER_ROW - lbl.get_height()) // 2))
