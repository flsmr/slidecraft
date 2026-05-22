---
description: Import a PowerPoint (.pptx) template and convert it into a Slidev theme
argument-hint: <path-to-pptx>
---

# Import Template

Convert a corporate PowerPoint template into a Slidev theme.

## Steps

1. **Locate the PPTX file**: If the user provided a path as an argument, use it. Otherwise ask which .pptx file to convert.

2. **Choose output location**: Ask the user where to save the generated Slidev theme. Suggest `~/slidev-themes/<company-name>/` as a default.

3. **Choose theme name**: Ask the user for a short name (e.g., "iu", "corporate", "brand"). This becomes part of the theme directory name: `slidev-theme-<name>`.

4. **Install dependencies** (if not already present):
   ```bash
   pip install python-pptx lxml Pillow --break-system-packages -q
   ```

5. **Locate the extraction script**: The script lives inside this plugin's directory. Find it by resolving the path relative to this command file:
   ```
   <this-plugin-dir>/scripts/extract-pptx-theme.py
   ```
   where `<this-plugin-dir>` is the parent of the `commands/` directory containing this file.

6. **Run extraction**: Execute the extraction script:
   ```bash
   python <this-plugin-dir>/scripts/extract-pptx-theme.py \
     --input "<pptx-path>" \
     --output "<output-dir>/slidev-theme-<name>" \
     --name "<name>"
   ```

7. **Install theme dependencies**: After extraction, install the theme's npm dependencies:
   ```bash
   cd "<output-dir>/slidev-theme-<name>"
   npm install
   ```
   This ensures `unocss` and other required packages are available when Slidev loads the theme.

8. **Review results**: Read the generated `theme-manifest.json` and show the user:
   - Color palette (list the 12 theme colors with hex values)
   - Fonts detected (heading + body)
   - Number of layouts generated (and which Slidev names they mapped to)
   - Logos/images found and extracted
   - Any warnings (missing fonts, gradient fills, etc.)

9. **Offer next steps**:
   - Preview the theme: `cd <output-dir>/slidev-theme-<name> && npx slidev example.md`
   - If corporate fonts aren't on Google Fonts, explain how to add .woff2 files
   - Suggest creating a new presentation with this theme using `/slidecraft:start`
