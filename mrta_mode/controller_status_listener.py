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

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def drain_clicks(self) -> list[ClickEvent]:
        events = []
        while True:
            try:
                events.append(self._click_queue.get_nowait())
            except queue.Empty:
                break
        return events

    def _run(self) -> None:
        asyncio.run(self._listen_forever())

    async def _listen_forever(self) -> None:
        backoff = 1.0
        while not self._stop.is_set():
            try:
                async with websockets.connect(self.ws_url, open_timeout=5) as ws:
                    print(f"  [ws] connected to {self.ws_url}")
                    backoff = 1.0
                    async for raw in ws:
                        self._handle_raw(raw)
            except (OSError, websockets.exceptions.WebSocketException) as e:
                print(f"  [ws] disconnected ({e}); retrying in {backoff:.0f}s")
            if self._stop.is_set():
                break
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 10.0)

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
