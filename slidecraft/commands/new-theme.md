---
description: Create a new Slidev theme repo from a corporate PPTX template, or scaffold an empty theme
argument-hint: <theme-name> [--from-pptx <path>]
---

# New Theme

Create a new corporate theme as a flat sibling repo at
`D:\Archive\03_Freizeit\Projects\slidev-theme-<name>\`.

## Steps

1. **Parse arguments**: Extract `<theme-name>` from the argument. Check for
   `--from-pptx <path>` flag. Store as `THEME_NAME` and optionally `PPTX_PATH`.

2. **Resolve target directory**:
   ```
   THEME_DIR = D:\Archive\03_Freizeit\Projects\slidev-theme-<THEME_NAME>
   ```
   Abort if it already exists (ask the user to confirm overwrite first).

3. **Create directory structure**:
   ```
   mkdir THEME_DIR
   mkdir THEME_DIR\layouts
   mkdir THEME_DIR\layouts-generated
   mkdir THEME_DIR\components
   mkdir THEME_DIR\public\assets
   ```

4. **Write scaffold files** (if `--from-pptx` was NOT given):

   `package.json` — standard Slidev theme package with `"name": "slidev-theme-<THEME_NAME>"`,
   `"version": "0.1.0"`, `"slidev"` key with `colorSchema: "light"` and font defaults.

   `style.css` — empty file with a comment: `/* Global theme styles */`.

   `_fonts.css` — empty file with a comment: `/* Font-face declarations */`.

   `uno.config.ts` — minimal UnoCSS config:
   ```ts
   import { defineConfig } from 'unocss'
   export default defineConfig({})
   ```

   `theme-manifest.json` — stub:
   ```json
   { "schema_version": "2.0", "source_pptx": null, "layouts": [] }
   ```

   `example.md` — minimal Slidev deck using the theme:
   ```md
   ---
   theme: ./
   ---
   # Hello from slidev-theme-<THEME_NAME>
   ```

5. **If `--from-pptx <PPTX_PATH>` was given**, run the full extraction pipeline
   (find the plugin dir as the parent of the `commands/` directory containing this file):

   ```bash
   python <plugin-dir>/scripts/extract-pptx-theme.py \
     --pptx "<PPTX_PATH>" \
     --theme-dir "<THEME_DIR>" \
     --name "<THEME_NAME>"

   python <plugin-dir>/scripts/extract-fonts.py \
     --pptx "<PPTX_PATH>" \
     --theme-dir "<THEME_DIR>"

   python <plugin-dir>/scripts/extract-assets.py \
     --pptx "<PPTX_PATH>" \
     --theme-dir "<THEME_DIR>"

   python <plugin-dir>/scripts/generate-layouts.py \
     --manifest "<THEME_DIR>/theme-manifest.json" \
     --shapes-index "<THEME_DIR>/assets-shapes.json" \
     --out "<THEME_DIR>/layouts-generated"
   ```

6. **Write `.gitignore`**:
   ```
   node_modules/
   dist/
   .slidev/
   *.log
   .DS_Store
   Thumbs.db
   ```

7. **Git init**:
   ```bash
   cd THEME_DIR
   git init
   ```

8. **Install npm dependencies**:
   ```bash
   cd THEME_DIR
   npm install
   ```

9. **Report to the user**:
   - Theme directory created at `THEME_DIR`
   - Whether extraction ran or scaffold was used
   - Next steps: `npx @slidev/cli example.md` to preview

   Reference to use the theme in a deck:
   ```yaml
   theme: ../../../slidev-theme-<THEME_NAME>
   ```
   (from `Projects/<decks-repo>/<deck-name>/content/slides.md`).
