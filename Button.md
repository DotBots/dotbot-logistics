# The MRTA mode button

An ON/OFF toggle in the DotBot web console that turns this repository's MRTA mode
on and off. This file is the contract it speaks and the record of what was built
behind it.

> **Status — 2026-08-27: A, B, C and D are all implemented; live verification is
> still pending.** The `/mrta/*` proxy (A) is in the `feat/mrta-mode-toggle`
> branch of the PyDotBot checkout; the HTTP server (B), the restartability fixes
> (C) and the OFF sequence (D) are in `mrta_mode/` here (`server.py`,
> `mrta_server.py`, and the C.1/C.2/C.3 changes to `controller_status_listener.py`
> / `live_position_store.py` / `mrta_session.py`). Design:
> `diagrammes/mrta_mode_button_architecture.puml` and
> `diagrammes/mrta_mode_button_state_machine.puml`. What is **not** done: the live
> end-to-end check (step 4 below), a project-local venv, and the drive-pad
> `move_raw` conflict in "What the button changes for everything else". The
> per-subsection notes below record what shipped.

Read `AGENT.md` first for what MRTA mode is. The short version: `mrta_mode`
watches the controller's REST + WS surface, intercepts the waypoints an operator
sets from the console, and re-plans them through PIBT so bots route around each
other instead of driving straight lines. Today it is a CLI you start and stop
with Ctrl+C (`sim_dotbot_mrta.py`); the button makes it a mode of the console.

## What the button does today

Shipped in PyDotBot on branch `feat/mrta-mode-toggle`, in the unified console:

| File | Role |
|---|---|
| `dotbot/console-web/src/mrta.ts` | the state machine, pure and unit-tested |
| `dotbot/console-web/src/mrta.test.ts` | 13 tests |
| `dotbot/console-web/src/useMrta.ts` | polls status, posts the toggle |
| `dotbot/console-web/src/MrtaToggle.tsx` | the pill in the top bar |
| `dotbot/console-web/src/api.ts` | `fetchMrtaStatus()`, `postMrtaMode()` |
| `dotbot/console-web/src/App.tsx` | four lines of wiring |

With no server behind it, `/mrta/status` 404s, the console reads that as
"unavailable", and the pill renders greyed out as `MRTA N/A` with a tooltip
saying where to start the server. That is the intended resting state, not a
failure: the console has to stay fully usable with no MRTA in the picture.

## The contract

Two routes, same-origin under `/mrta`. The console already calls them.

### `GET /mrta/status`

```json
{ "state": "off", "bots": null, "detail": null }
```

| Field | Meaning |
|---|---|
| `state` | `off` \| `connecting` \| `on` \| `stopping` |
| `bots` | fleet size the running session snapshotted, `null` when not running |
| `detail` | one short line for the tooltip: why it is off, or what it is doing |

`unavailable` is a fifth state **the console infers and the server must never
send**. It is what a 404, a 502 or an unreachable host all collapse into.
`parseStatus()` rejects it from the wire on purpose.

### `POST /mrta/mode`

```json
{ "on": true }
```

Returns the same status object. Accept it (`202`) and return the *transition*
state — `connecting` or `stopping` — not the settled one: both take seconds, and
the button already renders them as a blinking amber pill.

Refuse with any non-2xx when the mode is already transitioning. The console
treats a refusal as "ask again next poll" rather than an error, so a refusal is
cheap; a second session started by a double click is not.

### Polling

The console polls status every 1.5 s and holds its optimistic label while a POST
is in flight. State lives in the MRTA process, never in the browser: two consoles
open on the same testbed have to agree, and closing one must change nothing.

## What was built

Four pieces, in dependency order. A and B make the button work; C and D make it
correct. All four shipped 2026-08-27 — the "**Done:**" note under each records
what landed against the plan that follows it.

### A. The `/mrta/*` proxy in PyDotBot

**Done:** PyDotBot commit "dotbot: proxy /mrta/* to the MRTA mode server
(dotbot-logistics)" on branch `feat/mrta-mode-toggle`. `mrta_url` (default
`http://localhost:8002`, `--mrta-url` / `[run.controller] mrta_url` /
`DOTBOT_MRTA_URL`) threaded through `__init__.py`, `config.py`, `controller.py`,
`controller_app.py`; `mrta_proxy` in `server.py` mirrors `swarmit_proxy` minus
the SSE/streaming machinery (plain 5 s timeout, `Response` not
`StreamingResponse`). The `/mrta` prefix is stripped, so the server sees
`/status` and `/mode`. `doc/cli/run.md` and `doc/reference/configuration.md`
updated. Verified: `/mrta/status` with nothing behind it returns 502, which the
console reads as `MRTA N/A`; 79 console-web tests still pass.

Same shape as the existing swarmit proxy — `dotbot/server.py:392-423`,
`swarmit_url` threaded through `config.py:149`, `controller_app.py:261-323`,
`controller.py:141`. Copy it for `mrta_url`, default `http://localhost:8002`,
overridable by `[run.controller] mrta_url`, `--mrta-url`, `DOTBOT_MRTA_URL`.

Why a proxy rather than letting the console call `localhost:8002` directly: the
console is served by the controller, so a second origin means CORS, mixed content
under HTTPS, and a UI that is no longer self-contained. The swarmit integration
already refused that trade; this follows it.

The streaming machinery of the swarmit proxy is not needed here — no SSE, two
small JSON routes — so the timeout can be a plain short one.

**This is a change to PyDotBot**, which breaks the "no changes to the PyDotBot
controller" invariant `sim_dotbot_mrta.py` has held so far. It is the smallest
possible break: the controller learns one URL, never anything about MRTA.

### B. The MRTA HTTP server, here

**Done:** `mrta_mode/server.py` — `MrtaMode` owns the state machine + session
lifecycle (state is process-global under a `threading.Lock` so two polling
consoles agree); `build_app()` is a small FastAPI app (`GET /status`,
`POST /mode {on}`); `serve()` runs it on uvicorn. `connect()` and the `tick()`
loop run on a worker thread, never on the serving loop. A POST during a
transition is refused `409`; a POST matching the settled state is a `202` no-op.
`mrta_server.py` is the CLI (`python mrta_server.py [--mrta-port N] [--dry-run]`,
mirroring `sim_dotbot_mrta.py`'s connect args). FastAPI/uvicorn come in via
pydotbot and are imported lazily, so `mrta_mode/__init__.py` still imports
without them for the plain CLI. Verified at unit level: the full
off→connecting→(409)→off-on-failure walk, plus a clamped one-line `detail`.

New module, `mrta_mode/server.py`, owning three things:

1. **The state machine.** `off → connecting → on → stopping → off`, and nothing
   else. Reject every other transition; that rejection is what stops a double
   click from starting two sessions driving the same bots.
2. **The session lifecycle.** ON builds a *new* `MRTASession` via `connect()` and
   runs `tick()` in a dedicated thread. OFF stops it. There is no resume: a
   session snapshots the fleet at `connect()` time (`addresses`/`agents` are
   fixed, and a bot appearing later is ignored), so ON is always a fresh PIBT
   world. That makes OFF/ON the way to pick up bots that joined late — worth
   saying in the UI rather than treating as a wart.
3. **A thread, not the event loop.** `tick()` blocks: up to `step_timeout` (4 s)
   in `wait_until_all_arrived`, plus `settle_s`. It cannot run on an asyncio
   loop that is also serving these routes.

`MRTASession` was already refactored for this — `start()`, `stop()`,
`handle_click()`, `tick()` exist precisely so a caller other than a blocking CLI
`while` loop can drive it (`mrta_mode/mrta_session.py`). `run()` stays the CLI's
own wrapper.

`connect()` retries up to 10 × 1 s waiting for `min_bots`, so it must run off the
request thread: POST returns `connecting` immediately and the poll reports the
outcome. A failed `connect()` (`MRTAConnectionError`) lands back in `off` with
its message in `detail`, which is exactly what the tooltip is for.

### C. Three fixes that make `MRTASession` genuinely restartable

**Done, all three:**
- **C.1** — `ControllerStatusListener` now owns an explicit event loop (published
  as `_loop`); `stop()` schedules `_aio_stop.set()` onto it, the read loop races
  `recv()` against that Event through `asyncio.wait`, and `stop()` joins the
  thread (5 s timeout). No more leaked thread/socket per OFF/ON.
- **C.2** — `LivePositionStore.interrupt()` sets a flag and `notify_all()`s on the
  same `Condition` the wait parks on; `wait_until_all_arrived()` returns
  immediately on it and skips the REST reconcile + `settle_s`. `MRTASession.stop()`
  calls it.
- **C.3** — `_handle_raw()` forwards `lh2_waypoints == []` (was: dropped on
  truthiness); `handle_click()` treats an empty `waypoints_mm` as the operator's
  Stop nav and calls `set_target(agent_id, agent.position)` + clears the pending
  chain. A non-empty payload that merely dedups to nothing keeps the old
  early-return.

The CLI starts one session and exits; a toggle starts many. Three things that
never mattered before now do.

1. **The WS listener does not actually stop.** `stop()` only sets a flag
   (`mrta_mode/controller_status_listener.py:44`), but the thread is parked in
   `async for raw in ws:`, which never checks it — the flag is only read after
   the socket closes or errors. There is no `join()` either. So every OFF/ON
   cycle leaks a thread and an open socket to the controller. Close the
   websocket from the loop (keep the reference, `run_coroutine_threadsafe` a
   `ws.close()`, or race a stop task against the iteration), then join.

2. **The arrival wait is not interruptible.** `wait_until_all_arrived` blocks on
   a `Condition` until `step_timeout`, then sleeps `settle_s`
   (`mrta_mode/live_position_store.py`). OFF therefore takes up to ~4.3 s before
   the bots are even told to stop. The `Condition` is already there: pass a stop
   `Event` and `notify_all()` on it, and the join becomes immediate.

3. **An empty waypoint list must cancel, not be ignored.** The console's "Stop
   nav" sends `putWaypoints(..., [])` (`App.tsx`, `onStopNav`). MRTA sees the
   echo, `translate([])` yields no cells, and `handle_click` returns early
   (`mrta_mode/mrta_session.py`, the `if not cells: return` guard) — the target
   survives and the next tick re-sends a waypoint. **While MRTA is on, the
   operator's Stop button does nothing.** There is no ambiguity to fear: MRTA
   never sends an empty list, so an empty list is always the operator.

   This also makes OFF fall out for free — OFF is this same operation applied to
   every bot in the snapshot.

   **Update, 2026-08-27: the mechanism this fix needs now exists, but the fix
   itself is still not applied.** `mrta_mode`/`sim_dotbot_mrta.py` were
   reconnected to the real upstream engine the same day (`AGENT.md`'s "Roadmap" §0):
   `MRTASession` now drives `pibt.LifelongGoalOrchestrator` instead of the old
   `FleetManager`/`Task` model, and `_cancel_agent_tasks()` has no equivalent —
   nor does it need one. Cancelling an agent's target is just
   `orchestrator.set_target(agent_id, agent.position)`: `assign_missions()`
   sees `position == target` on the next tick and clears the slot on its own
   (the same mechanism `LifelongGoalOrchestrator` already uses for ordinary
   arrival). Per-bot targeting was never at risk either way — `set_target()`
   takes an explicit `agent_id`, there was no shared-pool design to lose it to.
   This fix is exactly as small as it was always going to be. **Applied
   2026-08-27** — see the C.3 note at the top of section C.

### D. What OFF means

**Done:** `MRTASession.halt_all()` drops every `_active_target` / `_pending_chain`
entry and calls `WaypointCommandClient.send_stop(self.addresses)` (parallel,
best-effort `PUT []`). `MrtaMode._stop_session()` runs the load-bearing order
below: `stop_flag.set()` → `session.stop()` (wakes the arrival wait) →
`tick_thread.join(10 s)` → `session.halt_all()`.

**OFF stops the bots.** Not "stops planning and lets them coast to their last
commanded cell". The order is load-bearing:

```
set stop flag  →  wake the arrival wait  →  join the tick thread  →  PUT [] to every address in the snapshot
```

Clear the waypoints *before* joining and an in-flight `send_all_parallel()` re-arms
the bots a moment later; they drive one more cell and stop there, which reads as
latency rather than as the bug it is.

Clear exactly `session.addresses` — the snapshot. A bot that joined after
`connect()` was never driven by MRTA and has nothing to take back.

One good side effect: because OFF leaves every waypoint list empty, the next
`connect()` finds no residue, so `seed_commanded()` starts clean and cannot
mistake a leftover for a fresh operator click.

## What the button changes for everything else

Worth stating in the UI, not just here. While MRTA is on, a map click no longer
means "drive there" but "PIBT will route you there". Same control, different
meaning — the tooltip says so, and it is the one thing about this mode an
operator has to know.

Two related consequences, neither solved by the button:

- The drive pad sends `move_raw`, which puts the firmware back in MANUAL while
  MRTA still believes it is driving in AUTO. `agent.position` then diverges from
  reality and PIBT plans on a stale world. Either gate the pad while MRTA is on,
  or have MRTA treat a `move_raw` on one of its bots as a cancel for that bot.
- Waypoint *missions* (a queued chain, not a single point) already work: the
  translator turns the chain into one `Task` per cell. Nothing to do.

## How to verify

1. `npm --prefix dotbot/console-web run typecheck && npm --prefix dotbot/console-web run lint && npm --prefix dotbot/console-web test`
   — 79 tests, 13 of them on the toggle's state machine.
2. Build, serve, and check the degraded path is the one described above:
   ```
   curl -o /dev/null -w '%{http_code}\n' localhost:8000/mrta/status   # 404 today -> pill reads N/A
   ```
3. With A and B in place: start the MRTA server, reload the console, and the
   pill should read `OFF`. Toggle it and watch it sit on `STARTING` for as long
   as `connect()` takes, then settle on `ON` with the bot count in the tooltip.
4. The one that actually matters, and that no unit test covers: with MRTA `ON`,
   drive two bots at each other from the console and confirm they route around
   one another; then hit OFF mid-travel and confirm they stop where they are
   rather than finishing their segment.
