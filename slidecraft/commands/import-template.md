---
description: Import a PowerPoint (.pptx) template and convert it into a Slidev theme + demo deck
argument-hint: <path-to-pptx>
---

# Import Template

Convert a corporate PowerPoint template into a Slidev theme plus a demo deck
that exercises every layout, so the user can preview the conversion in the
browser.

## Steps

1. **Locate the PPTX file**: If the user provided a path as an argument, use it. Otherwise ask which .pptx file to convert.

2. **Choose output base directory**: Ask the user where to save the conversion output. Suggest `~/slidev-themes/<company-name>/` as a default. Two sub-directories will be created inside it:
   - `slidev-theme-<name>/` — the importable Slidev theme (layouts, assets, package.json)
   - `deck/` — a demo deck (`slides.md` + `package.json`) that consumes the theme via a `file:` dependency, so the user can preview every layout immediately.

3. **Choose theme name**: Ask the user for a short slug (e.g., "iu", "corporate", "brand"). It becomes the npm package name `slidev-theme-<name>` and lands in the deck's `theme:` frontmatter.

4. **Install Python dependencies** (if not already present):
   ```bash
   pip install python-pptx lxml Pillow --break-system-packages -q
   ```

5. **Run the conversion**: Invoke the importer's `convert()` entry point directly. It parses the .pptx, extracts and deduplicates picture assets (with crop/duotone derivatives), writes per-slide `.vue` layouts, generates the theme `package.json`, and emits the demo `slides.md`:

   ```bash
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

   The call returns a `ConvertResult` dataclass with `slides_count`, `typefaces_total`, `typefaces_substituted`, `sans_families`, `alias_font_faces`, and `warnings`.

   Note: this command currently has no CLI shim — it calls the Python API directly. A `python -m slidecraft.importer` entry point may be added later; until then, prefer the `python -c` invocation above.

6. **Install deck npm dependencies**: The theme itself declares no npm deps (Slidev provides UnoCSS transitively via `@slidev/cli`), so the install must happen in the **deck** directory, not the theme:

   ```bash
   cd "<output-base>/deck"
   npm install
   ```

   This pulls in `@slidev/cli` and links the local theme via the `file:../slidev-theme-<name>` dependency that the deck's `package.json` declares.

7. **Review results**: Report what landed on disk and what `ConvertResult` returned:
   - `slides_count` — number of layouts emitted as `<theme-dir>/layouts/slide<N>.vue` (one per slide in the source PPTX)
   - `sans_families` — fonts the theme references via Google Fonts (or local @font-face if substituted)
   - `typefaces_substituted` — count of MS-proprietary fonts (Calibri, Cambria, …) auto-remapped to open-source metric-compatible families (Carlito, Caladea, …)
   - `alias_font_faces` — count of weight-suffix aliases (e.g. "Source Sans Pro Bold" → ("Source Sans Pro", 700))
   - Extracted assets — list `<theme-dir>/assets/` (SHA1-deduplicated images plus any crop/duotone derivatives)
   - `warnings` — any per-picture or per-slide warnings (unsupported color spaces, missing media references, derivative failures)

8. **Slot naming hint**: When the user wants to override placeholder content in the deck's `slides.md`, the slot names follow the semantic OOXML type — not numeric indices. Show a quick example so they know what to type:
   ```markdown
   ::title::
   My custom title

   ::body-19::
   My custom body text

   ::picture-22::
   ![](/my-photo.jpg)
   ```
   Singletons (`title`, `footer`, `date`, `slide-number`, `subtitle`) emit a bare name; repeatable types use `{type}-{ooxml-idx}` so names stay stable across re-imports. See `slidecraft/importer/emit/naming.py` for the full mapping.

9. **Offer next steps**:
   - Preview the deck in the browser: `cd <output-base>/deck && npx slidev` (defaults to `slides.md` — no need to name it explicitly)
   - If corporate fonts aren't on Google Fonts, explain how to add .woff2 files under `<theme-dir>/styles/` and add `@font-face` declarations
   - Suggest creating a fresh presentation that consumes this theme via `/slidecraft:start`
