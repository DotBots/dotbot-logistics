#!/usr/bin/env python3
"""
dotbot_pibt_demo-v1.py — Exécution pas-à-pas synchronisée (reflète le cas réel).

Calcule des trajectoires PIBT et les exécute pas-à-pas : à chaque pas, un seul
waypoint par bot (sa case suivante), puis attente que TOUS les bots soient arrivés
avant le pas suivant (barrière de synchronisation). Préserve la garantie anti-collision
de PIBT. Fonctionne avec le simulateur et le matériel réel.

Prérequis (simulateur) :
    dotbot run simulator \\
        --map-size 2000x2000 \\
        --simulator-init-state /home/dok/testInria/simulator_init_state.toml

Prérequis (réel) : gateway + contrôleur connectés au swarm, bots localisés (LH2).

Usage :
    python dotbot_pibt_demo-v1.py                 # exécution pas-à-pas synchronisée
    python dotbot_pibt_demo-v1.py --dry-run       # affiche les cibles sans envoyer
    python dotbot_pibt_demo-v1.py --steps 40      # nombre de steps PIBT (défaut : 30)
    python dotbot_pibt_demo-v1.py --map-cells 8 --cell-mm 250  # grille 8×8 (défaut)

Mapping grille ↔ mm :
    case (gx, gy) → centre mm = (gx*cell_mm + cell_mm//2, gy*cell_mm + cell_mm//2)
    pos (x_mm, y_mm) → case   = (int(x/cell_mm), int(y/cell_mm))
"""

import sys
import os
import math
import time
import argparse
import random
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../Inria/Main/simulation"))

from core import Simulation, Agent, Grid, Position
from algo.pibt import PIBT

DEFAULT_BASE_URL = "http://localhost:8000"
DEFAULT_CELL_MM = 250       # taille d'une case en mm
DEFAULT_MAP_CELLS = 8       # grille 8×8 = 2000×2000 mm
DEFAULT_STEPS = 30
DEFAULT_THRESHOLD = 100     # mm — un bot est considéré "arrivé" quand distance < threshold.
                            # 100mm : < demi-case (125mm), > bruit LH2 (~20mm).
DEFAULT_STEP_TIMEOUT = 8.0  # s — attente max par pas PIBT
DEFAULT_SETTLE = 0.3        # s — pause après arrivée pour laisser les bots s'immobiliser


# ── GridStateManager ──────────────────────────────────────────────────────────

class GridStateManager:
    """
    Récupère l'état courant des DotBots depuis l'API REST et le convertit
    en positions sur la grille PIBT.
    """

    def __init__(self, base_url: str, cell_mm: int, map_cells: int):
        self.base_url = base_url
        self.cell_mm = cell_mm
        self.map_cells_x = map_cells
        self.map_cells_y = map_cells

    def set_map_size(self, width_mm: int, height_mm: int) -> None:
        if width_mm % self.cell_mm or height_mm % self.cell_mm:
            print(f"  ⚠ cell_mm={self.cell_mm} ne divise pas la carte "
                  f"{width_mm}×{height_mm} mm — grille tronquée.")
        self.map_cells_x = max(1, width_mm // self.cell_mm)
        self.map_cells_y = max(1, height_mm // self.cell_mm)

    def fetch_dotbots(self) -> list[dict]:
        r = requests.get(f"{self.base_url}/controller/dotbots", timeout=5)
        r.raise_for_status()
        return [b for b in r.json() if b.get("lh2_position") and b.get("status") != 2]

    def fetch_map_size(self) -> tuple[int, int]:
        r = requests.get(f"{self.base_url}/controller/map_size", timeout=5)
        r.raise_for_status()
        data = r.json()
        return data["width"], data["height"]

    def mm_to_cell(self, x_mm: float, y_mm: float) -> Position:
        gx = max(0, min(self.map_cells_x - 1, int(x_mm / self.cell_mm)))
        gy = max(0, min(self.map_cells_y - 1, int(y_mm / self.cell_mm)))
        return Position(gx, gy)

    def cell_to_mm(self, pos: Position) -> tuple[float, float]:
        return (pos.x * self.cell_mm + self.cell_mm // 2,
                pos.y * self.cell_mm + self.cell_mm // 2)

    def get_grid_state(self) -> dict[str, Position]:
        dotbots = self.fetch_dotbots()
        raw: dict[str, Position] = {}
        for bot in dotbots:
            p = bot["lh2_position"]
            raw[bot["address"]] = self.mm_to_cell(p["x"], p["y"])
        return self.resolve_conflicts(raw)

    def resolve_conflicts(self, positions: dict[str, Position]) -> dict[str, Position]:
        occupied: dict[Position, str] = {}
        result: dict[str, Position] = {}
        for address, pos in positions.items():
            if pos not in occupied:
                occupied[pos] = address
                result[address] = pos
            else:
                candidates = [
                    Position(pos.x + dx, pos.y + dy)
                    for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1),
                                   (1, 1), (-1, 1), (1, -1), (-1, -1)]
                    if 0 <= pos.x + dx < self.map_cells_x and 0 <= pos.y + dy < self.map_cells_y
                ]
                free = next((c for c in candidates if c not in occupied), pos)
                occupied[free] = address
                result[address] = free
        return result


# ── Planification PIBT ────────────────────────────────────────────────────────

def _assign_random_goals(
    agents: list[Agent],
    grid: Grid,
    rng: random.Random,
) -> dict[Agent, Position]:
    all_cells = [Position(x, y) for x in range(grid.width) for y in range(grid.height)]
    chosen = rng.sample(all_cells, len(agents))
    return {agent: cell for agent, cell in zip(agents, chosen)}


def build_pibt(
    grid_state: dict[str, Position],
    cells_x: int,
    cells_y: int,
    rng: random.Random,
):
    grid = Grid(width=cells_x, height=cells_y)
    addresses = list(grid_state.keys())
    agents = [Agent(agent_id=i, position=grid_state[addr]) for i, addr in enumerate(addresses)]
    goals_by_agent = _assign_random_goals(agents, grid, rng)
    pibt = PIBT(goals=goals_by_agent)
    sim = Simulation(grid, coordinator=pibt)
    for agent in agents:
        sim.add_agent(agent)
    goals_by_address = {addresses[i]: goals_by_agent[agents[i]] for i in range(len(agents))}
    return sim, agents, addresses, goals_by_agent, goals_by_address


# ── Synchronisation ───────────────────────────────────────────────────────────

def wait_until_all_arrived(
    gsm: GridStateManager,
    targets: dict[str, Position],
    threshold: int,
    step_timeout: float,
    settle_s: float,
) -> set[str]:
    target_mm = {addr: gsm.cell_to_mm(cell) for addr, cell in targets.items()}
    deadline = time.time() + step_timeout
    arrived: set[str] = set()
    poll_interval = 0.05  # démarre à 50 ms, recul exponentiel jusqu'à 500 ms
    while time.time() < deadline:
        try:
            bots = {b["address"]: b["lh2_position"] for b in gsm.fetch_dotbots()}
        except requests.RequestException:
            time.sleep(poll_interval)
            continue
        arrived = {
            addr
            for addr, (tx, ty) in target_mm.items()
            if (p := bots.get(addr)) and math.hypot(p["x"] - tx, p["y"] - ty) < threshold
        }
        if len(arrived) == len(target_mm):
            break
        time.sleep(poll_interval)
        poll_interval = min(poll_interval * 1.5, 0.5)

    missing = set(target_mm) - arrived
    if missing:
        print(f"    ⚠ non arrivé(s) avant timeout {step_timeout}s : "
              f"{', '.join(a[:8] + '…' for a in missing)}")
    if settle_s:
        time.sleep(settle_s)
    return arrived


def _send_all_parallel(
    base_url: str,
    moved_mm: dict[str, tuple[float, float]],
    threshold: int,
) -> None:
    if not moved_mm:
        return
    with ThreadPoolExecutor(max_workers=len(moved_mm)) as executor:
        futures = {
            executor.submit(send_waypoints, base_url, addr, [wp_mm], threshold): addr
            for addr, wp_mm in moved_mm.items()
        }
        for future in as_completed(futures):
            addr = futures[future]
            try:
                future.result()
            except requests.RequestException as e:
                print(f"    → Erreur envoi {addr[:8]}… : {e}")


# ── Exécution pas-à-pas ───────────────────────────────────────────────────────

def run_pibt_live(
    gsm: GridStateManager,
    sim: Simulation,
    agents: list[Agent],
    addresses: list[str],
    goals_by_agent: dict[Agent, Position],
    threshold: int,
    steps: int,
    step_timeout: float,
    settle_s: float,
    dry_run: bool,
) -> None:
    prev = {addr: agents[i].position for i, addr in enumerate(addresses)}
    next_targets: dict[str, Position] | None = None  # pré-calculé pendant le déplacement

    for step in range(1, steps + 1):
        # Utilise le step pré-calculé si disponible, sinon calcule maintenant
        if next_targets is not None:
            targets = next_targets
            next_targets = None
        else:
            sim.step()
            targets = {addr: agents[i].position for i, addr in enumerate(addresses)}

        moved = {addr: cell for addr, cell in targets.items() if cell != prev[addr]}
        all_at_goal = all(agents[i].position == goals_by_agent[agents[i]] for i in range(len(agents)))

        print(f"\n── Pas {step} ──")
        for addr, cell in targets.items():
            x, y = gsm.cell_to_mm(cell)
            tag = "" if addr in moved else "  (immobile)"
            print(f"  {addr[:8]}… → case {cell} = ({x:.0f}, {y:.0f}) mm{tag}")

        if not dry_run:
            # 1. Envoi parallèle de tous les waypoints
            _send_all_parallel(
                gsm.base_url,
                {addr: gsm.cell_to_mm(cell) for addr, cell in moved.items()},
                threshold,
            )
            # 2. Pré-calcul du step suivant pendant que les bots se déplacent
            if step < steps and not all_at_goal:
                sim.step()
                next_targets = {addr: agents[i].position for i, addr in enumerate(addresses)}
            # 4. Attente avec polling adaptatif
            wait_until_all_arrived(gsm, targets, threshold, step_timeout, settle_s)

        prev = targets
        if all_at_goal:
            print(f"\nTous les bots au but au pas {step}.")
            break


# ── Navigation DotBot ─────────────────────────────────────────────────────────

def send_waypoints(
    base_url: str,
    address: str,
    waypoints_mm: list[tuple[float, float]],
    threshold: int,
) -> None:
    payload = {
        "threshold": threshold,
        "waypoints": [{"x": float(x), "y": float(y)} for x, y in waypoints_mm],
    }
    r = requests.put(
        f"{base_url}/controller/dotbots/{address}/0/waypoints",
        json=payload,
        timeout=5,
    )
    r.raise_for_status()


def fetch_grid_state_with_retry(
    gsm: GridStateManager,
    min_bots: int,
    attempts: int = 10,
    delay: float = 1.0,
) -> dict[str, Position]:
    state: dict[str, Position] = {}
    for _ in range(attempts):
        state = gsm.get_grid_state()
        if len(state) >= min_bots:
            return state
        print(f"  … {len(state)} bot(s) avec position LH2, attente de ≥ {min_bots}…")
        time.sleep(delay)
    return state


# ── Point d'entrée ────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="PIBT → DotBot waypoints demo (pas-à-pas synchronisé)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Affiche les cibles sans envoyer ni attendre")
    parser.add_argument("--steps", type=int, default=DEFAULT_STEPS,
                        help=f"Nombre de steps PIBT (défaut : {DEFAULT_STEPS})")
    parser.add_argument("--cell-mm", type=int, default=DEFAULT_CELL_MM,
                        help=f"Taille d'une case en mm (défaut : {DEFAULT_CELL_MM})")
    parser.add_argument("--map-cells", type=int, default=DEFAULT_MAP_CELLS,
                        help=f"Dimension de grille NxN de repli (défaut : {DEFAULT_MAP_CELLS})")
    parser.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD,
                        help=f"Rayon d'arrivée par case en mm (défaut : {DEFAULT_THRESHOLD})")
    parser.add_argument("--step-timeout", type=float, default=DEFAULT_STEP_TIMEOUT,
                        help=f"Attente max (s) par pas (défaut : {DEFAULT_STEP_TIMEOUT})")
    parser.add_argument("--settle", type=float, default=DEFAULT_SETTLE,
                        help=f"Pause (s) après arrivée par pas (défaut : {DEFAULT_SETTLE})")
    parser.add_argument("--min-bots", type=int, default=2,
                        help="Nombre minimal de bots localisés requis (défaut : 2)")
    parser.add_argument("--base", default=DEFAULT_BASE_URL,
                        help=f"URL du contrôleur (défaut : {DEFAULT_BASE_URL})")
    parser.add_argument("--seed", type=int, default=None,
                        help="Graine RNG reproductible (défaut : aléatoire)")
    args = parser.parse_args()

    rng = random.Random(args.seed)
    gsm = GridStateManager(args.base, args.cell_mm, args.map_cells)

    print(f"Connexion à {args.base}…")
    try:
        width_mm, height_mm = gsm.fetch_map_size()
        gsm.set_map_size(width_mm, height_mm)
        grid_state = fetch_grid_state_with_retry(gsm, args.min_bots)
        dotbots_raw = gsm.fetch_dotbots()
    except requests.RequestException as e:
        print(f"Erreur : impossible de joindre le contrôleur ({e})")
        print("  → dotbot run simulator --map-size 2000x2000 --simulator-init-state simulator_init_state.toml")
        sys.exit(1)

    if len(grid_state) < args.min_bots:
        print(f"Seulement {len(grid_state)} DotBot(s) localisé(s) (min : {args.min_bots}).")
        sys.exit(1)

    pos_by_addr = {b["address"]: b["lh2_position"] for b in dotbots_raw}
    print(f"\n{len(grid_state)} DotBot(s) détecté(s) :")
    for addr, cell in grid_state.items():
        p = pos_by_addr.get(addr, {})
        print(f"  {addr[:8]}…  pos=({p.get('x', '?'):.0f}, {p.get('y', '?'):.0f}) mm  case={cell}")

    print(f"\nCalcul PIBT — grille {gsm.map_cells_x}×{gsm.map_cells_y} cases "
          f"({width_mm}×{height_mm} mm, cell={args.cell_mm} mm), {args.steps} steps max…")

    sim, agents, addresses, goals_by_agent, goals_by_address = build_pibt(
        grid_state, gsm.map_cells_x, gsm.map_cells_y, rng
    )
    print("Buts assignés :")
    for addr in addresses:
        print(f"  {addr[:8]}…  départ={grid_state[addr]}  but={goals_by_address[addr]}")

    mode = "[dry-run] " if args.dry_run else ""
    print(f"\n{mode}Exécution pas-à-pas "
          f"(threshold={args.threshold} mm, step-timeout={args.step_timeout}s)…")

    run_pibt_live(
        gsm, sim, agents, addresses, goals_by_agent,
        threshold=args.threshold,
        steps=args.steps,
        step_timeout=args.step_timeout,
        settle_s=args.settle,
        dry_run=args.dry_run,
    )

    if args.dry_run:
        print("\n[dry-run] Aucune commande envoyée.")
    else:
        print(f"\nTerminé. Ouvrir {args.base} pour visualiser.")


if __name__ == "__main__":
    main()
