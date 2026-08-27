# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this
repository.

The project map lives in @AGENT.md — read it first, especially the "Current known
inconsistencies" section, **before** touching any root-level L0/L1/L2 script: most of them are
still broken, because the vendored `simulation/` engine they depended on was removed (2026-08-27)
and has not been ported for every script yet (`mrta_mode`/`sim_dotbot_mrta.py` are the exception —
see AGENT.md's "Roadmap" §0). That section tracks the exact list.

## Contributing rules

Every code change, file rename, and new file MUST follow @AGENT.md's "Contributing conventions"
section: commit style, branch naming, issue labels.

@AGENT.md
