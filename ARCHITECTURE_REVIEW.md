# Revue d'architecture — dotbot-logistics vs Start-Kit (League of Robot Runners)

Document de synthèse d'une session d'analyse comparant `dotbot-logistics` (et son moteur
`simulation/`) au starter-kit officiel de la League of Robot Runners (compétition de Lifelong
MAPF), dans le but d'identifier ce qui, dans l'architecture actuelle, mérite d'être simplifié,
renforcé, ou laissé tel quel.

**Lecture recommandée** : la section 2 (résumé exécutif) et la section 6 (recommandations)
suffisent pour une discussion de haut niveau. Les sections 3 à 5 contiennent le détail factuel
qui justifie chaque recommandation, avec chemins de fichiers précis.

---

## 1. Contexte

- **`dotbot-logistics`** est le pont entre un moteur PIBT/MRTA (`simulation/`, sous-projet Python
  autonome) et l'environnement DotBot (simulateur REST, ou hardware réel LH2/MQTT). Objectif final :
  un article expérimental. Trois niveaux : L0 (algorithme pur), L1 (simulateur DotBot), L2 (hardware
  réel).
- **Le Start-Kit** est le kit officiel d'une compétition annuelle de Lifelong MAPF (repo
  `MAPF-Competition/Start-Kit`, actif depuis 2023, versionné 3.1.0). Un moteur C++ exécute une
  simulation tick-par-tick à partir d'un planner que chaque participant fournit.
- Les deux projets résolvent un problème structurellement proche : **substituer l'algorithme /
  le backend qui pilote les robots, sans que le moteur central le sache.**

Deux comparaisons ont été faites, sur deux cibles différentes de `dotbot-logistics` :

| Cible comparée | Fait le … | Équivalent Start-Kit |
|---|---|---|
| Scripts racine (`sim_dotbot_pibt.py`, `real_dotbot_pibt.py`, `real_dotbot_pibt_batch.py`, `sim_dotbot_mrta.py`) | pont bas niveau, protocole REST/WS, spécifique au hardware DotBot | rien d'équivalent direct — c'est la partie "intégration terrain", hors périmètre du kit |
| `simulation/` (le moteur) | calcul PIBT/MRTA pur, agnostique du hardware | `src/`+`inc/`+`default_planner/` |

**La comparaison utile est la seconde.** La première a un problème réel et documenté
(§3), mais ce n'est pas la même catégorie de code que le moteur du Start-Kit.

---

## 2. Résumé exécutif

1. **Le moteur `simulation/` n'a pas à rougir de la comparaison.** Sa conception va même, sur un
   point précis (la séparation allocation/coordination), plus loin que le Start-Kit. Ce n'est pas
   là que le problème se situe.
2. **Le problème "overly complicated" a deux causes distinctes, presque opposées** :
   - Les **scripts racine** sont **sous-abstraits** : un pattern à 3 parties est dupliqué 4 fois,
     sans interface commune. Un bug réel (le "halt reflex", §3) est passé inaperçu jusqu'au
     hardware précisément à cause de ça.
   - Le **moteur `simulation/`** est correctement abstrait (3 interfaces : `Coordinator`,
     `Dispatcher`, `Allocator`) mais **ces abstractions ne sont vérifiées par aucun test** — le
     projet l'admet lui-même (`simulation/AGENT.md` : *"there is currently no test suite"*). De la
     complexité bien conçue, mais sans filet, se ressent aussi comme "compliquée" — parce
     qu'il faut la relire en entier à chaque changement pour être sûr qu'elle tient encore.
3. **Un rôle manque structurellement** : le Start-Kit a une troisième interface, `Executor`, dont
   le seul travail est "rejouer un plan déjà calculé, en sécurité, tick par tick, sous incertitude
   d'exécution réelle (retard, désynchronisation)". `dotbot-logistics` n'a **aucun** équivalent
   formalisé — cette responsabilité est éclatée dans les 4 scripts racine dupliqués, sous forme de
   `wait_until_all_arrived()`. C'est exactement la zone où le bug de halte immédiate a explosé.
4. **La recommandation prioritaire n'est pas "ajouter encore une couche d'abstraction"** — il y en
   a déjà assez côté moteur. C'est : **(a) consolider les scripts racine derrière une interface
   étroite**, et **(b) ajouter des tests de contrat légers** sur les abstractions qui existent déjà,
   pour transformer une complexité qui doit être relue en une complexité qui peut être vérifiée.

---

## 3. La duplication des scripts racine (déjà sous-abstraite)

`GridStateManager` (poll REST, conversion mm↔cellule, résolution de collisions) existe en **4
copies quasi identiques** :

```
sim_dotbot_pibt.py:57
real_dotbot_pibt.py:57
real_dotbot_pibt_batch.py:71
sim_dotbot_mrta.py:77
```

Aucune classe commune ne les relie. Le pattern à 3 parties (`GridStateManager` → `build_*()` →
`run_*_live()`) est délibérément dupliqué par convention (documenté dans `AGENT.md` racine), avec
un coût déjà reconnu dans ce même fichier : un changement d'API du contrôleur DotBot doit être
répercuté à la main dans les 4 scripts.

**`sim_dotbot_mrta.py` est devenu un monolithe de 668 lignes** (voir `AGENT.md` racine, section
"Known limitation") : 6 responsabilités orthogonales (polling REST, planification MRTA, détection
de clic manuel, navigation, boucle d'exécution, point d'entrée) vivent à plat dans un seul fichier,
sans frontière de module.

**Le post-mortem du "halt reflex" (`a6d265a`, abandonné) illustre le coût réel** : une tentative
d'ajouter un réflexe de halte immédiate sur clic manuel a introduit une race condition entre un
thread d'écoute WebSocket et la boucle principale — l'écouteur lisait un état partagé *avant* que
le thread principal ne l'écrive, concluant à tort "clic externe" à chaque tick PIBT normal, gelant
tous les robots en hardware réel. **La cause profonde documentée** : *"manual-click detection" has
no module boundary to state its threading contract against* — rien ne forçait à écrire l'invariant
("l'écho WS ne doit jamais être lu avant l'écriture qui l'a causé") ni à le tester. Le bug n'a été
détecté qu'en conditions réelles.

---

## 4. Le moteur `simulation/` — correctement abstrait, mais pas vérifié

### 4.1 Correspondance de classes

| `simulation/core/` | Équivalent Start-Kit | Remarque |
|---|---|---|
| `engine/simulation.py` (`Simulation.step()`) | `inc/CompetitionSystem.h` + `inc/Simulator.h` | un seul niveau de tick chez vous ; deux chez eux (planification lente / exécution rapide) |
| `engine/coordinator.py` (`Coordinator`, ABC) | `inc/MAPFPlanner.h` | interface de planification — correspondance propre |
| `engine/dispatcher.py` (`Dispatcher`, ABC) | `inc/TaskScheduler.h` | interface d'assignation — correspondance propre, avec nuances (§4.3) |
| `engine/dispatch_intent.py` (`DispatchIntent`) | — | pas d'équivalent ; le Start-Kit laisse cette traduction implicite dans le planner |
| `engine/plan_result.py` (`PlanResult`) | `inc/Plan.h` (`Plan`) | sortie du coordinateur |
| `entities/agent.py`, `position.py` | `inc/States.h` (`State`) | eux : pas de classe `Agent`, juste `vector<State>` indexé |
| `entities/entity.py`, `zone.py` | — | pas d'équivalent — leur carte est du texte statique, pas d'objets |
| `environment/grid.py` (`Grid`) | `inc/Grid.h` (`Grid`) | équivalent direct |
| — | `inc/SharedEnv.h` (`SharedEnvironment`) | **pas d'équivalent** — voir §4.4, c'est le point le plus important |
| — | `inc/ActionModel.h` | pas d'équivalent — la validation de mouvement est inline dans `Simulation._validate()` |
| — | `inc/DelayGenerator.h`, `inc/TaskManager.h` | pas dans `core/` — le second existe mais dans `mrta/FleetManager`, volontairement hors `core/` |

### 4.2 Ce qui va plus loin que le Start-Kit : `Dispatcher` sépare ce qu'ils laissent implicite

Le Start-Kit traduit "assignation de tâche" → "but/priorité pour le planner" **à l'intérieur**
du `MAPFPlanner` (`Entry::compute()` appelle `scheduler.plan()` puis passe le résultat brut à
`planner.plan()`, qui fait lui-même la conversion). `dotbot-logistics` a isolé cette étape dans
`Dispatcher.dispatch() -> DispatchIntent` (`core/engine/dispatcher.py`), consommé par
`Coordinator.plan()` sans jamais muter l'un ou l'autre. C'est une séparation allocation/navigation
plus propre que celle du Start-Kit.

### 4.3 Ce que ça coûte — trois problèmes concrets, vérifiés dans le code

1. **Le DTO ne garantit aucune stabilité temporelle.** `Allocator.allocate(pending, free, grid)`
   est sans mémoire, rappelé à chaque tick. Rien dans l'ABC n'empêche un agent déjà engagé d'être
   réattribué au tick suivant — cette garantie tient aujourd'hui uniquement parce que
   `FleetManager._allocate()` (`mrta/fleet_manager.py:170-174`) filtre les agents déjà assignés
   avant d'appeler l'allocateur, et parce que `_watchdog()` gère le décrochage. C'est une discipline
   d'implémentation, pas un contrat vérifié.
2. **L'abstraction est déjà contournée en pratique.** `Dispatcher.dispatch()` n'a qu'une méthode,
   qui ne sait exprimer que "voici les buts/priorités de ce tick". `run_mrta_live()`
   (`sim_dotbot_mrta.py`) a besoin d'opérations impératives (annuler une tâche sur reclic, injecter
   une cible manuelle) que `dispatch()` ne porte pas — `AGENT.md` racine le documente explicitement :
   *"`fleet` and `queue_source` are still passed around and mutated directly by
   `run_mrta_live()`... behaviour `SimulationDriver` deliberately keeps off its interface."*
   Le type concret `FleetManager` fuit déjà à travers l'abstraction dès qu'on sort du cas nominal.
3. **`DispatchIntent` est un point de synchronisation figé entre toute la matrice
   d'implémentations.** Toute nouvelle capacité MRTA (deadline souple, zone à éviter, reprise après
   blocage) oblige à étendre ce DTO partagé par les 2 `Dispatcher` et les 2 `Coordinator` existants
   à la fois. Le Start-Kit n'a pas ce coût — chaque planner interprète le schedule brut à sa façon,
   au prix de dupliquer cette logique par planner.

**Note pour éviter un contresens** : `RandomWalkCoordinator` et `RandomAllocator` (les "deuxièmes
implémentations" de `Coordinator`/`Allocator`) ne sont pas du code mort — ils sont câblés dans
`client/control/factory.py:16,81` et servent de ligne de base pour comparer l'algorithme réel
(légitime pour un article expérimental). Le nombre d'implémentations n'est donc pas le problème ;
l'absence de vérification du contrat qui les relie au moteur, si.

### 4.4 Le point le plus important : `Simulation` fusionne deux rôles que le Start-Kit sépare

`Simulation.step()` (`core/engine/simulation.py`) passe **les objets vivants** `self.agents` et
`self.grid` directement à `coordinator.plan()` et `dispatcher.dispatch()` — les mêmes objets que
`Simulation` s'apprête à muter juste après (phases lift/place). Le docstring de `Coordinator.plan()`
dit *"the grid (read-only)"*, mais rien ne l'impose : rien n'empêche un `Coordinator` d'appeler
`agent.move_to(...)` directement pendant `plan()`, contournant `_validate()` et le mécanisme
lift/place.

Le Start-Kit sépare structurellement ces deux rôles : `CompetitionSystem`+`Simulator` possèdent
l'état vivant ; **`SharedEnvironment` est une copie de valeur**, resynchronisée explicitement avant
chaque appel planner/scheduler/executor :

```cpp
// Simulator::sync_shared_env() — Start-Kit
env->curr_states = predict_states;   // copie de valeur
env->system_states = curr_states;    // copie de valeur
```

Même si un planner écrit dans `env->curr_states`, l'état vivant du `Simulator` n'est pas touché —
le prochain `sync_shared_env()` réécrase la copie depuis la source de vérité. `dotbot-logistics` n'a
pas cette isolation : la "lecture seule" est une convention documentée, pas une garantie
structurelle.

---

## 5. Ce qui manque : un équivalent d'`Executor`

Le Start-Kit a une troisième interface, `Executor` (`inc/Executor.h`), dont le rôle est distinct de
`MAPFPlanner`/`TaskScheduler` : **rejouer, tick par tick, un plan déjà calculé, en arbitrant en
temps réel via un graphe de dépendances temporelles (TPG)** si un agent prend du retard — un
problème générique d'exécution sous incertitude, indépendant de l'algorithme de planification. Une
seule implémentation est fournie (`default_executor.{h,cpp}`, 253 lignes, référence Ma, Kumar &
Koenig 2017), et c'est délibéré : ce n'est pas un axe de variation que les participants explorent.

**`dotbot-logistics` n'a aucun équivalent formalisé.** J'ai vérifié : ni `core/`, ni
`client/control/controller.py` (`SimulationController`) ne portent cette responsabilité — le
docstring de `SimulationController.step()` dit explicitement *"step() owns no clock and no loop, so
the caller decides the pacing"*. C'est un choix assumé, pas un oubli — mais son effet est que
"rejouer un plan en sécurité sous incertitude d'exécution réelle" n'existe **que** dans les scripts
racine, sous forme de `wait_until_all_arrived()`/`send_waypoints()`, dupliqués 4 fois, sans ABC,
sans test. C'est *exactement* la zone où le bug de halte immédiate (§3) est né et n'a été détecté
qu'en hardware réel.

---

## 6. Recommandations, par ordre de priorité

L'objectif : réduire la complexité *ressentie*, qui vient moins du nombre de couches que de
l'absence de garanties sur ces couches et de la duplication là où une couche manque.

### P0 — Consolider les scripts racine derrière une interface étroite

Extraire un module partagé (p. ex. `bridge/driver.py`) avec une interface minimale —
`poll_state()`, `send_waypoints()`, `wait_until_all_arrived()` — implémentée une fois par backend
(`SimulatorDriver`, `HardwareDriver`). Remplace les 4 copies de `GridStateManager` par 1 interface +
2-3 implémentations minces. C'est le changement au meilleur rapport gain/effort : il supprime la
duplication documentée dans `AGENT.md`, et donne enfin à "manual-click detection" une frontière
nommée où écrire l'invariant threading qui a cassé une fois déjà.

### P1 — Ajouter des tests de contrat légers sur `Coordinator`/`Dispatcher`/`Allocator`

Un test minimal par ABC, avec une implémentation factice, qui vérifie juste l'ordre d'appel et la
forme des données (`dispatch()` avant `plan()`, jamais l'inverse ; `DispatchIntent` bien formé) —
sans faire tourner d'algorithme réel. C'est le pattern `python_interface_test.cpp` +
`dummy_planner.py` du Start-Kit. Sans ça, chaque couche déjà bien conçue reste un pari sur la
discipline future plutôt qu'une garantie — c'est ce qui transforme une complexité maîtrisée en
complexité qui *semble* fragile.

### P2 — Décider, puis documenter, le statut réel de `Dispatcher`

Soit étendre l'ABC pour couvrir les opérations impératives (`cancel_task`, `set_priority`) que les
scripts racine appellent déjà directement sur `FleetManager` en la contournant, soit documenter
explicitement que le mode MRTA interactif exige `FleetManager` concret (pas "un `Dispatcher`
quelconque"). Le but est d'arrêter de prétendre à une substituabilité qui n'existe déjà plus en
pratique — une abstraction qu'on sait déjà contourner ailleurs coûte plus cher qu'elle ne rapporte.

### P3 — Envisager une vue en lecture seule pour `Coordinator`/`Dispatcher`

Pas nécessairement une copie complète (coût perf à chaque tick, contrairement au C++) — un type
distinct et gelé (`frozen dataclass`/vue) pour ce que `plan()`/`dispatch()` reçoivent, de sorte
qu'une mutation par erreur lève une exception plutôt que de corrompre l'état silencieusement. À
arbitrer consciemment plutôt que laisser vide.

### P4 (optionnel) — Unifier le logging

`report/` (CSV structuré, MRTA) et `log/pibt/` (métriques brutes, hardware) restent deux mécanismes
séparés, assumé dans `AGENT.md`. À ne fusionner que si l'article a besoin de croiser les deux
catégories de runs un jour — pas urgent.

---

## 7. Documents à fournir à un agent de discussion sans accès au code

Pour qu'un agent puisse discuter architecture sans lire le code, dans cet ordre de priorité :

**Essentiels**
1. Ce document (`ARCHITECTURE_REVIEW.md`) — la synthèse elle-même.
2. `/home/dok/Inria/dotbot-logistics/AGENT.md` — carte du projet, pattern de pont, le
   post-mortem du monolithe et du "halt reflex" (§3 de ce document en est un résumé, mais l'original
   a plus de détail historique).
3. `/home/dok/Inria/dotbot-logistics/simulation/AGENT.md` — carte du moteur, règles de dépendance
   entre packages, admission explicite de l'absence de tests.

**Utiles si la discussion va plus loin sur le moteur**
4. `/home/dok/Inria/dotbot-logistics/simulation/core/AGENT.md`
5. `/home/dok/Inria/dotbot-logistics/simulation/algo/AGENT.md`
6. `/home/dok/Inria/dotbot-logistics/simulation/mrta/AGENT.md`
7. `/home/dok/Inria/dotbot-logistics/simulation/client/AGENT.md`
8. `/home/dok/Inria/dotbot-logistics/simulation/report/AGENT.md`
9. `/home/dok/Inria/dotbot-logistics/simulation/diagrammes/_model.iuml` — le diagramme de classe
   source de vérité du moteur (format PlantUML texte, lisible sans outil).

**Optionnel — contexte de conventions, pas d'architecture**
10. `/home/dok/Inria/dotbot-logistics/CONVENTION.md` — utile seulement si la discussion touche au
    process (commits, branches), pas à l'architecture elle-même.

**Artefacts visuels déjà produits dans cette session** (liens à partager si l'agent peut ouvrir des
URLs) :
- Diagrammes de classe simplifiés Start-Kit vs `simulation/` (Coordinator/Dispatcher/Allocator) :
  https://claude.ai/code/artifact/604fb00d-0c99-48ea-86cb-53e14ee998de

Ne pas fournir `CLAUDE.md` (racine ou `simulation/`) — ce sont des pointeurs vers `AGENT.md`, sans
contenu propre au-delà.
