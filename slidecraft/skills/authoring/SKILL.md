---
name: authoring
description: >
  Transform raw material into a complete slide deck. Use when the user wants to
  create a new presentation, draft slides, build a deck from raw material,
  structure a talk, or turn notes into slides. Triggers on phrases like
  "create presentation", "draft slides", "build a deck", "make slides from
  these notes", "turn this into a presentation", "structure my talk",
  "write a deck about", "create slides for", "build a presentation from".
---

# Authoring Skill

You transform raw material from the `resources/` folder into a fully rendered Slidev presentation. The deck's canonical source is **one markdown file per slide** under `<deck>/slides/<descriptive-name>.md`, ordered by `<deck>/slides.md` which uses `---src:` imports. Slidev consumes the files directly — there is no rendering step. You don't draft inline; you delegate to the [`slide-author`](../../agents/slide-author.md) subagent, then run the [`slide-critic`](../../agents/slide-critic.md) + [`source-researcher`](../../agents/source-researcher.md) loop.

Before starting, read `references/best-practices.md` for presentation design rules and apply them throughout.

---

## Step 1 — Asset Analysis

Read material in the `resources/` folder of the workspace. (`assets/` is reserved for Slidev runtime assets and must not be confused with `resources/`, which holds the source material the deck is built from.)

> **Hard rule: never `Read` a PDF directly. Always go through the cache.** A 1000-page reference book would blow the context window; the cache exists to prevent this. PDFs are consumed only via the manifest + extracted markdown produced by `scripts/extract_pdf_assets.py`.

### 1a. Discover resources structure

Detect whether the user has organised material into the conventional subfolders. Any combination may be present (or none):

- `resources/Content/` — primary material the deck draws from heavily (lecture notes, the brief, outlines). Expect to load it all.
- `resources/Sources/` — reference material cited selectively (papers, textbooks). Use map-mode first; pull full text only when needed for a specific slide.
- `resources/Instructions/` — user-authored guidance for the deck (the brief, talking-point hints, "must include X" notes). Read in full; treat as authoritative.
- Anything else, or files at the `resources/` root — treat as `Content/`-equivalent.

Categorize every file accordingly. If none of the conventional subfolders exist, the whole `resources/` tree is `Content/`.

### 1b. Run the PDF extractor

Before reading any PDF, run the extractor from the deck root:

```bash
python -m slidecraft.scripts.extract_pdf_assets --deck <deck-dir>
```

The script is idempotent — already-cached PDFs are skipped via a SHA1 match, so re-running it is cheap. It writes per-PDF caches under `<deck-dir>/.slidecraft/cache/pdf/<doc-slug>/`.

If the script reports `pymupdf is required. Install with: pip install pymupdf`, tell the user to run `pip install pymupdf` and **stop**. Do not attempt to parse PDFs without it.

### 1c. Load extracted content tier-aware

For every PDF, **always read `manifest.json` first**. The fields you care about are `source`, `size_tier` (`"small"` | `"large"`), `page_count`, `chapters[]` (each with `title`, `file`, `page_start`, `page_end`, `word_count`), and `images[]`.

Then load text according to where the PDF lives:

- **`Instructions/` PDFs** — always load `text.md` (small tier) or every `text/ch-NN.md` (large tier). If a large PDF appears in `Instructions/`, flag it to the user — that's unusual and may be a misfile.
- **`Content/` PDFs** —
  - Small tier: load `text.md` in full.
  - Large tier: load `map.md` first. Then load whichever chapters look most relevant by title. You may load all chapters if their `word_count` sum is reasonable (≤ ~20K words total).
- **`Sources/` PDFs** — **always load `map.md` only** at first. Open a specific `text/ch-NN.md` later, only when a slide being drafted needs material from that chapter. Mention this deferred-read plan in the storyline step so the user knows references will be consulted lazily. **Never load a Sources PDF's full `text.md` blindly.**

### 1d. Catalog extracted images

Walk every `manifest.json`'s `images[]` array and build an in-memory list of available figures with their source PDF and source page. These become useful later — the `illustrate` enhancement pass (Step 8) consumes this catalog, and the `visual-enrichment` skill can also draw on it. For now, just report the total count to the user (e.g. "extracted 47 figures from 3 PDFs").

### 1e. Non-PDF files

- `.md` and `.txt` — read as text.
- `.png` / `.jpg` / `.jpeg` / `.svg` at the top level of `resources/` (or in any subfolder) — note them as available figures with their path and a guessed alt-text from the filename. Add them to the same in-memory catalog as the PDF-extracted images.
- Anything else (`.docx`, `.xlsx`, `.pptx`, …) — list to the user as "not consumed in MVP" and continue.

### Summary pass

Once everything loaded is in context, summarize to yourself:
- What topics and arguments appear in the material?
- What data points, quotes, or examples are present?
- What structure does the material suggest (e.g., problem → solution, timeline, comparison)?
- What does the user most likely want to communicate?

---

## Step 2 — Briefing & Clarification

If `resources/Instructions/` contains a brief, treat it as authoritative — do not re-ask the user for things the brief already specifies. State that you've read the brief and are honouring it, then only fill in genuinely missing pieces below.

Based on the resources and any instructions the user has already given, confirm the following with the user — but only ask about what is genuinely unclear. If the resources make something obvious, state your assumption and proceed.

Key questions to cover:

- **Target audience**: Who will see this? (e.g., executives, technical team, students, customers)
- **Length**: How many slides, or how many minutes? Default to ~1 slide/min for keynote, ~0.5 slides/min for business briefing, ~0.33 slides/min for academic / technical teaching (dense material needs time to land).
- **Deck mode** — the most important question, drives everything below:

| Mode | When | Single argument? | Tone reference |
|---|---|---|---|
| **argument-driven** | research talks, briefings answering "should we…" | yes — one defensible sentence | `business.md` or `academic.md` |
| **textbook recap** | university lecture pedagogically restructuring a chapter | no — *coverage* with teaching scaffold (Ausubel + Def-Ex-Thm-Ex) | `academic.md` |
| **source-mirror** | lecture or recap that closely follows the source's own structure | no — *faithful* to source's section order, with human-in-loop topic selection | `academic.md` |
| **decision briefing** | executive update, change proposal | yes — the recommendation | `business.md` |
| **keynote / pitch** | conference talk, sales pitch | yes — the one big idea | `keynote.md` |
| **other** | anything else | ask the user | ask the user |

**Difference between textbook-recap and source-mirror.** Both target academic teaching audiences and load `academic.md`. They diverge on *structure source*:
- `textbook-recap` overlays a pedagogical skeleton (Ausubel advance organiser + Definition→Example→Theorem→Example→Remark) on top of the source. The deck has its own internal logic; the source provides content.
- `source-mirror` follows the source's own section order. The deck IS the chapter, with selected topics dropped or kept. Human-in-the-loop selection step (Step 4b) is mandatory.

- **For argument-driven, decision briefing, keynote**: ask for *the single argument* — not "the topics", but the **one defensible claim** the deck makes, the sentence the audience should repeat the next day.
- **For textbook recap**: ask for *the chapter or sections* covered + *what practical examples the user wants interleaved*. Do NOT force a single argument; coverage is the point.

If the resources/Instructions/ brief specifies any of these, honour it without re-asking.

### Load the tone reference

Once the deck mode is fixed, read the matching file:

- argument-driven (academic context) → [references/tones/academic.md](../../references/tones/academic.md)
- argument-driven (business context) → [references/tones/business.md](../../references/tones/business.md)
- textbook recap → [references/tones/academic.md](../../references/tones/academic.md)
- decision briefing → [references/tones/business.md](../../references/tones/business.md)
- keynote / pitch → [references/tones/keynote.md](../../references/tones/keynote.md)

The tone file governs voice, register, citation conventions, worked-example placement, and active-learning beats for this deck. Don't restate its rules in your own context — refer back to it when drafting.

After the briefing, write a one-paragraph **audience-and-purpose profile** to yourself before drafting. The shape depends on the deck mode:

For **argument-driven / decision briefing / keynote**:

> *Audience: <role> with <prior knowledge> who has <time/attention budget> and needs to leave <understanding/decision>. Single argument: "<one sentence>". The deck succeeds if a listener can paraphrase this sentence the next day.*

For **textbook recap**:

> *Audience: <role> with <prior knowledge> studying <course/chapter> who needs to leave able to <use/apply/recognise> the chapter's key concepts. Coverage scope: <which sections, which examples, what's deferred to the reading>. The deck succeeds if a student can do the chapter's end-of-section exercises afterward.*

You don't need to show this profile to the user, but every subsequent decision (slide titles, depth, examples) must be defensible against it. If you find yourself drafting a slide that isn't traceable to the profile, it doesn't belong.

---

## Step 3 — Storyline Drafting (internal)

Plan a narrative arc — **but do not present a text outline to the user**. Text outlines like `Slide 01 [cover] — "Title"` are abstract and hard to evaluate; the user can't tell from a 25-line list whether the deck is any good. Go straight to a rendered first draft they can actually preview (Steps 4 + 5).

Use this section as a planning checklist for yourself, not as something to show the user.

### 3a. Pick the narrative skeleton

The right skeleton depends on the deck mode chosen in Step 2:

- **SCQA** (Situation → Complication → Question → Answer) — argument-driven research talks, analyst-style decks. Sets up context, names the problem, asks the question the deck answers, then answers it.
- **Pyramid / answer-first** (Minto) — executive briefings. Lead with the conclusion; subsequent slides are evidence supporting it.
- **Problem → Insight → Action** — change-management, decision-forcing decks. Frames a pain, reveals the key reframe, prescribes what to do differently.
- **Hero's journey / contrast arc** (Duarte sparkline) — keynote / pitch. Oscillates "today" and "tomorrow" states until the call to action.
- **Advance-organiser + Def→Ex→Thm→Ex→Remark** — textbook recap (see below for details). The teaching skeleton.

Pick one and commit. Mixing skeletons is a common silent failure — the deck drifts and the audience loses the through-line.

#### Textbook-recap skeleton in detail

For a chapter-recap lecture (university level), the skeleton is grounded in Ausubel's advance-organiser model and the math-lecture Definition→Theorem→Example tradition:

1. **Advance organiser** (1 slide). An abstract conceptual scaffold one level *above* the chapter — how this chapter fits in the course, what frame to bring. NOT a TOC. A comparative organiser ("here's how this builds on Ch. 4 and contrasts with the Bayesian view") works well.
2. **Expository core** (8–12 slides). Cycle of: definition → worked example → theorem/principle → worked example → remark. Repeat 3–5 times across the chapter's key concepts. **Place worked examples immediately after each definition**, before any theorem uses it (Sweller's worked-example effect, robust for novice learners).
3. **Integrative reconciliation** (1–2 slides). Connect new material back to the advance organiser. Explicit contrasts with neighbouring chapters or alternative frameworks. This is where retention is highest (Bligh) — put the hardest synthesis here, not in the warm-up.
4. **Consolidation cue** (1 slide). Nudge to the assessment, problem set, or reading. Not a "recap" — a *next step*.

Optional: 2–3 **active-learning beats** spread across the deck (pause-and-predict, peer instruction, or 60-second silent processing). One beat is too few; mechanical every-10-min spacing is folklore — place them where the conceptual jumps are hardest.

For full design rules including notation conventions (bold for definitions, framed boxes for theorems), citation style (bottom-right author-year + final References slide), and pacing (0.33 slides/min default — *equation slides count double*), read [references/tones/academic.md](../../references/tones/academic.md) once at the start and refer back as needed.

### 3b. The ghost-deck test (gate before drafting)

After the storyline takes shape, **write the title of every slide in sequence, nothing else, and read them as a single block**. If the titles alone tell the complete argument, the storyline is sound. If a reader needs the bullets to follow the story, the titles aren't doing their job — rewrite them before you draft a single body.

This is the operational test for assertion titles (Alley, *Assertion-Evidence Approach*). Don't skip it: it's the cheapest critique you'll run all session, and it catches structural problems before you waste effort on bodies.

### 3c. Choose the visual type before the words

For each planned slide, pick the visual type FIRST. The body content follows from the type — not the other way around.

| Slide purpose | Visual type | Anti-pattern to avoid |
|---|---|---|
| Sequence / steps over time | numbered list or arrow diagram | 2-column comparison (no parallel structure) |
| Compare 2–4 alternatives | side-by-side table | bullets (lose the cross-comparison) |
| Show parallel items of equal weight | grid or icon-row | hierarchy implied by ordered bullets |
| Highlight one big number / fact | hero statement (one number, large) | bullet list with the number buried |
| Quote / testimonial | pull-quote layout | block of regular text |
| Walk through math / a derivation | annotated equation (label every symbol on the slide, not in notes) | bare formula (forces the audience to decode it live) |
| Show a process or pipeline | flow diagram | bullets (lose the directionality) |
| Bring evidence for a claim | one annotated exhibit (chart, image, figure) | three bullets restating the title |
| Default to bullets only when | the slide is genuinely a small enumeration of equal items | almost any other case |

The default bullet-list slide is the failure mode you're trying to avoid — it's what every AI-generated deck looks like. Reach for bullets last, not first.

### 3d. Per-slide design rules (with the *why*)

#### Title length by slide role

A title that's too long reads as a bullet. Differentiate by what the slide is FOR:

| Slide role | Title length | Form | Example |
|---|---|---|---|
| `cover` | 1–4 words | short noun phrase, **no formula, no sentence** | *"Camera Geometry"*, *"From Pixels to 3D"* |
| `section`, `section-overview` | 1–5 words | chapter heading | *"Multi-view geometry"*, *"Today's agenda"* |
| `default`, `content-image`, others | 4–10 words | assertion sentence or rich noun phrase | *"Two views recover lost depth"*, *"Calibration drift in field use"* |
| `end` | fixed | "Thank you" / "Questions?" — from theme defaults | *"Thank you"* |

Why differentiated: the previous 8–14-word "assertion-style for everything" rule (Alley) produced cover titles like *"Every camera obeys one equation: x = K[R\|t]X"* — that's a bullet, not a cover. Covers are deck *names*, sections are *signposts*, content is *claim*-bearing. Each role has its own job.

#### Body limits (7×7, relaxed from the previous 4×7)

- **Maximum 7 bullets per slide, ≤ 7 words each, ≤ 49 words total body** — the classic "7×7 rule" used widely in academic and corporate decks. Tight, but more flexible than the 4-bullet cap. Prefer fewer; the cap is the upper bound, not the target.
- For academic recap decks, target 3–5 bullets per content slide — leave whitespace for the speaker to elaborate.
- For keynote decks, prefer 0–2 bullets; full sentences in bodies are rare.

#### Other per-slide design rules

- **One idea per slide** — because a slide with two ideas forces the audience to choose which to listen to; they usually pick neither.
- **Bullets must be evidence FOR the title, not paraphrase OF it** — if the title says "Three risks threaten Q3 launch" and bullet 1 says "Risks threaten the launch", delete it. Each bullet must be a *separate*, *named*, *specific* piece of support. Concrete > abstract every time: "Acme lost $4M when their stereo rig drifted 2°" beats "calibration matters".
- **Telegraphic language is fine** — drop articles where meaning survives. "Engineers chose Rust over Go" not "The engineers chose Rust over Go." Saves bullet width, reads more confidently.
- **Speaker notes are mandatory and are the script** — not a repeat of the slide. Include the transition into the slide, the elaboration the slide can't fit, citations for every non-trivial claim, and any predict-then-reveal beat. If the notes are short enough to fit on the slide, the slide is under-written.
- **Slot content is a single paragraph** — no blank lines inside any slot's content. Blank lines close the slot block early in Slidev's MDC parser; the renderer wraps offending content in a `<div>` and warns, but the cleaner fix is to not author multi-paragraph slot content in the first place. If you need two paragraphs of text in one slot, use `<br><br>` or restructure into bullets.

### 3e. Pacing budget

Compute the slide budget from session length and tone *before* drafting:

| Format | Slides per minute | 30 min → | 60 min → |
|---|---|---|---|
| Academic / technical lecture | 0.33 – 0.5 | 10 – 15 | 20 – 30 |
| Business briefing | 0.5 – 1.0 | 15 – 30 | 30 – 60 |
| Keynote / TED | 1.0 – 2.0 | 30 – 60 | 60 – 120 |

Drafting more slides than the budget allows is the most common mistake. If you find yourself wanting 25 slides for a 30-minute academic session (which is keynote pacing), reduce — either compress, or push secondary material to an appendix the speaker can skip.

When the skeleton, ghost-deck test, visual-type choices, and budget all agree — hand off to Step 4. Don't pause for outline approval; the convergence loop happens **after** the user has previewed real slides.

---

## Step 4 — Slide-file authoring (delegated to the `slide-author` subagent)

The deck's canonical source is **one markdown file per slide** under `<deck>/slides/<descriptive-name>.md`, plus a thin `<deck>/slides.md` that imports them in order via `---src: ./slides/<name>.md` frontmatter blocks. **There is no rendering step** — Slidev consumes the slide files directly.

You don't draft the slides inline in your own context. **You delegate to the `slide-author` subagent** so the drafting context is clean of this conversation's working dialog. The author returns the slide files; you then run the critic loop (Step 5).

### 4a. Invoke the `slide-author` subagent

```
Task({
  subagent_type: "slide-author",
  description: "Draft deck",
  prompt: `Draft the deck at <deck-dir>.

Brief:
  audience: <one-line role + prior knowledge>
  deck mode: <argument-driven | textbook-recap | source-mirror | decision-briefing | keynote>
  pacing: <duration in minutes; target slide count>
  coverage: <chapter / section / scope>

Sources: <deck-dir>/.slidecraft/cache/pdf/ (extractor already run)
Theme: <theme-dir> (read its semantic-layouts.json for alias intent + slot maps)
Tone reference: slidecraft/references/tones/<academic|business|keynote>.md (read it)

Audience-and-purpose profile:
  <one paragraph; see Step 2>

Output expected:
  - one file per slide at <deck>/slides/<descriptive-name>.md
  - <deck>/slides.md updated to import them in order
  - <deck>/references.bib for cited sources
  - return summary listing filenames, cite keys, structural issues`,
})
```

The author's full protocol is in [`slidecraft/agents/slide-author.md`](../../agents/slide-author.md). It reads sources, picks a skeleton per deck mode, drafts files using the theme's intent docs + tone reference, and returns the file list. It does **not** invoke critic / researcher — that's your job in Step 5.

### 4b. Special case — source-mirror mode pauses for selection

If the deck mode is `source-mirror`, the author **stops mid-draft** with a candidate list of teaching topics extracted from the source ("here are 12 candidates from Unit 1.3-1.5"). Present this list to the user with the question *"which 5–8 should the deck actively teach?"*. Once the user confirms the selection, re-invoke the author with the chosen topics; it then drafts only those. Other deck modes don't pause.

### 4c. The slide-file schema (canonical form)

Each file under `<deck>/slides/` has this shape:

```markdown
---
id: pinhole                       # stable id == filename without .md
layout: content-image             # semantic role from theme's semantic-layouts.json
sources:                          # citation keys + locator + relevance
  - key: szeliski2022
    locator: "§2.1.4"
    relevance: "pinhole projection model"
  - key: bobmellish2005
    locator: "Wikimedia Commons"
    relevance: "figure attribution"
visualization_hint: ""            # optional: hint for a future viz agent
---

::title::
Pinhole: 3D rays converge through one point

::body-16::
- Light through a tiny aperture creates an inverted image
- Every 3D point traces a ray through the **camera centre**
- Foundational model — real lenses approximate it
- Inversion usually flipped in diagrams

::picture-14::
![Pinhole camera (Bob Mellish 2005, CC BY-SA 3.0)](/figures/pinhole-camera.png)

::citations::
Szeliski, 2022, §2.1.4; Mellish, 2005, Wikimedia Commons

<!-- ==== SLIDE CONTEXT — for agents and the editor; not rendered ====

## Verbatim source extracts
**Szeliski 2022, §2.1.4:** "3D to 2D projections. ..." (full paragraph)
**IU course book §1.3:** "The pinhole camera model, ..."

## Drafting decisions
- Lead with "rays converge" framing over "image inversion" — the
  latter is a visual quirk; ray-through-centre is load-bearing.

## Downstream agent hints
- **Visualization agent**: a custom SVG would replace this stock photo.
- **Quiz generator**: "double f → image scale does what?" (linearly).
- **Critic**: Rule 3 ✓; Rule 4 ✓.

==== END CONTEXT ==== -->

<!--
Speaker notes (Slidev parses the last comment as notes):
Definition slide. Worked example IS the figure. Source: Szeliski (2022) §2.1.4.
-->
```

**Section order matters:**
1. YAML frontmatter (structured fields, no markdown)
2. Slot blocks (`::slot-name::`) — the renderable content per the theme's slot map
3. Context block (`<!-- ==== SLIDE CONTEXT ... -->`) — placed after slot blocks so editors hit content first, not background
4. Speaker notes (`<!-- ... -->`) — last comment in the file; Slidev parses it as notes

**Filenames are descriptive nouns**, never numeric. Order lives in `<deck>/slides.md`. Deleting one slide means editing one import line; renaming means editing two; two agents working on different files don't collide.

### 4d. Theme intent docs are mandatory reading

The author reads `<theme-dir>/semantic-layouts.json` before populating any slide. Each alias has an `intent` field that tells the author what that layout is FOR. Honor it. Examples:

- `cover` intent says "title is a short noun phrase, NEVER a formula" — author writes "Camera Geometry", not "Every camera obeys x = K[R\|t]X".
- `end` intent says "title is 'Thank you' or 'Questions?' — NOT recap content" — author writes "Thank you", not the deck's summary.
- `content-image` intent says "image slot is a SINGLE paragraph markdown image reference" — author never writes multi-paragraph slot content (it breaks MDC parsing).

The schema supports `defaults` per alias (e.g. `defaults: {title: "Thank you"}` on the end role), but these are **documentation, not auto-fill**. The author reads them and explicitly types the value into the slide file.

### 4e. references.bib

The author maintains `<deck>/references.bib` in BibTeX format. Every cite key referenced in any slide's `sources:` frontmatter must have a bib entry. Format follows APA-7th-ready BibTeX conventions (Pandoc and Zotero compatible).

---

## Step 5 — Lint + Critic + Researcher Loop (before showing the user)

Don't ship the first draft. The default AI failure mode is bullet-list slides that paraphrase their titles; the cheapest defense is to send the draft through a **lint pass + critic agent** before the user sees it.

The author returned a list of slide files. The lint catches mechanical errors (bad layout names, bad slot names, image-in-slot, formula-in-title) at near-zero cost. The critic catches judgment-call issues (assertion vs label, evidence vs paraphrase, monotony, intent compliance). The researcher verifies specific claims. You apply fixes by editing slide files. No CIF, no render step — files are the canonical form.

### 5a. Run the lint first

Before invoking the critic, run the lint script to catch mechanical errors:

```bash
python -m slidecraft.scripts.lint_slides --deck <deck-dir>
```

Exit codes: `0` = clean; `1` = errors (must fix before continuing); `2` = warnings only (under `--strict`).

The lint catches:
- **L1** — semantic layout names that Slidev would silently fall back from to its built-in layouts
- **L2** — semantic slot names that produce invisible slots
- **L3** — image references inside named slot blocks that break Vite import-guard
- **L4** — blank lines inside slot blocks that close the slot early in MDC
- **L5** — unparseable YAML frontmatter
- **L6** — formulae / single uppercase letters / operator characters in titles (warning; promoted to error with `--strict`)
- **L7–L12** — soft warnings on missing speaker notes, body-over-49-words, anti-monotony, etc.

For any **L1–L5 error**, fix it before invoking the critic — these are render-breaking. For **L6–L12 warnings**, fold the suggestions into the critic's findings.

### 5b. Invoke the critic

After the author returns, spawn the `slide-critic` agent via the Task tool:

```
Task({
  subagent_type: "slide-critic",
  description: "Critique slide deck",
  prompt: `Review the draft deck at <deck-dir>.

Slide files: <deck-dir>/slides/*.md (read each)
Deck-level: <deck-dir>/slides.md (ordering + theme frontmatter)
References: <deck-dir>/references.bib
Argument profile: <copy the one-paragraph audience-and-purpose profile from Step 2>
Focus: all slides`,
})
```

The critic returns a prose summary followed by a fenced JSON block. Parse the JSON — it conforms to the schema documented in `slidecraft/agents/slide-critic.md`. The fields you care about:

- `ghost_deck_reading` — the titles in sequence; check it tells the argument
- `pacing.in_budget` and `pacing.recommended_cut_count` — pacing verdict
- `findings[]` — per-slide issues, each with `severity`, `rule`, `current`, `suggested_fix`, and `needs_research`
- `overall_verdict` — `ready` / `needs_revision` / `structural_issues`

### 5c. If verdict is `structural_issues`: stop and surface

If the critic says the deck has structural issues (ghost-deck test fails, argument drift, wildly off pacing), don't try to fix slide-by-slide — the storyline itself is broken. Bring the critic's diagnosis to the user, propose a restructure, and wait for their direction. Don't burn cycles patching individual slides on a broken skeleton.

### 5d. For each `needs_research: true` finding: spawn the researcher

The critic doesn't verify claims itself; it flags them. For each finding with `needs_research: true`, spawn the `source-researcher` agent via Task:

```
Task({
  subagent_type: "source-researcher",
  description: "Verify claim for <slide-id>",
  prompt: `Verify this claim against the deck at <deck-dir>:

Claim: "<verbatim research_claim from the finding>"
Slide: <slide-id> (<slide title>)
Context: <optional surrounding text from the slide>
Web fallback: not allowed`,
})
```

The researcher returns a verdict (`supported` / `partial` / `unsupported`) with evidence quotes from the cache, plus a recommended action. Apply the recommendation to the slide:
- **supported** — keep the claim; if academic deck, add the citation it returned.
- **partial** — apply the `suggested_rephrasing` (or weaken the claim accordingly).
- **unsupported** — apply the researcher's `recommended_action` (`rephrase`, `drop`, etc.).

Allow web fallback only if the user has previously authorized internet research in this session.

### 5e. Apply the critic's other fixes

For each finding without `needs_research`, apply the `suggested_fix` by **editing the individual slide file** the finding names. Edits follow the standard pattern: copy the current `slides/<name>.md` to `.slidecraft/history/<name>-YYYYMMDD-HHMMSS.md`, modify the slide file in place, and you're done — Slidev hot-reloads.

If a fix is **structural** (e.g. the critic wants a comparison-table slide but the theme has no `two-cols` alias in `semantic-layouts.json`), flag it to the user as a separate question rather than degrade the slide silently.

### 5f. Re-invoke the critic — at most once

After applying fixes, re-invoke `slide-critic` once. If the verdict is now `ready` or there are only minor findings, proceed to Step 7. If major findings remain, accept them as known caveats and hand off to the user with a brief note; don't loop a third time.

### 5g. Persist the critique

Save the final critic JSON to `.slidecraft/history/critique-YYYYMMDD-HHMMSS.json`. This makes the critic's reasoning auditable later when the user asks "why is slide 12 like this?".

### 5h. Don't show the user the raw critique

The user evaluating the deck for the first time should see your best work, not a confession. Show them the rendered preview only. The critique is for you, not for them — unless they explicitly ask "what did the critic say?", in which case summarise.

---

## Step 6 — Preview & Edit Loop

After the critique pass, **do not present a text outline of the slides**. Instead, point the user at the actual rendered preview — they're going to evaluate the deck visually, not as a list of titles. Tell them:

> Rendered `slides.md` (N slides). To preview:
>
> ```
> cd <deck-dir> && npx slidev
> ```
>
> Visit the localhost URL it prints and page through. When you're ready, tell me what to change — by slide number, by title, or in natural language ("the third slide feels too text-heavy", "add a slide about X after the camera-model section", "swap 4 and 5").

Then wait for their edit requests. Don't volunteer a critique of your own draft — the user's first impression of the rendered deck is the signal you want.

### Accepted edit commands

Handle these natural-language edit requests:

- **"Change slide 3"** or **"Rewrite slide 3"** — Ask what should change, then edit the corresponding `slides/<name>.md` file directly (the deck's `slides.md` import list gives you the filename for ordinal "slide 3").
- **"Add a slide about X"** — Determine the best position, create a new slide entry, renumber IDs if needed.
- **"Remove slide 5"** or **"Delete the quote slide"** — Delete the slide file from `slides/` AND remove its `---src:` line from `slides.md`. No renumbering needed (filenames are descriptive).
- **"Swap slides 4 and 5"** — Exchange the two entries in the `slides` array.
- **"Show me slide 7"** — Display the full content, notes, and layout of that slide.
- **"Change the title of slide 2 to X"** — Update just the `title` field.
- **"Add speaker notes to slide 4"** — Update the `notes` field.
- **"Change the layout of slide 6 to two-cols"** — Update the `layout` field.

### For every edit

1. Copy the slide file to `.slidecraft/history/<name>-YYYYMMDD-HHMMSS.md`
2. Apply the edit directly to `slides/<name>.md`
3. Slidev hot-reloads on file save — no render step
4. Confirm the change to the user

Continue the loop until the user is satisfied with the deck.

---

## Step 7 — Enhancement Menu

After a successful render, critique pass, and the user's first preview (Step 7), present the enhancement menu **once per authoring run**. The deck is already usable at this point — enhancements are opt-in, and the user can pick zero, one, or many.

Show the menu verbatim:

```
Your deck is rendered and ready to preview. You can stop here, or run one or
more enhancement passes:

  1. Visualize     — add Mermaid diagrams, tables, code blocks where the
                      slide content benefits from a visual. (skill: visual-enrichment)
  2. Illustrate    — drop in figures extracted from your PDFs as image
                      placeholders on relevant slides. (built into authoring; see below)
  3. Exemplify     — add worked examples, case studies, or analogies to
                      concrete-up abstract slides. (skill: example-generator)
  4. Quiz          — insert interactive check-for-understanding slides
                      between sections. (skill: quiz-generator)
  5. Cite          — attach Sources/ references to relevant slides as
                      footnotes / further-reading bullets. (NOT YET IMPLEMENTED)
  6. Edit          — make specific changes to individual slides.
                      (skill: interactive-editing)
  7. Review        — run the content-reviewer agent for a structured
                      quality pass. (agent: content-reviewer)

  Done — Stop here. Re-preview the deck and call it ready.

Pick one or more (e.g. "1 and 3", "all", "just 6"), or "done".
```

### How the menu works

- The menu is shown **once per authoring run**. After each enhancement completes, control returns to this menu so the user can chain additional passes. Loop until the user says "done".
- For items **1, 3, 4, 6** — invoke the named skill. The user can also re-enter any of these skills later outside an authoring run by saying a phrase that matches the skill's description (e.g. say "add quizzes" anytime to re-enter `quiz-generator`, or "make it visual" to re-enter `visual-enrichment`). Mention this to the user when relevant.
- For item **5 (Cite)** — respond that this is not yet implemented and is on the roadmap as a future skill. Do not silently skip; the labeling is intentional so the user sees the planned shape of the toolchain.
- For item **7 (Review)** — hand off to the `content-reviewer` agent.
- For item **2 (Illustrate)** — handle inline. See below.

### Inline behaviour: Illustrate

This is the only menu item handled directly inside the authoring skill, because Step 1d already cataloged every available image.

1. For each cataloged image, attempt a **simple keyword match** between the slide's title/content and the image's source-PDF chapter title (for PDF images) or filename (for loose image files). Score matches loosely — favour overlap on content nouns.
2. Build a proposal table for the user:

   ```
   slide → proposed image          (source)
   ─────────────────────────────────────────────────────
   04   → page-012-fig-03.png      (Smith2022.pdf, ch.2)
   11   → page-047-fig-01.png      (Smith2022.pdf, ch.5)
   ```

3. Wait for the user's approval (they may reject individual rows, accept all, etc.).
4. On approval, for each accepted row:
   - **Copy** the chosen image from `.slidecraft/cache/pdf/<slug>/images/<name>` (or from its `resources/` location for loose images) into `<deck>/public/figures/`. The cache lives under `.slidecraft/`, which Slidev does **not** serve from `public/` — direct cache references will 404. Keep the same file basename; since the cache name is SHA1-influenced (`page-NNN-fig-NN.<ext>`) collisions across PDFs are highly unlikely, but if one occurs, prefix the destination with the doc-slug.
   - Reference the copied image from the slide using a `/figures/<filename>` URL (Slidev resolves `/` against `public/`).
5. **Updates follow the standard slide-file-edit pattern:**
   - Copy the current `slides/<name>.md` to `.slidecraft/history/<name>-YYYYMMDD-HHMMSS.md`.
   - Modify the slide file — add the image to the appropriate slot (often `::image::` or `::picture-<N>::` per the theme's alias) and set a frontmatter flag like `illustrated: true` on each touched slide for auditability.
   - Slidev hot-reloads; no render step.
   - Confirm the changes to the user, then return to the enhancement menu.

---

## Key rules (the *why* in one place)

- **`slides.md` is the ordering manifest, not content** — edit it only to reorder, add, or remove slide imports. All slide content lives in `slides/<name>.md`.
- **Save slide-file history before overwriting** — because every edit is reversible only if there's a snapshot, and authoring is iterative; you'll want to roll back a bad change at least once per session.
- **Speaker notes are the script, not optional** — because a slide is a headline and the notes are what's actually said; a slide without notes can't be presented, only read.
- **One idea per slide** — because a slide with two ideas forces the audience to pick which to listen to; they usually pick neither.
- **Assertion titles** — because the ghost-deck test requires that titles alone tell the argument; topic labels ("Performance") leave the work to the body, which the audience doesn't read while listening.
- **≤ 40 words / ≤ 4 bullets per slide body** — because beyond that, audiences read instead of listen, and the speaker becomes redundant. Compress or split.
- **Concrete > abstract in every bullet** — because "Acme lost $4M on miscalibration" sticks; "calibration matters" does not. If a bullet has no named entity, number, or specific failure mode, it's probably restating the title.
- **Visual type before content (Step 3c matrix)** — because picking words first leads to bullet-list defaults; picking the shape first opens the door to tables, hero numbers, comparisons, and annotated exhibits.
- **Run the critique pass (Step 5) before showing the user** — because the first draft is reliably a B-grade deck and the cheapest fix is to read it as a critic before the user does.
- **Read `references/best-practices.md` at session start** — because the density, font, and pacing limits there are the empirical baseline; the skill's rules above are derived from them.
- **Never `Read` PDFs directly** — because a 1000-page reference book blows the context window; the cache (Step 1b) exists to prevent this. Large `Sources/` PDFs are map-only until a specific slide needs deeper material.
- **Illustrate copies images to `public/figures/`** — because Slidev serves only from `public/`; references to the `.slidecraft/cache/` path 404 in the browser.
