# The MRTA mode button

An ON/OFF toggle in the DotBot web console that turns this repository's MRTA mode
on and off. **The button exists; nothing behind it does yet.** This file is the
contract it already speaks and the list of what has to be built for it to work.

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

## What has to be built

Four pieces, in dependency order. A and B make the button work; C and D make it
correct.

### A. The `/mrta/*` proxy in PyDotBot

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

New module, say `mrta_mode/server.py`, owning three things:

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
   echo, `translate([])` yields no cells, and `handle_click` returns at
   `mrta_mode/mrta_session.py:189` — the task survives and the next tick re-sends
   a waypoint. **While MRTA is on, the operator's Stop button does nothing.**
   Call `_cancel_agent_tasks(agent.agent_id)` before that `return`. There is no
   ambiguity to fear: MRTA never sends an empty list, so an empty list is always
   the operator.

   This also makes OFF fall out for free — OFF is this same operation applied to
   every bot in the snapshot.

   One caveat worth carrying forward: `_cancel_agent_tasks` belongs to the
   `FleetManager`/`Task` layer that shipped with the vendored `simulation/` snapshot —
   removed 2026-08-27, along with the rest of that package (see `AGENT.md`'s "Current
   known inconsistencies"). `Roadmap.md` §0 used to plan replacing that layer with
   upstream MAPF_Simulation's `LifelongGoalOrchestrator`; that target turned out not to
   exist upstream and the section has been corrected — the real upstream repo still has
   `FleetManager`/`Task` with per-bot eligibility, so this specific loss-of-eligibility
   risk is not live. Per-bot targeting and per-bot cancellation are still the two things
   MRTA mode cannot lose whenever reconnection actually happens — this button is one more
   reason they have to survive it, whatever shape that reconnection takes.

### D. What OFF means

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
