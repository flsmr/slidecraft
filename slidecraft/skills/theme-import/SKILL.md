---
name: theme-import
description: Import a corporate PowerPoint (.pptx) template and convert it into a pixel-accurate Slidev theme. Extracts colors, fonts (with offline bundling), logos, decorative shapes, backgrounds, and slide layouts — then validates the result against the source. Triggers on phrases like "import template", "convert pptx theme", "create theme from powerpoint", "use our company template", or any request involving .pptx files and Slidev themes.
---

# Theme Import Skill

You convert corporate PowerPoint templates (.pptx) into fully functional, pixel-accurate Slidev themes. The generated theme reproduces the PPTX slide master's exact shapes, colors, positions, and typography using CSS and Vue components.

## Pipeline Overview

```
PPTX file
  │
  ├─ 1. extract-pptx-theme.py   → theme-manifest.json + scaffolded theme
  ├─ 2. extract-fonts.py         → public/fonts/*.woff2 + _fonts.css
  ├─ 3. Manual layout refinement → layouts/*.vue with decorative shapes
  └─ 4. validate-theme.py        → validation-report.json (pixel + structural)
```

## Scripts

All scripts are in `slidecraft/scripts/`:

| Script | Purpose | Key dependencies |
|--------|---------|------------------|
| `extract-pptx-theme.py` | Full extraction: colors, fonts, logos, layouts, backgrounds → scaffolded Slidev theme | python-pptx, lxml, Pillow |
| `extract-fonts.py` | Extract/download fonts, bundle as offline .woff2 | python-pptx, lxml, requests |
| `validate-theme.py` | Compare generated Slidev theme against source PPTX | python-pptx, lxml, Pillow, scikit-image (optional) |

Install all dependencies:
```bash
pip install python-pptx lxml Pillow requests scikit-image
```

## Step 1: Extract Theme Scaffold

```bash
python scripts/extract-pptx-theme.py \
  --input <path-to-pptx> \
  --output <theme-output-dir> \
  --name <theme-name>
```

This generates the base theme structure with CSS variables, placeholder layouts, extracted images, and a `theme-manifest.json` containing all extracted metadata.

## Step 2: Extract and Bundle Fonts

```bash
python scripts/extract-fonts.py \
  --pptx <path-to-pptx> \
  --theme-dir <theme-output-dir> \
  [--force-download]
```

The font extraction tries three strategies in order:

1. **ODTTF deobfuscation** — PPTX `.fntdata` files are XOR-obfuscated TTF/OTF. The script tries to deobfuscate using the GUID from the relationship filename. Works for simple XOR but NOT for MTX-compressed EOT (Microsoft's proprietary compression).

2. **Google Fonts download** — Falls back to downloading `.woff2` files from the Google Fonts CSS API. Handles font renames (e.g., "Source Sans Pro" → "Source Sans 3"). Downloads latin subset only in regular/semibold/bold × normal/italic variants.

3. **Manual fallback** — If both fail, prints instructions listing the exact font files needed.

Output:
- `public/fonts/*.woff2` — Offline font files
- `_fonts.css` — `@font-face` declarations for all variants
- Updates `style.css` to `@import './_fonts.css'` instead of Google Fonts CDN

## Step 3: Refine Layouts with Decorative Shapes

The initial extraction generates placeholder layouts. This step is where pixel-accuracy comes from — you must manually refine each Vue layout using exact shape data from the PPTX.

### Accessing PPTX Shape Data

Use `python-pptx` to extract every shape from each layout. The key data points are:

```python
from pptx import Presentation
from pptx.util import Emu

prs = Presentation("template.pptx")
master = prs.slide_masters[0]

# Slide dimensions (needed for % conversion)
slide_w = prs.slide_width   # EMU
slide_h = prs.slide_height  # EMU

for layout in master.slide_layouts:
    for shape in layout.shapes:
        # Position and size in inches
        left_in  = Emu(shape.left).inches
        top_in   = Emu(shape.top).inches
        w_in     = Emu(shape.width).inches
        h_in     = Emu(shape.height).inches

        # Convert to percentage of slide
        left_pct = shape.left / slide_w * 100
        top_pct  = shape.top / slide_h * 100
        w_pct    = shape.width / slide_w * 100
        h_pct    = shape.height / slide_h * 100

        # Fill, border, rotation
        shape.fill.type          # SOLID, BACKGROUND, PATTERNED, etc.
        shape.fill.fore_color    # .rgb or .theme_color
        shape.line.width         # Border width in EMU
        shape.line.color         # .rgb or .theme_color
        shape.rotation           # Degrees
```

### Theme Color Resolution

PPTX shapes reference colors by theme slot names. You MUST resolve these to hex values using the theme XML. The mapping for each template is in `theme-manifest.json` under `colors`, but here is how to read it from XML:

```
Theme slot    → OOXML scheme name    → Resolved hex (example: IU Group Green)
dk1 / tx1     → srgbClr              → #1D1D1F  (black — dark backgrounds)
lt1 / bg1     → srgbClr              → #FFFFFF  (white — light backgrounds)
dk2 / tx2     → srgbClr              → #0BF000  (brand green)
lt2 / bg2     → srgbClr              → #C2C2C8  (medium gray)
accent1       → srgbClr              → #E0E0E3  (light gray)
accent2       → srgbClr              → #55FF4D  (light green)
accent3       → srgbClr              → #575E62  (dark gray)
accent4-6     → srgbClr              → varies
```

python-pptx reports theme colors as enum values like `BACKGROUND_1 (14)`, `ACCENT_1 (5)`, etc. The mapping is:

| python-pptx enum | Theme slot | Typical resolved color |
|------------------|------------|----------------------|
| `BACKGROUND_1 (14)` | lt1 | White (#FFFFFF) |
| `BACKGROUND_2 (16)` | lt2 | Light gray (#C2C2C8) |
| `TEXT_1 / DARK_1` | dk1 | Black (#1D1D1F) |
| `TEXT_2 / DARK_2` | dk2 | Brand color (#0BF000) |
| `ACCENT_1 (5)` | accent1 | Accent (#E0E0E3) |

Layout backgrounds use scheme names: `scheme:tx1` → dk1 → black, `scheme:bg1` → lt1 → white, `scheme:accent1` → accent1 → light gray.

### Mapping PPTX Shapes to CSS

Every PPTX shape maps to a CSS technique:

#### Filled rectangles (decorative)
Use `::before` or `::after` pseudo-elements:
```css
.layout-name::before {
  content: '';
  position: absolute;
  left: 24.7%;     /* shape.left / slide_width * 100 */
  top: 25.5%;      /* shape.top / slide_height * 100 */
  width: 80.6%;    /* shape.width / slide_width * 100 */
  height: 88.4%;   /* shape.height / slide_height * 100 */
  border: 11pt solid #FFFFFF;  /* from shape.line */
  background: transparent;
  transform: rotate(-4deg);    /* from shape.rotation */
  pointer-events: none;
}
```

#### Lines (vertical/horizontal accents)
Thin pseudo-elements:
```css
.layout-name::after {
  content: '';
  position: absolute;
  left: 21.5%;
  top: 11.5%;
  width: 6pt;       /* line width */
  height: 89%;
  background: #0BF000;  /* line color */
  transform: rotate(-4deg);
}
```

#### Triangles
Use `clip-path`:
```css
.decorative-triangle {
  clip-path: polygon(100% 0, 0% 100%, 100% 100%);
  background: #E0E0E3;
}
```

#### Colored title bars (filled text containers)
Style the text element directly:
```css
.layout-name h1 {
  background: #E0E0E3;
  padding: 0.3em 0.8em;
  display: inline-block;
}
```

#### Large decorative numbers ("01", "02")
Absolutely positioned styled spans:
```css
.chapter-number {
  position: absolute;
  left: 0.8%;
  top: -1.6%;
  font-size: 96pt;
  font-weight: 700;
  color: #0BF000;
  line-height: 1;
}
```

#### Freeform paths (rare)
Use inline SVG in the Vue template when CSS cannot reproduce the shape.

### Slidev Layout Structure

Each layout is a Vue SFC in `layouts/`. Key rules:

1. **Default `<slot />`** renders whatever markdown follows the frontmatter. `# Title` becomes `<h1>` inside the default slot.
2. **Named slots** use `::slotname::` syntax in slides.md. Use for columns: `<slot name="col1" />`, `<slot name="col2" />`.
3. **The layout `<div>` must be `position: relative`** so decorative pseudo-elements position correctly.
4. **Use CSS variables** from `style.css` for all colors — never hardcode hex values in layouts.

Example layout template:
```vue
<template>
  <div class="slidev-layout cover">
    <!-- Decorative shapes are CSS pseudo-elements (::before, ::after) -->
    <div class="content-area">
      <slot />
    </div>
  </div>
</template>

<style scoped>
.cover {
  position: relative;
  overflow: hidden;
  background: var(--iu-black);
  height: 100%;
  padding: 0;
}

/* Tilted rectangle with white border */
.cover::before {
  content: '';
  position: absolute;
  left: 24.7%;
  top: 25.5%;
  width: 80.6%;
  height: 88.4%;
  border: 11pt solid var(--iu-white);
  transform: rotate(-4deg);
  pointer-events: none;
}

.content-area {
  position: relative;
  z-index: 1;  /* Above pseudo-elements */
  padding: 2rem 3rem;
}
</style>
```

### Logo Handling

Logos are extracted as PNG and SVG from the PPTX `ppt/media/` directory. The slide master references them via relationship IDs in `ppt/slideMasters/_rels/slideMaster1.xml.rels`.

Two variants are typical:
- **Dark logo** (black on transparent) — for white backgrounds
- **Light logo** (white on transparent) — for dark backgrounds

Both go into `public/assets/`. The logo appears on every slide via `global-bottom.vue`:

```vue
<template>
  <div class="iu-global-bottom">
    <img
      :src="logoSrc"
      alt="Logo"
      class="iu-logo"
      @error="logoError = true"
      v-show="!logoError"
    />
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useSlideContext } from '@slidev/client'

const logoError = ref(false)
const { $slidev } = useSlideContext()

// Switch logo variant based on layout background
const darkLayouts = ['cover', 'section', 'section-gray', 'end', 'fact', 'fact-green']
const logoSrc = computed(() => {
  const layout = $slidev?.nav?.currentLayout || ''
  return darkLayouts.includes(layout)
    ? '/assets/logo-white.png'
    : '/assets/logo-dark.png'
})
</script>

<style scoped>
.iu-global-bottom {
  position: absolute;
  top: 0;
  right: 0;
  width: 17.8%;    /* 2.37in / 13.33in */
  padding: 0;
}
.iu-logo {
  width: 100%;
  height: auto;
}
</style>
```

If an SVG version exists (check `ppt/media/` for `.svg` files), prefer it over PNG for crisp scaling.

### Font Scheme

The theme font scheme defines two families:
- **Major font** (headings): from `<a:majorFont><a:latin typeface="..."/>`
- **Minor font** (body): from `<a:minorFont><a:latin typeface="..."/>`

After running `extract-fonts.py`, the fonts are bundled offline in `public/fonts/` and loaded via `_fonts.css` → `style.css`. No Google Fonts CDN dependency.

For fonts NOT available on Google Fonts:
1. Check if the font is available elsewhere (e.g., Adobe Fonts, font foundry websites)
2. Ask the user to provide `.woff2` files
3. Place them in `public/fonts/` and add `@font-face` declarations to `_fonts.css`

## Step 4: Validate

```bash
python scripts/validate-theme.py \
  --pptx <path-to-pptx> \
  --theme <theme-output-dir> \
  --output <validation-output-dir> \
  [--ssim-threshold 0.85] \
  [--position-threshold 2.0]
```

The validation pipeline:

1. **Renders PPTX slides as reference PNGs** via LibreOffice headless → PDF → pdftoppm (300 DPI)
2. **Renders Slidev slides as test PNGs** via `npx slidev export --format png`
3. **Structural comparison** — Extracts ALL shapes (not just placeholders) from each PPTX layout including decorative rectangles, lines, triangles. Compares positions against CSS in Vue files. Flags elements off by more than the threshold.
4. **Pixel comparison** — SSIM score and pixel-diff images (saved to `diffs/`)
5. **Report** — `validation-report.json` with per-layout scores and overall pass/fail

Interpretation:
- SSIM > 0.90: excellent match
- SSIM 0.80–0.90: acceptable, check diffs for specifics
- SSIM < 0.80: significant layout issues, inspect diff images
- Position delta > 2%: element is visibly misplaced

**Important caveat**: Font rendering differs between LibreOffice and the browser. Expect some noise around text edges. Focus on structural elements (backgrounds, borders, colored bars, shape positions) for pass/fail decisions.

## Output Structure

```
slidev-theme-<name>/
├── package.json              # npm metadata + slidev config
├── style.css                 # CSS custom properties + @import _fonts.css
├── _fonts.css                # @font-face declarations (offline)
├── uno.config.ts             # UnoCSS theme integration
├── layouts/
│   ├── cover.vue             # Title slides (dark bg, tilted border rect)
│   ├── default.vue           # Basic Text 1 column (white bg)
│   ├── two-cols.vue          # Basic Text 2 columns
│   ├── three-cols.vue        # Basic Text 3 columns
│   ├── section.vue           # Chapter entry (gray bg, large number)
│   ├── section-gray.vue      # Chapter entry gray variant
│   ├── section-overview.vue  # Chapter entry with agenda
│   ├── image-right.vue       # Text + image right
│   ├── image-left.vue        # Text + image left
│   ├── side-note.vue         # Marginal column
│   ├── accent.vue            # Farbe Text (colored title bar)
│   ├── fact.vue              # Headline/Facts (5 numbered columns)
│   ├── quote.vue             # Zitat (green vertical line)
│   ├── end.vue               # Danke (green title bar, contacts)
│   └── ...                   # Additional layouts
├── components/
│   └── CompanyLogo.vue       # Reusable logo component
├── global-bottom.vue         # Persistent logo on every slide
├── public/
│   ├── assets/               # Extracted logos, backgrounds
│   └── fonts/                # Offline .woff2 font files
├── theme-manifest.json       # Full extraction metadata (JSON)
└── example.md                # Demo slides showcasing all layouts
```

## Layout Name Mapping

The script maps PPTX layout names to Slidev-friendly slugs:

| PPTX Layout Name | Slidev Layout | Background |
|-------------------|---------------|------------|
| 1_Titel Schwarz / Titel Schwarz \| groß/mittel/klein | `cover` | Black (dk1) |
| Kapiteleinstieg Primärfarbe | `section` | Light gray (accent1) |
| Kapiteleinstieg Grau | `section-gray` | Black (dk1) |
| Kapiteleinstieg mit Übersicht | `section-overview` | Light gray (accent1) |
| Basic Text \| 1 Spalte | `default` | White (bg1) |
| Basic Text \| 2 Spalten | `two-cols` | White (bg1) |
| Basic Text \| 3 Spalten | `three-cols` | White (bg1) |
| Basic Text \| 1 Bild rechts | `image-right` | White (bg1) |
| Basic Text \| 1 Bild links | `image-left` | White (bg1) |
| Basic Text \| Marginalspalte | `side-note` | White (bg1) |
| Farbe Text \| * | `accent` / `accent-*` | White (bg1) |
| Headline 2z \| Facts Schwarz | `fact` | Black (dk1) |
| Headline 2z \| Facts Schwarz-Grün | `fact-green` | Black (dk1) + green fill |
| Zitat | `quote` | White (bg1) |
| Zitat auf Farbe | `quote-accent` | Light gray (accent1) |
| Danke | `end` | Black (dk1) |

## Limitations

- **Freeform vector paths** (`<a:custGeom>`) cannot be replicated in pure CSS. Use inline SVG in the Vue template for these (rare — typically only 1-2 layouts).
- **MTX-compressed EOT fonts** (Microsoft's proprietary compression) cannot be deobfuscated. The script falls back to Google Fonts download.
- **Font rendering differences** between LibreOffice and browsers will always produce some pixel-level noise in validation. This is expected.
- **Complex animations/transitions** in PPTX are not extracted. Use Slidev's built-in transition system instead.
- **Chart objects** embedded in PPTX slides are not converted. Recreate charts using Mermaid, Chart.js, or similar.

## User Interaction

1. Ask which .pptx file to use as the source template
2. Run `extract-pptx-theme.py` to scaffold the theme
3. Run `extract-fonts.py` to bundle fonts offline
4. Show the user the extracted color palette, font names, layout count, and logo previews
5. Refine layouts using the shape extraction data (this is the main manual effort)
6. Run `validate-theme.py` to check pixel accuracy
7. Iterate on layouts until validation passes
8. Offer to preview with `cd <theme-dir> && npx slidev example.md`
