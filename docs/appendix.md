# Appendix

## Glossary

| Term | Meaning |
|---|---|
| **PIBT** | Priority Inheritance with Backtracking — an iterative multi-agent path-finding algorithm. Each step, every agent picks its best move toward its goal; on a conflict the higher-priority agent wins and the loser *inherits* priority to push others aside, backtracking if stuck. Okumura et al., *Artificial Intelligence* (2022), [arXiv:1901.11282](https://arxiv.org/abs/1901.11282). |
| **MRTA** | Multi-Robot Task Allocation. Here it is deliberately minimal: `pibt.LifelongGoalOrchestrator` holds one mutable target slot per agent, written only through `set_target(agent_id, position)` — no queue, no cross-agent arbitration. |
| **MRTA mode** | this project's operator-driven mode: a console click becomes a PIBT-planned, collision-free route for one bot. |
| **mm world / cell world** | the two coordinate systems the bridge connects — millimetres (the DotBot API) and integer grid cells (the planner). |
| **Synchronisation barrier** | `wait_until_all_arrived()` — the step loop waits for every driven bot to reach its cell before planning the next step. |
| **LH2** | Lighthouse 2 — the optical localisation the real DotBots use for position. |
| **The proxy** | PyDotBot's `/mrta/*` reverse-proxy (`feat/mrta-mode-toggle` branch) that forwards the console's MRTA calls to `mrta_server.py`. |

## What used to be here

Before 2026-08-27 this repo vendored the planning engine at `simulation/` and shipped a
family of scripts organised in three levels — L0 (pure algorithm), L1 (DotBot simulator),
L2 (real hardware over MQTT/LH2). The engine was replaced by the `mapf-simulation`
dependency; the batch scripts were retired. Three unported ones remain in `test_scripts/`
(see [Reference](reference.md#test_scripts-archived)). The removed files and the reasoning
are recorded in the repo's [`AGENT.md`][agent]; recover any deleted file with
`git log --all --full-history -- <path>`.

## Upstream

- [PyDotBot documentation](https://pydotbot.readthedocs.io/en/latest/) — the DotBot
  hardware, controller, CLI, and REST/WebSocket/MQTT APIs.
- [MAPF_Simulation](https://github.com/RasdaCorentin/MAPF_Simulation) — the `core` + `pibt`
  planning engine, installed as `mapf-simulation`.

[agent]: https://github.com/DotBots/dotbot-logistics/blob/develop/AGENT.md
