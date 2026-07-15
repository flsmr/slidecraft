---
description: Build an ILSE lecture deck from a chapter PDF, autonomously, via the sprint-deck workflow
argument-hint: [deck-name]
---

# Sprint Deck

Autonomously builds an IU "ILSE" Slidev lecture deck from a chapter's course material, using the
`sprint_deck` workflow for the parallel agent work and the deterministic scripts for the spine.
This is the reusable recipe: prepare `recipe.json`, drop the sources, run this once.

> **New decks start at [new-deck.md](new-deck.md)** (the front door: theme pack + skeleton
> interview). Steps 1–2 below are its manual equivalent — use them only when re-running an
> existing recipe.

Prerequisites are one-time per machine — see [SETUP.md](../SETUP.md) (theme pack registered in
`~/.slidecraft/packs.json`, OWUI `.env`, `pymupdf`, a Claude Code build with the **Workflow tool**).

## Step 1 — Recipe + inputs
- Copy [`recipe.example.json`](../recipe.example.json) to `<deck>/resources/recipe.json` and fill it
  (deck name/location, course/module/chapter, `sources.chapter_pdf`, `sources.prefix`, agenda chapters +
  `active`, `enrich` flags). If `$ARGUMENTS` gives a deck name, use it.
- Confirm the named files exist in `<deck>/resources/`: the chapter PDF, and (optional) the template PPTX
  and exam catalogue. If the chapter PDF is missing, stop and say so.

## Step 2 — Scaffold (from the theme-pack skeleton)
```
python -m slidecraft.scripts.scaffold_deck --recipe "<deck>/resources/recipe.json"
```
Framing slides, deck files, deck-local layouts (agenda active-chapter + slide1 badge already
retargeted via placeholders), `slides.md` with the CONTENT marker, skeleton guides into
`resources/`, provenance into the recipe. Then `npm install`.

## Step 3 — Extract
```bash
python -m slidecraft.scripts.extract_chapter --deck "<deck>" --pdf "<chapter_pdf>" --prefix "<prefix>"
```
Read `<deck>/resources/<prefix>_extract.json`. Build the recipe's `sections` array from it: for each TOC
section set `{key, title, text_file, figs: "NN to MM" (the figure files whose page falls in the section
range), target, hint}`. Reserve the master DIN/overview figure for a deck-level overview slide.

## Step 4 — Author + enrich (the workflow)
```
Workflow({ scriptPath: "slidecraft/workflows/sprint_deck.js", args: <recipe with sections> })
```
It returns `{ sections[], mindmap, galleries, references, exam_focus, critic }`. Watch `/workflows`.

**Expect partial fan-out failure.** The workflow retries failed section-authors once itself; any section
still carrying `error`/empty `slides_md` in the result you author INLINE from the already-extracted
section text + the author guide (all grounding material is on disk — never re-launch the whole workflow
for one missing section). The DONE report lists per-section status either way.

## Step 5 — Images
- **Mind map:** write `mindmap.outline_md` to `<deck>/resources/<prefix>_mindmap.md`, then
  `python -m slidecraft.scripts.gen_mindmap --deck "<deck>" --structure "<…>_mindmap.md" --central "<mindmap.central>" --out "mindmap_<prefix>.png"`.
- **Galleries:** if `enrich.galleries=="search"`, run `python -m slidecraft.scripts.gallery_search --deck "<deck>"
  --queries "<…>"` from the workflow's `galleries.groups`, verify + downscale into `public/figures/gallery/`.
  If `galleries` names a deck to reuse, copy that deck's `gallery/` + `gallery_group*.json` instead.

## Step 6 — Assemble (per-slide files + citations)
The scaffold already wrote the framing slides and `slides.md` with a
`<!-- ===== CONTENT SECTIONS ... ===== -->` marker. Write ONE file per content slide under
`<deck>/slides/` (descriptive slugs) and replace the marker with their ordered `src:` imports:
overview figure first, then **each section's `slides_md` followed by its gallery**. Fill the
`filled_by: "author"` framing templates (study-goals, summary, exam-focus) — no `AUTHOR:` marker
may survive. Use the SPRINT_3 deck as the exact markup reference. References/image-sources slides
are NOT hand-written — they are generated in the next step.

**Evidence sidecars:** the workflow returns `evidence[]` per section (one entry per slide it produced,
with each claim's `locator`+`excerpt` and each figure's `intended_relationships`+`must_not`). Resolve each
`slide_title` to the slug you gave its file, write the list to a batch JSON, and persist the sidecars:
`python -m slidecraft.scripts.write_evidence --deck "<deck>" --batch <batch.json> --source-key <key> --origin <origin>`.
This creates `<deck>/resources/evidence/<slug>.json` — the raw reference the grounding-critic and image-critic
read (see `references/evidence-sidecars.md`). The writer MERGES, so research/enrichment passes can append later.

**Citations:** merge the workflow's `references.bibtex` + every section's `bib_entries` into
`<deck>/references.bib` (dedupe by key; on conflict keep the source-researcher's entry). Add one
`keywords = {image}` entry per AI/photo asset (see `references/bibtex-guide.md`). Slides carry only
`[@key]` markers. Then render everything deterministically:
```
python -m slidecraft.scripts.render_references --deck "<deck>" --style <recipe.workflow.citations.style> --per-page <...> --img-per-page <...>
```
(defaults live in `recipe.workflow.citations`, set by the skeleton; markers -> styled text,
generates references*/image-sources* pages, syncs the manifest before `thank-you.md`)

## Step 7 — Verify
- `python -m slidecraft.scripts.lint_slides --deck "<deck>"` — must exit 0 errors (L13 house-style
  chars, L14 attribute quoting, L15 portrait-on-full-width, L1..L9 mechanics).
- `python -m slidecraft.scripts.render_references --deck "<deck>" --check` — no unknown keys; act on
  uncredited-image warnings.
- `npm run build` must end `✓ built`. Fix any layout/slot/YAML error.
- Apply the workflow's `critic.findings` (edit the offending slide files).
- Optional: `vite preview --outDir dist` + a DOM check that every `img.naturalWidth > 0`.

## Step 8 — DONE report
Write `<deck>/DONE_REPORT.md`: per-phase status, slide count, every figure + source + licence, build result,
what was AI-generated vs real-photo vs reused, open items, and the exact `/slidecraft:improve-deck` /
tweak phrases to fix each. Point the user at `Start_Presentation.bat`.

## Notes
- Grounding is the invariant: nothing on a slide that is not in the chapter notes. The `grounding-critic` in the
  workflow is the backstop; honour its findings before declaring done.
- Galleries reuse only works when the new chapter shares example topics with an existing deck; otherwise use search.
