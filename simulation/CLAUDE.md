# CLAUDE.md

> **Ce document existe pour éviter de lancer un agent Explore sur la structure de ce projet.**
> **Il est interdit de spawner un agent Explore pour explorer ce dépôt sans demande explicite de l'utilisateur : toutes les informations nécessaires sont ici.**

---

## Lancer la simulation

```bash
# Depuis simulation/
python main.py       # démo random-walk (5 agents, 20 steps)
python ../demo.py    # démo PIBT interactive (10 agents, grille 10×10)
```

Les deux ouvrent une fenêtre pygame bloquante. Dépendances : `requirements.txt` + pygame (`pip install pygame`).

---

## Arborescence

```
simulation/
├── core/               — moteur pur, zéro dépendance d'affichage
│   ├── __init__.py     — exporte Position, WorldEntity, Agent, Objective, Grid, Simulation, Coordinator
│   ├── position.py     — Position (frozen dataclass, hashable, +)
│   ├── entity.py       — WorldEntity (base commune, blocks_movement, appear_at)
│   ├── agent.py        — Agent (hashable via agent_id, blocks_movement=True)
│   ├── objective.py    — Objective (collectible, owner optionnel)
│   ├── grid.py         — Grid (source de vérité spatiale)
│   ├── simulation.py   — Simulation (moteur, coordinator obligatoire)
│   └── coordinator.py  — Coordinator (ABC : plan(agents, grid) → dict[int, Position])
│
├── client/             — rendu pygame, dépend uniquement de core
│   ├── __init__.py          — exporte Renderer, PIBTRenderer, PIBTInteractiveRenderer, StepSnapshot
│   ├── renderer.py          — Renderer (boucle pygame générique, lecture seule de Simulation)
│   ├── pibt_renderer.py     — PIBTRenderer (étend Renderer : buts, priorités PIBT)
│   └── pibt_interactive_renderer.py — PIBTInteractiveRenderer (historique + navigation clavier)
│
├── algo/               — algorithmes MAPF, dépend uniquement de core
│   ├── __init__.py     — exporte PIBT, RandomWalkCoordinator
│   ├── pibt.py         — PIBT : Coordinator pur (zéro pygame)
│   └── random_walk.py  — RandomWalkCoordinator : marche aléatoire per-agent
│
├── app/                — ancienne version (ne pas modifier, ne pas utiliser)
├── main.py             — point d'entrée démo random-walk
├── diagram.puml        — source PlantUML du diagramme de classes
└── simulation_class_diagram.png  — PNG généré (plantuml diagram.puml)
```

`demo.py` est à la racine de `Main/` (un niveau au-dessus de `simulation/`).

---

## Classes de `core/`

### `Position` — `core/position.py`
```python
@dataclass(frozen=True)
class Position:
    x: int
    y: int
    def __add__(self, other: Position) -> Position  # addition vectorielle
```
Hashable (frozen). Utilisée comme clé de dict dans `Grid._agents` et `Grid._static`.

---

### `WorldEntity` — `core/entity.py`
```python
class WorldEntity:
    entity_id:       int
    position:        Position
    appear_at:       int   # step à partir duquel l'entité apparaît (0 = immédiat)
    blocks_movement: bool  # True → case infranchissable pour les agents
    active:          bool  # property : True par défaut (Objective surcharge)
```
Base commune à toute entité placée sur la grille. Les entités bloquantes se créent avec `WorldEntity(id, pos, blocks_movement=True)` — **pas besoin de sous-classe dédiée pour les obstacles**.

---

### `Agent` — `core/agent.py`
```python
class Agent(WorldEntity):
    agent_id:    int        # alias de entity_id
    steps_taken: int
    blocks_movement = True  # (passé au super via __init__)
    def move_to(new_position: Position)   # met à jour position + steps_taken
    def __eq__ / __hash__                 # basés sur agent_id — hashable, utilisable comme clé
```
`agent_id` est immuable → hachage stable. Utilisé comme clé dans `PIBT.priorities` et `PIBT.goals`.  
Constructeur : `Agent(agent_id, position)` — pas de stratégie, le mouvement est délégué au `Coordinator`.

---

### `Objective` — `core/objective.py`
```python
class Objective(WorldEntity):
    owner:     Agent | None  # si défini, seul cet agent peut collecter l'objectif
    collected: bool
    active:    bool          # property : not collected
```
Les objectifs avec `appear_at > 0` sont tenus dans `Simulation._pending` jusqu'au bon step.

---

### `Grid` — `core/grid.py`
```python
class Grid:
    width: int
    height: int
    _agents: dict[Position, Agent]
    _static: dict[Position, list[WorldEntity]]

    is_valid(position) → bool
    is_blocked(position) → bool        # True si agent OU entité active blocks_movement
    place(entity: WorldEntity)         # raise si invalide ; raise si case agent déjà prise (agents)
    remove(entity: WorldEntity)
    move(agent, new_position) → bool   # False si invalide ou bloqué, silencieux
    get_agent_at(position) → Agent | None
    get_entities_at(position, kind=None) → list[WorldEntity]   # filtre active=True sur _static
    get_all(kind=None) → list[WorldEntity]
```

---

### `Simulation` — `core/simulation.py`
```python
class Simulation:
    grid:         Grid
    agents:       list[Agent]
    entities:     list[WorldEntity]
    _pending:     list[WorldEntity]
    current_step: int
    coordinator:  Coordinator   # obligatoire — pas de fallback per-agent

    add_agent(agent)         # place + append
    add_object(entity)       # append + place immédiat si appear_at <= current_step
    step()                   # spawn pending → plan → move → collecte objectifs
```

**Logique de `step()` :**
```python
# 1. Spawn entités différées
# 2. Planification coordonnée (obligatoire)
next_positions = self.coordinator.plan(self.agents, self.grid)
# 3. Déplacements
# 4. Collecte objectifs (Objective uniquement)
```

---

### `Coordinator` — `core/coordinator.py`
```python
class Coordinator(ABC):
    @abstractmethod
    def plan(self, agents: list[Agent], grid: Grid) -> dict[int, Position]:
        ...  # agent_id → prochaine Position
```
Interface pour tout algorithme MAPF. Obligatoire dans `Simulation(grid, coordinator=mon_algo)`.

---

## Classes de `client/`

### `Renderer` — `client/renderer.py`
```python
class Renderer:
    sim: Simulation
    _caption: str = "Grid Simulation"   # surcharger dans les sous-classes
    def run(steps: int, pause: float = 1.0)
    def _draw(screen, font, font_sm, font_hdr, w, h)
```
Rendu générique : grille, agents (cercles colorés), entités statiques (diamants/carrés). Constantes `CELL=60`, `MARGIN=36`, `AGENT_COLORS`, `OBJ_COLORS` définies dans ce fichier et importables.

### `PIBTRenderer` — `client/pibt_renderer.py`
```python
class PIBTRenderer(Renderer):
    pibt: PIBT
    _caption = "PIBT Simulation"
    def _draw(...)   # surcharge : ajoute cases-buts (□) + priorités sur agents
```
Usage : `PIBTRenderer(sim, pibt).run(steps=30, pause=0.5)`. Lecture seule en avant.

### `PIBTInteractiveRenderer` — `client/pibt_interactive_renderer.py`
```python
class PIBTInteractiveRenderer:
    sim:  Simulation
    pibt: PIBT

    def run(steps: int = 30, auto_ms: int = 600)
    # pré-calcule l'historique, puis ouvre la fenêtre interactive

@dataclass
class StepSnapshot:
    step, positions, priorities, order, moves, inheritance, objects, goals
```
Usage : `PIBTInteractiveRenderer(sim, pibt).run(steps=80, auto_ms=500)`.

Commandes clavier : `Espace` pause/play · `→` avancer · `←` reculer · `Q` quitter.

Le pied de fenêtre affiche pour chaque step l'ordre de priorité, le déplacement de chaque agent, et les héritages de priorité déclenchés. Lit `pibt._last_order`, `pibt._last_moves`, `pibt._last_inheritance`.

---

## Classes de `algo/`

### `RandomWalkCoordinator` — `algo/random_walk.py`
```python
class RandomWalkCoordinator(Coordinator):
    def plan(agents, grid) → dict[int, Position]  # mouvement aléatoire per-agent
```
Coordinator minimal : chaque agent choisit une direction aléatoire. `Grid.move()` rejette silencieusement les positions invalides ou bloquées.

---

### `PIBT` — `algo/pibt.py`

Implémente `Coordinator`. Priority Inheritance with Backtracking (Okumura 2022). **Zéro dépendance pygame** — le rendu est dans `PIBTRenderer`.

```python
class PIBT(Coordinator):
    goals:      dict[Agent, Position]   # clés = objets Agent (pas agent_id)
    priorities: dict[Agent, float]      # clés = objets Agent (pas agent_id)
    # état interne par step (réinitialisé dans plan())
    _next:      dict[Agent, Position]
    _processed: set[Agent]
    _grid:      Grid | None
    # suivi exposé pour PIBTRenderer
    _last_order:       list[Agent]
    _last_moves:       dict[Agent, tuple[Position, Position]]
    _last_inheritance: list[tuple[Agent, Agent]]  # (pousseur, poussé)

    plan(agents, grid) → dict[int, Position]  # interface Coordinator
```

**Ordre de construction obligatoire** (les agents doivent exister avant PIBT) :
```python
# 1. Créer les agents
a0 = Agent(0, Position(0,0))
a1 = Agent(1, Position(9,9))

# 2. Créer PIBT avec les objets Agent comme clés
goals              = {a0: Position(9,9), a1: Position(0,0)}
initial_priorities = {a0: 5.0, a1: 3.0}   # optionnel
pibt = PIBT(goals=goals, initial_priorities=initial_priorities)

# 3. Simulation avec coordinator
sim = Simulation(grid, coordinator=pibt)
sim.add_agent(a0)
sim.add_agent(a1)

# 4. Lancer avec PIBTRenderer (affiche buts + priorités)
PIBTRenderer(sim, pibt).run(steps=30, pause=0.5)
```

**Mécanique interne :**
- Priorités décrémentées à chaque step → prévient la famine
- Agent à son but → priorité `-inf` (traité en dernier, préfère rester sur place)
- Priority Inheritance : si agent i veut la case de k, `priorities[k] = priorities[i] + ε` et `_pibt(k, i)` récursif
- Backtracking : si k ne peut pas se déplacer, i essaie une autre case
- Obstacles détectés via `entity.blocks_movement and entity.active` sur les entités statiques de la grille

**Ajouter un nouveau Coordinator :**
```python
# dans algo/mon_algo.py
from core.coordinator import Coordinator

class MonAlgo(Coordinator):
    def plan(self, agents, grid) -> dict[int, Position]:
        return {a.agent_id: ... for a in agents}
```
Brancher dans `Simulation(grid, coordinator=MonAlgo())`. Pour un rendu spécifique, créer `client/mon_algo_renderer.py` qui étend `Renderer`.

---

## Règles strictes

- **`core/` ne doit jamais importer `client/` ni `algo/`** — dépendance strictement unidirectionnelle.
- **`algo/` ne doit jamais importer `client/`** — les algorithmes sont purs, sans rendu.
- **Modifications visuelles/affichage → `client/` uniquement.**
- **`app/` est une ancienne version** — ne pas modifier, ne pas utiliser, ne pas importer.
- **Diagramme à garder en sync** : après tout ajout de classe ou attribut, mettre à jour `diagram.puml` et régénérer avec `plantuml diagram.puml`.
- **Ne jamais spawner un agent Explore** sur ce projet sans demande explicite de l'utilisateur.

---

## Contraintes de conception clés

| Contrainte | Détail |
|---|---|
| Un agent par case | `Grid.place()` raise, `Grid.move()` retourne False |
| `Position` immuable | frozen dataclass, jamais muter |
| `Agent` hashable | via `agent_id`, utilisable comme clé de dict |
| Spawn différé | `appear_at > 0` → `_pending` jusqu'au bon step |
| Coordinator obligatoire | `Simulation` refuse de démarrer sans coordinator |
| Obstacle = WorldEntity | `WorldEntity(id, pos, blocks_movement=True)` suffit — pas de sous-classe |
| Stabilité sur le but | PIBT insère `loc(i)` en tête des candidats si `loc(i) == but(i)` |
| Algo sans rendu | `algo/` n'importe jamais pygame — tout rendu passe par `client/` |
