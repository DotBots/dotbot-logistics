# Run MRTA mode

Three processes run side by side: the **DotBot swarm**, the **MRTA server**, and your
**browser** on the console. Use three terminals, each with the venv activated
(`source venv/bin/activate`).

## 1 — the DotBot swarm

```bash
dotbot run simulator --map-size 2000x2000 \
    --simulator-init-state PyDotBot/simulator_init_state.toml \
    --mrta-url http://localhost:8002
```

- `--map-size 2000x2000` is the arena in millimetres. With the default 5×5 grid that is
  400 mm cells (see [Reference → Grid ↔ mm](reference.md#grid-mm-mapping)).
- `--simulator-init-state` points at any seed TOML with ≥ 2 bots
  (see [Installation → the simulator seed](installation.md#3-the-simulator-seed)).
- `--mrta-url http://localhost:8002` is what makes the console's `/mrta/*` proxy forward to
  the MRTA server. Equivalent: `[run.controller] mrta_url` in the pydotbot config, or the
  `DOTBOT_MRTA_URL` environment variable.

The web console is now at <http://localhost:8000/PyDotBot/>.

## 2 — the MRTA server

```bash
python mrta_server.py             # serves 0.0.0.0:8002
```

Add `--dry-run` to build the session and tick without ever sending a waypoint — useful for
checking the wiring without any bot moving. `Ctrl+C` shuts it down.

## 3 — the console

Open <http://localhost:8000/PyDotBot/>. The **MRTA** pill in the top bar shows the state:

| Pill reads | Meaning |
|---|---|
| **MRTA N/A** (greyed) | the console can't reach `mrta_server.py` — check step 2 and `--mrta-url` |
| **OFF** | server reachable, MRTA not engaged — a map click drives straight there (plain PyDotBot) |
| **…** (blinking amber) | `connecting` or `stopping` — a transition in progress |
| **ON** | MRTA engaged — a map click means "PIBT routes you there"; tooltip shows the bot count |

Click the pill to flip it **ON**. It blinks while the server snapshots the fleet
(`connect()` retries for a few seconds until at least `--min-bots` localised bots are
present), then settles on **ON**.

!!! note "The fleet is snapshotted at ON"
    A bot that joins after you flipped ON is *not* driven by MRTA. Flip **OFF then ON** to
    pick it up — there is no live resume.

## Drive a bot

With the pill **ON**, in the console:

1. **Select** a bot (click it in the list or on the map).
2. **Click a point** on the map.
3. Hit **Apply waypoints**.

That is the console's own existing gesture — nothing new. `mrta_server.py` catches the
resulting `PUT`, snaps your point to the nearest grid cell, and hands it to PIBT. The bot
walks there **one cell per tick**, waiting to actually arrive at each cell before taking the
next step.

- **Re-click** a bot that is still moving → it redirects immediately (the new target
  overwrites the old one).
- **Stop nav** (the console's own button, an empty waypoint list) → that bot cancels its
  target and parks where it is.
- Bots you never clicked **stay parked**.

## Worked example — two bots crossing

The point of MRTA mode is what happens when two paths conflict. Try this on the 5×5 grid:

1. Pill **ON**.
2. Select the bot near the **left edge**, click a point near the **right edge**, **Apply
   waypoints**. It starts walking east, one cell per tick.
3. Before it reaches the middle, select a bot near the **top edge**, click a point near the
   **bottom edge**, **Apply waypoints**.

Now both bots are headed for cells that cross at the centre. Watch the centre cell: PIBT
never lets both occupy it on the same tick. One bot takes the cell; the other **waits one
tick** (priority inheritance) or **sidesteps** into a free neighbour, then resumes. Neither
stops for long, and neither path is planned around a wall — they are planned around *each
other*, re-evaluated every tick.

Send a **third** bot through the same centre and the effect compounds: the planner threads
all three, still one cell per tick, still collision-free.

## Turn it OFF

Flip the pill **OFF**. Every bot in the snapshot **stops where it stands** — MRTA does not
let them coast to their last commanded cell. Internally: the tick loop is stopped, the
arrival wait is interrupted, and an empty waypoint list is `PUT` to every address.

A map click with the pill OFF is back to plain PyDotBot: the bot drives straight to the
point.

!!! warning "The drive pad while MRTA is ON"
    The console's manual drive pad sends `move_raw`, which puts the firmware back into MANUAL
    while MRTA still believes the bot is under AUTO waypoint control. PIBT then plans on a
    stale position for that bot. Until this is resolved, don't use the drive pad on a bot
    MRTA is driving — flip OFF first.
