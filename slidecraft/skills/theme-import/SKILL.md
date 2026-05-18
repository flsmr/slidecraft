---
name: theme-import
description: Import a corporate PowerPoint (.pptx) template and convert it into a Slidev theme. Extracts colors, fonts, logos, backgrounds, and slide layouts. Triggers on phrases like "import template", "convert pptx theme", "create theme from powerpoint", "use our company template", or any request involving .pptx files and Slidev themes.
---

# Theme Import Skill

You help users convert corporate PowerPoint templates (.pptx) into fully functional Slidev themes.

## What You Do

1. Accept a .pptx template file from the user
2. Run the extraction script to pull: theme colors (12-color scheme), fonts (heading + body), logos, background images, and slide layout definitions
3. Generate a complete Slidev theme directory containing:
   - `package.json` with font and color schema config
   - `style.css` with CSS custom properties mapped from PPTX theme colors
   - `layouts/*.vue` components generated from PPTX slide layout placeholders
   - `global-bottom.vue` for persistent logos/watermarks
   - `public/assets/` with extracted media (logos, backgrounds)
4. Verify the generated theme by checking file completeness

## How to Run

Use the extraction script at `scripts/extract-pptx-theme.py`:

```bash
python scripts/extract-pptx-theme.py --input <path-to-pptx> --output <theme-output-dir>
```

The script requires `python-pptx` and `lxml`. Install with:
```bash
pip install python-pptx lxml
```

## Output Structure

The generated theme follows Slidev's theme convention:

```
slidev-theme-<name>/
├── package.json          # npm metadata + slidev config
├── style.css             # CSS custom properties from PPTX colors
├── uno.config.ts         # UnoCSS theme integration
├── layouts/
│   ├── cover.vue         # From "Title Slide" layout
│   ├── default.vue       # From "Title and Content" layout
│   ├── section.vue       # From "Section Header" layout
│   ├── two-cols.vue      # From "Two Content" layout
│   └── ...               # Additional layouts found in PPTX
├── components/
│   └── CompanyLogo.vue   # Reusable logo component
├── global-bottom.vue     # Persistent footer with logo
├── public/
│   └── assets/           # Extracted logos, backgrounds
└── example.md            # Demo slides using the theme
```

## User Interaction

- Ask which .pptx file to use as the source template
- Ask where to save the generated theme (suggest `~/slidev-themes/<company-name>/`)
- After generation, offer to preview with `npx slidev example.md`
- If corporate fonts are not on Google Fonts, inform the user they may need to provide .woff2 files

## Limitations

- Gradient fills in PPTX require manual CSS adjustment after extraction
- Decorative shapes (accent bars, geometric elements) on layouts become approximate CSS, not pixel-perfect
- Corporate fonts not available on Google Fonts need manual .woff2 bundling
