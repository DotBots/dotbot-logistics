# Reference

## `mrta_server.py` command line

All configuration is CLI flags — there is no config file. `python mrta_server.py --help` for
the authoritative list; this table is the same content with context.

### Server

| Flag | Default | Meaning |
|---|---|---|
| `--mrta-host H` | `0.0.0.0` | bind address for this server |
| `--mrta-port N` | `8002` | bind port — must match the controller's `--mrta-url` |
| `--dry-run` | off | build the session and tick, but never send waypoints or wait (wiring smoke test) |

### Controller connection

| Flag | Default | Meaning |
|---|---|---|
| `--base URL` | `http://localhost:8000` | the DotBot controller's REST base |
| `--ws-url URL` | derived from `--base` | the controller's WebSocket status URL |
| `--reconcile-interval S` | `2.0` | period of the REST poll that recovers a click or position the WebSocket missed |

### Grid and motion

| Flag | Default | Meaning |
|---|---|---|
| `--map-cells N` | `5` | grid resolution N×N — `5` → 400 mm cells, `8` → 250 mm, on a 2000×2000 map |
| `--cell-mm N` | derived | cell size in mm; overrides `--map-cells` |
| `--threshold N` | `100` | how close (mm) a bot must get to a cell centre to count as "arrived" |
| `--step-timeout S` | `4.0` | max seconds to wait for all bots to finish a step before moving on |
| `--settle S` | `0.3` | pause after each step to let bots come to rest |
| `--min-bots N` | `2` | refuse to turn ON until this many localised bots are present |
| `--idle-sleep S` | `0.2` | pause between idle ticks when no bot has a target |

## Controller API consumed

`mrta_mode/` talks to only this slice of the DotBot controller:

```text
GET  /controller/dotbots                     → bot list (filter: lh2_position present, status != 2)
GET  /controller/map_size                    → { width, height } in mm
PUT  /controller/dotbots/{addr}/0/waypoints  → { threshold, waypoints: [{x, y}] }
WS   /controller/ws/status                   → broadcasts { cmd, data } on every state change
                                               (cmd 2 = UPDATE; carries lh2_waypoints and lh2_position)
```

If the controller API changes shape, the files to update are
`mrta_mode/grid_state_manager.py` (`GridStateManager`),
`mrta_mode/waypoint_command_client.py` (`WaypointCommandClient.send()`), and
`mrta_mode/controller_status_listener.py` (`ControllerStatusListener._handle_raw()` for the
WebSocket shape).

## Grid ↔ mm mapping

```text
cell (gx, gy)   →  centre in mm = (gx·cell_mm + cell_mm//2,  gy·cell_mm + cell_mm//2)
pos (x, y) mm   →  cell         = (⌊x / cell_mm⌋,  ⌊y / cell_mm⌋)
```

`mm → cell` discards the sub-cell offset. Two bots that snap to the same cell are separated
by `GridStateManager.resolve_conflicts()` before PIBT ever sees the state.

## HTTP surface

See [The console toggle → the contract](console-toggle.md#the-contract) for
`GET /mrta/status` and `POST /mrta/mode`.

## `test_scripts/` — archived

`sim_dotbot_pibt.py`, `sim_dotbot_right_left.py`, and `sim_many_pibt.py` are the survivors of
the removed Level 0/1 batch scripts. They still `import` the vendored `simulation/` engine
that was deleted on 2026-08-27, so they **do not run**. They are kept only as a porting
reference: the swap is `algo.PIBTCoordinator` / `core.Simulation` / `core.Grid` /
`core.Position` → `pibt.PIBTPlanner` / `core.WorldEngine` / `core.Grid2D` /
`core.Coordinates2D`, the shape `mrta_mode/` already uses.
