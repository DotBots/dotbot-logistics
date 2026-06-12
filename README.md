# dotbot-pibt

Démos PIBT (Priority-Inheritance with Backtracking) pour swarm de DotBots —
navigation multi-robot sans collision sur une grille discrète.

Documentation DotBot/pydotbot : **https://pydotbot.readthedocs.io/en/latest/**

---

## Contenu

| Fichier | Description |
|---------|-------------|
| `sim_dotbot_pibt.py` | Simulateur — calcule les trajectoires PIBT et envoie **tous les waypoints en masse**. Chaque bot suit son chemin à son rythme. Adapté au simulateur (physique propre). |
| `real_dotbot_pibt.py` | Matériel réel — exécution **pas-à-pas synchronisée** : un waypoint à la fois, barrière d'attente entre chaque pas. Préserve la garantie anti-collision de PIBT sur du matériel asynchrone. |
| `simulation/` | Moteur de simulation PIBT autonome (`core/`, `algo/pibt.py`). |

---

## Installation

```bash
pip install pydotbot
pip install -r requirements.txt
```

---

## Lancement rapide

### 1. Démarrer le simulateur DotBot

```bash
dotbot run simulator \
    --map-size 4000x4000 \
    --init-state simulator_init_state.toml
```

> Le fichier `simulator_init_state.toml` définit les positions initiales des bots.
> Un exemple est disponible dans la documentation :
> https://pydotbot.readthedocs.io/en/latest/

### 2. Lancer la démo simulateur (waypoints en masse)

```bash
python sim_dotbot_pibt.py
python sim_dotbot_pibt.py --dry-run       # affiche sans envoyer
python sim_dotbot_pibt.py --steps 40      # 40 pas PIBT
python sim_dotbot_pibt.py --seed 42       # buts reproductibles
```

### 3. Lancer la démo matériel réel (pas-à-pas)

```bash
python real_dotbot_pibt.py
python real_dotbot_pibt.py --dry-run
python real_dotbot_pibt.py --threshold 120 --step-timeout 10
python real_dotbot_pibt.py --min-bots 3   # attend 3 bots localisés
```

---

## Options communes

| Option | Défaut | Description |
|--------|--------|-------------|
| `--base URL` | `http://localhost:8000` | URL du contrôleur pydotbot |
| `--cell-mm N` | `500` | Taille d'une case en mm |
| `--map-cells N` | `8` | Grille N×N de repli (normalement dérivée de l'API) |
| `--steps N` | `30` | Nombre de pas PIBT maximum |
| `--threshold N` | `50` / `100` | Rayon d'arrivée par waypoint (mm) |
| `--seed N` | aléatoire | Graine RNG pour des buts reproductibles |
| `--dry-run` | — | Affiche sans envoyer de commandes |

Options supplémentaires de `real_dotbot_pibt.py` :

| Option | Défaut | Description |
|--------|--------|-------------|
| `--step-timeout S` | `8.0` | Attente max par pas (secondes) |
| `--settle S` | `0.3` | Pause après arrivée pour laisser les bots s'immobiliser |
| `--min-bots N` | `2` | Nombre minimal de bots localisés requis au démarrage |

---

## Mapping grille ↔ mm

```
case (gx, gy)  →  centre mm = (gx×cell_mm + cell_mm//2, gy×cell_mm + cell_mm//2)
pos (x, y) mm  →  case      = (int(x/cell_mm), int(y/cell_mm))
```

Avec `cell_mm=500` et une carte `4000×4000 mm` : grille 8×8 cases.

---

## Différence entre les deux scripts

```
sim_dotbot_pibt.py          real_dotbot_pibt.py
─────────────────────────   ──────────────────────────────────
Calcule tout d'un coup      Calcule pas à pas
Envoie N waypoints/bot      Envoie 1 waypoint/bot/pas
Pas d'attente               Barrière de sync entre chaque pas
Simulateur uniquement       Simulateur ET matériel réel
threshold = 50 mm           threshold = 100 mm
```
