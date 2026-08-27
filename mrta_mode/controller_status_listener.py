"""WS client for the controller's single broadcast channel,
ws://<base>/controller/ws/status -- NOT /controller/ws/dotbots, which is a
separate, bidirectional command-relay channel that never receives
broadcasts (confirmed by reading PyDotBot's dotbot/server.py directly).

Every message is a DotBotNotificationCommand; cmd=2 (UPDATE) carries *both*
waypoint-set events (data.lh2_waypoints) and continuous LH2 position updates
(data.lh2_position), the latter pushed on every advertisement frame the
controller receives (PyDotBot controller.py:405-567, confirmed against the
up-to-date repo at dotbot-workspace/repos/PyDotBot). This listener replaces
the old WaypointWatcher, which kept only the waypoints half and silently
dropped the rest: it now dispatches waypoint events to a click queue
(drained by MRTASession.tick()) and position events straight into a
LivePositionStore.

Retries forever with exponential backoff: the controller may not be up yet
at script start, or may restart mid-session, and this is meant to run
indefinitely.

stop() is real, not a flag-and-hope: the MRTA mode button starts and stops a
fresh session on every OFF/ON, so a listener that only sets a flag would leak
a thread and an open socket to the controller each cycle (Button.md C.1). It
wakes the read loop out of a blocking recv(), lets the thread unwind, and
joins it.
"""

import asyncio
import json
import queue
import threading

import websockets

from .click_event import ClickEvent
from .live_position_store import LivePositionStore


class ControllerStatusListener:
    def __init__(self, ws_url: str, position_store: LivePositionStore) -> None:
        self.ws_url = ws_url
        self._position_store = position_store
        self._click_queue: "queue.Queue[ClickEvent]" = queue.Queue()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        # Published from the listener thread once its loop is running, so
        # stop() (any thread) can schedule the wake-up onto that loop.
        self._loop: asyncio.AbstractEventLoop | None = None
        # Bound lazily to the listener thread's loop on first use.
        self._aio_stop = asyncio.Event()

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Idempotent, safe from any thread. Signals the read loop, wakes it
        out of a blocking recv(), and joins the thread so an OFF/ON cycle
        leaves no thread or open socket behind (Button.md C.1)."""
        self._stop.set()
        loop = self._loop
        if loop is not None:
            try:
                loop.call_soon_threadsafe(self._aio_stop.set)
            except RuntimeError:
                pass  # loop already stopped / closed
        t = self._thread
        if t is not None and t is not threading.current_thread():
            t.join(timeout=5.0)
            if t.is_alive():
                print("  [ws] listener thread did not stop within 5s")

    def drain_clicks(self) -> list[ClickEvent]:
        events = []
        while True:
            try:
                events.append(self._click_queue.get_nowait())
            except queue.Empty:
                break
        return events

    def _run(self) -> None:
        loop = asyncio.new_event_loop()
        self._loop = loop
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._listen_forever())
        finally:
            self._loop = None
            loop.close()

    async def _listen_forever(self) -> None:
        backoff = 1.0
        while not self._stop.is_set():
            try:
                async with websockets.connect(self.ws_url, open_timeout=5) as ws:
                    print(f"  [ws] connected to {self.ws_url}")
                    backoff = 1.0
                    await self._read_until_stop(ws)
            except (OSError, websockets.exceptions.WebSocketException) as e:
                print(f"  [ws] disconnected ({e}); retrying in {backoff:.0f}s")
            if self._stop.is_set():
                break
            if await self._sleep_or_stop(backoff):
                break
            backoff = min(backoff * 2, 10.0)

    async def _read_until_stop(self, ws) -> None:
        """Reads messages until stop() fires. Racing recv() against the stop
        Event lets stop() cut a blocking read short -- an `async for raw in
        ws` would stay parked until the socket itself closed or errored."""
        while not self._stop.is_set():
            recv_task = asyncio.ensure_future(ws.recv())
            stop_task = asyncio.ensure_future(self._aio_stop.wait())
            done, pending = await asyncio.wait(
                {recv_task, stop_task}, return_when=asyncio.FIRST_COMPLETED
            )
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            if stop_task in done:
                return
            self._handle_raw(recv_task.result())  # re-raises a closed socket

    async def _sleep_or_stop(self, delay: float) -> bool:
        """Sleep `delay` seconds; return True early if stop() fires first."""
        try:
            await asyncio.wait_for(self._aio_stop.wait(), timeout=delay)
            return True
        except asyncio.TimeoutError:
            return False

    def _handle_raw(self, raw: str) -> None:
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            return
        if msg.get("cmd") != 2:  # DotBotNotificationCommand.UPDATE
            return
        data = msg.get("data") or {}
        address = data.get("address")
        if not address:
            return

        waypoints = data.get("lh2_waypoints")
        if waypoints:
            self._click_queue.put(ClickEvent(address=address, waypoints_mm=waypoints, source="ws"))

        position = data.get("lh2_position")
        if position and "x" in position and "y" in position:
            self._position_store.update(address, position["x"], position["y"])
