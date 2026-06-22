# Level 2 — Vrrrm! Now it's real test time

Same plan, real robots. The controller is now connected to a physical swarm through the
**Mari gateway** over **MQTT**, and each DotBot runs the waypoint-following loop on board,
localised by **Lighthouse 2 (LH2)**. This is the ground-truth level: it's where real
physics — turning radius, overshoot, localisation noise — meets the plan.

The driver, `real_dotbot_pibt.py`, is the **conservative** counterpart of the Level 1
script: it sends one waypoint per bot sequentially, then holds a synchronisation barrier
that polls the bots' real LH2 positions until all have arrived. A bot that exceeds
`--step-timeout` is logged and skipped instead of blocking the swarm (no deadlock).

## Prerequisites

- A provisioned DotBot swarm and a gateway flashed with the Mari firmware.
- An LH2 setup (two base stations) calibrated for your arena — follow PyDotBot's
  [Lighthouse 2 calibration guide](https://pydotbot.readthedocs.io/en/0.29.1/guides/lh2-calibration.html).
- The `[calibrate]` extra installed (see [Installation](installation.md)).

## 1. Start the MQTT broker

```bash
mosquitto -c mosquitto.conf      # listens on :1883
```

## 2. Bring up the gateway and the bots

With the nRF gateway connected over USB, check the fleet:

```bash
dotbot swarm status              # should list the real DotBotV3 units
```

If the bots show as **"Bootloader"**, they aren't running the DotBot application and won't
appear in the controller. Flash and start the full sandbox app:

```bash
dotbot swarm flash <path-to>/dotbot-sandbox-dotbot-v3.bin -ys
dotbot swarm start
dotbot swarm status              # should now read "Running"
```

!!! note
    Only the `dotbot-sandbox-dotbot-v3` application provides LH2 advertisement **and**
    waypoint navigation. Demo apps like `spin`, `move`, or `rgbled` are not drivable from
    the controller.

## 3. Start the real controller

```bash
dotbot run controller \
    --conn mqtt://localhost:1883 \
    --swarm-id 1234 \
    --map-size 2000x2000
```

`--map-size` must cover your real LH2 area; `--swarm-id` is the one in the MQTT topic
(`/mari/1234/…`). Do **not** run `dotbot run simulator` at the same time — it would occupy
port 8000.

Confirm the controller sees the bots:

```bash
curl -s http://localhost:8000/controller/dotbots | python3 -m json.tool
```

You should see the **real** addresses with a non-null `lh2_position` and `calibrated ≠ 0`.
An empty `[]` means the controller is still in simulator mode, or the bots are still in
bootloader.

## 4. Run the PIBT test

Always dry-run first, then start small and scale up:

```bash
python real_dotbot_pibt.py --dry-run --seed 1     # no commands sent
python real_dotbot_pibt.py --seed 1 --steps 20    # real run
```

| Option | Default | Role |
|--------|---------|------|
| `--threshold` | 100 mm | Distance under which a bot counts as "arrived" at its cell |
| `--step-timeout` | 8.0 s | Max wait per step; beyond it the bot is logged and skipped |
| `--settle` | 0.3 s | Pause after arrival to let bots come to a stop |
| `--min-bots` | 2 | Localised bots required before starting |
| `--steps` | 30 | Maximum PIBT steps |
| `--seed` | random | Reproducible random goals |
| `--map-cells` | 5 | Grid resolution N×N (5 → 400 mm cells, 8 → 250 mm on a 2000×2000 map) |
| `--cell-mm` | derived | Cell size in mm (overrides `--map-cells`; centres at `gx*cell_mm + cell_mm//2`) |

## Reproducing the experiments

The batch harness runs many seeded trials at a fixed bot count and records per-run metrics
and a summary under `log/`:

```bash
python real_dotbot_pibt_batch.py --bots 4 --runs 5
python real_dotbot_pibt_batch.py --bots 8           # 8 bots, 5 runs (default)
```

Each invocation writes:

- a raw run log to `log/raw_logs/`,
- per-run rows to `log/l1_per_run.csv`,
- an aggregated `log/l1_summary.csv`.

The experiment sweeps cell size on a fixed 2000 × 2000 mm arena (4×4 / 5×5 / 8×8) and
overlays the result against the Level 0 sweep.

## Quick troubleshooting

| Symptom | Likely cause |
|---------|--------------|
| `curl` returns `[]` | Controller still in simulator mode, or bots in bootloader (`dotbot swarm start`). |
| `Connection refused` | Controller not running on `:8000`. |
| Bots not localised | LH2 coverage / calibration — recalibrate if positions look wrong. |
| One bot stalls a step | Expected — `--step-timeout` skips it after the delay and continues. |
