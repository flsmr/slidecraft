---
description: Interactive front door for building a Slidev theme (or full theme pack) from a blueprint — PPTX, an existing Slidev theme, images, a live website, or a plain description. Analyses the blueprint, writes a precise style guide, lays out the layouts + slots, and (optionally) a starter skeleton.
argument-hint: [theme-slug]
---

# New Theme

Build a **theme** (visuals-only `slidev-theme-<slug>/`) or a full **theme pack**
(theme + `skeletons/` + `pack.json` + style guide) from whatever blueprint the user
has. See `/CONTEXT.md` for the glossary (plugin / theme / theme pack / skeleton / deck)
and `/docs/adr/` for the rules this command must respect.

The command is **derive-first, confirm-once** (workflow-design decision 6): it ingests and
analyses the blueprint BEFORE asking anything it can answer itself, then presents ONE
confirmation round. It is **fully portable** — every path and the output location are
prompted from the user; nothing about drive letters or folder layout is assumed.

Two hard rules inherited from the architecture:
- **Physical names only in rendered layouts** (ADR-0001): `.vue` layouts and `slides.md`
  must use the theme's real layout/slot names (`slide4`, `::title::`, `::ph-1::`).
  Semantic aliases (`cover`, `default`, `section`) live ONLY in `semantic-layouts.json`,
  never in rendered files (the May-2026 render-time-failure lesson).
- **A theme is visuals only.** Deck structure (framing-slide sequence, decision points)
  belongs in a *skeleton* inside the theme pack, never in the theme package.

Reference implementation to mirror for structure: the IU theme pack the user already has
(ask them for it, or read `~/.slidecraft/packs.json`) — `pack.json`,
`slidev-theme-ilse/` (`package.json`, `layouts/*.vue`, `assets/`, `semantic-layouts.json`),
and `skeletons/sprint/` (`skeleton.json`, `templates/*.md`, `author-guide.md`,
`diagram-style.md`). The root `styleguide.md` is the reference format for the style guide.

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
   sales or pitch / training & workshop / other). This shapes the layout inventory, the
   framing-slide set, and the writing-style section of the style guide. Store as `PURPOSE`.
4. **Scope** — `theme` (visuals only + style guide + demo deck) or `pack` (also generate a
   starter skeleton so `/slidecraft:new-deck` can consume it immediately). Store as `SCOPE`.
5. **Output parent folder** — where should the new theme/pack be created? Suggest the folder
   where the user's other theme packs live (from `~/.slidecraft/packs.json` if present),
   but let them choose. Resolve to an absolute path.
   - For `SCOPE=pack`: `OUT = <parent>/<slug>-theme-pack/`, theme at `OUT/slidev-theme-<slug>/`.
   - For `SCOPE=theme`: `OUT` is the theme dir itself, `<parent>/slidev-theme-<slug>/`.
   Abort and ask before overwriting an existing non-empty target.

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
absolute-positioned physical-name slots, extracted assets, a demo deck, and a
`theme-manifest.json` with the resolved palette + fonts.
```bash
python -c "
from pathlib import Path
from slidecraft.importer.convert import convert
r = convert(
    pptx_path=Path(r'<BLUEPRINT>'),
    theme_dir=Path(r'<THEME_DIR>'),      # OUT/slidev-theme-<slug> (pack) or OUT (theme)
    deck_dir=Path(r'<THEME_DIR>/deck'),  # demo deck sibling
    theme_name='slidev-theme-<slug>',
)
print(r)
"
```
`ConvertResult` reports `slides_count`, `typefaces_total/substituted`, `sans_families`,
`alias_font_faces`, `warnings` — surface these. The importer emits `package.json`,
`layouts/*.vue`, and `assets/` (it does NOT write a `theme-manifest.json` — that belonged to
the older `extract-pptx-theme.py` script). Fill the design observation by reading the emitted
artifacts:
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

Write `<OUT>/styleguide.md` (for a pack) or `<THEME_DIR>/styleguide.md` (theme-only), in the
**14-section format** of the root `styleguide.md`, describing the OBSERVED style precisely —
not a generic template. Fill every section with concrete specifics from Phase 1:

1. Overall visual character · 2. Colour palette (every hex, with role + "use sparingly"
notes) · 3. Typography (families, weights, casing, alignment) · 4. Image style · 5. Icons &
illustrations · 6. Charts & data-viz · 7. Layout behaviour for generated content · 8. Shapes
& graphic elements · 9. Dark-slide style · 10. Light-slide style · 11. Writing style
(matched to `PURPOSE`) · 12. Positive prompt template · 13. Negative prompt · 14. Practical
generation rules.

This document is the human- and AI-facing description of the theme's look. If `SCOPE=pack`
its rules become the seed for the skeleton's `diagram-style.md` **consistency contract**
(Phase 4) — one source of truth for both the figure generator and the image-critic.

Show the user the palette + font + layout-inventory summary now (the derived facts), so the
Phase 3 confirmation is a quick check rather than data entry.

---

## Phase 3 — Assemble the theme (layouts + slots + config)

The output theme dir must end up with:
```
slidev-theme-<slug>/
  package.json            # npm metadata + slidev.defaults (colorSchema, aspectRatio,
                          #   canvasWidth, fonts.sans/weights)
  layouts/*.vue           # one per layout kind; PHYSICAL slot names via <slot name="…">
  assets/                 # logos, backgrounds, decorative SVG/PNG (+ manifest if extracted)
  styles/index.css        # optional global styles / CSS custom properties
  semantic-layouts.json   # alias → { layout, slots{alias:physical}, intent } map
  example.md              # demo deck exercising every layout (npx slidev-runnable)
```

- **PPTX path (1a):** layouts + assets + `package.json` already emitted; your job is to
  review them, then AUTHOR `semantic-layouts.json` by mapping each meaningful layout to a
  semantic alias with per-slot `intent` strings (copy the ILSE `semantic-layouts.json` shape:
  `aliases.<name> = { layout, slots{semantic:physical}, intent, defaults }`, plus
  `unmapped_layouts`). Write `example.md`.
- **Copied/authored paths (1b–1e):** ensure/author each layout `.vue`. Rules:
  - Root element `position: relative; overflow: hidden;` sized to the canvas (e.g.
    1280×720); slots are absolutely-positioned `<div>`s wrapping `<slot name="…">`.
  - Colours via CSS variables / the theme palette — no scattered hardcoded hexes.
  - Provide a **default** content layout, and the layout kinds the inventory + `PURPOSE`
    call for. Sensible starter inventory (include what fits; confirm with the user):
    `cover`, `agenda`/`section-overview`, `section` (divider), `default` (title+body),
    `content-image` (text+figure), `two-cols`, `quote`, `facts`, `end`/`thank-you`.
  - Persistent furniture (logo, slide number, footer) → `global-bottom.vue` or per-layout
    slots, matching the blueprint.
  Then AUTHOR `semantic-layouts.json` mapping aliases → these physical names + slot intents.

**Confirmation round (the one checkpoint):** `AskUserQuestion` with the derived values —
palette (editable), fonts, and a multiSelect of which layouts to include — plus, if
`SCOPE=pack`, which framing slides the skeleton should offer. Apply the answers.

---

## Phase 4 — (Only if `SCOPE=pack`) starter skeleton + pack.json

Mirror the ILSE pack layout. Write:

`<OUT>/pack.json`:
```json
{
  "name": "<slug>-theme-pack",
  "version": "<today>",
  "description": "<slug> theme pack: the slidev-theme-<slug> theme plus its skeletons.",
  "theme": { "package": "slidev-theme-<slug>", "path": "slidev-theme-<slug>" },
  "skeletons": ["<skeleton-name>"]
}
```

`<OUT>/skeletons/<skeleton-name>/`:
- `skeleton.json` — `name`, `version`, `description`, `theme`, a `_placeholders` note
  (templates use `@@KEY@@` markers, NOT `{{…}}` which collides with Vue;
  `scripts/scaffold_deck.py` substitutes them from `recipe.json`), a `framing_slides[]`
  sequence (each `{id, file, template, layout: <PHYSICAL name>, optout, filled_by}` with a
  single `CONTENT` insertion point), `decision_points[]` (each with a `derive` hint), and a
  `workflow` block (citations / mindmap / galleries / exam_focus toggles, `polish_passes`,
  `author_rules`, `diagram_style`). Reference the theme's PHYSICAL layout names only, and
  tailor the framing set to `PURPOSE` (a pitch deck ≠ a lecture).
- `templates/*.md` — the framing-slide templates using physical `::slot::` names and
  `@@KEY@@` placeholders.
- `author-guide.md` — house style + per-slot writing rules for the author agents.
- `diagram-style.md` — the **consistency contract** for AI figures, seeded from the Phase 2
  style guide (one shape per role, one connector style, one accent, fill the canvas, etc.).

Keep skeletons self-contained (duplication between skeletons is accepted for independence —
ADR-0001). Do NOT invent workflow extension points beyond the fixed set (ADR-0002).

---

## Phase 5 — Finalise & report

- Write `<THEME_DIR>/.gitignore` (`node_modules/`, `dist/`, `.slidev/`, `*.log`, `.DS_Store`,
  `Thumbs.db`).
- Offer to `git init` the theme/pack (default: ask; no by default).
- `npm install` in the demo deck / theme so it previews.
- Report:
  - Output path(s); whether a theme or a full pack was produced; blueprint type used.
  - For PPTX: `slides_count`, `sans_families`, `warnings` from `ConvertResult`.
  - Palette + fonts + the final layout inventory (alias → physical).
  - Where the style guide is; where the skeleton is (if any).
  - Preview command: `cd "<demo-deck-or-theme>" && npm install && npx slidev`.
  - Next step: run `/slidecraft:new-deck` and point it at `<OUT>` to build a deck on it.
  - If a theme repo was cloned/copied: note its licence and that attribution was preserved.

---

## Rules

- Derive before you ask; one confirmation round; never ask what the blueprint answers.
- Rendered layouts use physical names; semantic aliases live only in `semantic-layouts.json`.
- The theme package stays visuals-only; structure lives in skeletons (theme-pack scope).
- Downloads (git clone, file fetch) need explicit user go-ahead; browsing declines
  consent banners and never submits forms or logs in.
- Preserve licences/attribution of any copied theme.
- Fast, backward-compatible path still works for a bare PPTX conversion: choose
  `pptx` + `theme` scope and accept the defaults.
