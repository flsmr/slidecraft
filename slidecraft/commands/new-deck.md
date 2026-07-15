---
description: Front door for creating a deck — theme pack + skeleton interview, scaffold, then the autonomous build
argument-hint: [deck-name]
---

# New Deck (the front door)

Creates a deck from a **theme pack skeleton** (see `/CONTEXT.md` + ADR-0001/0002): interview →
scaffold → autonomous build. The interview derives everything it can from the sources FIRST and
asks the user to confirm ONCE (workflow-design decisions 6/7). After the confirm round the build
is fully autonomous.

## Step 1 — Pick pack + skeleton
- Read `~/.slidecraft/packs.json`. If missing or empty: ask the user for the theme-pack folder and
  register it there (`{"packs":[{"name":"...","path":"..."}]}`).
- Read `<pack>/pack.json` and each `<pack>/skeletons/<name>/skeleton.json`.
- AskUserQuestion (skip whatever is unambiguous): theme pack (if several), skeleton (if several),
  deck name (`$ARGUMENTS` if given) + deck parent folder (default: where the previous decks live).

## Step 2 — Sources in, derive everything
- `mkdir <deck>/resources`; ask the user to drop (or point you at) the chapter PDF, optional
  template PPTX, optional exam catalogue; copy them in.
- Extract: `python -m slidecraft.scripts.extract_chapter --deck "<deck>" --pdf "<chapter_pdf>" --prefix "chN"`.
- Derive the skeleton's `decision_points` values (each carries a `derive` hint): chapter
  number/title from the TOC, agenda chapters from the template PPTX Topic Outline,
  presenter/course/module from the previous deck's recipe, date = today, divider lines from the
  short title. Build the draft `recipe.json` (schema: `recipe.example.json`) including the
  auto-filled `sections`. **Never ask what the sources can answer.**

## Step 3 — ONE confirm round
AskUserQuestion with the pre-filled values; judgment calls only:
- title / short-title / presenter / date corrections,
- framing-slide opt-outs (multiSelect over the skeleton's `optout: true` slides),
- enrichment toggles pre-set from `skeleton.json.workflow` (mindmap, galleries mode, exam focus,
  citation style), and section slide-target overrides if offered.
Record every answer in `recipe.json` (`slide_optouts`, `workflow`, plain fields).

## Step 4 — Scaffold (deterministic)
```
python -m slidecraft.scripts.scaffold_deck --recipe "<deck>/resources/recipe.json"
```
Renders the framing slides from the skeleton templates, copies deck files + deck-local layouts,
writes `slides.md` with the CONTENT insertion marker, copies the skeleton's `author-guide.md` +
`diagram-style.md` into `<deck>/resources/`, and records provenance. Then `npm install` in the deck.

## Step 5 — Build
Continue with [sprint-deck.md](sprint-deck.md) **from Step 4** (author + enrich workflow, images,
per-slide assembly into the manifest marker, citations, verify, DONE report). The author agents
receive `<deck>/resources/author-guide.md`; diagram prompts follow
`<deck>/resources/diagram-style.md`; `render_references` takes `--style` and pagination from
`recipe.workflow.citations`.

## Rules
- The skeleton defines structure; the plugin defines control flow. Never invent framing slides or
  extension points that are not in `skeleton.json` (ADR-0002).
- `filled_by: "author"` templates (study-goals, summary, exam-focus) contain `AUTHOR:` markers —
  the build MUST replace them all; a finished deck may not contain the string `AUTHOR:`.
- Exam focus stays concept-level; never actual exam questions or scores on slides.
- Decks are independent artifacts: skeleton updates never propagate to existing decks; the recipe
  records which skeleton version created the deck.

## Fallback — no pack fits
For a quick generic Slidev deck outside any theme pack (no skeleton, no build workflow), the old
scaffolder still works: `python -m slidecraft.scaffold.new_deck --name ... --location ... [--theme <dir>]`.
