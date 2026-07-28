from client.view import StepSnapshot

from .frontend import Frontend


class HeadlessFrontend(Frontend):
    """Terminal frontend: prints each step, zero pygame.

    The fast way to exercise a scenario without a window. Reads the same
    StepSnapshot the pygame frontend does, so what it reports is exactly
    what the window would show — no separate code path to drift.
    """

    def run(self, steps: int) -> None:
        """Input: how many steps to run.
        Output: None. Prints the initial state, then every step.
        """
        self._print(self.controller.snapshot(), steps)
        for _ in range(steps):
            self._print(self.controller.step(), steps)

    def _print(self, snap: StepSnapshot, total: int) -> None:
        """Input: a snapshot and the run length.
        Output: None. Prints one frame.
        """
        label = "Initial" if snap.step == 0 else f"Step {snap.step} / {total}"
        print(f"\n{'=' * 58}\n  {label}\n{'=' * 58}")

        forced_by = {pushed: pusher for pusher, pushed in snap.result.inheritance}
        forces    = {pusher: pushed for pusher, pushed in snap.result.inheritance}
        order     = snap.result.order or sorted(snap.result.positions)

        for rank, aid in enumerate(order):
            prio = snap.result.priorities.get(aid, 0.0)
            prio_str = "-inf" if prio == float("-inf") else f"{prio:+.0f}"
            goal = snap.goals.get(aid)
            goal_str = f"  -> goal ({goal.x},{goal.y})" if goal else ""

            if aid in snap.result.moves:
                from_p, to_p = snap.result.moves[aid]
                if from_p == to_p:
                    action = f"stays        ({from_p.x},{from_p.y})"
                else:
                    action = f"({from_p.x},{from_p.y}) -> ({to_p.x},{to_p.y})"
            else:
                pos = snap.result.positions.get(aid)
                action = f"at           ({pos.x},{pos.y})" if pos else "-"

            note = ""
            if aid in forces:
                note = f"  v inherits Agent {forces[aid]}"
            elif aid in forced_by:
                note = f"  ^ forced by Agent {forced_by[aid]}"

            print(f"  #{rank+1:2}  Agent {aid:2}  prio: {prio_str:>5}  {action}{goal_str}{note}")

        if snap.tasks or snap.completed or snap.failed:
            counts = snap.counts()
            print("  tasks: " + "  ".join(f"{k}={v}" for k, v in counts.items()))

        if snap.objects:
            print("  obstacles: " + "  ".join(f"#({p.x},{p.y})" for p, _ in snap.objects))
