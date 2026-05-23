# Architecture: PPTX → Slidev (importer rewrite)

> Working document for the `feat/importer-rewrite` branch. Not intended to be committed long-term — captures the design we're aligning on before code is written.

## Scope of v1 (this layer)

One layer at a time. v1 = **text-content placeholders only**:
- Placeholders (`<p:ph>` shapes) declared on slide masters / slideLayouts and used by slides.
- Text-bearing placeholder types only: `title`, `ctrTitle`, `body`, `subTitle`, `dt`, `ftr`, `sldNum`, and untyped placeholders that contain a `<p:txBody>`.

**Out of scope for v1** (will be added as later layers):
- Pictures (`<p:pic>` and picture-type placeholders)
- Tables, charts, group shapes, freeform/connectors
- Non-placeholder text boxes (on-slide content not tied to a master placeholder)
- Animations, transitions, speaker notes
- Layout deduplication (multiple PPT slides sharing one Slidev layout)

## User-facing entry point

```python
importer.convert(
    pptx_path: Path,         # source PowerPoint template
    theme_dir: Path,         # output Slidev theme folder
    deck_dir: Path,          # output Slidev deck folder
)
```

Test paths (per user instruction; not committed):
- `theme_dir = D:\Archive\03_Freizeit\Projects\slidecraft-themes\slidecraft-tmp-theme`
- `deck_dir  = D:\Archive\03_Freizeit\Projects\slidecraft-slide-decks\slidecraft-tmp-deck`

## Output layout

### Theme folder
```
slidecraft-tmp-theme/
  package.json          # Slidev theme manifest (includes `slidev` block, `engines.slidev`, `keywords`)
  layouts/
    slide1.vue
    slide2.vue
    …
    slideN.vue
  styles/
    index.css           # auto-injected by Slidev; contains @font-face declarations + global tokens
  public/
    fonts/              # bundled font binaries (Slidev serves public/ at /)
      *.woff2 / *.ttf / *.otf
      manifest.json     # per-typeface provenance (used by verifier)
```

`theme/package.json` shape:
```json
{
  "name": "slidev-theme-slidecraft-tmp",
  "version": "0.0.1",
  "keywords": ["slidev-theme", "slidev"],
  "engines": { "slidev": ">=0.48.0" },
  "slidev": {
    "colorSchema": "light",
    "defaults": {
      "canvasWidth": 1920,                // confirmed honored in Slidev 52.15.2
      "aspectRatio": "16/9",
      "fonts": { "provider": "none" }     // disable Slidev's Google Fonts auto-import; we ship our own
    }
  }
}
```
- `fonts.provider: "none"` is required so Slidev doesn't inject Google Fonts CDN links over our bundled `@font-face` declarations.
- `canvasWidth` placement confirmed by spike; see *Coordinate system* below.

### Deck folder
```
slidecraft-tmp-deck/
  package.json          # references the theme
  slides.md             # one entry per PPT slide
```

## Pipeline

### Stage 0 — Parse PPTX
- Load with `python-pptx`. Drop down to raw XML (`lxml`) when properties python-pptx doesn't surface are needed (alpha, gradient stops, body-frame insets, paragraph spacing, etc.).
- Read `<p:sldSz cx cy/>` → native slide dimensions in EMU → convert to px. Typical 16:9 = 1920×1080.

### Stage 1 — Fonts

Recover the prior `extract-fonts.py` from dropped commit `92a0243` (`git show 92a0243:slidecraft/scripts/extract-fonts.py`) as a starting point. Place under `slidecraft/importer/fonts.py`; review and prune anything tied to the old approach.

**Resolution pipeline (per typeface referenced in the PPTX, in order — first match wins):**

1. **Embedded.** Pull the font from the .pptx itself. PPT stores embedded fonts as obfuscated TTF/OTF (`application/vnd.ms-office.activeX` style obfuscation on the first 32 bytes); deobfuscate before writing.
2. **Google Fonts — exact name lookup.** Hit the public CSS endpoint `https://fonts.googleapis.com/css2?family=<Name>` with a real browser UA. If we get a CSS body back, parse `src: url(…woff2)` and download. No API key.
3. **Metric-compatible substitute table.** Hardcoded mapping in `fonts.py` for MS proprietary fonts not on Google Fonts. Substitute fonts are bundled with the importer (in `slidecraft/importer/data/substitutes/`) and copied to `theme/fonts/` on demand.
   - Calibri → Carlito
   - Cambria → Caladea
   - Times New Roman → Tinos
   - Arial → Arimo
   - Courier New → Cousine
   - Consolas → Inconsolata
   - Verdana → DejaVu Sans
   - (extensible; ~10–12 entries cover the common cases)
4. **Generic CSS family** (`sans-serif` / `serif` / `monospace`) — chosen from the PPT's `<a:fontScheme>` classification. Final fallback only.

**Output:**
- `theme/public/fonts/*.{woff2,ttf,otf}` — all font binaries (embedded + Google + substitutes). Slidev serves `public/` at site root, so the URL in `@font-face src` is `/fonts/<file>`.
- `theme/styles/index.css` — Slidev auto-injects this. Contains one `@font-face` block per file, keyed by the **PPT typeface name** verbatim and using explicit `font-weight` / `font-style`. Example:
  ```css
  @font-face { font-family: "Calibri"; font-weight: 400; font-style: normal; src: url("/fonts/Carlito-Regular.woff2") format("woff2"); }
  @font-face { font-family: "Calibri"; font-weight: 700; font-style: normal; src: url("/fonts/Carlito-Bold.woff2")    format("woff2"); }
  ```
  (Substituted fonts re-declare under the original PPT name — layouts reference `font-family: "Calibri"` regardless of the actual file.)
- `theme/public/fonts/manifest.json` — per-typeface provenance. Drives verifier behavior:
  ```json
  {
    "Calibri":         { "source": "metric-substitute", "substitute": "Carlito",  "fidelity": "high" },
    "MyCustomFont":    { "source": "embedded",          "files": ["…"],           "fidelity": "exact" },
    "Open Sans":       { "source": "google-fonts",      "files": ["…"],           "fidelity": "exact" },
    "UnknownTypeface": { "source": "fallback",          "fallback": "sans-serif", "fidelity": "low" }
  }
  ```

**Layout references** use the verbatim PPT typeface name in quotes, followed by a fallback chain:
```css
font-family: "Calibri Light", "Segoe UI Light", sans-serif;
```

**Verifier coupling:** the per-slide SSIM threshold is relaxed when any placeholder on that slide references a typeface whose manifest entry has `fidelity: low`. `fidelity: high` (metric substitute) does not relax. Manifest entry `fidelity: exact` enforces the strict threshold.

### Stage 2 — Per-slide generation (1:1 mapping)

For each PPT slide N (1-indexed):

1. **Identify in-scope placeholders.** Walk slide → for each `<p:sp>` with `<p:nvSpPr><p:nvPr><p:ph idx="K"/>`, include if it carries text content or its master/layout counterpart does.
2. **Resolve effective properties** by climbing the cascade: slide → slideLayout → slideMaster → theme defaults (`<a:fontScheme>`, `<a:clrScheme>`). Layout-level placeholders are matched to slide-level placeholders by `idx`; master-level by `type`.
3. **Generate `theme/layouts/slide<N>.vue`** — fully resolved positions and styling baked in. One `<div class="ph-<idx>">` per placeholder, each containing `<slot name="ph_<idx>"/>`.
4. **Append slide entry to `deck/slides.md`** with `layout: slide<N>` frontmatter and one `::ph_<idx>::` block per placeholder. Slot content is the placeholder's resolved text with run-level HTML formatting. (`::name::` is Slidev's markdown-friendly sugar for Vue `<template #name>`; both address the layout's `<slot name="…"/>`.)

## Generated layout shape

```vue
<!-- theme/layouts/slide1.vue -->
<template>
  <div class="slide-root">
    <div class="ph-5" style="
      position:absolute; left:120px; top:80px; width:1680px; height:120px;
      transform:rotate(0deg);
      background:transparent;
      opacity:1;
      display:flex; align-items:flex-start;
      padding:0 0 0 0;
      text-align:left;
      color:#000000;
      font-family:'Calibri'; font-size:44px; font-weight:700;
    ">
      <slot name="ph_5" />
    </div>
    <div class="ph-6" style="…">
      <slot name="ph_6" />
    </div>
  </div>
</template>

<style scoped>
.slide-root {
  position: relative;
  width: 1920px;
  height: 1080px;
  background: #FFFFFF;  /* resolved slide background */
  overflow: hidden;
}
</style>
```

## Generated slide entry shape

```md
---
layout: slide1
---

::ph_5::
Welcome to the deck

::ph_6::
This is **bold** body text.

Second paragraph.

- bullet one
- bullet two

::ph_7::
<p style="text-align:center">A centered paragraph with a <span style="color:#f00">red</span> word and an <u>underlined</u> phrase.</p>

---
layout: slide2
---
…
```

Vue-template form (`<template #ph_5>…</template>`) is equivalent and remains a fallback if a slot's content ever needs constructs that confuse the `::name::` parser (rare edge case).

> **Caveat to verify with a quick spike:** I'm confident Slidev's `::name::` notation supports named slots in markdown decks (idiomatic, long-standing). What's worth a 30-second check against the current Slidev version is the tolerance for raw-HTML run formatting *inside* a `::name::` block — specifically multi-line `<p>` with inline styles. If anything is brittle, the Vue-template form is the safer fallback for those slots.

## Text content emission policy

The layout `.vue` carries every placeholder's *resolved default* formatting (font, weight, color, size, alignment, line-spacing, bullet styling, etc.). Slot content in `slides.md` therefore only emits styling when a run or paragraph **deviates** from that baked-in default.

**Per-run rules (walking `<a:r>` inside `<a:p>`):**

| Run deviation from placeholder default rPr | Emission |
|---|---|
| None | Plain text. |
| Subset of {bold, italic, strikethrough} | Markdown markers: `**bold**`, `*italic*`, `~~strike~~`. Combinable (`***bold-italic***`). |
| Underline only | `<u>text</u>`. |
| Any non-markdown property (color, font-size, font-family) — alone or in combination | Single `<span style="…">text</span>` carrying only the deviating properties. |

**Per-paragraph rules (walking `<a:p>`):**

| Paragraph deviation from placeholder default pPr | Emission |
|---|---|
| None | Plain text. Paragraphs separated by blank lines. |
| Bulleted (`buChar` / `buAutoNum`) | Markdown `- text` (unordered) or `1. text` (ordered). Bullet *styling* (glyph, color, font, size, indent per-level) is encoded in the layout's CSS via `::marker`, not the slide. See *Bullet styling* below. |
| Alignment, line-spacing, indent, space-before/after that differs from default | Wrap entire paragraph in `<p style="…">…</p>` carrying only the deviating properties. |

**Nesting rule:** When a paragraph is wrapped in a block-level HTML element (`<p style="…">…</p>`) for paragraph-level reasons, the runs *inside* are emitted as HTML (`<span style="…">`, `<u>`, `<strong>`, `<em>`) — **never** markdown markers. Confirmed by spike against Slidev 52.15.2: this is the CommonMark rule (markdown-it does not process markdown spans inside HTML blocks like `<p>`/`<div>`), not a Slidev quirk.

**Inline HTML in markdown paragraphs is fine.** A markdown paragraph (no `<p>` wrapper) can contain `<span style="…">…</span>`, `<u>`, `<strong>`, `<em>` mid-text and *still* process markdown markers around them. So a paragraph with one colored run can stay mostly markdown:

```md
This is **bold** and <span style="color:#f00">red</span> in the same line.
```

The block-HTML restriction only triggers when the whole paragraph is `<p>`-wrapped.

**Soft line break inside a paragraph** (`<a:br/>`) → `<br/>`. Linebreak characters embedded *inside* `<a:t>` text (`\r\n`, `\n`) are normalised and split into the same `<br/>`-marker runs — PPT 365 sometimes stores multi-line single-runs this way (e.g. the IU thank-you slide's address block).

In practice the typical slot is plain text or markdown with the occasional emphasis. HTML only surfaces where PPT genuinely has properties markdown can't express.

## Bullet styling

PPT bullets live in **three places**, none of which is the theme:

1. **Slide master** (`<p:txStyles>`) — canonical location. Per-level bullets in `<p:titleStyle>` / `<p:bodyStyle>` / `<p:otherStyle>`, each defining `<a:lvl1pPr>`…`<a:lvl9pPr>`.
2. **Slide layout** — per-placeholder overrides via `<a:lstStyle>/<a:lvlNpPr>`.
3. **Slide-level paragraph** — per-paragraph override via `<a:pPr>`.

The theme part (`ppt/theme/theme1.xml`) carries only color/font/format **primitives** — bullets reference into the theme (e.g. `<a:buClr><a:schemeClr val="accent6"/></a:buClr>`) but the bullet definition itself lives in the master.

### Cascade resolution (parse-time)

Per OOXML, bullet styling resolves through the same chain as run/paragraph defaults:

```
theme defaults
└─ master <p:txStyles>{title,body,other}Style/<a:lvlNpPr>      ← per-level bullets
   └─ master placeholder <p:txBody>/<a:lstStyle>/<a:lvlNpPr>
      └─ layout placeholder <p:txBody>/<a:lstStyle>/<a:lvlNpPr>
         └─ slide-level paragraph <a:pPr>                      ← highest
```

`inheritance._extract_ppr` reads five bullet-related elements at each level:

| OOXML | `Paragraph` field |
|---|---|
| `<a:buChar @char>` | `bullet="char"`, `bullet_char="X"` |
| `<a:buAutoNum @type>` | `bullet="auto-num"`, `bullet_autonum_type="arabicPeriod"`/etc. |
| `<a:buNone/>` | `bullet="none"` |
| `<a:buClr>` (wraps `<a:srgbClr>`/`<a:schemeClr>`/`<a:sysClr>`) | `bullet_color: RGB` — scheme references resolve through theme + clrMap, including `<a:tint>` / `<a:shade>` / `<a:lumMod>` etc. modifiers |
| `<a:buFont @typeface>` | `bullet_font: str` — IU master uses `Symbol` (for `-` glyph) and `Arial` (for `▪` glyph) |
| `<a:buSzPct @val>` | `bullet_size_pct: float` — 100 = same size as surrounding text |

### Emission

`emit/layout.py` walks the resolved paragraphs per placeholder and produces one CSS `::marker` rule per `(placeholder, level)` combination. Markdown content in `slides.md` is **unchanged** — author still writes `- item` / `1. item`. The visual bullet comes entirely from the layout's scoped CSS.

For a placeholder whose level-0 default is `<a:buChar char="-"/>` + `<a:buClr><a:schemeClr val="accent6"/>` + `<a:buFont typeface="Symbol"/>` + `<a:buSzPct val="120000"/>`:

```css
.slidev-layout .ph-16 ul > li::marker {
  content: "-\00a0";              /* buChar + non-breaking space */
  color: #AAAEB0;                 /* accent6 resolved */
  font-family: 'Symbol', sans-serif;
  font-size: 120%;
}
```

For numbered lists (`<a:buAutoNum type="arabicPeriod"/>`):

```css
.slidev-layout .ph-3 ol > li {
  list-style-type: decimal;
}
.slidev-layout .ph-3 ol > li::marker {
  color: #1D1D1F;
  font-family: 'Source Sans Pro', sans-serif;
}
```

OOXML `buAutoNum @type` maps to CSS `list-style-type` per a fixed table in `emit/layout.py::_AUTONUM_TO_LIST_STYLE` — covers arabic/alpha/roman with period/paren variants. Exotic forms (`arabicDbPlain`, `circleNumWdBlackPlain`, etc.) fall back to `decimal`.

### Per-level

The cascade resolves `Placeholder.default_para_props` for level 0. Per-paragraph overrides can change any level individually via `<a:pPr lvl="N">`. For each `(placeholder, level)` pair actually USED in the slide, we emit a separate `::marker` rule with the matching CSS selector (`ul > li::marker`, `ul ul > li::marker`, …). Levels 1+ with no per-paragraph override use the placeholder's level-0 defaults — sufficient for the IU template, where all 5 body levels share the same `-` / Symbol / accent6 / 120 % styling.

## Property mapping (PPT → CSS / HTML)

| PPT XML | CSS / HTML | Notes |
|---|---|---|
| `spPr/xfrm/off @x @y` | `left`, `top` | EMU → px |
| `spPr/xfrm/ext @cx @cy` | `width`, `height` | EMU → px |
| `spPr/xfrm @rot` | `transform: rotate(deg)` | rot is 60000ths of a degree |
| `spPr/solidFill` | `background: rgb(…)` |  |
| `spPr/gradFill` | `background: linear-gradient(…)` / `radial-gradient(…)` |  |
| `spPr/noFill` | `background: transparent` |  |
| `solidFill/srgbClr/alpha` | rgba alpha or `opacity` | alpha is per-channel; opacity is element-wide |
| `bodyPr/anchor` (t/ctr/b) | `align-items: flex-start/center/flex-end` | requires `display:flex` on the div |
| `bodyPr/lIns/tIns/rIns/bIns` | `padding: t r b l` | EMU → px; defaults 91440/45720/91440/45720 |
| `bodyPr/rot` | `transform: rotate(deg)` on placeholder div (combine with `spPr/xfrm/@rot` if both present) | rot in 60000ths of a degree, same as shape rotation |
| `bodyPr/normAutofit/@fontScale` | scaled `font-size` | PPT shrinks to fit; bake into resolved size |
| `a:pPr/@algn` | `text-align` |  |
| `a:pPr/@marL` | `padding-left` on `<p>` |  |
| `a:pPr/@indent` | `text-indent` |  |
| `a:pPr/lnSpc` | `line-height` | pct → unitless, points → px |
| `a:pPr/spcBef` `spcAft` | `margin-top` / `margin-bottom` on `<p>` |  |
| `a:pPr/buChar` `buAutoNum` `buNone` | Markdown `- ` / `1. ` / no marker in slides.md; bullet *styling* baked into layout CSS via `::marker` (see *Bullet styling*). |
| `a:pPr/buClr/<srgbClr|schemeClr>` | `::marker { color: … }` — `schemeClr` resolved through theme + clrMap, including `<a:tint>` / `<a:shade>` / `<a:lumMod>` / `<a:lumOff>` / `<a:satMod>` modifiers. |
| `a:pPr/buFont @typeface` | `::marker { font-family: … }` — the IU master uses `Symbol` for `-` bullets, `Arial` for `▪` bullets. |
| `a:pPr/buSzPct @val` | `::marker { font-size: P% }` — relative to surrounding text size. PPT stores `120000` = 120 %. |
| `a:r/rPr @b` | `font-weight: 700` |  |
| `a:r/rPr @i` | `font-style: italic` |  |
| `a:r/rPr @u` | `text-decoration: underline` |  |
| `a:r/rPr @sz` | `font-size` | sz/100 → pt → px |
| `a:r/rPr/solidFill` | `color` |  |
| `a:r/rPr/latin @typeface` | `font-family` | name must match what fonts.css declares |

## Inheritance resolution

Resolved at generation time. No CSS inheritance to mimic at runtime — layouts are self-contained.

Cascade (highest to lowest priority):
1. Slide `<p:sp>` with matching `<p:ph idx>`
2. SlideLayout `<p:ph idx>` (matched by idx)
3. SlideMaster `<p:ph type>` (matched by type, then by idx)
4. `<p:txStyles>` on master (titleStyle / bodyStyle / otherStyle) for default paragraph + run properties at each list level
5. Theme `<a:fontScheme>` / `<a:clrScheme>` defaults

The fully-resolved value goes into the layout `.vue`. The slide entry only carries:
- Text content (paragraph + run structure)
- Run-level formatting **that differs** from the placeholder's default `rPr`
- Paragraph-level formatting **that differs** from the placeholder's default `pPr`

In both cases, "differs from" is computed against the resolved cascade, so a property set identically on slide and layout produces no emission. See *Text content emission policy* above for the markdown-first / HTML-on-deviation rules.

## Slot naming

v1: `ph_<idx>` (numeric, stable for debugging).

Future iteration may add type-based aliases (`title`, `body`, etc.) — but PPT `type` is not unique within a slide, and Slidev doesn't natively alias slots, so we don't pursue this for v1.

## Coordinate system

- Slidev canvas configured to PPT's native dimensions (e.g. 1920×1080 for 16:9 — read from `<p:sldSz>`).
- All positions/sizes in absolute px relative to the canvas root.
- Slidev's built-in canvas scaling handles viewport resizes.
- **Canvas size lives in `theme/package.json` under `slidev.defaults.canvasWidth`.** Confirmed empirically against Slidev 52.15.2: the parser's config merge order is `defaultConfig → themeMeta.defaults → headmatter.config → headmatter`, so theme-level `canvasWidth` is honored, with per-deck frontmatter overriding when explicitly set. Generated decks emit no `canvasWidth` in frontmatter; the theme handles it.

## Layout CSS scoping

Slidev's docs recommend wrapping layout CSS selectors under `.slidev-layout` so theme styles don't leak into presenter mode and other UI surfaces. All generated `<style scoped>` blocks in `layout<N>.vue` files should keep their selectors inside `.slidev-layout`, e.g.:

```css
.slidev-layout .slide-root { width: 1920px; height: 1080px; … }
.slidev-layout .ph-5 { … }
```

## Slide background

Each PPT slide's background is resolved by climbing slide → slideLayout → slideMaster (`<p:bg>` or `<p:bgRef>` against `<a:clrMap>`), then baked into `.slide-root` in that slide's generated `layout<N>.vue`. v1 supports solid colors and simple gradients. Picture backgrounds deferred to the picture layer.

## Text autofit

PPT's `<a:normAutofit fontScale="…" lnSpcReduction="…"/>` shrinks placeholder text to fit. We read `fontScale` (and `lnSpcReduction` when present) at generation time and bake the scaled values into the resolved `font-size` / `line-height` in the layout `.vue`. No runtime autofit primitive in Slidev — this is the simplest deterministic mapping for v1.

## Verification (layer 1)

Per-slide visual diff:
1. Render PPTX slide N → PNG via PowerPoint COM on Windows (preferred), LibreOffice headless (`soffice --headless --convert-to png`) as fallback on non-Windows or when PowerPoint isn't available.
2. Render Slidev slide N → PNG via `slidev export --format png`.
3. SSIM compare.
4. Threshold:
   - **Strict: 0.98** — applied by default.
   - **Relaxed: 0.90** — applied to slides where any placeholder references a typeface with `fidelity: low` in `theme/fonts/manifest.json`. Typefaces marked `exact` or `high` use the strict threshold.
5. Returns per-slide pass/fail + paths to source PNG, generated PNG, and diff PNG.

Per-placeholder verify deferred — available as a debugging tool when a slide diff is too noisy to localize. Not a v1 deliverable.

## Module layout

```
slidecraft/importer/
  __init__.py
  convert.py            # convert(pptx_path, theme_dir, deck_dir) entry point
  parse.py              # PPTX → internal resolved-slide model
  inheritance.py        # property cascade resolver
  emit/
    __init__.py
    theme.py            # theme package.json + scaffolding (canvasWidth, aspectRatio, fonts.css link)
    layout.py           # resolved model → slide<N>.vue
    slide.py            # resolved model → slides.md entry
  fonts/
    __init__.py
    extract.py          # embedded font extraction + deobfuscation
    google.py           # Google Fonts CSS endpoint lookup
    substitute.py       # metric-substitute table + hardcoded mapping
    manifest.py         # theme/fonts/manifest.json writer
    data/
      substitutes/      # bundled substitute font files (Carlito, Caladea, Tinos, Arimo, Cousine, Inconsolata, …)
  verify/
    __init__.py
    main.py             # per-slide SSIM diff entry point
    pptx_render.py      # PowerPoint COM / LibreOffice
    slidev_render.py    # `slidev export --format png` wrapper
    image_diff.py       # SSIM + pixel diff
  requirements.txt
```

File names are final-ish; minor renames OK once code starts.

## Layer 3 — Non-placeholder shapes (designed + implemented)

Designed in parallel with Layer 2 (pictures). Implemented in its own subpackage; minimal touch on Layer 1 files. Originally scoped to text-bearing shapes only; **expanded** to cover all visible non-placeholder shapes (decorative rectangles, custom-geometry freeforms, preset polygons) — the model class name `TextShape` is a historical artifact.

### Scope

**In:** `<p:sp>` elements **without** a `<p:ph>` that are visible — meaning any of:
- carry a `<p:txBody>` with non-whitespace text content, OR
- carry a visible `<a:solidFill>` / `<a:gradFill>` background, OR
- carry a non-empty `<a:ln>` stroke (border).

Located at any cascade level — master, slideLayout, or slide.

Includes the shape's "box chrome":
- `<a:solidFill>` → CSS `background` (or SVG `fill`)
- `<a:ln>` (stroke) → CSS `border` (or SVG `stroke` + `stroke-width`)
- Rotation (`<a:xfrm @rot>`) → CSS `transform: rotate(...)`
- `<a:bodyPr>` insets / anchor / autofit — same handling as Layer 1 placeholders
- `<a:prstGeom>` presets (rect, triangle, rtTriangle, parallelogram, trapezoid, diamond, pentagon, hexagon, star5, line) → inline `<svg>` with the corresponding `<path>` from `pictures.geometry.preset_to_svg_path`. Plain `prst="rect"` with no adjusts takes a fast CSS-div path.
- `<a:custGeom>` freeform paths → inline `<svg>` with `<path d="...">` from `pictures.geometry.cust_geom_to_svg_path`.

**Out (deferred to future layers):**
- Pictures, including `<p:pic>` on master/layout (Layer 2)
- `<p:grpSp>` group shapes
- `<p:cxnSp>` connectors
- `ellipse` / `roundRect` presets (current implementation renders these via CSS border-radius; the SVG path branch in `preset_to_svg_path` deliberately returns `None` for them — caller should fall back to CSS chrome with `border-radius`)
- Gradient fills on SVG paths render only the first stop's color (inline `<defs><linearGradient>` generation deferred)
- Shadow/glow/reflection effects (none present in the reference IU template)
- `<a:arcTo>` commands inside custGeom paths (skipped — see `cust_geom_to_svg_path` docstring)

**Filters — shape skipped if any are true:**
- Has a `<p:ph>` (placeholder — Layer 1's territory).
- Bounding box has `cx=0` or `cy=0` (catches the IU master's 3 zero-size text-box artifacts).
- Fails the visibility check: no text AND no visible fill AND no border.

### Walk order (per slide)

A slide's full visual stack of non-placeholder text shapes is collected in this order:

1. **Master** non-placeholder text shapes, in PPT `<p:spTree>` document order — **skipped entirely** if the slideLayout has `showMasterSp="0"` OR the slide has `showMasterSp="0"` (OOXML-spec behavior; the IU template uses this on 17/45 layouts).
2. **SlideLayout** non-placeholder text shapes, in PPT document order.
3. **Slide** non-placeholder text shapes, in PPT document order.

**Emission z-order (current):** layout/master-source text shapes are emitted FIRST (background decoration), then placeholders, then pictures, then slide-source text shapes (foreground content). This matches PPT semantics where the layout/master spTree renders below the slide spTree. Within each segment, `order_index` preserves PPT document order. Field is named `order_index` to match `Picture.order_index` in `model.py`.

> Note: a fully unified single-list z-order across placeholders, pictures, and text shapes (sorted purely by `order_index`) would require placeholders to also carry `order_index`. The current split is sufficient for the IU template and matches PPT's actual rendering pipeline.

### Property cascade

Reuse `inheritance.resolve_placeholder()` unchanged. For a non-placeholder text shape:

```python
resolve_placeholder(
    slide_sp=the_shape_sp,   # the <p:sp> being emitted (at whichever level)
    layout_ph=None,          # no cascade partner for non-placeholder shapes
    master_ph=None,
    master_tx_styles=master.txStyles,
    theme_el=theme,
    ph_type=None,            # falls through to <a:otherStyle> at line 353 of inheritance.py
    level=paragraph_level,
    clr_map=master.clrMap,
)
```

This is the OOXML-spec-correct cascade for non-placeholder shapes: theme defaults → master `<a:otherStyle>` → shape's own `<p:txBody>` (lstStyle / first-pPr / first-rPr / endParaRPr). `inheritance.py` requires no changes — only a new call site.

### Emission split

Slide-level text is treated as user content (editable in `slides.md`). Layout/master text is treated as template decoration (baked into `slide<N>.vue`).

| Source level | Slot in `slides.md`? | Text content lives in |
|---|---|---|
| Slide (`<p:sp>` on the slide itself) | YES — `::txt_<id>::` block | `slides.md` |
| SlideLayout / Master | NO — text baked into template | `theme/layouts/slide<N>.vue` |

**Slot name:** `txt_<cNvPr.id>` where `id` is `<p:cNvPr id="N"/>` on the shape. OOXML guarantees uniqueness within a slide; the `txt_` prefix is disjoint from `ph_`.

### Layout `.vue` emission shape

Per text shape (placeholder-host analog, but resolved styling AND chrome carry through):

```vue
<div class="txt-<id>" style="
  position:absolute; left:Xpx; top:Ypx; width:Wpx; height:Hpx;
  transform:rotate(Rdeg);
  background:<solidFill or transparent>;
  border:<ln-width> solid <ln-color>;     /* only if <a:ln> is set */
  opacity:O;
  display:flex; align-items:<flex-start|center|flex-end>;
  padding:<t r b l>;                       /* bodyPr insets */
  text-align:<left|center|right>;
  color:<rgb>; font-family:'…'; font-size:Npx; font-weight:N;
  overflow:hidden;                          /* PPT clip behavior */
">
  <!-- slide-level shape: -->
  <slot name="txt_<id>" />
  <!-- layout/master shape: -->
  <p>baked text content rendered as HTML, same Run/Paragraph helper as placeholder defaults</p>
</div>
```

Same text emission policy (markdown vs HTML on deviation, per the Layer 1 *Text content emission policy* table) applies inside slot content in `slides.md`, since the inner model is the same `Run` / `Paragraph`.

### Model additions

New file `slidecraft/importer/shapes/model.py`:

```python
@dataclass
class BorderProps:
    width_pt: float                                # `<a:ln w>` is EMU → pt (matches Run.font_size_pt)
    color: RGB
    style: Literal["solid", "dashed", "dotted"] = "solid"   # v1 emits only "solid"

@dataclass
class TextShape:
    source: Literal["slide", "layout", "master"]   # decides slot vs baked emission
    shape_id: int                                  # PPT cNvPr id (used for `txt_<id>` slot, `.txt-<id>` class)
    name: str                                      # PPT cNvPr name — debug only
    x_px: float; y_px: float; width_px: float; height_px: float
    rotation_deg: float
    fill: Fill                                     # SolidFill / LinearGradientFill / NoFill — same union as Placeholder.fill
    border: Optional[BorderProps]                  # None if no <a:ln>
    opacity: float
    text_frame: Optional[TextFrame]                # bodyPr + paragraphs (reuses Layer 1's TextFrame)
    default_run: Run                               # cascade-resolved defaults (theme → otherStyle → shape txBody)
    default_para: Paragraph
    order_index: int                               # for z-order merge with placeholders + pictures
```

Existing `model.Slide` gets:
```python
text_shapes: list[TextShape] = field(default_factory=list)   # parallels `pictures: list[Picture]`
```

Existing `model.Placeholder` gets:
```python
order_index: int = 0                                          # for sort with text_shapes + pictures
```

Defaults make both additions backward-compatible with Layer 1 code paths that don't yet populate them.

### Module layout

```
slidecraft/importer/shapes/
  __init__.py
  model.py       # TextShape, BorderProps dataclasses
  parse.py       # walk_text_shapes(slide_el, layout_el, master_el, theme_el, …)
                 #   → list[TextShape] across all source levels, with showMasterSp suppression
  emit.py        # render_text_shape_host(shape, emit_slot: bool) → str
                 # render_text_shape_slot_content(shape) → markdown body for slides.md
```

**Existing files touched (minimal, to avoid colliding with parallel Layer 1 polish / Layer 2 sessions):**
- `model.py` — add the two fields above. Backward-compatible defaults; no behavior change on its own.
- `parse.py` — after collecting placeholders, call `shapes.parse.walk_text_shapes()`. Assign `order_index` to placeholders as their position in the `<p:spTree>` walk. Populate `slide.text_shapes`.
- `emit/layout.py` — build a merged list of `(order_index, kind, element)` triples across placeholders, pictures, and text shapes; sort; dispatch by `kind`.
- `emit/slide.py` — for each `TextShape` with `source == "slide"`, emit a `::txt_<id>::` block in `slides.md` using the same markdown/HTML deviation policy as Layer 1 placeholder slots.

### Implementation tickets

Each is independently assignable; T1 lands first.

| Ticket | Files | Depends on | Description |
|---|---|---|---|
| **T1 — Model additions** | new: `shapes/model.py` (LANDED); edit: `model.py` (queued behind Layer 1 polish session) | — | Add `TextShape`, `BorderProps` (shipped). Add `text_shapes` to `Slide`. Add `order_index` to `Placeholder`. Backward-compatible. |
| **T2 — Shape parser** | new: `shapes/parse.py` | T1 | `walk_text_shapes(slide_el, layout_el, master_el, theme_el, master_tx_styles, clr_map) -> list[TextShape]`. Honors `showMasterSp` on layout and slide. Reuses `inheritance.resolve_placeholder()` with `ph_type=None`. Unit-testable from raw XML strings. |
| **T3 — Shape emitter** | new: `shapes/emit.py` | T1 | `render_text_shape_host(shape, emit_slot)` builds the positioned `<div>` with box chrome (background / border / rotation / insets / overflow). Layout/master variant inlines baked text via the same `Run`/`Paragraph → HTML` helper used by placeholder defaults. |
| **T4 — Wiring (layout side)** | edit: `parse.py`, `emit/layout.py` | T1, T2, T3 | Populate `resolved_slide.text_shapes`. In `emit/layout.py`, merge with placeholders by `document_order` and dispatch by type. |
| **T5 — Slide-side emission** | edit: `emit/slide.py` | T1, T2, T3 | For `source == "slide"` shapes, emit `::txt_<id>::` blocks in `slides.md`, diffing against `shape.default_run` / `shape.default_para`. |
| **T6 — Fixture + smoke test** | new test fixtures + test | T1–T5 | Handcrafted PPTX covering: slide-level text box, layout-level decoration text, master-level text, suppressed master, empty-text filter, zero-size filter. |

## Future layers (sketch, not designed)

- **Layer 2:** Pictures — placeholder-typed and `<p:pic>` shapes. Asset extraction → theme/assets/, `<img>` in slots. *(parallel session)*
- **Layer 4:** Tables.
- **Layer 5:** Pure non-placeholder shapes (rects, triangles, lines, custGeom, connectors) — the geometric companion to Layer 3.
- **Layer 6:** Group shapes (`<p:grpSp>`) and freeforms — flatten to absolute coords.
- **Layer 7:** Charts (likely render to image and treat as pictures; full-fidelity chart conversion is a huge undertaking).
- **Layer 8:** Layout deduplication pass — fold equivalent `slideN.vue` files into shared layouts, lift master shapes into `global-bottom.vue`.
