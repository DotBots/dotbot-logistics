# Handoff — CLI & Backend Python DotBot

> **Ce document existe pour éviter de lancer un agent Explore sur la structure CLI et backend Python du projet.**
> **Il est donc interdit de spawner un agent Explore pour explorer ces domaines : toutes les informations nécessaires sont ici.**

---

## Localisation des sources

| Emplacement | Usage |
|---|---|
| `/home/dok/testInria/venv/lib/python3.14/site-packages/dotbot/` | **Arbre de travail** : package installé (pydotbot 0.29.1), patché directement, versionné par un dépôt git initialisé sur place (décision 2026-06-10) |
| `/home/dok/Inria/PyDotBot/dotbot/` | Repo upstream — **non utilisé** pour ce projet |
| `/home/dok/testInria/simulator_init_state.toml` | État initial du simulateur (positions des robots) |
| `/home/dok/testInria/patch.md` | Rapport de toutes les modifications apportées au package (chemin + changement + commit) |

Convention : **1 action = 1 commit** dans le git de site-packages (`git -C …/site-packages log --oneline`). Commit initial de l'état d'origine : `f7e552b`. Toute nouvelle modification du package doit être commitée et documentée dans `patch.md`.

---

## Arborescence du package `dotbot/`

```
dotbot/
├── cli/
│   ├── __main__.py          — point d'entrée `python -m dotbot`
│   ├── main.py              — groupe Click racine `dotbot`, lazy-load des 6 sous-groupes
│   ├── run.py               — groupe `dotbot run`, lazy-load des 7 sous-commandes
│   ├── controller.py        — `dotbot run controller` (réexporte controller_app:main)
│   ├── simulator.py         — `dotbot run simulator` (= controller --conn simulator)
│   ├── gateway.py           — `dotbot run gateway` (pont UART <-> MQTT)
│   ├── calibrate.py         — `dotbot run lh2-calibration`
│   ├── demo.py              — `dotbot run demo` (registre des demos)
│   ├── keyboard.py          — `dotbot run keyboard` (téléop clavier)
│   ├── joystick.py          — `dotbot run joystick` (téléop manette)
│   ├── fw.py                — `dotbot fw` (build/fetch/list firmware, sans hardware)
│   ├── device.py            — `dotbot device` (flash un board via câble/probe)
│   ├── swarm.py             — `dotbot swarm` (flotte OTA : status, flash, monitor)
│   ├── swarm_lh2.py         — sous-commandes LH2 de swarm
│   ├── config_cmd.py        — `dotbot config` (affiche config résolue)
│   ├── deployment_cmd.py    — `dotbot deployment` (liste les déploiements)
│   ├── _lazygroup.py        — LazyGroup Click : imports différés à l'invocation
│   ├── _lazy.py             — lazy_subcommand pour packages optionnels
│   ├── _cfg.py              — décorateur from_config (lit les défauts du fichier de config)
│   ├── _conn.py             — parsing --conn (simulator / serial / mqtts://...)
│   ├── _artifacts.py        — helpers téléchargement firmware
│   ├── _fw_helpers.py       — helpers build firmware
│   └── _swarm_inject.py     — injection de commandes swarm
│
├── examples/
│   ├── circle/
│   │   └── circle.py        — demo `dotbot run demo circle` (template REST minimal)
│   ├── qrkey_demo/
│   │   └── cli.py           — demo `dotbot run demo qr` (pont téléphone MQTT)
│   ├── charging_station/
│   │   └── charging_station.py
│   ├── labyrinth/
│   │   └── labyrinth.py
│   ├── minimum_naming_game/
│   │   ├── minimum_naming_game.py
│   │   ├── minimum_naming_game_with_motion.py
│   │   ├── controller.py
│   │   ├── controller_with_motion.py
│   │   └── walk_avoid.py
│   ├── motions/
│   │   └── motions.py
│   ├── work_and_charge/
│   │   └── work_and_charge.py
│   └── common/
│       ├── orca.py          — algorithme ORCA (évitement de collisions)
│       ├── sct.py           — Space-Constrained Topology
│       └── vec2.py          — vecteur 2D utilitaire
│
├── controller_app.py        — Click command `main` (FastAPI + config + boucle async)
├── controller.py            — moteur du contrôleur (état robots, dispatch commandes)
├── server.py                — serveur HTTP FastAPI (port 8000), monte le frontend
├── rest.py                  — RestClient async (httpx) pour les exemples/demos
├── websocket.py             — gestion WebSocket côté serveur
├── adapter.py               — couche transport (serial / MQTT / simulator)
├── protocol.py              — protocole BLE bas niveau, ApplicationType, ControlModeType
├── models.py                — modèles Pydantic (DotBotModel, commandes, notifications)
├── dotbot_simulator.py      — simulateur DotBot (physics 2D)
├── sailbot_simulator.py     — simulateur SailBot (GPS)
├── config.py                — chargement config dotbot.toml / ~/.dotbot/config.toml
├── logger.py                — structlog + setup_logging
├── joystick.py              — driver manette (module, pas CLI)
├── keyboard.py              — driver clavier (module, pas CLI)
├── csv_data_logger.py       — enregistrement CSV des positions
└── calibration/
    └── cli.py               — logique de calibration LH2
```

---

## Hiérarchie CLI complète

```
dotbot                          (main.py — LazyGroup)
├── fw                          (fw.py — firmware sans hardware)
│   ├── build
│   ├── fetch
│   ├── list
│   └── make
├── device                      (device.py — un board via câble)
│   └── flash-mari-gateway
├── swarm                       (swarm.py — flotte OTA)
│   ├── status
│   ├── start / stop
│   ├── flash
│   └── monitor
├── run                         (run.py — processus hôte)
│   ├── controller              → controller_app:main (FastAPI, port 8000)
│   ├── simulator               → controller --conn simulator
│   ├── gateway                 → pont UART <-> MQTT
│   ├── lh2-calibration         → calibration LH2
│   ├── keyboard                → téléop clavier
│   ├── joystick                → téléop manette
│   └── demo                   (demo.py — demos enregistrées)
│       ├── circle              → examples/circle/circle.py
│       └── qr                 → examples/qrkey_demo/cli.py
├── config                      (config_cmd.py — lecture seule)
└── deployment                  (deployment_cmd.py — lecture seule)
```

**Options globales (avant le sous-groupe) :**
- `-c / --config PATH` — fichier de config (défaut : `dotbot.toml` dans le cwd, puis `~/.dotbot/config.toml`)
- `--deployment NAME` — déploiement cible
- `--version`

---

## Démarrage du simulateur

```bash
dotbot run simulator            # DotBot (roues différentielles)
dotbot run simulator --sailbot  # SailBot (voilier GPS)
dotbot run simulator -w         # ouvre le navigateur sur http://localhost:8000
```

`dotbot run simulator` est un alias propre : il préfixe `--conn simulator` et délègue à `controller_app:main`. Toutes les options du controller sont transmises telles quelles.

**Avec état initial personnalisé :**
```bash
dotbot run simulator --simulator-init-state /home/dok/testInria/simulator_init_state.toml
```
⚠️ L'option s'appelle bien `--simulator-init-state` (et non `--init-state`).

---

## Chaîne d'exécution interne

```
dotbot run simulator / controller
  → controller_app.py:main()    (Click, lit --conn, configure ControllerSettings)
    → controller.py:Controller  (moteur : gère l'état de chaque robot)
      → adapter.py              (transport : serial / MQTT / simulator)
      → protocol.py             (décodage paquets BLE)
      → server.py               (FastAPI HTTP :8000 + WebSocket)
        → rest.py endpoints     (GET/PUT /controller/...)
        → websocket.py          (WS /controller/ws/status)
        → frontend/             (fichiers statiques servis par FastAPI)
      → dotbot_simulator.py     (si --conn simulator : physics 2D)
      → models.py               (état des robots : DotBotModel)
```

---

## Modèles de données clés (`models.py`)

### `DotBotModel` — état complet d'un robot

```python
address: str
application: ApplicationType        # DotBot=0, SailBot=1, Freebot=2, XGO=3
swarm: str = "0000"
status: DotBotStatus                # ACTIVE=0, INACTIVE=1, LOST=2
mode: ControlModeType               # MANUAL / AUTONOMOUS
last_seen: float
direction: Optional[int]            # degrés
lh2_position: Optional[DotBotLH2Position]    # { x, y } en mm
gps_position: Optional[DotBotGPSPosition]    # { latitude, longitude }
waypoints: List[...]
waypoints_threshold: int = 100      # mm (DotBot) ou m (SailBot)
position_history: List[...]
calibrated: int                     # bitmask : 0x01 LH2#1, 0x02 LH2#2
battery: float = 3.0               # Volts
move_raw: Optional[DotBotMoveRawCommandModel]
rgb_led: Optional[DotBotRgbLedCommandModel]
```

### Commandes Pydantic

```python
DotBotMoveRawCommandModel   → { left_x, left_y, right_x, right_y }  # int
DotBotRgbLedCommandModel    → { red, green, blue }                   # int
DotBotXGOActionCommandModel → { action: int }
DotBotWaypoints             → { threshold: int, waypoints: List[...] }
DotBotLH2Position           → { x: float, y: float }                # mm
DotBotGPSPosition           → { latitude: float, longitude: float }
DotBotMapSizeModel          → { width: int, height: int }            # mm
```

### Notifications WebSocket (`DotBotNotificationCommand`)

```python
NONE=0, RELOAD=1, UPDATE=2, PIN_CODE_UPDATE=3, NEW_DOTBOT=4
```

---

## API REST du contrôleur (base : `http://localhost:8000`)

```
GET  /controller/dotbots                                    → List[DotBotModel]
     ?address=&application=&status=&limit=&max_battery=&min_battery=
     &max_positions=&max_position_x=&min_position_x=&max_position_y=&min_position_y=

GET  /controller/map_size                                   → DotBotMapSizeModel

PUT  /controller/dotbots/{address}/{application}/move_raw
     body: { left_x, left_y, right_x, right_y }            # int, [-128, 127]

PUT  /controller/dotbots/{address}/{application}/rgb_led
     body: { red, green, blue }                             # int [0, 255]

PUT  /controller/dotbots/{address}/{application}/waypoints
     body: { threshold: int, waypoints: [...] }

PUT  /controller/dotbots/{address}/{application}/clear_position_history
     body: ""

PUT  /controller/dotbots/{address}/{application}/xgo_action
     body: { action: int }

WS   /controller/ws/status                                  → DotBotNotificationModel
```

`application` dans l'URL est la valeur entière de `ApplicationType` : `0` pour DotBot, `1` pour SailBot.

---

## `RestClient` async (`rest.py`)

Client httpx utilisé dans les exemples/demos :

```python
async with rest_client(host="localhost", port=8000, https=False) as client:
    bots = await client.fetch_dotbots(query=DotBotQueryModel(application=ApplicationType.DotBot))
    await client.send_move_raw_command(address, ApplicationType.DotBot,
                                       DotBotMoveRawCommandModel(left_x=0, left_y=60, right_x=0, right_y=30))
    await client.send_waypoint_command(address, ApplicationType.DotBot,
                                       DotBotWaypoints(threshold=100, waypoints=[...]))
    await client.clear_position_history(address)
```

---

## Template pour une nouvelle demo (`circle.py` comme base)

**Fichier :** `dotbot/examples/circle/circle.py` — **copier ce pattern** pour toute nouvelle demo.

```python
import time
import click
import requests

@click.command(name="ma-demo", help="Description courte.")
@click.option("--base", default="http://localhost:8000", show_default=True)
@click.option("--seconds", "-t", default=5.0, show_default=True)
def main(base, seconds):
    bots = requests.get(f"{base}/controller/dotbots", timeout=5).json()
    address = bots[0]["address"]
    move = f"{base}/controller/dotbots/{address}/0/move_raw"
    end = time.time() + seconds
    try:
        while time.time() < end:
            requests.put(move, json={"left_x": 0, "left_y": 60, "right_x": 0, "right_y": 30})
            time.sleep(0.1)
    finally:
        requests.put(move, json={"left_x": 0, "left_y": 0, "right_x": 0, "right_y": 0})
```

**Pour enregistrer la demo dans `dotbot run demo` :**

Modifier `dotbot/cli/demo.py` (2 lignes) :
```python
from dotbot.examples.ma_demo.ma_demo import main as _ma_demo_main
cmd.add_command(_ma_demo_main, name="ma-demo")
```

**Alternative sans toucher au package** — script standalone suffisant pour prototypage :
```bash
python mon_script.py   # utilise uniquement requests + l'API REST
```

---

## Configuration (`config.py`)

Ordre de découverte :
1. `-c PATH` ou `DOTBOT_CONFIG` env var
2. `dotbot.toml` dans le répertoire courant
3. `~/.dotbot/config.toml`

Variables d'environnement MQTT (ne jamais passer en flag) :
- `DOTBOT_MQTT_USER`
- `DOTBOT_MQTT_PASS`

---

## Simulateur : ajouter des robots et configurer la grille

### Ajouter/positionner des robots

Fichier : `/home/dok/testInria/simulator_init_state.toml`

Ajouter un bloc `[[dotbots]]` par robot supplémentaire :
```toml
[[dotbots]]
address = "AABBCCDDEEFF0011"   # adresse unique, 16 caractères hex
pos_x = 500                    # mm depuis le coin haut-gauche [0, map_size]
pos_y = 500
direction = 0                  # degrés : 0=nord, sens horaire, [0, 360]
calibrated = 0xff              # bitmask LH2 : 0xff = les deux phares calibrés
                               # (obligatoire pour apparaître sur la carte SVG)
network_mode = "default"       # optionnel : "default" ou "mari"
```

Lancer avec cet état :
```bash
dotbot run simulator --simulator-init-state /home/dok/testInria/simulator_init_state.toml
```

### Taille de la grille (`--map-size`)

Défaut : `2000x2000` mm. Format : `LARGEURxHAUTEUR` en mm.

Les carreaux SVG font **500 mm** chacun. La taille de la grille = nb_cases × 500.

| Grille souhaitée | --map-size |
|---|---|
| 4×4 cases (2 m × 2 m, défaut) | `2000x2000` |
| 10×10 cases (5 m × 5 m) | `5000x5000` |
| 12×12 cases (6 m × 6 m) | `6000x6000` |

La portée LH2 est typiquement inférieure à 6 m — rester en dessous de `6000x6000`.

```bash
dotbot run simulator --map-size 5000x5000   # 10×10 cases
```

⚠️ Les `pos_x` / `pos_y` du toml doivent rester dans `[0, valeur map-size]`.  
Avec `5000x5000`, les positions vont de 0 à 5000 mm.

Commande complète avec grille et état initial :
```bash
dotbot run simulator \
  --map-size 5000x5000 \
  --simulator-init-state /home/dok/testInria/simulator_init_state.toml
```

---

## Internes du contrôleur (`controller.py`)

Flux d'un paquet entrant (advertisement DotBot → mise à jour d'état → notification WS) :

```
adapter (serial/MQTT/simulateur)
  → Controller.handle_received_frame(frame)        # ligne ~306
      ├─ ignore CMD_MOVE_RAW / CMD_RGB_LED (early return)
      ├─ décode source + PayloadType (protocol.py)
      ├─ DOTBOT_ADVERTISEMENT : extrait lh2_position, batterie, mode,
      │    historique de positions, log CSV (csv_data_logger)
      ├─ construit DotBotNotificationModel (cmd=UPDATE/NEW_DOTBOT)
      └─ asyncio.create_task(self.notify_clients(notification))   # fin, ~ligne 559
  → notify_clients(notification)                   # ligne ~577
      └─ json.dumps(model_dump(exclude_none=True)) → tous les WS connectés
```

- **Envoi de commandes** : `Controller.send_payload(destination, payload)` (~ligne 589) → `self.adapter.send_payload(...)`. Point de passage **unique** de toutes les commandes sortantes, quel que soit le transport.
- **Adapters** (`adapter.py`) : `SerialAdapter` (série brute, déprécié), `MarilibEdgeAdapter` (série via Marilib), `MarilibCloudAdapter` (MQTT), `DotBotSimulatorAdapter` / `SailBotSimulatorAdapter` (in-process). Tous exposent `start()` + `send_payload()`.
- **Boucle principale** : `Controller.run()` (~ligne 715) lance 4 tâches asyncio : uvicorn, adapter, refresh statut (1 s), ouverture navigateur.
- **`logger.py`** : structlog + stdlib, timestamps ISO (`TimeStamper(fmt="iso")`), handler console (rich) + fichier `pydotbot.log` (logfmt). Logger racine : `LOGGER = structlog.get_logger("pydotbot")`.
- **`csv_data_logger.py`** : `CSVDataLogger.log()` écrit une ligne par advertisement (positions réelle/simulée, PWM, encodeurs, batterie…) avec `timestamp` (`time.time()`) **et `timestamp_ns`** (`time.time_ns()`, ajouté 2026-06).
- D'origine, les payloads WebSocket ne contenaient **aucun timestamp** ; un champ optionnel a été ajouté (voir ci-dessous).

---

## Instrumentation latence (ajoutée 2026-06-10)

Détail complet : `/home/dok/testInria/patch.md`. Résumé :

- **Opt-in** : définie par la variable d'env `DOTBOT_LATENCY_DIR=<dossier>` au lancement du contrôleur. Sans elle : no-op total (vérifié).
- **Module** : `dotbot/latency.py` (singleton `LATENCY`, un CSV par catégorie).
- **Logs produits** : `http.csv` (middleware FastAPI + header `X-Process-Time`), `controller_frame.csv` (durée `handle_received_frame`), `ws_notify.csv` (diffusion WS), `serial_tx.csv` (écriture adapter), `frontend_ws.csv` (probe navigateur), `rtt.csv` (script `measure_rtt.py`).
- **Page de consultation** : `http://localhost:8000/latency` (+ API `/latency/data[/{cat}]`, `POST /latency/frontend`).
- **WS** : `DotBotNotificationModel.timestamp` (heure serveur) présent dans chaque message quand l'instrumentation est active.
- **RTT bout-en-bout** : `/home/dok/testInria/measure_rtt.py` (`--trials`, `--method ws|poll`, `--threshold-mm`).

---

---

## Gateway Mari — build et flash firmware custom

> **Branche :** `real-dotbot-algorithm-improvement` — **hors-scope** de l'article L0/L1.
> Merger sur `develop` uniquement si les résultats réels montrent une amélioration mesurable.



**Contexte :** le schedule du gateway est hardcodé dans `firmware/app/03app_gateway_net/main.c` (repo `mari`, `/home/dok/dotbot-logistics/mari/`). Actuellement configuré sur `schedule_medium` (sf_duration 115,51 ms, ≤44 nœuds).

**Build :** SEGGER Embedded Studio installé dans `/opt/SEGGER/segger_embedded_studio_8.28/`. Le Makefile du firmware utilise `SEGGER_DIR=/opt/segger` par défaut → toujours passer la variable.

**Commande complète (build + stage + flash) :**
```bash
fish ~/dotbot-logistics/flash_gateway_medium.fish
```

Ce script :
1. Compile le firmware gateway (app + net core)
2. Crée `~/.dotbot/artifacts/swarmit-local/` avec des symlinks (bootloader + netcore depuis `swarmit-0.8.0`, gateway .hex depuis le build)
3. Flashe avec `dotbot device flash-mari-gateway --fw-version local --probe 10`

**Pour changer de schedule :** modifier la ligne 59 de `mari/firmware/app/03app_gateway_net/main.c` (`schedule_medium` → `schedule_tiny` / `schedule_big` / `schedule_huge`), relancer le script.

| Schedule | ID | max_nodes | sf_duration |
|---|---|---|---|
| tiny   | 6 | 10  | 29,31 ms  |
| medium | 4 | 44  | 115,51 ms |
| big    | 3 | 66  | 174,12 ms |
| huge   | 1 | 102 | 256,88 ms |

**Rollback firmware :** `git -C ~/dotbot-logistics/mari revert 30b0dc5`

---

## Voir aussi

- **Structure frontend (React/TS)** → `Handoff_Frontend.md`
- **Rapport des modifications du package + instrumentation latence** → `patch.md`
- **API REST** également documentée côté frontend dans `Handoff_Frontend.md` (section API REST)
