"""Mesure du RTT de bout en bout d'un DotBot.

Pour chaque essai : lecture de la position LH2 de référence, envoi d'une
commande PUT /controller/dotbots/{address}/{app}/move_raw, puis attente que la
position LH2 dévie de plus de --threshold-mm (écoute WebSocket par défaut, ou
polling REST). Le RTT couvre toute la chaîne : HTTP + controller + transport
(série/BLE ou simulateur) + réaction moteur + fix LH2 + retour.

Résultats ajoutés à rtt.csv dans $DOTBOT_LATENCY_DIR (ou --latency-dir),
visibles sur http://localhost:8000/latency. Fonctionne en simulateur et réel.

Usage :
    python measure_rtt.py --trials 10
    python measure_rtt.py --method poll --threshold-mm 50 --speed 80
"""

import asyncio
import json
import math
import os
import statistics
import sys
import time

import click
import requests
import websockets

from dotbot.latency import LatencyLogger

UPDATE_CMD = 2  # DotBotNotificationCommand.UPDATE


def fetch_dotbot(base, address=None):
    """Return (address, lh2_position) of the target DotBot."""
    bots = requests.get(f"{base}/controller/dotbots", timeout=5).json()
    candidates = [b for b in bots if b.get("lh2_position")]
    if address is not None:
        candidates = [b for b in candidates if b["address"] == address]
    if not candidates:
        raise click.ClickException(
            "Aucun DotBot avec position LH2 trouvé"
            + (f" pour l'adresse {address}" if address else "")
        )
    bot = candidates[0]
    return bot["address"], bot["lh2_position"]


def distance(pos_a, pos_b):
    return math.hypot(pos_a["x"] - pos_b["x"], pos_a["y"] - pos_b["y"])


def send_move(base, address, application, left_y, right_y):
    requests.put(
        f"{base}/controller/dotbots/{address}/{application}/move_raw",
        json={"left_x": 0, "left_y": left_y, "right_x": 0, "right_y": right_y},
        timeout=5,
    )


async def wait_motion_ws(base, address, baseline, threshold, timeout):
    """Wait via WebSocket until the bot moves > threshold mm; return distance."""
    ws_url = base.replace("http", "ws", 1) + "/controller/ws/status"
    deadline = time.perf_counter() + timeout
    async with websockets.connect(ws_url) as ws:
        while True:
            remaining = deadline - time.perf_counter()
            if remaining <= 0:
                return None
            try:
                message = json.loads(await asyncio.wait_for(ws.recv(), remaining))
            except asyncio.TimeoutError:
                return None
            if message.get("cmd") != UPDATE_CMD:
                continue
            data = message.get("data") or {}
            if data.get("address") != address or not data.get("lh2_position"):
                continue
            dist = distance(data["lh2_position"], baseline)
            if dist > threshold:
                return dist


def wait_motion_poll(base, address, baseline, threshold, timeout, period=0.01):
    """Wait via REST polling until the bot moves > threshold mm."""
    deadline = time.perf_counter() + timeout
    while time.perf_counter() < deadline:
        bots = requests.get(
            f"{base}/controller/dotbots", params={"address": address}, timeout=5
        ).json()
        if bots and bots[0].get("lh2_position"):
            dist = distance(bots[0]["lh2_position"], baseline)
            if dist > threshold:
                return dist
        time.sleep(period)
    return None


@click.command(help="Mesure le RTT commande move_raw -> mouvement LH2 détecté.")
@click.option("--base", default="http://localhost:8000", show_default=True)
@click.option("--address", default=None, help="Adresse du bot (défaut: 1er localisé).")
@click.option("--application", default=0, show_default=True, help="0=DotBot.")
@click.option("--trials", "-n", default=10, show_default=True)
@click.option("--threshold-mm", default=30.0, show_default=True)
@click.option("--method", type=click.Choice(["ws", "poll"]), default="ws", show_default=True)
@click.option("--speed", default=60, show_default=True, help="Vitesse moteurs [0-127].")
@click.option("--timeout", default=10.0, show_default=True, help="Timeout par essai (s).")
@click.option("--settle", default=1.0, show_default=True, help="Pause entre essais (s).")
@click.option(
    "--latency-dir",
    default=None,
    help="Dossier de sortie rtt.csv (défaut: $DOTBOT_LATENCY_DIR, sinon ./latency_logs).",
)
def main(base, address, application, trials, threshold_mm, method, speed, timeout, settle, latency_dir):
    out_dir = latency_dir or os.environ.get("DOTBOT_LATENCY_DIR") or "latency_logs"
    logger = LatencyLogger(directory=out_dir)
    rtts = []
    for trial in range(1, trials + 1):
        address, baseline = fetch_dotbot(base, address)
        t0 = time.perf_counter()
        send_move(base, address, application, speed, speed)
        try:
            if method == "ws":
                dist = asyncio.run(
                    wait_motion_ws(base, address, baseline, threshold_mm, timeout)
                )
            else:
                dist = wait_motion_poll(base, address, baseline, threshold_mm, timeout)
        finally:
            send_move(base, address, application, 0, 0)  # stop
        if dist is None:
            click.echo(f"essai {trial:2d}: TIMEOUT (> {timeout}s, aucun mouvement > {threshold_mm} mm)")
        else:
            rtt_ms = (time.perf_counter() - t0) * 1000
            rtts.append(rtt_ms)
            logger.log(
                "rtt",
                address=address,
                method=method,
                threshold_mm=threshold_mm,
                distance_mm=round(dist, 1),
                rtt_ms=round(rtt_ms, 3),
            )
            click.echo(f"essai {trial:2d}: RTT = {rtt_ms:8.1f} ms (déplacement {dist:.0f} mm)")
        time.sleep(settle)

    if not rtts:
        click.echo("Aucune mesure réussie.")
        sys.exit(1)
    ordered = sorted(rtts)
    p95 = ordered[max(0, int(len(ordered) * 0.95) - 1)]
    click.echo(
        f"\n{len(rtts)}/{trials} essais — min {ordered[0]:.1f} ms | "
        f"moyenne {statistics.fmean(rtts):.1f} ms | p95 {p95:.1f} ms | max {ordered[-1]:.1f} ms"
    )
    click.echo(f"Mesures ajoutées à {os.path.join(out_dir, 'rtt.csv')} (page: {base}/latency)")


if __name__ == "__main__":
    main()
