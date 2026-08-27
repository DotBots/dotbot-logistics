"""HTTP surface for the MRTA mode toggle in the DotBot web console.

`Button.md` is the contract. Two routes, served here and reached by the
console through PyDotBot's `/mrta/*` proxy (the `/mrta` prefix is stripped
on the way, exactly like `/swarmit/*`):

    GET  /status              -> {"state", "bots", "detail"}
    POST /mode  {"on": bool}  -> 202 with the transition state;
                                 409 while a transition is already running

`state` is one of `off | connecting | on | stopping`. The console's fifth
state, `unavailable`, is inferred client-side from a 404/502/timeout and
must never be sent from here.

State lives in this process, guarded by a lock: two consoles polling every
1.5 s must agree, and closing one must change nothing (Button.md "Polling").

The MRTA session runs on a dedicated thread, never on the asyncio loop that
serves these routes -- `tick()` blocks for up to `step_timeout + settle_s`
inside `wait_until_all_arrived` (Button.md B.3).

    off  --POST {on:true}--> connecting --connect() ok----> on
                             connecting --connect() fails--> off   (reason in `detail`)
    on   --POST {on:false}-> stopping   --stop+join+halt---> off

Every ON builds a *fresh* `MRTASession` via `connect()`: the fleet is
snapshotted at `connect()` time, so OFF/ON is the way to pick up bots that
joined late -- there is no resume (Button.md B.2).
"""

import threading

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .mrta_session import MRTAConnectionError, MRTASession

_TRANSITIONING = ("connecting", "stopping")
_DETAIL_MAX = 160


def _short(msg: str) -> str:
    """`detail` is a one-line tooltip (Button.md "The contract"). connect()'s
    RequestException string can be a multi-line urllib3 dump -- keep the
    front (where "Connection refused" / "Name or service not known" sits)
    and clip the rest."""
    one_line = " ".join(msg.split())
    return one_line if len(one_line) <= _DETAIL_MAX else one_line[: _DETAIL_MAX - 1] + "…"


class MrtaMode:
    """The state machine + session lifecycle behind the two routes. Owns the
    single source of truth for the mode's state; the HTTP layer only reads
    and pokes it."""

    def __init__(self, connect_kwargs: dict) -> None:
        self._connect_kwargs = connect_kwargs
        self._lock = threading.Lock()
        self._state = "off"
        self._detail: str | None = None
        self._session: MRTASession | None = None
        self._tick_thread: threading.Thread | None = None
        self._stop_flag = threading.Event()

    # ---- read path -------------------------------------------------------
    def status(self) -> dict:
        with self._lock:
            return self._status_locked()

    def _status_locked(self) -> dict:
        running = self._state in ("on", "stopping") and self._session is not None
        return {
            "state": self._state,
            "bots": len(self._session.addresses) if running else None,
            "detail": self._detail,
        }

    # ---- write path ----------------------------------------------------
    def set_mode(self, on: bool) -> tuple[int, dict]:
        """Returns (status_code, body). 409 while a transition runs -- the
        console reads a refusal as "ask again next poll", so refusing a
        double click is cheap and a second session is not. A request that
        matches the settled state is a no-op answered 202."""
        with self._lock:
            if self._state in _TRANSITIONING:
                return 409, self._status_locked()
            if on and self._state == "off":
                self._state = "connecting"
                self._detail = "building a PIBT session from the current fleet"
                self._stop_flag = threading.Event()
                self._tick_thread = threading.Thread(
                    target=self._run_session, name="mrta-tick", daemon=True
                )
                self._tick_thread.start()
            elif not on and self._state == "on":
                self._state = "stopping"
                self._detail = "stopping the bots"
                threading.Thread(
                    target=self._stop_session, name="mrta-stop", daemon=True
                ).start()
            return 202, self._status_locked()

    # ---- worker threads ----------------------------------------------
    def _run_session(self) -> None:
        try:
            session = MRTASession.connect(**self._connect_kwargs)
        except MRTAConnectionError as e:
            self._settle_off(_short(str(e)))
            return
        except Exception as e:  # keep the server alive on any connect failure
            self._settle_off(_short(f"connect failed: {e}"))
            return

        session.start()
        with self._lock:
            self._session = session
            self._state = "on"
            self._detail = None

        try:
            while not self._stop_flag.is_set():
                session.tick()
        except Exception as e:  # noqa: BLE001 - a planner bug must not wedge the server
            print(f"  [mrta] tick loop crashed: {e}")
        finally:
            session.stop()
            with self._lock:
                if self._state == "on":  # crashed rather than a clean OFF
                    self._state = "off"
                    self._detail = "the planning loop stopped unexpectedly"
                    self._session = None

    def _stop_session(self) -> None:
        with self._lock:
            session = self._session
            tick_thread = self._tick_thread

        # Button.md D order: set the stop flag -> wake the arrival wait ->
        # join the tick thread -> only THEN clear the waypoints, so no
        # in-flight send_all_parallel() can re-arm a bot a moment later.
        self._stop_flag.set()
        if session is not None:
            session.stop()
        if tick_thread is not None:
            tick_thread.join(timeout=10.0)
            if tick_thread.is_alive():
                print("  [mrta] tick thread did not stop within 10s")
        if session is not None:
            try:
                session.halt_all()
            except Exception as e:  # noqa: BLE001
                print(f"  [mrta] halt_all error: {e}")

        with self._lock:
            self._state = "off"
            self._detail = None
            self._session = None
            self._tick_thread = None

    def _settle_off(self, detail: str) -> None:
        with self._lock:
            self._state = "off"
            self._detail = detail
            self._session = None
            self._tick_thread = None


def build_app(mode: MrtaMode) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/status")
    def status() -> dict:
        return mode.status()

    @app.post("/mode")
    async def set_mode(request: Request) -> JSONResponse:
        try:
            body = await request.json()
            on = bool(body["on"])
        except (ValueError, KeyError, TypeError):
            return JSONResponse({"detail": 'body must be {"on": bool}'}, status_code=400)
        code, payload = mode.set_mode(on)
        return JSONResponse(payload, status_code=code)

    return app


def serve(connect_kwargs: dict, host: str = "0.0.0.0", port: int = 8002) -> None:
    import uvicorn

    mode = MrtaMode(connect_kwargs)
    print(f"MRTA mode server on {host}:{port} "
          f"(controller {connect_kwargs.get('base_url')})")
    uvicorn.run(build_app(mode), host=host, port=port, log_level="warning")
