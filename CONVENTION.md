# Git conventions

## Language

**English** is used throughout the project: code, docstrings, comments, commits,
branches, issues, and this document.

## Repository structure

Folder and file names are in English.

`dotbot-logistics` is the bridge between the `simulation/` engine and the DotBot environment
(simulator today, real hardware over LH2/MQTT). This tree is the root repo's own layout — for
`simulation/`'s internal structure (`core/`, `algo/`, `mrta/`, `client/`, `report/`), see
[`simulation/CONVENTION.md`](simulation/CONVENTION.md); the two are not the same tree.

```
.
├── .gitignore
├── LICENSE
├── requirements.txt
├── dotbot.toml                   — pydotbot CLI config (MQTT broker, swarm id)
├── mosquitto.conf                — local MQTT broker config for L2
├── mkdocs.yml                    — config for the docs/ site
├── simulator_init_state.toml     — L1 simulator seed, 5x5 grid (400 mm cells)
├── simulator_init_state_8x8.toml — L1 simulator seed, 8x8 grid (250 mm cells)
├── README.md                     — human-facing overview, install, script reference
├── AGENT.md                      — full architecture reference for coding agents
├── CLAUDE.md                     — pointer that imports AGENT.md
├── CONVENTION.md                 — this file
├── docs/                         — MkDocs site: level-0/1/2 guides, installation, contributing
├── simulation/                   — PIBT/MRTA engine (own CLAUDE.md/AGENT.md/CONVENTION.md)
├── log/                          — experiment outputs (raw_logs/, *_per_run.csv, *_summary.csv)
├── sim_pibt.py                   — L0 interactive PIBT viewer
├── sim_many_pibt.py              — L0 headless benchmark sweep
├── sim_dotbot_pibt.py            — L1: drives the DotBot simulator via REST API
├── real_dotbot_pibt.py           — L2: drives real DotBots over LH2/MQTT
├── real_dotbot_pibt_batch.py     — L2: batch harness (N bots x M runs)
└── run_metrics.py                — CSV metrics helper for the L2 batch harness
```

## Branch naming

Branches use a `prefix/suffix` scheme. The prefix is in English.

- **Main branch**: `main`
- **Development branch**: `develop`
- **Feature branches**: `feat/{feature-name}`
- **Bug-fix branches**: `fix/{fix-name}`
- **Documentation branches**: `docs/{topic}`
- **Refactor branches**: `refactor/{topic}`
- **Project-management branches**: `pm/{name}`

## Commit rules

Commits follow the [Conventional Commits](https://www.conventionalcommits.org)
specification, in English, using the imperative mood:

```
type(scope)!: subject
```

- **type** — one of:
  | Type       | Purpose                                             |
  |:-----------|:----------------------------------------------------|
  | `feat`     | a new feature                                       |
  | `fix`      | a bug fix                                            |
  | `refactor` | a change that neither fixes a bug nor adds a feature |
  | `docs`     | documentation only                                  |
  | `test`     | adding or fixing tests                              |
  | `chore`    | tooling, dependencies, housekeeping                 |
- **scope** *(optional)* — the affected area, e.g. `core`, `algo`, `mrta`, `client`.
- **`!`** *(optional)* — marks a breaking change, e.g. `refactor(core)!: ...`.
- **subject** — short, imperative, no trailing period.

**One logical change = one commit.** Do not bundle unrelated changes; split a
distinct fix, rename, feature, or documentation batch into its own commit with a
clear message. A commit body (after a blank line) may explain the *why* and any
verification performed.

Examples:

```
feat(core): add scale attribute to WorldEntity
fix: repair main.py import broken by the core subpackage split
docs: rewrite README for the current architecture
refactor(core)!: remove Objective entity
```

## Issue rules

- Issues are written in **English**.
- Each issue should have an assignee.
- Each issue should have a due date when possible.

Issues are categorised with the following labels:

| Description            | Label               |
|:-----------------------|:--------------------|
| To do                  | `To Do`             |
| In progress            | `On-going`          |
| Bug fix                | `type: bug`         |
| Project management     | `type: PM`          |
| Feature addition       | `type: feature`     |
| Low priority           | `priority: low`     |
| Medium priority        | `priority: medium`  |
| High priority          | `priority: high`    |
| Critical priority      | `priority: critical`|

## Versioning

We use numbered versioning of the form `Major.Minor.Fix`, starting at 0.

Trailing zeros may be omitted for brevity:

```
version 0.1.0 --> version 0.1
version 1.0.0 --> version 1
```

Each merge into `main` marks a new version and must be tagged as described above.
Ideally the tag is accompanied by release notes describing the changes since the
previous version.

## Merge requests

Merge requests into `develop` and `main` must be approved by the majority of the
development team. Any required correction must be written down in the review
comments for proper project tracking.
