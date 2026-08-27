"""Live per-bot position cache fed by ControllerStatusListener's WS
lh2_position events.

Replaces the old REST poll loop (GET /controller/dotbots on a 50ms->500ms
backoff) with an event-driven wait: wait_until_all_arrived() blocks on a
Condition notified by update(), and only falls back to one REST poll if the
WS link missed an update or is down -- same safety-net principle as
ManualClickTranslator.reconcile().

The wait is interruptible: interrupt() wakes it immediately and makes it
return whatever has arrived so far, skipping the REST reconcile and the
settle sleep. The MRTA mode button's OFF path needs this -- otherwise every
OFF waits out step_timeout + settle_s (~4.3s) before the bots are even told
to stop (Button.md C.2 / D).
"""

import math
import threading
import time

import requests

from core import Coordinates2D

from .grid_state_manager import GridStateManager


class LivePositionStore:
    def __init__(self, gsm: GridStateManager):
        self._gsm = gsm
        self._condition = threading.Condition()
        self._positions_mm: dict[str, tuple[float, float]] = {}
        self._interrupted = threading.Event()

    def update(self, address: str, x_mm: float, y_mm: float) -> None:
        with self._condition:
            self._positions_mm[address] = (x_mm, y_mm)
            self._condition.notify_all()

    def interrupt(self) -> None:
        """Wake an in-flight wait_until_all_arrived() now and make it return.
        Notifies through the same Condition the wait blocks on -- setting the
        flag alone would not unpark it (Button.md C.2)."""
        with self._condition:
            self._interrupted.set()
            self._condition.notify_all()

    def clear_interrupt(self) -> None:
        self._interrupted.clear()

    def snapshot(self) -> dict[str, tuple[float, float]]:
        with self._condition:
            return dict(self._positions_mm)

    def wait_until_all_arrived(
        self,
        targets: dict[str, Coordinates2D],
        threshold: int,
        timeout: float,
        settle_s: float,
    ) -> set[str]:
        target_mm = {addr: self._gsm.cell_to_mm(cell) for addr, cell in targets.items()}
        deadline = time.time() + timeout

        with self._condition:
            arrived = self._arrived_locked(target_mm, threshold)
            while (
                len(arrived) < len(target_mm)
                and time.time() < deadline
                and not self._interrupted.is_set()
            ):
                self._condition.wait(timeout=max(0.0, deadline - time.time()))
                arrived = self._arrived_locked(target_mm, threshold)

        if self._interrupted.is_set():
            return arrived

        missing = set(target_mm) - arrived
        if missing:
            self._reconcile_from_rest()
            with self._condition:
                arrived = self._arrived_locked(target_mm, threshold)
            missing = set(target_mm) - arrived

        if missing:
            print(f"    ⚠ not arrived before timeout {timeout}s: "
                  f"{', '.join(a[:8] + '...' for a in missing)}")
        if settle_s:
            time.sleep(settle_s)
        return arrived

    def _arrived_locked(
        self, target_mm: dict[str, tuple[float, float]], threshold: int
    ) -> set[str]:
        return {
            addr
            for addr, (tx, ty) in target_mm.items()
            if (p := self._positions_mm.get(addr)) and math.hypot(p[0] - tx, p[1] - ty) < threshold
        }

    def _reconcile_from_rest(self) -> None:
        """WS may have missed an update, or the link is down -- one
        GET /controller/dotbots poll to fill the gap."""
        try:
            bots = self._gsm.fetch_dotbots()
        except requests.RequestException:
            return
        for bot in bots:
            p = bot.get("lh2_position")
            if p:
                self.update(bot["address"], p["x"], p["y"])
