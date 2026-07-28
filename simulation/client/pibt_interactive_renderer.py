"""
PIBTInteractiveRenderer — PIBT renderer with keyboard navigation.

Pre-computes all steps then allows free navigation through history:
  Space     pause / play
  ->        step forward
  <-        step back
  Q / Esc   quit

The footer bar shows for each step the priority order,
each agent's move, and any priority inheritances triggered.

Each snapshot wraps the PlanResult returned by ``sim.step()`` — the
renderer depends only on core, never on the algo package. Goals are
read from ``sim.coordinator.goals`` (public coordinator attribute).

Usage:
    from client import PIBTInteractiveRenderer
    PIBTInteractiveRenderer(sim).run(steps=80, auto_ms=500)
"""

from dataclasses import dataclass, field

from core import Simulation, Agent, PlanResult

MUTED      = ( 90,  90, 110)
SEP        = (150, 150, 180)
HDR_BG     = (230, 234, 250)

CELL       = 60
MARGIN     = 38   # header height
FOOTER_HDR = 22   # footer section title height
FOOTER_ROW = 20   # height per agent row in footer


@dataclass
class StepSnapshot:
    """Frozen view of one simulation step, built for later navigation.

    Wraps the PlanResult of the step plus the display context that the
    result does not carry (goals and static objects on the grid).
    """

    step:    int
    result:  PlanResult                            # plan of this step (positions, diagnostics)
    goals:   dict = field(default_factory=dict)    # agent_id → Position
    objects: list = field(default_factory=list)    # [(Position, "obstacle")]


class PIBTInteractiveRenderer:
    """Interactive PIBT renderer: pre-computes history, navigates with keyboard."""

    def __init__(self, simulation: Simulation) -> None:
        """Input: the simulation to display (its coordinator is expected
        to expose a public ``goals`` dict[Agent, Position]).
        Output: None.
        """
        self.sim = simulation

    # ── Public API ────────────────────────────────────────────────────────────

    def run(self, steps: int = 30, auto_ms: int = 600) -> None:
        """Input: number of steps to pre-compute and auto-play delay (ms).
        Output: None. Opens the interactive pygame window.
        """
        history = self._build_history(steps)
        self._run_loop(history, auto_ms)

    def run_debug(self, steps: int = 30) -> None:
        """Input: number of steps to pre-compute.
        Output: None. Prints each step to the terminal, no pygame window.
        """
        history = self._build_history(steps)
        total   = len(history) - 1
        for snap in history:
            self._print_snapshot(snap, total)

    def _print_snapshot(self, snap: "StepSnapshot", total: int) -> None:
        """Input: a snapshot and the total number of steps.
        Output: None. Prints the snapshot to the terminal.
        """
        label = "Initial" if snap.step == 0 else f"Step {snap.step} / {total}"
        print(f"\n{'═' * 50}")
        print(f"  {label}")
        print(f"{'═' * 50}")

        if snap.step == 0:
            for aid, pos in sorted(snap.result.positions.items()):
                goal = snap.goals.get(aid)
                goal_str = f"  goal: ({goal.x},{goal.y})" if goal else ""
                print(f"  Agent {aid}  pos: ({pos.x},{pos.y}){goal_str}")
        else:
            forced_by = {pushed: pusher for pusher, pushed in snap.result.inheritance}
            forces    = {pusher: pushed for pusher, pushed in snap.result.inheritance}
            order     = snap.result.order if snap.result.order else sorted(snap.result.positions)

            for rank, aid in enumerate(order):
                prio = snap.result.priorities.get(aid, 0)
                prio_str = "-inf" if prio == float("-inf") else f"{prio:+.0f}"

                if aid in snap.result.moves:
                    from_p, to_p = snap.result.moves[aid]
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
            obj_str = "  ".join(f"■({p.x},{p.y})" for p, k in snap.objects)
            print(f"  obstacles: {obj_str}")

    # ── History building ──────────────────────────────────────────────────────

    def _build_history(self, total_steps: int) -> list[StepSnapshot]:
        """Input: number of steps to simulate.
        Output: list of StepSnapshot (index 0 = initial state), built by
        running the simulation and capturing each step's PlanResult and
        goals. Goals now come from the tick's intent (via the coordinator),
        so they are captured per frame after each step; the initial frame
        is back-filled from the first step's goals.
        """
        history = [StepSnapshot(
            step=0,
            result=PlanResult(
                positions={a.agent_id: a.position for a in self.sim.agents},
            ),
            goals={},
            objects=self._snapshot_objects(),
        )]
        for _ in range(total_steps):
            result = self.sim.step()
            goals_now = {
                a.agent_id: pos
                for a, pos in getattr(self.sim.coordinator, "goals", {}).items()
            }
            history.append(StepSnapshot(
                step=self.sim.current_step,
                result=result,
                goals=goals_now,
                objects=self._snapshot_objects(),
            ))
        # Back-fill the initial frame's goals from the first step (correct
        # for static goals; a reasonable preview for dynamic ones).
        if len(history) > 1 and not history[0].goals:
            history[0].goals = history[1].goals
        return history

    def _snapshot_objects(self) -> list[tuple]:
        """Input: none.
        Output: list of (Position, kind) for active static entities
        currently on the grid.
        """
        result = []
        for e in self.sim.grid.get_all():
            if isinstance(e, Agent) or not e.active:
                continue
            result.append((e.position, "obstacle"))
        return result

    # ── Interactive pygame loop ───────────────────────────────────────────────

    def _run_loop(self, history: list[StepSnapshot], auto_ms: int) -> None:
        """Input: pre-computed history and auto-play delay (ms).
        Output: None. Runs the interactive pygame event loop.
        """
        import pygame
        from client.palette import AGENT_COLORS, OBJ_COLORS, BG_A, BG_B, GRID_C, BLACK, WHITE, DARK

        n_agents = len(history[0].result.positions)
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
            """Input: none (closure). Output: None. Redraws the frame."""
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
        """Input: pre-computed history, total steps and the two fonts.
        Output: pixel width of the longest text (header + footer lines).

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
            forced_by = {pushed: pusher for pusher, pushed in snap.result.inheritance}
            forces    = {pusher: pushed for pusher, pushed in snap.result.inheritance}
            order     = snap.result.order if snap.result.order else sorted(snap.result.positions)
            for rank, aid in enumerate(order):
                prio = snap.result.priorities.get(aid, 0)
                prio_str = "−∞" if prio == float("-inf") else f"{prio:+.0f}"
                if aid in snap.result.moves:
                    from_p, to_p = snap.result.moves[aid]
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

        return widest + 16   # right margin

    # ── Drawing ───────────────────────────────────────────────────────────────

    def _draw_header(self, screen, snap: StepSnapshot, total: int,
                     playing: bool, font_hdr, w: int) -> None:
        """Input: surface, snapshot, total steps, play state, font, width.
        Output: None. Draws the header bar.
        """
        import pygame
        from client.palette import DARK
        pygame.draw.rect(screen, HDR_BG, (0, 0, w, MARGIN))
        label  = "Initial" if snap.step == 0 else f"Step {snap.step} / {total}"
        status = "▶ play" if playing else "⏸ pause"
        lbl = font_hdr.render(
            f"{label}   {status}   Space=pause   ← →=navigate   Q=quit",
            True, DARK,
        )
        screen.blit(lbl, (10, (MARGIN - lbl.get_height()) // 2))

    def _draw_grid(self, screen, snap: StepSnapshot, font, font_sm) -> None:
        """Input: surface, snapshot and fonts.
        Output: None. Draws the grid, goals, obstacles and agents.
        """
        import pygame
        from client.palette import AGENT_COLORS, OBJ_COLORS, BG_A, BG_B, GRID_C, BLACK, WHITE, DARK
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
            pygame.draw.rect(screen, color, (ox - r, oy - r, r * 2, r * 2))
            pygame.draw.rect(screen, DARK,  (ox - r, oy - r, r * 2, r * 2), 2)
            lbl = font_sm.render("X", True, DARK)
            screen.blit(lbl, lbl.get_rect(center=(ox, oy)))

        for aid, pos in snap.result.positions.items():
            cx = pos.x * CELL + CELL // 2
            cy = MARGIN + pos.y * CELL + CELL // 2
            color = AGENT_COLORS[aid % len(AGENT_COLORS)]
            r = CELL // 2 - 14
            pygame.draw.circle(screen, color, (cx, cy), r)
            pygame.draw.circle(screen, BLACK, (cx, cy), r, 1)
            screen.blit(font.render(str(aid), True, WHITE),
                        font.render(str(aid), True, WHITE).get_rect(center=(cx, cy)))
            prio = snap.result.priorities.get(aid)
            if prio is not None:
                pstr = "−∞" if prio == float("-inf") else f"{prio:.0f}"
                screen.blit(font_sm.render(pstr, True, DARK),
                            (pos.x * CELL + 2, MARGIN + pos.y * CELL + 2))

    def _draw_footer(self, screen, snap: StepSnapshot, font_sm, font_hdr,
                     w: int, footer_top: int) -> None:
        """Input: surface, snapshot, fonts, width and footer top y.
        Output: None. Draws the per-agent priority/move/inheritance rows.
        """
        import pygame
        from client.palette import AGENT_COLORS, DARK
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

        forced_by = {pushed: pusher for pusher, pushed in snap.result.inheritance}
        forces    = {pusher: pushed for pusher, pushed in snap.result.inheritance}
        order     = snap.result.order if snap.result.order else sorted(snap.result.positions)

        for rank, aid in enumerate(order):
            row_y = footer_top + FOOTER_HDR + rank * FOOTER_ROW + 2
            color = AGENT_COLORS[aid % len(AGENT_COLORS)]
            badge_cy = row_y + FOOTER_ROW // 2
            pygame.draw.circle(screen, color, (14, badge_cy), 8)
            pygame.draw.circle(screen, DARK,  (14, badge_cy), 8, 1)

            prio = snap.result.priorities.get(aid, 0)
            prio_str = "−∞" if prio == float("-inf") else f"{prio:+.0f}"

            if aid in snap.result.moves:
                from_p, to_p = snap.result.moves[aid]
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
