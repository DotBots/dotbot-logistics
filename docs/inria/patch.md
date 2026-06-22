# patch.md — Modifications du projet dotbot-logistics

## Modification schedule gateway Mari — schedule_huge → schedule_medium (2026-06-17)

> **Branche :** `real-dotbot-algorithm-improvement` — **hors-scope** de l'article L0/L1.
> Ce travail concerne le firmware radio et le dispatch des commandes de mouvement ; il n'affecte
> pas les métriques L0 (simulation) ni la méthodologie L1 de base. À merger sur `develop` si les
> résultats montrent une amélioration significative du `conflict_ratio` et des `step_timeouts`.



**Repo :** `/home/dok/dotbot-logistics/mari/` (branche `main`)
**Commit :** `30b0dc5`
**Fichier :** `firmware/app/03app_gateway_net/main.c`, ligne 59

**Motivation :** réduction de la latence uplink. Le schedule "huge" (sf_duration = 256,88 ms) est surdimensionné pour une expérience à ≤10 DotBots. "medium" (sf_duration = 115,51 ms, max 44 nœuds) divise la latence par ~2,2 et réduit la profondeur de file TX.

**Changement :**
```c
// avant
schedule_t *schedule_app = &schedule_huge;
// après
schedule_t *schedule_app = &schedule_medium;
```

**Rollback :** `git -C ~/dotbot-logistics/mari revert 30b0dc5`

### Script de build + flash

**Fichier :** `/home/dok/dotbot-logistics/flash_gateway_medium.fish`
**Commit dotbot-logistics :** `bb64f08`

Enchaîne en une commande :
1. `make -C ~/dotbot-logistics/mari/firmware gateway SEGGER_DIR=/opt/SEGGER/segger_embedded_studio_8.28`
2. Stage `~/.dotbot/artifacts/swarmit-local/` (symlinks : bootloader + netcore depuis `swarmit-0.8.0`, gateway .hex depuis le build local)
3. `dotbot device flash-mari-gateway --fw-version local --probe 10`

Le dossier `~/.dotbot/artifacts/swarmit-0.8.0/` n'est jamais modifié.

```bash
fish ~/dotbot-logistics/flash_gateway_medium.fish
```

**Rappel terminal fish :** `config.fish` affiche la commande à l'ouverture d'un terminal (après le rappel mosquitto).

---

# patch.md — Instrumentation de mesure de latence PyDotBot

**Date :** 2026-06-10
**Arbre de travail :** `/home/dok/testInria/venv/lib/python3.14/site-packages/` (package `dotbot` installé, pydotbot 0.29.1), versionné par un dépôt git local initialisé sur place.
**Convention :** 1 action = 1 commit → rollback possible avec `git revert <hash>` (ou `git checkout f7e552b -- <fichier>` pour revenir à l'état d'origine d'un fichier).

---

## Activation (opt-in)

L'instrumentation est **désactivée par défaut** (zéro impact, vérifié). Elle s'active en définissant la variable d'environnement `DOTBOT_LATENCY_DIR` au lancement du contrôleur :

```bash
DOTBOT_LATENCY_DIR=/home/dok/testInria/latency_logs \
  dotbot run simulator --simulator-init-state /home/dok/testInria/simulator_init_state.toml
```

(⚠️ l'option s'appelle `--simulator-init-state`, pas `--init-state`.)

## Page de consultation des logs

**http://localhost:8000/latency** — une page HTML unique, auto-rafraîchie toutes les 2 s, qui affiche pour chaque fonctionnalité : statistiques (count, min, moyenne, p95, max en ms), les dernières entrées, et un lien de téléchargement du CSV brut.

API associée :
- `GET /latency/data?limit=N` — résumé JSON de toutes les catégories ;
- `GET /latency/data/{categorie}` — CSV brut ;
- `POST /latency/frontend` — réception des mesures du navigateur (utilisé par le probe JS).

## Un log (CSV) par fonctionnalité

Dans `$DOTBOT_LATENCY_DIR` :

| Fichier | Fonctionnalité mesurée | Point de mesure |
|---|---|---|
| `http.csv` | Traitement de chaque requête HTTP (method, path, status, duration_ms) | middleware FastAPI, `server.py` |
| `controller_frame.csv` | Traitement de chaque paquet reçu par la boucle du controller (payload_type, address, duration_ms) | `controller.py::handle_received_frame` |
| `ws_notify.csv` | Diffusion des notifications WebSocket (cmd, n_clients, duration_ms) | `controller.py::notify_clients` |
| `serial_tx.csv` | Écriture vers l'adapter série/MQTT/simulateur (destination, payload_type, duration_ms) | `controller.py::send_payload` |
| `frontend_ws.csv` | Latence backend → navigateur (server_timestamp, client_timestamp, latency_ms) | probe JS + `POST /latency/frontend` |
| `rtt.csv` | RTT bout-en-bout commande → mouvement LH2 (method, threshold_mm, distance_mm, rtt_ms) | script `measure_rtt.py` |

---

## Fichiers modifiés / créés

### Dans site-packages (versionnés git — `git -C …/site-packages log --oneline`)

| Commit | Fichier | Modification |
|---|---|---|
| `f7e552b` | — | **État initial** de `dotbot/` + `dotbot_utils/` avant toute modification |
| `3ff7a1a` | `dotbot/latency.py` | **NOUVEAU** |
| `b901eec` | `dotbot/models.py` | champ `timestamp` optionnel |
| `c00db87` | `dotbot/controller.py` | 3 points de mesure |
| `fbb6c4f` | `dotbot/server.py` + `dotbot/latency.py` | middleware + endpoints `/latency` + page HTML |
| `2f8d5a2` | `dotbot/csv_data_logger.py` | colonne `timestamp_ns` |
| `59ec12f` | `dotbot/frontend/build/` | état initial du build (était ignoré par `frontend/.gitignore`, absent du 1er commit) |
| `42dcdb5` | `dotbot/frontend/build/latency-probe.js` + `index.html` | **NOUVEAU** probe + balise `<script>` |

#### `dotbot/latency.py` (nouveau — commits `3ff7a1a`, `fbb6c4f`)
- Classe `LatencyLogger` : écrit chaque mesure en append dans `<DOTBOT_LATENCY_DIR>/<categorie>.csv` (header automatique, écriture line-buffered, verrou thread). **No-op total si `DOTBOT_LATENCY_DIR` n'est pas définie.**
- Singleton `LATENCY` importé par `controller.py` et `server.py`.
- Côté lecture : `categories()`, `read()`, `summary()` (stats sur la première colonne `*_ms`) — utilisés par les endpoints `/latency/*`.
- Constante `VIEWER_HTML` : la page de visualisation autonome (HTML + JS, fetch `/latency/data` toutes les 2 s).

#### `dotbot/models.py` (commit `b901eec`)
- `DotBotNotificationModel` : ajout de `timestamp: Optional[float] = None`. Posé à `time.time()` (heure serveur) juste avant l'envoi WebSocket quand l'instrumentation est active ; absent sinon (`exclude_none=True` → payload inchangé).

#### `dotbot/controller.py` (commit `c00db87`)
- Import `from dotbot.latency import LATENCY`.
- `handle_received_frame()` : `time.perf_counter_ns()` à l'entrée ; à la fin, log `controller_frame.csv` (durée totale de décodage + mise à jour d'état + déclenchement notification). C'est le **profiling en continu de la boucle du controller** : si la durée croît avec le nombre de DotBots, c'est visible ici.
- `notify_clients()` : injecte `notification.timestamp = time.time()` (consommé par le probe frontend), chronomètre le `asyncio.gather` d'envoi à tous les clients → `ws_notify.csv`.
- `send_payload()` : chronomètre `self.adapter.send_payload(...)` → `serial_tx.csv`. *Point unique couvrant les 4 adapters (SerialAdapter, MarilibEdgeAdapter, MarilibCloudAdapter, simulateur) sans patcher `adapter.py`. La mesure côté firmware (gateway nRF DK) est hors périmètre logiciel.*

#### `dotbot/server.py` (commit `fbb6c4f`)
- Middleware `@api.middleware("http")` : durée de traitement de chaque requête → header `X-Process-Time` (en secondes) + ligne dans `http.csv`. Les routes `/latency*` sont exclues (pas d'auto-pollution). Inactif si instrumentation désactivée.
- Endpoints `GET /latency`, `GET /latency/data`, `GET /latency/data/{category}`, `POST /latency/frontend` (modèle pydantic `LatencyFrontendEntry`).

#### `dotbot/csv_data_logger.py` (commit `2f8d5a2`)
- Ajout de la colonne `timestamp_ns` (`time.time_ns()`, époque en nanosecondes) à côté du `timestamp` existant, dans `fieldnames` et `log()`.
- ⚠️ Si un ancien fichier `csv_data_output` est réutilisé (mode append), son header ne contient pas la nouvelle colonne : supprimer/renommer les anciens fichiers.

#### `dotbot/frontend/build/latency-probe.js` (nouveau) + `build/index.html` (commit `42dcdb5`)
- `frontend/src` du venv étant **incomplet** (`utils/` absent, pas de `node_modules`), un rebuild React est impossible → probe autonome injecté dans le build :
- `latency-probe.js` : ouvre son propre WebSocket sur `/controller/ws/status` ; pour chaque message portant `timestamp`, enregistre `{server_timestamp, client_timestamp: Date.now()/1000, cmd}` et envoie par lots (toutes les 2 s) vers `POST /latency/frontend` → `frontend_ws.csv`. Reconnexion automatique ; silencieux quand l'instrumentation est désactivée (pas de `timestamp` dans les messages). Horloges identiques car même machine (localhost).
- `index.html` : une ligne ajoutée : `<script defer src="/PyDotBot/latency-probe.js"></script>`.

### Dans `/home/dok/testInria/` (hors git)

#### `measure_rtt.py` (nouveau) — RTT de bout en bout
Script standalone (REST + WebSocket uniquement, simulateur **et** robots réels) :

```bash
DOTBOT_LATENCY_DIR=/home/dok/testInria/latency_logs ./venv/bin/python measure_rtt.py --trials 10
# options : --address, --method ws|poll, --threshold-mm 30, --speed 60, --timeout 10, --settle 1
```

Par essai : position LH2 de référence → `t0 = perf_counter()` → `PUT …/move_raw` → attente d'une déviation > seuil (WebSocket par défaut, ou polling REST 10 ms) → RTT → commande stop. Écrit `rtt.csv` + stats console (min/moyenne/p95/max).

Le RTT couvre **toute la chaîne** : HTTP FastAPI + controller + adapter (UART/BLE ou simulateur) + réaction moteur + fix LH2 + notification retour.

---

## Vérifications effectuées (2026-06-10, simulateur 10 bots)

- Sans `DOTBOT_LATENCY_DIR` : aucun fichier créé, pas de header `X-Process-Time`, pas de `timestamp` dans les messages WS, `/latency/data` → `enabled: false`. Comportement d'origine inchangé.
- Avec instrumentation : les 6 CSV se remplissent ; page `/latency` OK.
- Ordres de grandeur mesurés (simulateur) : http ≈ 0,3–3,9 ms ; controller_frame ≈ 0,3–5,3 ms ; ws_notify ≈ 0,001–9 ms ; serial_tx ≈ 0,2–0,5 ms ; **RTT ≈ 235–500 ms** (10 essais, méthodes ws et poll).

## Procédures manuelles complémentaires

- **Profiling ponctuel de la boucle** (en plus de `controller_frame.csv`) :
  `./venv/bin/pip install pyinstrument` puis
  `DOTBOT_LATENCY_DIR=… ./venv/bin/pyinstrument -m dotbot run simulator …` — rapport d'appels à l'arrêt (Ctrl+C). Analyser la chaîne `adapter → protocol → controller → models`.
- **Temps de rendu React (`DotBotsMap`)** : extension navigateur React Developer Tools → onglet *Profiler* → enregistrer pendant un déplacement avec beaucoup de robots → inspecter les commits de `DotBotsMap`. (Non instrumentable en code sans rebuild du frontend.)

---

## Modification rayon DotBot 40 mm → 50 mm (2026-06-17)

**Commit :** `baf12a4`
**Fichier :** `dotbot/frontend/build/assets/index-DIogaYNf.js`
**Motivation :** affichage +25% plus grand (40 × 1.25 = 50 mm). Rayon actif/survolé : 55 mm (50+5).

**Changement :** `Li=40` → `Li=50` (1 occurrence — variable minifiée de `dotbotRadius` dans `constants.ts`).

**Impact threshold :** aucun. Le threshold de waypoint est une valeur indépendante envoyée au serveur via `PUT .../waypoints` ; la taille visuelle du robot ne l'affecte pas.

**Rollback :** `git -C …/site-packages revert baf12a4` ou `sed -i 's/Li=50/Li=40/' …/index-DIogaYNf.js`

---

## Modification grille SVG — taille des cases 250 mm → 400 mm (2026-06-17)

**Commit :** `effb798`
**Fichier :** `dotbot/frontend/build/assets/index-DIogaYNf.js`
**Motivation :** passage à une grille 5×5 cases pour 2000×2000 mm (400 mm/case). La valeur 250 mm donnait 8×8 cases, incorrecte pour l'affichage PIBT 5×5.

**Changement :** remplacement de `250*a/e.areaSize.width` par `400*a/e.areaSize.width` — 6 occurrences (3 paires width/height pour `<pattern id>`, `<rect>`, `<path>`).

**Rollback :** `git -C …/site-packages revert effb798` ou `sed -i 's/400\*a\/e\.areaSize\.width/250*a\/e.areaSize.width/g' dotbot/frontend/build/assets/index-DIogaYNf.js`

---

## Modification grille SVG — taille des cases 500 mm → 250 mm (2026-06-15)

**Commit :** `1418e66`
**Fichier :** `dotbot/frontend/build/assets/index-DIogaYNf.js`
**Motivation :** passage à une grille 2000×2000 mm avec cases PIBT de 250 mm (au lieu de 4000×4000 / 500 mm). La grille SVG affiche maintenant 8×8 cases.

**Changement :** remplacement de `500*a/e.areaSize.width` par `250*a/e.areaSize.width` — 3 occurrences dans le JS minifié (pattern unique : `id`, `rect`, `path`).

**Rollback :** `git -C …/site-packages revert 1418e66` ou `sed -i 's/250\*a\/e\.areaSize\.width/500*a\/e.areaSize.width/g' dotbot/frontend/build/assets/index-DIogaYNf.js`

> ⚠️ **Cache navigateur** : le hash du fichier JS ne change pas quand on patche directement → après tout patch du build, faire un **Ctrl+Shift+R** (hard refresh) dans le navigateur pour forcer le rechargement.

---

## Limites connues

- Une **réinstallation/mise à jour de pydotbot** (`pip install …`) écraserait les fichiers patchés ; le dépôt git de site-packages permet de re-appliquer (`git diff f7e552b HEAD -- dotbot | git apply`) ou de comparer.
- La mesure `serial_tx` s'arrête à l'écriture côté Python ; le transit radio et le firmware (gateway nRF DK, DotBot) ne sont mesurables que via le RTT global.
- `frontend_ws.csv` mesure la latence de **livraison** WebSocket au navigateur, pas le temps de rendu React (voir React Profiler ci-dessus).
