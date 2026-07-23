# Slide composition is two-stage: a planner routes, specialist designers build

One LLM call no longer composes a whole slide. A **planner** (the former
`slide-composer`, rewritten) decides the slide's didactic function, core message,
assertion title, layout, and — per content area — a `type` (`text` / `diagram` /
`image` / `source-image`), natural-language `instructions`, and the routed nugget
ids. Three **specialist designers** (text/table, diagram-in-Vue, image-generation)
each build one area from that brief plus the full slide raw material. Deterministic
glue (`km write-skeleton` / `km place-design`, driven by `compose_deck.py` +
`design_section.py`) validates the plan, renders a visible wireframe, places
`source-image` areas, fans the designer calls to OWUI, and stitches each result
back — with **no LLM inside any assembly step** (ADR-0001, strengthened).

Status: accepted (2026-07-22, D1–D17). Replaces the monolithic single-stage
composer path; `write-slide`'s content-slide role is superseded by
`write-skeleton` + `place-design`.

## Considered options

- **Hard medium lanes** (route each area to a fixed medium) — rejected (D2):
  faithfulness is earned by rich per-area briefs + exact-text discipline, not by
  restricting the composer's medium choice.
- **The planner names the diagram component** — rejected (D15): the planner
  describes the diagram in natural language; the diagram designer selects the
  component from a catalog generated from per-component `<catalog>` metadata (D14),
  so add/remove a component auto-syncs the prompt.
- **A hand-maintained component catalog** — rejected (D14): the catalog is
  extracted from each `.vue`'s `<catalog>` block, the single source of truth.

## Consequences

- **Heterogeneous slides** (a source figure beside a Vue decision tree) are built
  by experts; a visible wireframe renders the instant `write-skeleton` runs, and
  each area fills in as its designer lands (free live-preview progress).
- **Per-area re-generation** is the same code as the batch path (scope flags on
  `compose_deck.py` / `design_section.py`) — the human-in-the-loop seam.
- **Every prompt + response is logged** under the deck's `logs/prompts/<slide>/`
  and cross-referenced from `logs/actions.jsonl` (D16), so a deck's creation can be
  reconstructed, debugged, or re-run against another model.
- **Scripts own every OWUI call** (D7); the lead launches `compose_deck.py` and
  reads its report — it never hand-loops OWUI.
