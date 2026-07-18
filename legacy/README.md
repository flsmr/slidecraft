# legacy/ — quarantined previous-generation pipeline

This folder holds the **sprint-deck / new-deck / improve-deck generation** of slidecraft,
quarantined out of the plugin on 2026-07-16 (ticket 01). It sits at the repo root — outside
`slidecraft/` — so **nothing in here is loaded as a command, skill, or agent** by the
installed plugin.

It is kept, not deleted, because it is the knowledge quarry for the agentic presentation
framework (`architecture_proposal.md`): tickets 04, 07, and 08 salvage specific craft from
these files before they are eventually removed. The internal folder structure mirrors the
plugin layout it was moved out of (`commands/`, `workflows/`, `agents/`, `skills/`,
`scripts/`, `references/`, `scaffold/`, `tests/`).

Do not wire anything in the plugin, docs, or new tickets to files in this folder. If a
piece of it turns out to be needed, salvage the knowledge into a ticket's deliverable —
don't re-import the file.

## Salvage map (what to mine, and for which ticket)

| Quarantined artifact | Reusable knowledge | Destination |
|---|---|---|
| `agents/slide-author.md` | Slot-filling craft: how to write into a theme's physical layout slots, density discipline, speaker-note conventions | Ticket 08 (Composer) |
| `agents/layout-style.md`, `agents/slide-critic.md` | Layout-choice and style judgment: which layout fits which modality mix, monotony detection, mechanical form thresholds | Ticket 08 (Composer) |
| `references/best-practices.md` | Empirical design thresholds (word/bullet caps, typography minima, pacing ratios) the authoring/critic rules were derived from | Ticket 08 (Composer) |
| `agents/narrative.md` | Narrative arcs, register/emphasis pacing, assertion-evidence titling | Ticket 07 (storytelling skill) |
| `skills/quiz-generator/`, `skills/example-generator/` | Quiz and worked-example structural patterns (one question per slide, split-not-cram rules) | Ticket 07 (storytelling skill) |
| `references/tones/academic.md` (+ siblings) | Academic tone rules; business/keynote tones as future deck-type variants | Ticket 07 (storytelling skill) |
| `skills/authoring/SKILL.md` | PDF-cache and tier discipline: cache extracted chapter text once, tiered reading (headings → sections → verbatim) instead of re-parsing the PDF | Ticket 04 (harmonization) |
| `scripts/extract_chapter.py` | Paged-text extraction mechanics (PyMuPDF), page-anchor bookkeeping | Ticket 04 (harmonization) |

Everything else (workflow engines, scaffold package, gallery search, figure/mind-map
generation, deck splitting, evidence writing, linting, ILSE recipes, sprint-deck docs,
`ARCHITECTURE.md` / `placeholder-bg-findings.md` — both superseded by
`architecture_proposal.md`) is kept only for reference and has no salvage destination.
