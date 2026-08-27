# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this
repository.

The project map lives in @AGENT.md — read it first, especially the "Current known
inconsistencies" section, **before** touching any root-level L0/L1/L2 script: every one of them
is currently broken, because the vendored `simulation/` engine they depended on was removed
(2026-08-27) and reconnection to the real upstream engine is deliberately not done yet
(`Roadmap.md` §0). That section tracks the exact list.

## Contributing rules

Every code change, file rename, and new file MUST follow @CONVENTION.md: commit style, branch
naming, issue labels.

@AGENT.md

@CONVENTION.md
