# Tutoriel — Lancer le simulateur DotBot avec mesure de latence

## Prérequis

- Tout se passe dans `/home/dok/testInria` (le venv contient pydotbot 0.29.1 patché — détail des patchs : [`patch.md`](patch.md)).
- Aucun autre processus sur le port 8000.

## 1. Lancer le simulateur (instrumentation activée)

```bash
cd /home/dok/testInria
DOTBOT_LATENCY_DIR=/home/dok/testInria/latency_logs \
  ./venv/bin/dotbot run simulator \
  --simulator-init-state /home/dok/testInria/simulator_init_state.toml
```

- `DOTBOT_LATENCY_DIR` **active** la mesure de latence et fixe le dossier des logs CSV.
  Sans cette variable, le contrôleur tourne normalement, sans aucune mesure.
- ⚠️ L'option s'appelle `--simulator-init-state` (pas `--init-state`).
- Options utiles : `--headless` (ne pas ouvrir le navigateur), `--map-size 5000x5000` (grille 10×10).
- **Robots réels** : remplacer `run simulator` par `run controller` avec votre `--conn`
  (ex. gateway série) — l'instrumentation fonctionne à l'identique.

## 2. Ouvrir les pages

| URL | Contenu |
|---|---|
| http://localhost:8000/latency | **Tous les logs de latence** : stats (min / moyenne / p95 / max), dernières entrées, téléchargement CSV. Auto-refresh 2 s. |
| http://localhost:8000/PyDotBot | Interface DotBots (carte + joystick). L'ouvrir alimente aussi `frontend_ws.csv` via le probe intégré. |
| http://localhost:8000/api | Documentation OpenAPI (les endpoints `/latency/*` y figurent). |

## 3. Mesurer le RTT de bout en bout

Dans un second terminal, simulateur (ou contrôleur) déjà lancé :

```bash
cd /home/dok/testInria
DOTBOT_LATENCY_DIR=/home/dok/testInria/latency_logs \
  ./venv/bin/python measure_rtt.py --trials 10
```

Options : `--address <addr>`, `--method ws|poll`, `--threshold-mm 30`, `--speed 60`,
`--timeout 10`, `--settle 1`. Résultats dans `latency_logs/rtt.csv` + stats console.

## 4. Les logs produits (un CSV par fonctionnalité, dans `latency_logs/`)

| Fichier | Mesure |
|---|---|
| `http.csv` | Durée de traitement de chaque requête HTTP (aussi dans le header `X-Process-Time`) |
| `controller_frame.csv` | Durée de traitement de chaque paquet par la boucle du controller |
| `ws_notify.csv` | Durée de diffusion des notifications WebSocket |
| `serial_tx.csv` | Durée d'écriture vers l'adapter (série / MQTT / simulateur) |
| `frontend_ws.csv` | Latence backend → navigateur (nécessite l'UI ouverte) |
| `rtt.csv` | RTT commande `move_raw` → mouvement LH2 détecté (`measure_rtt.py`) |

## 5. Arrêter / désactiver

- Arrêt : `Ctrl+C` dans le terminal du simulateur.
- Désactiver la mesure : relancer simplement **sans** `DOTBOT_LATENCY_DIR`.
- Repartir de zéro : `rm -rf latency_logs/` (les CSV sont recréés à la demande).

## Pour aller plus loin

- [`patch.md`](patch.md) — chaque fichier modifié (chemin, changement, commit git), procédures pyinstrument et React Profiler, limites connues.
- [`Handoff_Command.md`](Handoff_Command.md) / [`Handoff_Frontend.md`](Handoff_Frontend.md) — structure du backend et du frontend.
- Rollback des patchs : `git -C venv/lib/python3.14/site-packages revert <hash>` (état d'origine : commit `f7e552b`).
