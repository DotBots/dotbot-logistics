"""
demo.py — Démo PIBT interactive sur une grille 10×10.

Commandes :
    Espace    pause / play
    →         avancer d'un pas
    ←         reculer d'un pas
    Q / Échap quitter

Le pied de fenêtre affiche l'ordre de priorité, les déplacements
et les héritages de priorité à chaque étape.

────────────────────────────────────────────────────────────────
Pour créer votre propre démo :

  1. Choisissez un Coordinator (PIBT, RandomWalkCoordinator, ou le vôtre).
  2. Créez les agents AVANT le coordinator si celui-ci utilise les objets
     Agent comme clés de dict (cas de PIBT : goals et priorities).
  3. Construisez la simulation : Simulation(grid, coordinator=mon_algo).
  4. Ajoutez agents et entités via sim.add_agent() / sim.add_object().
  5. Lancez avec :
       PIBTInteractiveRenderer(sim, pibt).run(steps=25)  # avec navigation
       PIBTRenderer(sim, pibt).run(steps=30, pause=0.3)  # lecture seule
       Renderer(sim).run(steps=30, pause=0.3)            # sans rendu PIBT

Pour ajouter votre propre algorithme :
  → voir simulation/algo/random_walk.py comme exemple minimal.
  → votre classe doit hériter de Coordinator et implémenter plan().
────────────────────────────────────────────────────────────────
"""

import sys
import os

DEBUG = "-d" in sys.argv
if DEBUG:
    os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "simulation"))

from core import Simulation, Agent, Grid, Position, Objective, WorldEntity
from algo.pibt import PIBT
if DEBUG:
    # Import direct — évite de charger pygame via client/__init__.py
    from client.pibt_interactive_renderer import PIBTInteractiveRenderer
else:
    from client import PIBTInteractiveRenderer

# ── 1. Grille ─────────────────────────────────────────────────────────────────

grid = Grid(width=5, height=5)

# ── 2. Agents — créés avant PIBT car ils servent de clés dans goals/priorities ─

start_positions = [
    Position(0, 0), Position(2, 1), Position(4, 3), Position(4, 0),
    Position(1, 0), Position(4, 4), Position(4, 2), Position(3, 4),
    Position(3, 0), Position(3, 3),
]
agents = [Agent(agent_id=i, position=pos) for i, pos in enumerate(start_positions)]

# ── 3. Buts PIBT : Agent → Position cible ─────────────────────────────────────
#    Modifiez ces associations pour changer où chaque agent veut aller.

goals = {
    agents[0]: Position(4, 4),
    agents[1]: Position(4, 1),
    agents[2]: Position(0, 4),
    agents[3]: Position(0, 0),
    agents[4]: Position(3, 4),
    agents[5]: Position(4, 3),
    agents[6]: Position(2, 2),
    agents[7]: Position(0, 2),
    agents[8]: Position(1, 1),
    agents[9]: Position(4, 2),
}

# ── 4. Priorités initiales — plus la valeur est haute, plus l'agent est servi ─
#    Optionnel : si omis, PIBT assigne des priorités par ordre d'insertion.
#    Modifiables ici ou en cours de simulation via pibt.priorities[agent] = x.

initial_priorities = {
    agents[0]: 20.0,
    agents[1]: 8.0,
    agents[2]: 7.0,
    agents[3]: 6.0,
    agents[4]: 5.0,
    agents[5]: 4.0,
    agents[6]: 3.0,
    agents[7]: 2.0,
    agents[8]: 1.0,
    agents[9]: 0.0,
}

# ── 5. Coordinator et simulation ──────────────────────────────────────────────
#    Pour tester un autre algo : remplacez PIBT par votre Coordinator
#    et Renderer(sim) par PIBTRenderer(sim, pibt) si applicable.

pibt = PIBT(goals=goals, initial_priorities=initial_priorities)
sim = Simulation(grid, coordinator=pibt)

for agent in agents:
    sim.add_agent(agent)

# ── 6. Entités du monde ───────────────────────────────────────────────────────

# Objectif libre (n'importe quel agent peut le collecter — diamant jaune)
sim.add_object(Objective(entity_id=0, position=Position(3, 3)))
"""
# Objectif réservé : seul agents[0] peut le collecter
sim.add_object(Objective(entity_id=1, position=Position(8, 1), owner=agents[0]))

# Obstacles : WorldEntity avec blocks_movement=True — pas besoin de sous-classe
sim.add_object(WorldEntity(entity_id=2, position=Position(5, 5), blocks_movement=True))
sim.add_object(WorldEntity(entity_id=3, position=Position(5, 6), blocks_movement=True))

# Objectif différé : n'apparaît sur la grille qu'à partir du step 2
sim.add_object(Objective(entity_id=4, position=Position(1, 8), appear_at=2))
"""
# ── 7. Lancement ──────────────────────────────────────────────────────────────
#    python demo.py       → fenêtre interactive (← → Espace Q)
#    python demo.py -d    → mode debug : print terminal, zéro pygame

renderer = PIBTInteractiveRenderer(sim, pibt)
if DEBUG:
    renderer.run_debug(steps=20)
else:
    renderer.run(steps=30, auto_ms=500)
