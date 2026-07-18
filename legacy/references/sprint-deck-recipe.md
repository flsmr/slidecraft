# Sprint-Deck Recipe — building an ILSE lecture deck from lecture notes + exam data

A field-tested playbook distilled from building **SPRINT_1_Production_Engineering** (DLBDSEAR01,
Chapter 1) in Slidev with the `slidev-theme-ilse` theme. It captures the inputs, the step-by-step
pipeline, the house-style conventions, the reusable prompts/scripts, the Windows/Slidev gotchas, and
a design for melding the whole thing into an **autonomous Slidecraft skill/workflow**.

Goal for next time: hand over **(chapter lecture-notes PDF + full course book + exam-question
catalogue + template PPTX + style guide)** and have agents build a first-shot, high-quality, *grounded*
deck autonomously, then iterate to raise quality without ever drifting from the reference notes.

---

## 0. Inputs (what the user provides)

| Input | Used for |
|---|---|
| **Chapter lecture-notes PDF** (e.g. `course_book_chapter_1.pdf`) | figures, text, the concepts to teach (the single source of truth — never hallucinate beyond it) |
| **Full course-book PDF** | TOC (chapter list for the agenda), overall learning objectives, per-figure printed source lines |
| **Exam-question catalogue** (`catalogue-*-tagged.json` + `-enriched.json`) | which concepts students struggle with → the (subtle) Exam-Focus slide |
| **Template PPTX** (`TEMPLATE_*.pptx`) | the official agenda/study-goals structure and the exact chapter list/order |
| **Style guide** (IUG/ILSE Swiss-editorial, as text) | the visual language for any generated image |
| **ILSE Slidev theme** (`slidev-theme-ilse`) | layouts (slide1…9), brand colours, fonts |

Everything the user dropped goes in the deck's **`resources/`** folder (source archive, not served by
Slidev). Generated/served assets go in **`public/figures/`**.

---

## 1. Scaffold the deck

Mirror an existing ILSE deck (or `/slidecraft:new-deck`). Minimum:

- `package.json` — `@slidev/cli`, `slidev-theme-ilse` (a `file:../../slidecraft-themes/...` dep), and
  `@iconify-json/mdi` (for icons). Scripts: `dev`/`build`/`export`.
- `vite.config.ts` — **`server.fs.strict = false`** (theme lives behind a non-ASCII OneDrive path) **and
  `server.watch.ignored = ['**/resources/**','**/dist/**','**/.slidecraft/**']`** (OneDrive locks files
  in `resources/` and crashes Vite's watcher with EBUSY).
- `slides.md` — first slide carries the deck headmatter (`theme: slidev-theme-ilse`, `title:`…).
- `layouts/` — deck-local layouts (see §7).
- `resources/`, `public/figures/`, a `Start_Presentation.bat` one-click launcher.

`npm install` once. Build to verify: `npm run build` must end `✓ built in …`.

---

## 2. Extract everything from the PDF  (`fitz` / PyMuPDF)

- **TOC**: `doc.get_toc()` → identify the chapter and its section page ranges.
- **Figures**: loop pages, `page.get_images(full=True)` → `doc.extract_image(xref)`; **dedupe by xref**
  and **skip tiny images** (`max(w,h) < 120` filters logos/icons). Save `ch{N}_fig_{i}.jpeg`.
- **Text**: `page.get_text()` → write to **UTF-8** files (Windows console is cp1252 and dies on `ﬁ`/`–`).
  Pull the section text, the chapter "study goals", and the course-level "Learning Objectives" page.
- **Per-figure source**: grep the chapter text for `Figure N …` + the following `Source: …` line — that is
  the *authoritative* attribution for each figure (e.g. DIN 8580, REFA, Schmid, Martin…).

## 3. Describe each figure (GPT-5.5 vision via OWUI)

Send each figure image + a prompt asking for: title, type, verbatim caption, content bullets
(transcribe labels), the concept it teaches, and a **reproduction note** (simple box/arrow → rebuild
natively; dense table/photo → keep as image). Save `ch{N}_fig_{i}.md`. These drive split-vs-full and
the native-vs-image decisions.

---

## 4. Build the deck skeleton (mirror template + course book)

Order that worked:

1. **Title** (`slide1`). Course name; **short** chapter title (drop "Introduction to …" if it overflows
   the second line); module code; presenter + date on separate lines. Badge text ("LEARNING SPRINT N")
   is **hardcoded in the theme's `slide1`**, so make a **deck-local `layouts/slide1.vue` override** that
   turns the badge into a `body-20` slot (import the logo from `../node_modules/slidev-theme-ilse/assets/…`).
2. **Agenda** — list **all** course chapters from the template/TOC and **highlight the current chapter**
   (coral). The theme's `slide2` only holds 5 rows and can't highlight, so build a deck-local
   **`layouts/agenda.vue`** (a `v-for` over the chapter list with an `active` index → coral badge + bold).
3. **Study Goals** — mirror the template's study-goals slide, but **add a small icon per goal** (see §6c).
4. **Section divider** (`slide3`).
5. **Mind map** ("§X at a glance") — see §6a.
6. **Content slides** — one per concept/figure; split-screen vs full per the reproduction note (§5).
7. **Summary** — an **icon-card recap grid** capturing every theme (see §6c).
8. **Exam Focus** — *subtle*, concept-level (see §6d).
9. **References + Image sources** (APA 7, consistent — see §6e).
10. **Thank You** (`slide9`).

---

## 5. Content slides — house style (NON-NEGOTIABLE conventions)

These were learned through iteration; bake them in from the start.

- **No centre dot `·` anywhere.** Use bullet points, or commas inside a line. (Applies to footers, legends,
  taglines, notes — everywhere.)
- **No long em-dash `—`.** Use a colon `:` for "label: definition", or a comma. (Keep en-dashes `–` for
  ranges like `1899–1984`, `pp. 216–219`.)
- **Every text slide opens with a ~10-word introductory sentence, then a blank line, then the bullets.**
  The blank line is enforced with a global rule
  `.body-16 p:first-of-type, .ph-1 p:first-of-type { margin-bottom: 0.8em }` (use `:global()` in the
  in-deck `<style>` so Slidev doesn't scope it away).
- **Bullet lists are lists of *related items* only.** Field labels are **not** bullets. E.g. on the DIN
  group slides: `**Definition:** …`, `**Cohesion of particles:** …`, `**Examples:**` are plain paragraphs
  (no `-`); only the example sub-items are bulleted. Put a **blank/`<br>` spacer above "Cohesion" and
  above "Examples"** for neatness (space permitting).
- **Long inline enumerations become sub-bullets**, not a `·`/comma run (e.g. the six DIN groups).
- **Figures**: choose **split** (`slide5`: 1/3 text + 2/3 image) when bullets add teaching value; **full**
  (`slidefigure`, full-width) for dense tables/standalone graphics. Use `object-fit: contain` so figures
  aren't distorted.
- **Citations**: figure caption = APA **in-text** style (surname + year, **no initials**: "Martin (2022)");
  the full APA entry (with initials) lives on the References slide. Verify the figure's printed source.
- **Presenter notes on every slide**: 3-5 bullets of what to say, **plus**
  `- Example to tell: <one relatable scenario>` and `- Memory hook: <mnemonic>`. Put German term roots
  (REFA: Rüsten/Ausführen/Grund…; the wastes → TIM-WOOD) in **notes**, never on the slide.
- **Only the actual course script** may seed slide bullets — no invented facts. Examples/mnemonics in the
  *notes* are allowed teaching aids (clearly the presenter's, not "from the book").

---

## 6. The enrichment workflows (the quality multipliers)

### 6a. Mind map (agent → structure → image, with a critique loop)
1. **Agent** reads the full section text → distils a **complete, accurate nested-markdown outline**
   (central topic, 6-8 main branches, subtopics, key terms). *Insist on completeness* — e.g. list all six
   DIN groups, not an abbreviation.
2. **GPT-5.5 (OWUI)** turns the outline into a radial-mind-map **image-gen prompt**, capped at ~2 levels
   for legibility (white bg, dark-teal centre, pale grey-blue nodes, thin grey connectors, one sparing
   coral accent, Source Sans Pro, 16:9, every label spelled out).
3. **Imagen 3** renders it (`POST /api/v1/images/generations`).
4. **Critical-review agent** compares the image + prompt against the lecture notes and fixes
   misconceptions (e.g. "cohesion is the ordering *principle*, not a 7th group; it applies to groups 1-5
   only"; remove a stray "(§1.1)" from the centre node; coral overused) → writes a corrected prompt.
5. **Regenerate** from the corrected prompt; swap onto the slide. (This loop is what made it accurate.)

### 6b. "Send a slide to ChatGPT for inspiration" (AI diagram polish)
For a text-heavy slide you want to make visual: send its content (and/or the source figure, via vision)
to GPT-5.5 → ask for **design ideas + ONE detailed content-only image-gen prompt** (no title — the
template supplies it; IUG style) → render with Imagen 3 → drop into a `slidefigure` (template keeps
title/logo/footer). Used for **"The big picture"** flow, the **REFA occupancy "story" timeline**
(figurines showing setup → run → idle → allowance summing to occupancy time), etc. Always sanity-check
the rendered text against the notes; regenerate if a label is wrong.

### 6c. Icon slides (Study Goals & Summary)
- Ask GPT-5.5 which **Material Design Icon (`mdi-…`)** fits each bullet (validate names exist).
- Realise them as **crisp vector icons** via `@iconify-json/mdi` (`<mdi-file-tree class="…"/>`), coral,
  in a flex/grid — **not** raster-generated (raster icons look rough at small size).
- Study Goals = an icon list; Summary = a 2×3 **icon-card recap** (icon + bold theme + one-line gloss)
  that mirrors the deck's structure.

### 6d. Exam-Focus slide (grounded but *subtle*)
- Parse `…-tagged.json` (unit/section per question) + `…-enriched.json` (correctRate / avgPercent) →
  rank the unit's questions by success rate to find weak concepts.
- The **visible slide stays general** ("Where to focus your revision" — concepts to master). **Never state
  what is asked or quote scores on the slide.** The performance data + specifics live in the **notes** only.

### 6e. Real example images (free, commercial-use, attributed)
- **Spawn agents** (one per topic/group) to find **real photos** that are **free for commercial use**:
  Public Domain / CC0 / CC BY / CC BY-SA — **never NC, never AI**. Prefer **Wikimedia Commons** (stable
  `upload.wikimedia.org` URLs). Each must be **verified** (HTTP 200 + image content-type). Output JSON
  `{label, direct_url, page_url, license, author, title}`.
- Download with a real **User-Agent** header (Wikimedia 429s empty UAs), **downscale** (PIL `thumbnail`
  ~600px), store in `public/figures/gallery/`.
- Present as a **2-row squared-image gallery** (deck-local `gallery` layout) after the relevant slide.
- **Attribution is mandatory**: the source/link goes (i) in the gallery slide's notes and (ii) as an
  **APA 7 entry on a dedicated "Image sources" slide**, and (iii) in `resources/sources.md`.
  AI-generated images are likewise credited ("OpenAI GPT-5.5 & Google Imagen 3 via IU OpenWebUI").

### 6f. Sources / APA 7 (one consistent format)
An agent compiles **all** sources (text + every image), verifies real bibliographic detail (no fabricated
DOIs/publishers/pages — cite the course book when unsure), formats **APA 7th**, and lays them out with a
**single `.srcref` CSS class** (one font size, one hanging-indent entry style, one header style) across
all source slides so the run is visually continuous.

---

## 7. Deck-local layouts you will (re)create

| File | Purpose |
|---|---|
| `slide1.vue` (override) | turn the hardcoded "LEARNING SPRINT" badge into a `body-20` slot |
| `agenda.vue` | 7-chapter agenda with a highlighted active chapter |
| `slidefigure.vue` | full-width single image + IU header/footer (figures, AI diagrams) |
| `gallery.vue` | full-width grid slot for the 2-row example galleries |

CSS conventions live in one in-`slides.md` `<style>` block (use `:global(...)`): the intro-gap rule, grey
`ph-1` markers, `.din-ex` (smaller example font), `.subkey` (boxed legend), `.study-goals`, `.recap`,
`.gallery`, `.srcref`.

---

## 8. Windows / Slidev / OWUI gotchas (the time-sinks)

- **OneDrive non-ASCII path** ("Präsentationen") breaks `cmd` long paths → use **8.3 short paths**
  (`PRSENT~1\SLIDEC~2\…`) in `launch.json`, or `npm --prefix "<long path>" run …` from Bash.
- **EBUSY watcher crash** — exclude `resources/` from Vite's watcher (OneDrive sync locks files).
- **YAML frontmatter** — a global find/replace that puts a `:` in `title:` breaks parsing → **quote** it.
- **UTF-8 everywhere** when writing text from Python (console is cp1252).
- **Restart the dev server** after `npm install`-ing a new dep (e.g. the icon collection).
- **OWUI image pipeline**: image models on the IU instance are **Google** (Imagen 3 at
  `/api/v1/images/generations`; nano-banana via chat-completions). **No OpenAI/DALL·E** is exposed. With a
  chat model + `features.image_generation`, GPT-5.5 emits a `generate_image` **tool call** whose `prompt`
  you then send to the image endpoint. Blob URLs are pre-signed (no auth header); `/api/v1/files/…` need
  the bearer token.
- Verify visually in the browser (the MCP screenshot tool was flaky); always `npm run build` to catch
  parse/layout errors.

---

## 9. Reusable prompt library (verbatim intents)

Stored alongside the OWUI skill; reuse these shapes.

- **Figure description**: "Describe this course figure precisely … reproduction note: simple box/arrow
  (rebuild natively) vs dense table/photo (keep as image)."
- **Mind-map structure (agent)**: "Distil into a complete nested-markdown outline … list ALL six DIN
  groups … only content actually in the notes."
- **Mind-map image (GPT-5.5)**: "Turn this outline into ONE legible radial-mind-map image prompt, ≤2
  levels, dark-teal centre, pale grey-blue nodes, one sparing coral, 16:9, spell out every label."
- **Mind-map critique (agent)**: "Compare image+prompt to the notes; fix misconceptions (cohesion =
  ordering principle for groups 1-5, not a 7th group; centre node = 'Manufacturing Technology'); write a
  corrected prompt."
- **Slide polish (GPT-5.5)**: "Improve this slide visually; design a content-only graphic (no title);
  return JSON {ideas, image_prompt} in IUG style."
- **Icon picker (GPT-5.5)**: "Pick ONE existing `mdi-…` icon per bullet; return JSON."
- **Real-image search (agent)**: "Find free, commercial-use real photos (PD/CC0/CC BY/CC BY-SA, no NC, no
  AI) on Wikimedia Commons for {examples}; verify direct URLs; write JSON {label,direct_url,page_url,
  license,author,title}."
- **Sources (agent)**: "Compile + verify all sources, APA 7th, no fabrication; consistent formatting."

## 10. Reusable scripts (in `~/.claude/skills/owui/`)

`render_prompt.py` (Imagen render), `plan_slides.py` (pages→slide plan), `describe_images.py`,
`group_examples.py` / `gen_group_images.py`, `mindmap.py` / `mindmap_v2.py`, `whatcourse_polish.py` /
`bigpicture_polish.py` / `occupancy_story.py` (slide→GPT-5.5→Imagen), `study_goals_icons.py`. The OWUI
client supports vision (`image_url` parts), chat-completions, and the image endpoint.

---

## 11. Melding into Slidecraft — autonomous skill/workflow design

Target: `/slidecraft:sprint-deck <deck-name>` (or the **Workflow** tool) that runs phases as agents,
grounded in the notes, with a critic loop. Suggested orchestration:

```
Phase 1  Extract        1 agent   PDF → TOC, figures, text, figure-descriptions, learning objectives
Phase 2  Plan           1 agent   concepts → ordered slide outline (split/full per figure) — grounded
Phase 3  Scaffold       inline    deck files + 4 deck-local layouts + title/agenda(highlight)/study-goals(icons)
Phase 4  Author         N parallel one agent per slide-block → bullets (intro+blank+list rules, no ·/—)
Phase 5  Enrich         parallel  (a) mind-map build+critique loop  (b) AI-diagram polish for 2-3 key slides
                                   (c) real-image galleries (1 search agent per group)  (d) notes: example+hook
Phase 6  Exam focus     1 agent   catalogue → weak concepts → SUBTLE focus slide (+ data in notes only)
Phase 7  Sources        1 agent   APA 7 compile + verify; one consistent .srcref style
Phase 8  House-style    1 agent   anti-slop pass: kill ·, kill —, enforce intro+blank, bullet/label rule,
                                   spacing, caption APA-in-text; then `npm run build`
Phase 9  Critic loop    1-2 agents review the rendered deck vs the notes; file concrete fixes; re-author;
                                   repeat until "no findings" or budget — successive quality, always grounded.
```

New agents to add to `slidecraft/agents/`:
- **`notes-extractor`** (PDF→structured text+figures+descriptions, grounded).
- **`deck-architect`** (outline + slide plan from the notes + template + exam data).
- **`mindmap-smith`** (structure→image with the built-in critique loop).
- **`image-curator`** (free-licensed real-image search + APA attribution).
- **`diagram-illustrator`** (slide→GPT-5.5→Imagen polish).
- **`exam-focus-analyst`** (catalogue→subtle focus slide).
- **`house-style`** (extend the existing `anti-slop` agent with the `·`/`—`/intro/bullet/spacing rules
  above, operating directly on `slides.md`).
- **`grounding-critic`** (review vs lecture notes; the iteration engine).

A shared **`references/house-style.md`** (the §5 rules) is read by every authoring/style agent so the
conventions are enforced uniformly. The **style guide** + **theme layout slots** are passed in as context.

**Definition of done (per deck):** builds clean; every figure attributed (caption APA-in-text + References
entry); every image free-for-commercial-use with a source; no `·`/`—`; every text slide has intro+blank;
bullet/label rule respected; mind map + galleries + focus slide present; presenter notes carry an example
+ memory hook; nothing on a slide that isn't in the lecture notes.
```
