# Tuto — Lancer le test PIBT sur DotBots (simulateur & réel)

Deux scripts, même algorithme PIBT, deux modes d'exécution :

| Script | Mode | Quand l'utiliser |
|---|---|---|
| `dotbot_pibt_demo-v1.py` | Envoi **en masse** (tout le chemin d'un coup) | Simulateur (physique propre) |
| `dotbot_pibt_demo-v2rc1.py` | **Pas-à-pas synchronisé** (1 waypoint/pas, barrière) | Réel **et** simulateur |

Les deux ne parlent qu'à l'**API REST** du contrôleur (`http://localhost:8000`) et
auto-détectent le nombre de bots. Ils ne dépendent pas du transport.

> Prérequis Python : le venv du projet, et le module de simulation accessible
> (`../Inria/Main/simulation`, déjà géré par le `sys.path.insert` en tête des scripts).

---

## Cas A — Simulateur

Aucun matériel. Le contrôleur simule des bots aux positions de `simulator_init_state.toml`.

### 1. Lancer le simulateur (terminal 1)
```bash
dotbot run simulator \
  --map-size 4000x4000 \
  --init-state /home/dok/testInria/simulator_init_state.toml
```
Ouvre l'UI sur http://localhost:8000 (option `-w` pour ouvrir le navigateur).

### 2. Vérifier que les bots sont visibles (terminal 2)
```bash
curl -s http://localhost:8000/controller/dotbots | python3 -m json.tool | head
```
Attendu : les 10 adresses du toml (`BADCAFE1…`, `DEADBEEF…`, …) avec `lh2_position`.

### 3. Lancer le test PIBT
```bash
# Version simulateur d'origine (envoi en masse)
python dotbot_pibt_demo-v1.py --seed 1

# OU version pas-à-pas (marche aussi en simu)
python dotbot_pibt_demo-v2rc1.py --seed 1
```
Ajouter `--dry-run` pour visualiser sans envoyer de commandes.

---

## Cas B — DotBots réels

Le contrôleur est branché sur le vrai swarm via le **gateway** (firmware Mari) et
**MQTT**. La navigation par waypoints s'exécute **à bord** de chaque bot (boucle LH2).

### 1. Broker MQTT local (terminal 1)
```bash
mosquitto -c /home/dok/testInria/mosquitto.conf   # écoute sur :1883
```

### 2. Gateway Mari (terminal 2)
Le gateway nRF (flashé `flash-mari-gateway`) doit être branché en USB. Vérifier la flotte :
```bash
dotbot swarm status        # doit lister les DotBotV3 réels
```

### 3. Mettre les bots en application DotBot
Si `swarm status` les montre en **"Bootloader"**, ils ne tournent pas l'app DotBot →
ils n'apparaissent PAS dans le contrôleur. Flasher l'app DotBot complète puis la démarrer :
```bash
dotbot swarm flash /home/dok/.dotbot/artifacts/dotbot-firmware-1.22.0/dotbot-sandbox-dotbot-v3.bin -ys
dotbot swarm start
dotbot swarm status        # doit passer à "Running"
```
> Seule l'app `dotbot-sandbox-dotbot-v3.bin` fournit advertisement LH2 + navigation
> waypoints. `spin`, `move`, `motors`, `timer`, `rgbled` ne sont PAS pilotables par le contrôleur.

### 4. Lancer le contrôleur réel (terminal 3)
```bash
dotbot run controller \
  --conn mqtt://localhost:1883 \
  --swarm-id 1234 \
  --map-size 4000x4000
```
> `--map-size` doit couvrir la zone LH2 réelle. `--swarm-id` = celui du topic (`/mari/1234/…`).
> NE PAS lancer `dotbot run simulator` en parallèle (il occuperait le port 8000).

### 5. Vérifier que le contrôleur voit les bots
```bash
curl -s http://localhost:8000/controller/dotbots | python3 -m json.tool
```
Attendu : les **vraies** adresses avec `lh2_position` non nul et `calibrated` ≠ 0.
Si `[]` : le contrôleur écoute encore en simulateur, ou les bots sont restés en bootloader.

### 6. Lancer le test PIBT (version durcie obligatoire)
```bash
# 1) Vérification à blanc (aucune commande envoyée)
python dotbot_pibt_demo-v2rc1.py --dry-run --seed 1

# 2) Test réel — commencer petit, puis augmenter
python dotbot_pibt_demo-v2rc1.py --seed 1 --steps 20
```

---

## Options utiles (v2rc1)

| Option | Défaut | Rôle |
|---|---|---|
| `--threshold` | 100 mm | Distance sous laquelle un bot est "arrivé" à sa case |
| `--step-timeout` | 8.0 s | Attente max par pas ; au-delà → log + on continue (anti-blocage) |
| `--settle` | 0.3 s | Pause après arrivée pour laisser les bots s'immobiliser |
| `--min-bots` | 2 | Bots localisés requis avant de démarrer |
| `--steps` | 30 | Pas PIBT max |
| `--seed` | aléatoire | Reproductibilité des buts aléatoires |
| `--map-cells` | 8 | Grille NxN de repli si l'API map_size ne répond pas |
| `--cell-mm` | 500 | Taille d'une case (centres = `gx*500+250`) |

## Dépannage rapide

- **`curl` renvoie `[]`** : contrôleur en simulateur, ou bots en bootloader (faire `swarm start`).
- **`Connection refused`** : contrôleur non lancé sur :8000.
- **Bots non localisés** : couverture/calibration LH2 (`~/.dotbot/calibration.out`). Recalibrer si positions incohérentes.
- **Un bot bloque le pas** : `--step-timeout` l'ignore après délai et poursuit les autres.
