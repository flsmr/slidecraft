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

4. **Run extraction**: Execute the extraction script:
   ```bash
   python <plugin-dir>/scripts/extract-pptx-theme.py \
     --input "<pptx-path>" \
     --output "<output-dir>/slidev-theme-<name>"
   ```

5. **Review results**: Show the user what was extracted:
   - Color palette (list the 12 theme colors)
   - Fonts detected (heading + body)
   - Number of layouts generated
   - Logos/images found
   - Any warnings (missing fonts, gradient fills, etc.)

6. **Offer next steps**:
   - Preview the theme: `cd <output-dir> && npx slidev example.md`
   - If corporate fonts aren't on Google Fonts, explain how to add .woff2 files
   - Suggest creating a new presentation with this theme using `/slidecraft:start`
