#!/usr/bin/env python3
"""
sim_dotbot_pibt.py — Version SIMULATEUR (envoi des waypoints en masse).

Calcule des trajectoires PIBT et les envoie comme listes de waypoints aux DotBots.
Chaque bot reçoit d'un coup tout son chemin et le suit à son rythme. Adapté au
simulateur (physique propre, grille peu dense). Pour du matériel réel asynchrone,
préférer real_dotbot_pibt.py (exécution pas-à-pas synchronisée).

Prérequis :
    dotbot run simulator \\
        --map-size 4000x4000 \\
        --init-state simulator_init_state.toml

Usage :
    python sim_dotbot_pibt.py              # fetch positions + envoie waypoints
    python sim_dotbot_pibt.py --dry-run    # simule sans envoyer de commandes
    python sim_dotbot_pibt.py --steps 40   # nombre de steps PIBT (défaut : 30)
    python sim_dotbot_pibt.py --map-cells 8 --cell-mm 500  # grille 8×8 (défaut)

Mapping grille ↔ mm :
    case (gx, gy) → centre mm = (gx*cell_mm + cell_mm//2, gy*cell_mm + cell_mm//2)
    pos (x_mm, y_mm) → case   = (int(x/cell_mm), int(y/cell_mm))
"""

import sys
import os
import argparse
import random
import requests

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "simulation"))

from core import Simulation, Agent, Grid, Position
from algo.pibt import PIBT

DEFAULT_BASE_URL = "http://localhost:8000"
DEFAULT_CELL_MM = 500     # taille d'une case (fixé dans DotBotsMap.tsx:256)
DEFAULT_MAP_CELLS = 8     # grille 8×8 = 4000×4000 mm
DEFAULT_STEPS = 30
DEFAULT_THRESHOLD = 50    # mm — le bot s'arrête quand distance < threshold
                          # 50mm suffit : la réduction de vitesse commence à 100mm


# ── GridStateManager ──────────────────────────────────────────────────────────

class GridStateManager:
    """
    Récupère l'état courant des DotBots depuis l'API REST et le convertit
    en positions sur la grille PIBT. Outil principal pour connaître l'état
    à moindre coût (un seul appel REST, zéro simulation).
    """

    def __init__(self, base_url: str, cell_mm: int, map_cells: int):
        self.base_url = base_url
        self.cell_mm = cell_mm
        # Dimensions de la grille en cases (par axe). Initialisées au fallback
        # carré ; écrasées par set_map_size() dès que l'API répond.
        self.map_cells_x = map_cells
        self.map_cells_y = map_cells

    def set_map_size(self, width_mm: int, height_mm: int) -> None:
        """Dérive les dimensions de la grille (en cases) depuis la taille réelle de la carte."""
        if width_mm % self.cell_mm or height_mm % self.cell_mm:
            print(f"  ⚠ cell_mm={self.cell_mm} ne divise pas la carte "
                  f"{width_mm}×{height_mm} mm — grille tronquée.")
        self.map_cells_x = max(1, width_mm // self.cell_mm)
        self.map_cells_y = max(1, height_mm // self.cell_mm)

    # ── Lecture API ────────────────────────────────────────────────────────────

    def fetch_dotbots(self) -> list[dict]:
        """GET /controller/dotbots — retourne les bots avec position LH2 valide et non perdus."""
        r = requests.get(f"{self.base_url}/controller/dotbots", timeout=5)
        r.raise_for_status()
        return [b for b in r.json() if b.get("lh2_position") and b.get("status") != 2]

    def fetch_map_size(self) -> tuple[int, int]:
        """GET /controller/map_size → (width_mm, height_mm)."""
        r = requests.get(f"{self.base_url}/controller/map_size", timeout=5)
        r.raise_for_status()
        data = r.json()
        return data["width"], data["height"]

    # ── Conversion ─────────────────────────────────────────────────────────────

    def mm_to_cell(self, x_mm: float, y_mm: float) -> Position:
        """Coordonnées mm → case grille (clampée par axe dans [0, map_cells_*-1])."""
        gx = max(0, min(self.map_cells_x - 1, int(x_mm / self.cell_mm)))
        gy = max(0, min(self.map_cells_y - 1, int(y_mm / self.cell_mm)))
        return Position(gx, gy)

    def cell_to_mm(self, pos: Position) -> tuple[float, float]:
        """Centre de la case en mm."""
        return (pos.x * self.cell_mm + self.cell_mm // 2,
                pos.y * self.cell_mm + self.cell_mm // 2)

    # ── État grille ────────────────────────────────────────────────────────────

    def get_grid_state(self) -> dict[str, Position]:
        """
        Retourne address → case courante pour tous les bots actifs.
        Coût : un seul appel REST.
        """
        dotbots = self.fetch_dotbots()
        raw: dict[str, Position] = {}
        for bot in dotbots:
            p = bot["lh2_position"]
            raw[bot["address"]] = self.mm_to_cell(p["x"], p["y"])
        return self.resolve_conflicts(raw)

    def resolve_conflicts(self, positions: dict[str, Position]) -> dict[str, Position]:
        """
        Si deux bots tombent sur la même case, décale le second sur une case libre adjacente.
        Préserve l'ordre d'insertion (le premier bot garde sa case).
        """
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
    """Buts aléatoires : chaque agent reçoit une case distincte tirée au hasard sur la grille."""
    all_cells = [Position(x, y) for x in range(grid.width) for y in range(grid.height)]
    chosen = rng.sample(all_cells, len(agents))
    return {agent: cell for agent, cell in zip(agents, chosen)}


def run_pibt(
    grid_state: dict[str, Position],
    cells_x: int,
    cells_y: int,
    steps: int,
    rng: random.Random,
) -> tuple[dict[str, list[Position]], dict[str, Position]]:
    """
    Lance la simulation PIBT et retourne :
      paths  : address → liste de Position grille (départ inclus)
      goals  : address → Position cible grille
    """
    grid = Grid(width=cells_x, height=cells_y)

    addresses = list(grid_state.keys())
    agents = [Agent(agent_id=i, position=grid_state[addr]) for i, addr in enumerate(addresses)]
    goals_by_agent = _assign_random_goals(agents, grid, rng)

    pibt = PIBT(goals=goals_by_agent)
    sim = Simulation(grid, coordinator=pibt)
    for agent in agents:
        sim.add_agent(agent)

    paths: dict[str, list[Position]] = {addr: [agents[i].position] for i, addr in enumerate(addresses)}

    for _ in range(steps):
        sim.step()
        for agent in sim.agents:
            addr = addresses[agent.agent_id]
            if agent.position != paths[addr][-1]:
                paths[addr].append(agent.position)

    goals_by_address = {addresses[i]: goals_by_agent[agents[i]] for i in range(len(agents))}
    return paths, goals_by_address


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


# ── Point d'entrée ────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="PIBT → DotBot waypoints demo (simulateur, envoi en masse)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Affiche les waypoints sans les envoyer")
    parser.add_argument("--steps", type=int, default=DEFAULT_STEPS,
                        help=f"Nombre de steps PIBT (défaut : {DEFAULT_STEPS})")
    parser.add_argument("--cell-mm", type=int, default=DEFAULT_CELL_MM,
                        help=f"Taille d'une case en mm (défaut : {DEFAULT_CELL_MM})")
    parser.add_argument("--map-cells", type=int, default=DEFAULT_MAP_CELLS,
                        help=f"Dimension de grille NxN de repli si l'API ne répond pas "
                             f"(défaut : {DEFAULT_MAP_CELLS} ; normalement dérivée de map_size)")
    parser.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD,
                        help=f"Rayon d'arrivée par waypoint en mm (défaut : {DEFAULT_THRESHOLD})")
    parser.add_argument("--base", default=DEFAULT_BASE_URL,
                        help=f"URL du contrôleur (défaut : {DEFAULT_BASE_URL})")
    parser.add_argument("--seed", type=int, default=None,
                        help="Graine RNG pour des buts aléatoires reproductibles (défaut : aléatoire)")
    args = parser.parse_args()

    rng = random.Random(args.seed)
    gsm = GridStateManager(args.base, args.cell_mm, args.map_cells)

    print(f"Connexion à {args.base}…")
    try:
        width_mm, height_mm = gsm.fetch_map_size()
        gsm.set_map_size(width_mm, height_mm)  # dérive la grille depuis la carte réelle
        grid_state = gsm.get_grid_state()
        dotbots_raw = gsm.fetch_dotbots()
    except requests.RequestException as e:
        print(f"Erreur : impossible de joindre le contrôleur ({e})")
        print("  → dotbot run simulator --map-size 4000x4000 --init-state simulator_init_state.toml")
        sys.exit(1)

    if not grid_state:
        print("Aucun DotBot avec position LH2 disponible.")
        sys.exit(1)

    # Afficher les positions réelles récupérées
    pos_by_addr = {b["address"]: b["lh2_position"] for b in dotbots_raw}
    print(f"\n{len(grid_state)} DotBot(s) détecté(s) :")
    for addr, cell in grid_state.items():
        p = pos_by_addr.get(addr, {})
        print(f"  {addr[:8]}…  pos=({p.get('x', '?'):.0f}, {p.get('y', '?'):.0f}) mm  case={cell}")

    print(f"\nCalcul PIBT — grille {gsm.map_cells_x}×{gsm.map_cells_y} cases "
          f"(dérivée de la carte {width_mm}×{height_mm} mm, cell={args.cell_mm} mm), "
          f"{args.steps} steps…")

    paths, goals = run_pibt(grid_state, gsm.map_cells_x, gsm.map_cells_y, args.steps, rng)

    print()
    any_sent = False
    for addr, cell in grid_state.items():
        path = paths.get(addr, [])
        waypoints_cells = path[1:]  # exclure position de départ (déjà la position courante)
        waypoints_mm = [gsm.cell_to_mm(p) for p in waypoints_cells]

        print(f"  Bot {addr[:8]}…  départ={cell}  but={goals.get(addr)}")
        if not waypoints_mm:
            print(f"    → déjà au but, aucun waypoint à envoyer")
            continue
        for x, y in waypoints_mm:
            print(f"    ({x:.0f}, {y:.0f}) mm", end="")
        print()

        if not args.dry_run:
            try:
                send_waypoints(args.base, addr, waypoints_mm, args.threshold)
                print(f"    → {len(waypoints_mm)} waypoint(s) envoyé(s) (threshold={args.threshold} mm)")
                any_sent = True
            except requests.RequestException as e:
                print(f"    → Erreur : {e}")
        else:
            print(f"    → [dry-run] non envoyés")

    if args.dry_run:
        print("\n[dry-run] Aucune commande envoyée.")
    elif any_sent:
        print("\nNavigation démarrée. Ouvrir http://localhost:8000 pour visualiser.")


if __name__ == "__main__":
    main()
