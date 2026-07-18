---
name: theme-import
description: Import a corporate PowerPoint (.pptx) template and convert it into a plain, deck-ready Slidev theme. The importer extracts colors, fonts (with metric-compatible substitution), logos, decorative shapes, backgrounds, and slide layouts, then emits a plain slidev-theme-<name>/ package plus a demo deck. Triggers on phrases like "import template", "convert pptx theme", "create theme from powerpoint", "use our company template", or any request involving .pptx files and Slidev themes.
---

# Theme Import Skill

You convert corporate PowerPoint templates (.pptx) into **plain, deck-ready Slidev themes**. A
theme is a visuals-only `slidev-theme-<name>/` npm package that also carries its own
`styleguide.md`; it contains **no** deck structure — no `skeletons/`, no `pack.json`, no
`theme-manifest.json`. Deck *shape* is the storyteller's runtime job, not a theme artifact (see
`docs/adr/0003-theme-is-a-plain-slidev-theme.md`).

The user-facing front door is the **`/slidecraft:import-template`** command; this skill is the
craft reference behind it.

## Pipeline overview

One Python entry point does the extraction — `slidecraft.importer.convert.convert()`:

```
PPTX file
  │  convert(pptx_path, theme_dir, deck_dir, theme_name="slidev-theme-<name>")
  ▼
slidev-theme-<name>/            deck/                 (temporary preview deck)
  package.json  (fonts+config)    slides.md
  layouts/slide<N>.vue            package.json  (file: dep on the theme)
  assets/  (deduped images + manifest.json)
  ↑ then you author:
  styleguide.md                 semantic-layouts.json
```

`convert()` parses the `.pptx`, substitutes MS-proprietary fonts (Calibri → Carlito, Cambria →
Caladea, …) with metric-compatible open-source families, extracts and SHA1-deduplicates picture
assets (with crop/duotone derivatives), writes one absolutely-positioned `.vue` layout per source
slide with **physical-name `<slot name="…">`** regions, generates the theme `package.json` (Slidev
native font config: `colorSchema`, `canvasWidth`, `aspectRatio`, `fonts.sans`), and emits the demo
deck. It returns a `ConvertResult` (`slides_count`, `typefaces_total/substituted`, `sans_families`,
`alias_font_faces`, `warnings`). It does **not** write a `theme-manifest.json` — that belonged to a
retired extractor; if you see references to `extract-pptx-theme.py`, `extract-fonts.py`, or
`validate-theme.py`, they are gone.

## Step 1: Run the conversion

Install deps and call the entry point (the `/slidecraft:import-template` command wraps this):

```bash
pip install python-pptx lxml Pillow --break-system-packages -q
python -c "
from pathlib import Path
from slidecraft.importer.convert import convert
base = Path(r'<output-base>')
r = convert(
    pptx_path=Path(r'<pptx-path>'),
    theme_dir=base / 'slidev-theme-<name>',
    deck_dir=base / 'deck',
    theme_name='slidev-theme-<name>',
)
print(r)
"
```

Normalize `<name>` to a valid npm package slug first (lowercase; spaces/invalid chars → hyphens;
strip leading dot/underscore). `convert()` validates again and raises `ValueError` with a hint if
anything slips through.

Install deck deps in the **deck** dir (the theme declares no npm deps; Slidev provides UnoCSS
transitively via `@slidev/cli`):

```bash
cd "<output-base>/deck" && npm install
```

## Step 2: Author `semantic-layouts.json` (the slot-role contract)

The importer produces one bespoke layout per source slide (`slide1.vue` … `slideN.vue`),
positionally named, with physical slot names (`title`, `body-19`, `picture-22`, …). Downstream
deck tooling — the slide-composer — drafts by **role**, so the theme needs a
`semantic-layouts.json` mapping each role to (a) a physical layout and (b) which physical slot
plays each role, plus a free-form `intent` and `defaults`. This is REQUIRED: without it a composer
sees `::body-26::` and cannot tell it means the deck title.

The `/slidecraft:import-template` command walks the user through building this interactively
(inventory the layouts' slots, pick which `slideN` is cover/default/section/end/…, map slots, and
capture each role's `intent` + `defaults`). The result is `<theme-dir>/semantic-layouts.json`
(schema v1.1), e.g.:

```json
{
  "version": "1.1",
  "theme": "slidev-theme-<name>",
  "aliases": {
    "cover": { "layout": "slide1", "slots": { "title": "body-26", "meta": "body-12" },
               "intent": "Deck cover. TITLE = the deck name (short noun phrase, never a formula). META = author · date.",
               "defaults": {} },
    "end":   { "layout": "slide9", "slots": { "title": "title" },
               "intent": "Closing slide. TITLE is a closing word ('Thank you'), never recap content.",
               "defaults": { "title": "Thank you" } }
  },
  "unmapped_layouts": ["slide2", "slide6"]
}
```

Every `layout` and every `slots` value is a **physical** name. `intent`/`defaults` must both be
present (`""`/`{}` when empty). `scan_theme.py` reads this file at `/init-deck` and surfaces each
layout's role map + intent + defaults into the deck's theme capabilities.

## Step 3: Write `styleguide.md` at the theme root

A theme carries its own visual contract. Write `<theme-dir>/styleguide.md` in the 14-section
format of the repo's root `styleguide.md`, describing the extracted palette, typography, image
style, and — importantly — a **figure/diagram consistency section** (one shape per role, one
connector style, one accent, direct labels, fill the canvas, flat vector). This is what the
image-composer consumes via its `%STYLE-GUIDE%` injection; there is no separate `diagram-style.md`.

## Reference: how PPTX shapes map to the emitted CSS

The importer already reproduces the master's shapes as absolutely-positioned CSS in each layout.
This section is background for **hand-refining** a layout the importer got approximately right —
it is not a separate step you must run.

### Accessing PPTX shape data

```python
from pptx import Presentation
from pptx.util import Emu

prs = Presentation("template.pptx")
master = prs.slide_masters[0]
slide_w, slide_h = prs.slide_width, prs.slide_height  # EMU

for layout in master.slide_layouts:
    for shape in layout.shapes:
        left_pct = shape.left / slide_w * 100
        top_pct  = shape.top / slide_h * 100
        w_pct    = shape.width / slide_w * 100
        h_pct    = shape.height / slide_h * 100
        shape.fill.type          # SOLID, BACKGROUND, PATTERNED, …
        shape.fill.fore_color    # .rgb or .theme_color
        shape.line.width         # EMU
        shape.rotation           # degrees
```

### Theme color resolution

PPTX shapes reference colors by theme slot names (`dk1`/`tx1`, `lt1`/`bg1`, `accent1`…). python-pptx
reports theme colors as enums (`BACKGROUND_1 (14)`, `ACCENT_1 (5)`, …). Resolve them to hex from the
theme XML. Layout backgrounds use scheme names: `scheme:tx1` → dark, `scheme:bg1` → white,
`scheme:accent1` → the accent hex.

### Mapping PPTX shapes to CSS

| PPTX shape | CSS technique |
|---|---|
| Filled/bordered rectangle (decorative) | `::before` / `::after` pseudo-element, `%`-positioned, `transform: rotate(...)` for tilt |
| Thin line (accent) | thin pseudo-element (`width`/`height` from the line, colored `background`) |
| Triangle | `clip-path: polygon(...)` |
| Colored title bar | style the `h1` directly (`background`, `display: inline-block`, padding) |
| Large decorative number ("01") | absolutely-positioned styled span |
| Freeform path (`<a:custGeom>`, rare) | inline SVG in the Vue template |

Each layout `<div>` is `position: relative; overflow: hidden;`; decorative shapes are pseudo-elements
so slot content sits above them (`z-index`). Prefer CSS variables / the theme palette over scattered
hardcoded hexes when you refine.

### Slidev slot rules

1. A bare `<slot />` renders the markdown after the frontmatter (the `default` slot).
2. Named slots (`<slot name="body-19" />`) are filled from `slides.md` with `::body-19::` MDC
   blocks. Singletons (`title`, `footer`, `date`, `slide-number`, `subtitle`) emit a bare name;
   repeatable types use `{type}-{ooxml-idx}` so names stay stable across re-imports (see
   `slidecraft/importer/emit/naming.py`).
3. Use **physical** slot names in every rendered file (ADR-0001) — semantic aliases live only in
   `semantic-layouts.json`.

### Logos & persistent furniture

Logos are extracted to `assets/` (prefer an `.svg` over `.png` if present). Put persistent furniture
(logo, slide number, footer) in a `global-bottom.vue`, switching a dark/light logo variant on the
current layout's background. Reference assets by the served path.

### Fonts

`convert()` substitutes MS-proprietary fonts with metric-compatible open families and configures
the sans stack via Slidev's native font config in `package.json` (Google Fonts). It does **not**
write a `_fonts.css` or bundle `.woff2` offline. For a corporate font not on Google Fonts, ask the
user for `.woff2` files, place them under `<theme-dir>/styles/`, and add `@font-face` declarations
there.

## Output structure (plain theme)

```
slidev-theme-<name>/
├── package.json              # npm metadata + Slidev font/color/aspect config
├── layouts/
│   └── slide<N>.vue          # one per source slide; physical-name <slot>s
├── assets/                   # SHA1-deduped images + derivatives + manifest.json
├── styles/                   # optional: index.css / bundled @font-face
├── semantic-layouts.json     # slot-role contract (Step 2)
├── styleguide.md             # visual contract (Step 3)
├── example.md                # demo deck (the importer emits one into deck/; copy/author here)
└── .gitignore                # node_modules/, dist/, .slidev/
```

No `theme-manifest.json`, no `skeletons/`, no `pack.json`.

## Limitations

- **Freeform vector paths** (`<a:custGeom>`) can't be pure CSS — inline SVG (rare, 1–2 layouts).
- **MTX-compressed EOT fonts** can't be deobfuscated — substitution / Google Fonts covers most.
- **Chart objects** embedded in PPTX aren't converted — recreate with a component or Mermaid.
- **Animations/transitions** aren't extracted — use Slidev's transition system.

## User interaction (via `/slidecraft:import-template`)

1. Ask which `.pptx` to convert and the output base dir + theme slug.
2. Run `convert()`; install deck deps.
3. Show the extracted palette, fonts, layout count, and any warnings.
4. Author `semantic-layouts.json` (Step 2) and `styleguide.md` (Step 3).
5. Preview: `cd <output-base>/deck && npx slidev`.
6. Next step: build a deck on the theme by pointing `/init-deck` at `<theme-dir>` (type: local).
