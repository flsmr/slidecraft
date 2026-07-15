---
description: Run polish/review passes over an existing ILSE deck and apply the fixes
argument-hint: [deck-name] [passes]
---

# Improve Deck

Runs review agents *over* an existing deck (grounding, house-style, critic, visual), collects prioritized
findings via the `improve_deck` workflow, and applies the fixes. This is the polish chain, and the same
machinery behind single-slide "tweak" phrases.

## Step 1 — Target + passes
- Resolve the deck dir (from `$ARGUMENTS` or ask). Confirm `<deck>/slides.md` exists and builds.
- Default passes: `grounding-critic, house-style, slide-critic, image-critic, visual-enrichment`. The user may
  name a subset ("just house-style and grounding") or a scope ("slides 7-12"). Default mode is `parallel`; use
  `sequential` if the user wants each pass to build on the previous.
- `image-critic` (see `slidecraft/agents/image-critic.md`) is the devil's-advocate vision pass: it opens every
  non-photographic figure (diagram, infographic, mind map, chart, redrawn figure) and checks rendered text,
  colour/accent, shape/layout, logical structure, and figure-slide coherence. It runs on a SINGLE model —
  `python -m slidecraft.scripts.image_critic --deck <deck>` (GPT-5.6 sol via OWUI; a panel was rejected as too
  costly), reconciled against the per-slide evidence sidecar to drop false positives. Its `fix` values feed the
  image tweak ladder in the catalog below (regenerate via canonical-labels, pixel-surgery, swap layout, native HTML).

## Step 2 — Run the workflow
```
Workflow({ scriptPath: "slidecraft/workflows/improve_deck.js",
           args: { deck: "<deck>", passes: [...], mode: "parallel", scope: "all" } })
```
Returns `{ total_findings, findings[] }` sorted high → low severity. Watch `/workflows`.

## Step 3 — Apply
- **high / med** findings: apply the `fix` by editing the offending `slides/<name>.md` file. Grounding
  findings win over style findings on any conflict.
- **low** / `visual-enrichment` suggestions: present as options, apply only what the user approves (image
  generation and new galleries are tier-2 — do them, then tell the user, don't silently restructure).
- `python -m slidecraft.scripts.lint_slides --deck "<deck>"` (0 errors), then `npm run build` (`✓ built`).

## Step 4 — Report
Summarize what changed (per pass), what was left as an optional suggestion, and the new build status.
Do not show the raw findings JSON unless asked.

## Single-slide tweaks
For a one-off ("improve slide 7 with a diagram", "tighten slide 4", "regenerate the mind map", "add real-photo
examples to the joining section", "fix the sources on slide 9"): skip the workflow and fire the one matching
agent/script directly, grounded in that slide's notes, then rebuild. Same rules, smaller blast radius.

## The tweak catalog (conventions proven in the SPRINT_2 editing sessions)

**Editing invariants**
- **Never overwrite an asset**: every regenerated/edited image gets a versioned filename
  (`mindmap_ch2_v2.png`, `diagram_separating_v2.png`); the old file stays on disk as the backup.
- **"Remove slide X" = remove its import line from `slides.md` only.** The slide file stays in
  `slides/` so restoring it is one line. Delete files only on an explicit "delete permanently".
- **Date changes target `::date::` slots** (and the title slide's body), never a global find/replace —
  a blanket sed once silently rewrote a "generated on" date inside an image credit.
- **Adding a slide** = one new `slides/<slug>.md` + one import line at the right position.

**Image tweaks (in order of preference)**
1. **Pixel surgery for subtractive edits** ("remove those lines/labels"): density-scan the PNG, find a
   content-free gutter around the target, erase that rectangle with PIL, save as `_v2`. Content
   provably untouched; no regeneration lottery.
2. **Rotate** a portrait figure (PIL `transpose`) when its content reads correctly rotated.
3. **Space-filling re-render** ("too small to read"): rebuild the Imagen prompt PROGRAMMATICALLY from
   the stored canonical-labels list (never retype content), instruct: fill the canvas edge to edge,
   wrap rows longer than ~7 boxes onto two lines, widen boxes in sparse rows, landscape left-to-right.
   Then verify the render label-by-label against the canonical list before swapping.
4. **Full regeneration** only for content changes, and always through the canonical-labels pipeline
   (spec -> programmatic prompt -> render -> label-by-label verify).

**"Fix the sources" (citation system)**
Sources live in `<deck>/references.bib`; slides carry `[@key]` markers. To fix/extend citations: edit
the bib (or import: `python -m slidecraft.scripts.import_ris --deck <deck> --ris <file>`), then
`python -m slidecraft.scripts.render_references --deck <deck>` regenerates inline citations and the
paginated References / Image-sources slides and reports orphaned credits + uncredited images. To
switch citation style: same command with `--style <csl-name>` — never edit rendered citation text.

**Honest reuse**: when a tweak reuses a figure for a different concept (shared mechanism), update the
bullets, alt text, and notes to explain the relationship in the same edit — never leave the mismatch
unexplained.
