---
description: Interactive front door for building a plain, deck-ready Slidev theme from a blueprint — PPTX, an existing Slidev theme, images, a live website, or a plain description. Analyses the blueprint, writes a precise style guide, lays out the layouts + slots, a slot-role map, and a standard demo deck.
argument-hint: [theme-slug]
---

# New Theme

Build a **theme**: a plain, deck-ready `slidev-theme-<slug>/` npm package that carries its own
**style guide** and visual conventions — from whatever blueprint the user has. A theme is
**visuals-only plus its `styleguide.md`**; it knows nothing about how decks are composed. Deck
*shape* (which structural slides, in what order) is the storyteller's runtime job and lives in
storytelling skills — **never** in the theme. There are no theme packs and no skeletons.
See `/CONTEXT.md` for the glossary (toolkit / theme / storytelling skill / deck) and
`/docs/adr/0003-theme-is-a-plain-slidev-theme.md` for the rule this command implements.

The command is **derive-first, confirm-once**: it ingests and analyses the blueprint BEFORE
asking anything it can answer itself, then presents ONE confirmation round. It is **fully
portable** — every path and the output location are prompted from the user; nothing about drive
letters or folder layout is assumed.

Two hard rules inherited from the architecture:
- **Physical names only in rendered layouts** (ADR-0001, surviving rule): `.vue` layouts,
  `example.md`, and any `slides.md` must use the theme's real layout/slot names (`slide4`,
  `::title::`, `::ph-1::`). Semantic aliases (`cover`, `default`, `section`) live ONLY in
  `semantic-layouts.json`, never in rendered files (the May-2026 render-time-failure lesson).
- **A theme is visuals only, plus its `styleguide.md`.** No deck structure, no skeletons, no
  `pack.json`. Everything that only makes sense for one theme lives in its repo; the toolkit
  stays generic.

Reference implementation to mirror for structure: the user's existing inner theme
`slidev-theme-general/` (`package.json`, `layouts/*.vue`, `components/*.vue`,
`semantic-layouts.json`, `styleguide.md`, `example.md`) — ask them for its path. The root
`styleguide.md` in this repo is the reference format for the style guide.

## Goal — the output tree

Theme creation must output ONLY a plain, deck-ready theme:

```
slidev-theme-<slug>/
  package.json            # name "slidev-theme-<slug>" + slidev.defaults (colorSchema,
                          #   aspectRatio, canvasWidth, fonts.sans/weights)
  layouts/*.vue           # one per kind; PHYSICAL names; each renderable slot is a
                          #   <slot name="…"> so scan_theme.py can read it
  components/*.vue        # optional
  public/                 # theme's own served assets (logos, backgrounds)  [PPTX importer
                          #   emits assets/ instead — either is fine]
  styles/index.css        # optional global styles / CSS custom properties
  semantic-layouts.json   # REQUIRED slot-role contract: alias → { layout, slots{role:physical},
                          #   intent, defaults }. How the composer knows a cryptic physical slot
                          #   (::body-26::, ::ph-1::, slide4) plays a ROLE, how to fill it, and
                          #   its default value.
  styleguide.md           # the theme's visual contract (Phase 2)
  example.md              # STANDARD DECK exercising every layout idiomatically (Phase 3)
  .gitignore              # node_modules/, dist/, .slidev/
```

No `pack.json`, no `skeletons/`, no `<slug>-theme-pack/` wrapper folder.

---

## Phase 0 — Intake (one questionnaire screen)

Parse `$ARGUMENTS` for an optional `[theme-slug]`. Then ask the user, batching into a
single `AskUserQuestion` call where possible (skip any part `$ARGUMENTS` already answers):

1. **Theme slug** — short kebab-case, becomes npm package `slidev-theme-<slug>`
   (e.g. `acme`, `bauhaus`, `nova`). Store as `SLUG`.
2. **Blueprint source** — which do you have? (this drives Phase 1)
   - `pptx` — a PowerPoint `.pptx` template
   - `slidev` — an existing Slidev theme (git URL or a local folder)
   - `images` — a folder of slide images / screenshots
   - `website` — a live web page or HTML/CSS template (URL)
   - `none` — no blueprint; build from a description / the base scaffold
3. **Purpose** — what are decks in this theme for? (academic lecture / corporate briefing /
   sales or pitch / training & workshop / other). This shapes the layout inventory and the
   writing-style section of the style guide. Store as `PURPOSE`.
4. **Output parent folder** — where should the new theme be created? Suggest the folder where
   the user's other themes live, but let them choose. Resolve to an absolute path. The theme dir
   is `THEME_DIR = <parent>/slidev-theme-<slug>/`. Abort and ask before overwriting an existing
   non-empty target.

After Phase 0, ask for the concrete **blueprint location** (path or URL) unless it was
already given. Store as `BLUEPRINT`.

> Permission note: cloning a git repo or downloading a file counts as a download — ask the
> user for an explicit go-ahead first (name the repo/URL). Browsing a live site is fine, but
> decline cookie/consent banners and never submit forms.

Install Python deps if a PPTX path is in play:
```bash
pip install python-pptx lxml Pillow requests --break-system-packages -q
```

---

## Phase 1 — Ingest & analyse the blueprint

The goal of this phase is a normalised **design observation** you hold in working memory:
- **Palette** — concrete `#RRGGBB` for background(s), primary text, and 1–3 accents (plus
  neutrals). Sample real pixels/CSS; do not guess round numbers.
- **Typography** — heading font + body font (family names), weights, casing (e.g. uppercase
  titles), alignment.
- **Layout inventory** — the distinct slide *kinds* the blueprint shows, each with its
  slots and their roles (title / body / image / agenda rows / contacts / …), background
  (light vs dark), and rough slot geometry.
- **Imagery & graphic language** — photo treatment, icon style, shapes, use of accent.
- **Logo / persistent furniture** — logos, footers, slide numbers.

Follow the sub-path for the chosen `BLUEPRINT` type:

### 1a. PPTX — reuse the importer (richest, pixel-accurate)
This is the extractor already built on the PPTX XML. It emits real `.vue` layouts with
absolute-positioned physical-name slots, extracted assets, a demo deck, and a theme
`package.json`. Prefer running the proven `/slidecraft:import-template` flow, or call the
importer directly:
```bash
python -c "
from pathlib import Path
from slidecraft.importer.convert import convert
r = convert(
    pptx_path=Path(r'<BLUEPRINT>'),
    theme_dir=Path(r'<THEME_DIR>'),        # <parent>/slidev-theme-<slug>
    deck_dir=Path(r'<THEME_DIR>/deck'),    # a temporary preview deck (not shipped in the theme)
    theme_name='slidev-theme-<slug>',
)
print(r)
"
```
`ConvertResult` reports `slides_count`, `typefaces_total/substituted`, `sans_families`,
`alias_font_faces`, `warnings` — surface these. The importer emits `package.json`,
`layouts/*.vue`, and `assets/` (it does NOT write any `theme-manifest.json` — that belonged to
an older extractor). Fill the design observation by reading the emitted artifacts:
- `<THEME_DIR>/package.json` → `slidev.defaults.fonts.sans` + `weights`, `colorSchema`,
  `canvasWidth`, `aspectRatio`.
- `<THEME_DIR>/layouts/*.vue` → inline `color:` / `font-family:` / `background:` values
  (palette + fonts), the absolutely-positioned slot `<div>`s, and each `<slot name="…">`
  (the PHYSICAL slot names + their geometry = the layout inventory).
- `<THEME_DIR>/assets/manifest.json` → extracted image/logo inventory (may be `{}`).

### 1b. Slidev theme — clone / copy and adapt
Ask permission, then (git URL) clone into a temp dir, or (local folder) read in place:
```bash
git clone --depth 1 <url> "<TMP>/blueprint-theme"
```
Copy `layouts/`, `components/`, `public/`/`assets/`, `styles/`/`style.css`, `global-*.vue`,
and `package.json` into `<THEME_DIR>`. Then adapt:
- Rename the package to `slidev-theme-<slug>`; keep the `slidev.defaults` (fonts, aspect
  ratio, canvasWidth) but review them.
- Read `style.css` / `uno.config.*` / `:root` custom properties to extract the palette and
  font families for the design observation.
- Read the theme's `example.md` / demo `slides.md` to learn which layouts + named slots
  exist and how they are used → this IS the layout inventory (physical names already).
Note the theme's licence; record it and keep any `LICENSE`/attribution.

### 1c. Images / screenshots — vision analysis
Read each image with the Read tool. For each distinct slide kind, describe: background
(sample the dominant hexes), title/body/accent colours, apparent font family + weights +
casing, the grid (columns, image placement), imagery treatment, and any logo/footer. Build
the layout inventory from the recurring kinds. Flag that geometry is approximate (no XML
ground truth) — layouts will be authored, not extracted.

### 1d. Live website / HTML template — Browser pane
Open the URL with `preview_start {url}`. Use `read_page` for structure, a screenshot for the
look, and `javascript_tool` to read computed styles for exact values, e.g.:
```js
getComputedStyle(document.body).fontFamily
getComputedStyle(document.querySelector('h1')).color
[...document.styleSheets].flatMap(s=>{try{return[...s.cssRules]}catch{return[]}})
  .filter(r=>r.selectorText===':root').map(r=>r.style.cssText)
```
Derive palette (background/text/accent hexes), fonts, and the layout inventory from the
page's sections. Decline consent banners; do not log in or submit anything.

### 1e. None — interview / base scaffold
Ask a few quick questions (2–3 background/text/accent colours, heading + body font, light or
dark default, vibe) OR start from `templates/slidev-base`. Produce a modest default layout
inventory for the chosen `PURPOSE` (see Phase 3).

---

## Phase 2 — Write the style guide

Write `<THEME_DIR>/styleguide.md`, in the **14-section format** of the root `styleguide.md`,
describing the OBSERVED style precisely — not a generic template. Fill every section with
concrete specifics from Phase 1:

1. Overall visual character · 2. Colour palette (every hex, with role + "use sparingly"
notes) · 3. Typography (families, weights, casing, alignment) · 4. Image style · 5. Icons &
illustrations · 6. Charts & data-viz · 7. Layout behaviour for generated content · 8. Shapes
& graphic elements · 9. Dark-slide style · 10. Light-slide style · 11. Writing style
(matched to `PURPOSE`) · 12. Positive prompt template · 13. Negative prompt · 14. Practical
generation rules.

**The style guide MUST include a figure/diagram consistency section** (fold it into §4/§6/§8
and the prompt templates §12–§14): the rules the **image-composer** consumes via its
`%STYLE-GUIDE%` injection to keep generated figures consistent — **one shape per role, one
connector style with one arrowhead, one accent, direct labels, generous whitespace, fill the
canvas, flat vector (no gradients/shadows/3D)**. This is the single source of truth for both the
figure generator and the image-critic; there is no separate `diagram-style.md`.

Show the user the palette + font + layout-inventory summary now (the derived facts), so the
Phase 3 confirmation is a quick check rather than data entry.

---

## Phase 3 — Assemble the theme (layouts + slots + config + slot-role map + standard deck)

Produce the **Goal** tree above. Concretely:

- **PPTX path (1a):** layouts + assets + `package.json` already emitted; your job is to review
  them, then AUTHOR `semantic-layouts.json` and `example.md` (below). If you ran
  `/slidecraft:import-template`, its interactive step already writes `semantic-layouts.json` —
  reuse it.
- **Copied/authored paths (1b–1e):** ensure/author each layout `.vue`. Rules:
  - Root element `position: relative; overflow: hidden;` sized to the canvas (e.g.
    1280×720); slots are absolutely-positioned `<div>`s wrapping `<slot name="…">`.
  - **Every renderable region is a `<slot name="…">` with a PHYSICAL name** — this is what
    `scan_theme.py` reads to build the deck's theme capabilities. A layout with only a bare
    `<slot/>` exposes a single `default` slot; name your regions when a layout has more than one.
  - Colours via CSS variables / the theme palette — no scattered hardcoded hexes.
  - Provide a **default** content layout, and the layout kinds the inventory + `PURPOSE`
    call for. Sensible starter inventory (include what fits; confirm with the user):
    `cover`, `agenda`/`section-overview`, `section` (divider), `default` (title+body),
    `content-image` (text+figure), `figure` (full-bleed), `two-cols`, `quote`, `facts`,
    `end`/`thank-you`.
  - Persistent furniture (logo, slide number, footer) → `global-bottom.vue` or per-layout
    slots, matching the blueprint.

### `semantic-layouts.json` — REQUIRED slot-role contract
AUTHOR (or reuse from the importer) a `semantic-layouts.json` mapping each meaningful layout to
a semantic alias. Shape (mirror `slidev-theme-general`):
```json
{
  "version": "1.1",
  "theme": "slidev-theme-<slug>",
  "aliases": {
    "cover":  { "layout": "<physical>", "slots": { "title": "<physical-slot>", "meta": "<physical-slot>" },
                "intent": "What this layout is for; per-slot roles, budgets, what must NOT go on it.",
                "defaults": {} },
    "end":    { "layout": "<physical>", "slots": { "title": "<physical-slot>" },
                "intent": "Closing slide; title is 'Thank you', never recap content.",
                "defaults": { "title": "Thank you" } }
  },
  "unmapped_layouts": ["<physical>", "..."]
}
```
Every `slots` value and every `layout` is a **physical** name. `intent` is free-form English the
composer reads to fill each slot by role; `defaults` supplies fixed content for otherwise-empty
role slots (agenda `title` → "Agenda", closing `title` → "Thank you"). Both fields must be
present (`""` / `{}` when empty). This is what lets a composer fill a cryptic physical slot
(`::body-26::`, `::ph-1::`) it would otherwise have no way to interpret.

### `example.md` — a first-class STANDARD DECK (not a stub)
AUTHOR a realistic, well-structured **standard deck** that exercises **every** layout
idiomatically: **cover · agenda · content · section · figure · closing** (add two-cols/quote if
the theme has them). Write it in the theme's **physical** layout + slot names. It serves two
jobs: it is the composer's concrete "how a deck looks in this theme" reference (it replaces the
old per-theme skeleton templates), and it is the render sanity-check for the theme. Use realistic
placeholder copy (a short coherent topic), not lorem ipsum; keep each slide within the density a
real slide would carry.

**Confirmation round (the one checkpoint):** `AskUserQuestion` with the derived values —
palette (editable), fonts, and a multiSelect of which layouts to include. Apply the answers.

---

## Phase 4 — Finalise & report

- Write `<THEME_DIR>/.gitignore` (`node_modules/`, `dist/`, `.slidev/`, `*.log`, `.DS_Store`,
  `Thumbs.db`).
- Offer to `git init` the theme (default: ask; no by default).
- Verify it renders: `cd "<THEME_DIR>" && npm install && npx slidev build example.md` should exit
  0 (or preview with `npx slidev example.md`). Fix any layout that fails to render.
- Report:
  - Output path (`<THEME_DIR>`); blueprint type used.
  - For PPTX: `slides_count`, `sans_families`, `warnings` from `ConvertResult`.
  - Palette + fonts + the final layout inventory (alias → physical, from `semantic-layouts.json`).
  - Where the style guide is (`<THEME_DIR>/styleguide.md`) and that the standard deck is
    `example.md`.
  - Preview command: `cd "<THEME_DIR>" && npm install && npx slidev example.md`.
  - **Next step:** point `/init-deck` at `<THEME_DIR>` (theme type: **local**) to build a deck on
    this theme; then drop inputs into `input/` and run `/draft-deck`.
  - If a theme repo was cloned/copied: note its licence and that attribution was preserved.

---

## Rules

- Derive before you ask; one confirmation round; never ask what the blueprint answers.
- Rendered layouts, `example.md`, and any `slides.md` use **physical names**; semantic aliases
  live only in `semantic-layouts.json`.
- The theme is **visuals-only plus its `styleguide.md`**. No `pack.json`, no `skeletons/`, no
  theme-pack wrapper. Deck shape lives in storytelling skills, not in the theme.
- `semantic-layouts.json` and a first-class `example.md` are **required** deliverables, not
  optional extras — the composer depends on both.
- Downloads (git clone, file fetch) need explicit user go-ahead; browsing declines consent
  banners and never submits forms or logs in.
- Preserve licences/attribution of any copied theme.
- Keep everything portable — prompt for paths, assume no drive letters or folder layout.
- Fast path for a bare PPTX conversion still works: choose `pptx` and accept the defaults (or run
  `/slidecraft:import-template` directly).
