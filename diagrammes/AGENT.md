# diagrammes/ — how the diagrams work, and how to change one

> Read this before editing any `.puml` in this folder, and before writing code that
> changes a class, a relation, or a package boundary that a diagram shows.
> The general project map is the root [`AGENT.md`](../AGENT.md); this file is only about
> the diagrams and the discipline that keeps them worth reading.

## The two rules

**1. The diagram is the source of truth, not a record kept after the fact.**
A code change that adds, removes, or reshapes a class, a relation, or a package seam
must be mirrored in **every diagram it touches** — and the diagram edit is **proposed
and validated by the user before the code is written**, never reconciled afterwards.
"I'll update the diagram once the code lands" is the exact failure this rule prevents:
the diagram stops being trustworthy the moment it is allowed to lag. A change that is
purely internal to one class (a private helper shown on no diagram) owes no diagram
update — the rule is about what the diagrams *claim*.

**2. A diagram describes the present. It never narrates how it got there.**
This is the rule this folder exists to enforce, because the diagrams here have broken
it. A reader opens a class diagram to learn what the system *is today* — every word
they must first mentally subtract is a defect. Concretely, a `.puml` in this folder
**must not contain**:

- **Stereotypes that encode history**: `<<new>>`, `<<renamed from DotBotNavigator>>`,
  `<<replaces WaypointWatcher>>`, `<<kept, thinned>>`. A stereotype names a *role*
  (`<<REST client>>`, `<<interface>>`, `<<value object>>`) or nothing at all.
- **Notes that compare to a past shape**: "was silently discarded before",
  "unchanged from before this reconnection", "replaces the vendored copy this diagram
  used to show". If the box is on the diagram, it is current; that is the whole claim.
- **Dated postmortems**: "CONFIRMED 2026-08-27", "wrong turn 1 / wrong turn 2",
  "an earlier pass marked this INVALIDATED", "78 commits behind". None of that is
  design. It belongs in the commit message and in the root `AGENT.md` "Roadmap §0"
  — both of which already carry it.
- **`INVALIDATED` / `TODO` / `open question` blocks** describing work not yet done.
  A diagram shows one coherent design. If a piece is undecided, leave it off and say
  so in prose, or draw a separate proposal diagram (see below) — do not ship a
  main diagram that argues with itself.

Git already answers "what changed and why". The diagram answers "what is the shape
now". Keep those jobs separate.

### The one exception: proposal diagrams

A diagram whose job is to *propose* a change may show the delta — amber for new,
green for existing, a legend saying so (`mrta_mode_button_architecture.puml` does
this against `Button.md`'s contract). That licence ends at merge: **the commit that
lands the last piece of the change also flattens the diagram** — delta colours out,
`<<new>>` out, "was X" notes out — leaving a plain picture of the now-current design.
If you find a shipped feature still drawn as a proposal, that flattening was missed;
do it.

## What a good note says

Notes earn their place by carrying what the boxes and arrows cannot:

- an **invariant** a reader would otherwise have to infer
  ("every bot starts parked until `set_target()` is called");
- a **constraint left to the caller** ("two agents set to the same cell is a
  collision this class does not arbitrate");
- **why the current shape is the way it is**, stated in the present tense
  ("one mutable target slot per agent, no queue, because the goal source decides
  per agent — there is nothing to arbitrate").

Not: what the code used to look like, when it changed, or who was wrong about it.

## Inventory

| Source | Scope | Regenerate with |
|---|---|---|
| `sim_dotbot_mrta_ws_target_class_diagram.puml` | `mrta_mode/` classes + the `mapf-simulation` (`core` + `pibt`) surface they consume | `plantuml diagrammes/sim_dotbot_mrta_ws_target_class_diagram.puml` |
| `mrta_mode_button_architecture.puml` | component view: where each piece of the MRTA-mode toggle lives across the three repos, and the PyDotBot delta | `plantuml diagrammes/mrta_mode_button_architecture.puml` |
| `mrta_mode_button_state_machine.puml` | server-side state machine of `mrta_mode/server.py`'s `MrtaMode` (off / connecting / on / stopping) | `plantuml diagrammes/mrta_mode_button_state_machine.puml` |

## Mechanics

- **Never edit a generated `.png`.** It is an output; regenerate it from the `.puml`
  in the same commit that changes the source, so the tracked image never lies.
- **Shared visual language.** All three diagrams use one palette — keep it identical
  when adding a diagram, so the set reads as one system:
  | Element | Colour |
  |---|---|
  | primary border (class / component / state) | `#4A90D9` |
  | fill | `#EAF4FF` |
  | package border / fill | `#888888` / `#F8F8F8` |
  | note | `#FFF8E1` fill, `#E0C060` border |
  | arrows | `#333333` |
  | `DefaultFontSize` | `13` |
- **`@startuml <name>` matches the filename** (without extension), and the filename
  says what the diagram is *of*, not what change introduced it.
- **Live iteration**: `../../3A/projets/MAPF_Simulation/diagrammes/script_perso.sh
  <file>.puml` watches a file and regenerates on save (`inotifywait` + `plantuml`);
  copy it here if you want it local.

## Before you commit a diagram change — checklist

1. Does every box, arrow, and note describe the code **as it is after this commit**?
2. Any `<<new>>` / `<<renamed>>` / "was …" / date / "wrong turn" left? Remove it.
3. Does the note say something the diagram cannot show, in the present tense?
4. Is the `.png` regenerated?
5. Was the diagram edit shown to the user **before** the code it describes?
6. Every other diagram touching the same seam updated too?
