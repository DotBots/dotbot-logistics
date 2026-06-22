# Handoff — Frontend DotBot

> **Ce document existe pour éviter de lancer un agent Explore sur la structure du frontend.**
> **Il est donc interdit de spawner un agent Explore pour explorer le frontend : toutes les informations nécessaires sont ici.**

---

## Localisation des sources

| Emplacement | Usage |
|---|---|
| `/home/dok/testInria/venv/lib/python3.14/site-packages/dotbot/frontend/` | **Arbre de travail** (décision 2026-06-10) : le `build/` y est patché directement et versionné dans le git de site-packages |
| `/home/dok/Inria/PyDotBot/dotbot/frontend/src/` | Repo upstream — **non utilisé** pour ce projet |

⚠️ **Contraintes du frontend dans le venv** (découvertes 2026-06-10) :
- Après tout patch d'un fichier dans `build/`, faire un **Ctrl+Shift+R** (hard refresh) dans le navigateur — le hash du nom de fichier JS ne change pas, donc le navigateur sert l'ancienne version depuis son cache sans ça.
- `src/` y est **incomplet** : `utils/` (constants.ts, helpers.ts, logger.ts, rest.ts) est absent et il n'y a pas de `node_modules` → **un rebuild React (`npm run build`) est impossible depuis le venv**.
- Le build servi par FastAPI est `frontend/build/` (monté sur `/PyDotBot`, voir `server.py` fin de fichier). Pour modifier le comportement côté navigateur sans rebuild : éditer `build/index.html` et/ou ajouter des scripts autonomes dans `build/` (pattern utilisé par `latency-probe.js`).
- `frontend/.gitignore` (livré) ignore `/build` : utiliser `git add -f` pour committer des changements du build.

---

## Stack technique

- React 18 + TypeScript
- Vite (build tool)
- Bootstrap 5 (UI)
- react-leaflet (carte GPS SailBot)
- MQTT.js (mode QrKey)
- vitest + @testing-library (tests)
- @use-gesture/react (drag joystick)
- @react-spring/web (animation joystick)
- react-colorful (color picker)
- use-interval (boucle de publication moteurs)

---

## Arborescence de `src/`

```
src/
├── App.tsx                  — Router principal (RestApp vs QrKeyApp selon ?use_qrkey)
├── RestApp.tsx              — WebSocket + REST API, passe publishCommand aux enfants
├── QrKeyApp.tsx             — Variante MQTT avec authentification QR code
├── QrKeyForm.tsx / .css     — Formulaire de saisie du pin code
├── DotBots.tsx              — Conteneur principal, logique waypoints + clavier
├── DotBotItem.tsx           — Accordion item : joystick + color picker + waypoints (DotBot)
├── DotBotsMap.tsx           — SVG grid LH2 (positions indoor lighthouse)
├── SailBotItem.tsx          — Accordion item : rudder slider + sail slider (SailBot)
├── SailBotsMap.tsx          — Carte Leaflet GPS (SailBot)
├── XGOItem.tsx              — Accordion item : joystick + boutons d'action (robot XGO)
├── Joystick.tsx             — Joystick drag générique (DotBot & XGO)
├── types.ts                 — Interfaces TypeScript
├── hooks/
│   └── keyPress.ts          — Hook useKeyPress (Ctrl+Enter, Ctrl+Backspace)
└── utils/
    ├── constants.ts         — ApplicationType, seuils, statuts, XGOActionId
    ├── helpers.ts           — lh2_distance, gps_distance, handleDotBotUpdate
    ├── logger.ts            — Pino logger avec couleurs console
    └── rest.ts              — Client Axios (base URL http://localhost:8000)
```

---

## Hiérarchie des composants

```
App.tsx (router)
├── RestApp.tsx  (WebSocket ws://localhost:8000/controller/ws/status)
│   └── DotBots.tsx
│       ├── DotBotsMap.tsx          (SVG, LH2, mapSize=350 mobile / 1000 desktop)
│       │   ├── DotBotsMapPoint     (robot : cercle coloré + triangle direction)
│       │   ├── DotBotsWaypoint     (waypoints : cercle + ligne pointillée + carré)
│       │   └── DotBotsPosition     (historique : ligne + cercle)
│       ├── SailBotsMap.tsx         (Leaflet GPS, mapSize=350 / 650)
│       │   └── SailBotMarker       (coque SVG + gouvernail + voile + vent)
│       ├── DotBotItem.tsx          (accordéon : Joystick + RgbColorPicker)
│       ├── SailBotItem.tsx         (accordéon : sliders rudder/sail)
│       └── XGOItem.tsx             (accordéon : Joystick + 8 boutons action)
└── QrKeyApp.tsx  (MQTT)
    └── DotBots.tsx  (même structure)
```

---

## Flux de données

1. `RestApp` ouvre un WebSocket → reçoit `WsMessage` (types : Reload, NewDotBot, Update).
   Depuis 2026-06, chaque message porte aussi un champ optionnel `timestamp` (heure serveur, epoch s) **uniquement quand le contrôleur tourne avec `DOTBOT_LATENCY_DIR`** — exploité par le probe `build/latency-probe.js` (latence backend→navigateur, POST par lot vers `/latency/frontend`, résultats sur `http://localhost:8000/latency`). Voir `patch.md`.
2. Fetch initial : `GET /controller/dotbots`
3. `publishCommand` est passé en prop jusqu'aux items
4. Les items publient via REST :
   - `PUT /controller/dotbots/{address}/{application}/move_raw`
   - `PUT /controller/dotbots/{address}/{application}/rgb_led`
   - `PUT /controller/dotbots/{address}/{application}/waypoints`
   - `PUT /controller/dotbots/{address}/{application}/clear_position_history`
   - `PUT /controller/dotbots/{address}/{application}/xgo_action`

---

## Composant : DotBotsMap (grille SVG)

**Fichier :** `src/DotBotsMap.tsx`

### Paramètres de la grille (à modifier pour changer l'affichage)

| Ce qu'on veut changer | Ligne src | Code actuel (src) | Build patché |
|---|---|---|---|
| Taille des carreaux (mm) | 256–257 | `400 * mapSize / props.areaSize.width` → changer `400` | **`400`** (patché 2026-06-17, commit effb798 — 5×5 cases) |
| Couleur des lignes | 269 | `stroke="gray"` | — |
| Épaisseur des lignes | 270 | `strokeWidth="1"` | — |
| Grille visible par défaut | 230 | `useState(true)` → `false` pour masquer | — |

> ⚠️ Le build servi est `frontend/build/assets/index-DIogaYNf.js`. La valeur courante est **`400`** (commit effb798, 2026-06-17) — 6 occurrences (3 paires width/height pour `<pattern id>`, `<rect>`, `<path>`). Affiche **5×5 cases** de 400 mm pour une grille 2000×2000 mm.

### Props reçus par `DotBotsMap`

```ts
dotbots: DotBot[]
active: string                          // adresse du robot actif
areaSize: AreaSize                      // { width, height } en mm
backgroundMap?: BackgroundMap           // image PNG base64 en fond
mapSize: number                         // 350 (mobile) ou 1000 (desktop)
showHistory: boolean
historySize: number
setHistorySize: (size: number) => void
updateActive: (address: string) => void
updateShowHistory: (show: boolean, application: number) => void
mapClicked: (x: number, y: number) => void
publish: (topic: string, message: unknown) => void
```

### Formule de conversion coordonnées

```
posX_svg = position_mm * mapSize / areaSize.width
```
Inverse (clic → coordonnée mm) :
```
x_mm = clientX * areaSize.width / mapSize
```

### Rendu de chaque robot (`DotBotsMapPoint`)

- Cercle coloré par `rgb_led` (`rgb(r, g, b)`)
- Rayon : `mapSize * 40 / areaSize.width` (40mm), +5mm si actif/survolé
- Triangle de direction si `dotbot.direction !== -1000`
- Opacité 80% si status=0 (actif), 20% sinon
- Trait de sélection noir si robot actif
- Filtre : seuls les robots avec `lh2_position` et `status !== 2` sont affichés

---

## Composant : Joystick

**Fichier :** `src/Joystick.tsx`

### Fonctionnement

- Drag contraint à 100px de rayon (container 200×200px)
- Publication toutes les 100ms quand actif (via `useInterval`)
- Au relâchement : publie `{ left_x: 0, left_y: 0, right_x: 0, right_y: 0 }`

### Formule vitesses moteurs

```ts
const speedOffset = 30;
dir   = (128 * position.y / 200) * -1   // avant/arrière
angle = (128 * position.x / 200)        // rotation

leftSpeed  = dir + angle  (+ speedOffset si > 0, - speedOffset si < 0)
rightSpeed = dir - angle  (idem)
// clampé à [-128, 127]
```

### Payload publié

```ts
{ left_x: 0, left_y: leftSpeed, right_x: 0, right_y: rightSpeed }
```
`left_x` et `right_x` sont toujours 0 — disponibles pour un second joystick.

### Props

```ts
address: string
application: number
publishCommand: PublishCommandFn
```

---

## Composant : DotBotItem

**Fichier :** `src/DotBotItem.tsx`

- Accordéon Bootstrap (expand/collapse par robot)
- Contenu visible seulement quand `expanded === true` (sinon `invisible`)
- Ligne 125 : **le seul `<Joystick>`** actuel
- Ligne 129 : `<RgbColorPicker>` avec bouton "Apply color"
- Lignes 136–152 : navigation autonome (si waypoints présents)
- Ligne 147 : slider threshold (0–1000mm)

### Pour ajouter un second joystick

Dupliquer le bloc lignes 124–126 en ajoutant un prop `secondary` :
```tsx
<div className={`mx-auto justify-content-center ${!expanded && "invisible"}`}>
  <Joystick address={dotbot.address} application={dotbot.application} publishCommand={publishCommand} secondary />
</div>
```
Et dans `Joystick.tsx`, utiliser `left_x`/`right_x` si `secondary === true`.

---

## Composant : SailBotItem

**Fichier :** `src/SailBotItem.tsx`

- Slider **rudder** : range -128 à 127 → publie `left_x`
- Slider **sail** : range -128 à 127 → publie `right_y`
- Payload : `{ left_x: rudder, left_y: 0, right_x: 0, right_y: sail }`
- Seuil waypoint GPS : 0–100 mètres

---

## Composant : XGOItem

**Fichier :** `src/XGOItem.tsx`

- Joystick identique à DotBot pour le déplacement
- 8 boutons d'action (SitDown, StandUp, Dance, Stretch, Wave, Pee, Naughty, SquatUp)
- Publie `xgo_action` avec `{ action: XGOActionId }`

---

## Constantes importantes

**Fichier :** `src/utils/constants.ts`

```ts
enum ApplicationType { DotBot = 0, SailBot = 1, Freebot = 2, XGO = 3 }
const dotbotRadius = 40           // mm
const maxWaypoints = 16
const maxPositionHistory = 100    // défaut, modifiable via UI
const inactiveAddress = "none"
```

---

## API REST (base : http://localhost:8000)

```
GET  /controller/dotbots                                    → liste DotBot[]
GET  /controller/map_size                                   → areaSize { width, height } en mm (taille de la grille)
PUT  /controller/dotbots/{address}/{app}/move_raw          → { left_x, left_y, right_x, right_y }
PUT  /controller/dotbots/{address}/{app}/rgb_led           → { red, green, blue }
PUT  /controller/dotbots/{address}/{app}/waypoints         → { threshold, waypoints: LH2Position[] }
PUT  /controller/dotbots/{address}/{app}/clear_position_history → ""
PUT  /controller/dotbots/{address}/{app}/xgo_action        → { action: number }
WS   /controller/ws/status                                 → WsMessage (Reload|NewDotBot|Update)
```

---

## Taille de la grille SVG vs taille du simulateur

La grille SVG s'adapte automatiquement à `areaSize` reçu via `GET /controller/map_size`.  
**Pour changer la taille**, passer `--map-size LARGEURxHAUTEUR` au simulateur (voir `Handoff_Command.md`).  
Les carreaux sont à **400 mm** dans `DotBotsMap.tsx:256` (src upstream), **250 mm** dans le build patché.  
Taille de la grille = nb_cases × taille_carreau. Pour 5×5 cases à 400 mm : `--map-size 2000x2000` (défaut).  
La portée LH2 est typiquement < 6 m — ne pas dépasser ~15×15 cases.
