# Contributing

The repo's [`AGENT.md`][agent] is the authoritative source for conventions and the project
map. This page is the short version.

## Language

Folder and file names, code, docstrings, comments, commits, branches, and issues are all in
**English**.

## Commits

[Conventional Commits][cc], imperative mood: `type(scope)!: subject`.

| Type | Purpose |
|---|---|
| `feat` | a new feature |
| `fix` | a bug fix |
| `refactor` | neither fixes a bug nor adds a feature |
| `docs` | documentation only |
| `test` | adding or fixing tests |
| `chore` | tooling, dependencies, housekeeping |

**One logical change = one commit.** Don't bundle an unrelated fix, rename, or doc batch into
the same commit. The body (after a blank line) may explain the *why* and any verification.

## Branches

`prefix/suffix`, prefix in English: `feat/`, `fix/`, `docs/`, `refactor/`, `pm/`. The main
branch is `main`; day-to-day work targets `develop`.

## Class-diagram-first

Any change to the PIBT/MRTA engine's design — a class, a relation, a package seam — is
**shown and validated as a diagram before the code is written**, never reconciled afterwards.
The diagrams live in `diagrammes/`; read [`diagrammes/AGENT.md`][diag] before editing any
`.puml`. The three current diagrams are rendered on
[How it works](how-it-works.md) and [The console toggle](console-toggle.md).

## Load-bearing invariants

- **The synchronisation barrier** (`wait_until_all_arrived`) is what gives PIBT its
  collision guarantee on asynchronous hardware. It is not a latency optimisation to cut.
- **`GridStateManager.resolve_conflicts()`** is what keeps two bots from aliasing to the
  same cell under localisation noise. Don't bypass it when reading bot state.
- **No `git push`** without an explicit request in the same breath.

## Building this site

```bash
pip install mkdocs-material
mkdocs serve            # live preview at http://localhost:8000
```

`.github/workflows/docs.yml` runs `mkdocs gh-deploy` on every push to `develop`.

[agent]: https://github.com/DotBots/dotbot-logistics/blob/develop/AGENT.md
[diag]: https://github.com/DotBots/dotbot-logistics/blob/develop/diagrammes/AGENT.md
[cc]: https://www.conventionalcommits.org
