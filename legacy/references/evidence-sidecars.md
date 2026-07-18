# Evidence sidecars (per-slide raw reference)

A design for giving every slide a machine-readable record of *what it was built from* — the source
excerpts behind each claim and the intended spec behind each figure — so every agent that later
works on the slide (grounding-critic, image-critic, house-style, a future rewrite) checks against a
written spec instead of re-deriving the truth.

## Where + naming
`<deck>/resources/evidence/<slide-slug>.json` — same basename as `slides/<slide-slug>.md`.
(Kept out of `slides/` so Slidev never imports it.)

## Schema (v0)
```jsonc
{
  "slide": "model-classes",          // slug, == markdown basename
  "title": "Model Classes",
  "origin": "gebhardt",              // lecture-notes | gebhardt | research | ...
  "claims": [                         // one per factual statement on the slide
    { "id": "c2",
      "statement": "<the claim, in English, as it appears on the slide>",
      "source": "gebhardt2025",       // bib key -> feeds citations directly
      "locator": "p. 358, Tabelle 4.3",
      "lang": "de",
      "excerpt": "<verbatim source text the claim came from>",
      "translation": "<optional EN>" }
  ],
  "figures": [                        // one per <img> the slide shows
    { "file": "model_class_mapping.png",
      "kind": "diagram|chart|infographic|mindmap|photo",
      "based_on_source": "gebhardt2025",
      "based_on_locator": "p. 356 + p. 358",
      "based_on_image": "resources/gebhardt/figures/geb_p17_x355.jpeg",  // if redrawn from a book figure
      "prompt_file": "resources/gebhardt/imgprompt_model_class_mapping.txt",
      "intended_labels": ["Concept model", "..."],
      "intended_relationships": "<the correct mapping/flow/grouping IN WORDS>",
      "must_not": ["<known trap 1>", "<known trap 2>"],
      "single_accent": "coral on <node> (the teaching point)" }
  ],
  "provenance": { "authored_by": "...", "date": "YYYY-MM-DD" }
}
```

## Why it is worth it (three wins from one artefact)
1. **Grounding/citations.** `claims[].source/locator/excerpt` IS the citation payload — the same
   data `render_references` needs, now attached to the exact sentence it supports. A grounding-critic
   checks each slide line against its own excerpt, not a whole notes file.
2. **Image review.** `figures[].intended_relationships` + `must_not` let the `image-critic` verify a
   diagram against a written spec. In the SPRINT_4 trial the critic had to OCR a jumbled German table
   to judge `model_class_mapping.png` and flagged low confidence; the sidecar states the mapping
   outright and lists the two traps the render actually fell into.
3. **Refinement & reuse.** A draft slide can be a sidecar with `claims`/`figures` and no prose yet;
   a research agent *appends* evidence to it during enrichment; a later pass turns it into the slide.

## Pipeline integration
- **Authoring emits it.** `sprint_deck.js` and `gebhardt_augment.js` authors now return an `evidence[]`
  array (one entry per slide: `claims[{statement, locator, excerpt}]` + `figures[{file,
  intended_relationships, must_not}]`) alongside `facts[]` / `figure_proposals[]`.
- **The assembly step persists it.** `commands/sprint-deck.md` (step 6) resolves each `slide_title` to
  its slug and calls `python -m slidecraft.scripts.write_evidence --deck <deck> --batch <batch.json>`,
  which writes/merges `resources/evidence/<slug>.json`.
- **The writer MERGES**, so a research/enrichment pass can append new claims/figures to a slide's
  sidecar over time without clobbering existing evidence.
- **Reviewers read `resources/evidence/<slug>.json`** for the slide under review: `image-critic` reads
  it (prefers `intended_relationships` + `must_not` over re-deriving); grounding-critic and house-style
  should follow.
- **render_references** can later source `[@key, locator]` from `claims[]` so markers and evidence
  never drift apart.

## Status
Automated: `scripts/write_evidence.py` (deterministic writer/merger) + `evidence[]` emission in both
authoring workflows + the assembly wiring in `commands/sprint-deck.md`. Validated on the v0 prototypes
`resources/evidence/model-classes.json` and `time-to-market.json` in SPRINT_4 (the model-classes sidecar
also demonstrates the image-review win: its `must_not` names the exact traps the first render fell into).
