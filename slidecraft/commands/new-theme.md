---
description: Create a new Slidev theme from a corporate PPTX template, or scaffold an empty theme
argument-hint: [theme-name] [--from-pptx <path>]
---

# New Theme

Create a new Slidev theme directory. Two modes:

- **With `--from-pptx <path>`** — full conversion: delegates to the same
  pipeline `/slidecraft:import-template` uses (the
  `slidecraft.importer.convert` Python API).
- **Without `--from-pptx`** — scaffold an empty theme skeleton the user
  can fill in by hand.

The command is fully portable — it does **not** assume any particular
project root, drive letter, or directory layout. All paths are prompted
from the user.

## Steps

1. **Parse arguments**: Extract `[theme-name]` (if given) and the optional `--from-pptx <path>`. Store as `THEME_NAME` and (optionally) `PPTX_PATH`.

2. **Theme name** (if not provided): Ask
   > Short slug for the new theme? (e.g. `iu`, `corporate`, `acme`) — becomes the npm package name `slidev-theme-<slug>`
   Store as `THEME_NAME`.

3. **Theme location**: Ask the user where the theme directory should be created. Default to the current working directory:
   > Where should `slidev-theme-<THEME_NAME>/` be created?
   > Default: `<CWD>` (creates `<CWD>/slidev-theme-<THEME_NAME>/`)
   Resolve to an absolute path and store as `THEME_DIR = <chosen-base>/slidev-theme-<THEME_NAME>`. Abort and ask the user to confirm overwrite if `THEME_DIR` already exists.

4. **Install Python dependencies** (only needed if `--from-pptx` was given):
   ```bash
   pip install python-pptx lxml Pillow --break-system-packages -q
   ```

5. **If `--from-pptx <PPTX_PATH>` was given** — full extraction via the importer API. Ask the user where to put the demo deck (defaults to a `deck/` sibling of the theme):
   > Where should the demo deck be written?
   > Default: `<chosen-base>/deck/`
   Store as `DECK_DIR`.

   Then run:
   ```bash
   python -c "
   from pathlib import Path
   from slidecraft.importer.convert import convert

   r = convert(
       pptx_path=Path(r'<PPTX_PATH>'),
       theme_dir=Path(r'<THEME_DIR>'),
       deck_dir=Path(r'<DECK_DIR>'),
       theme_name='slidev-theme-<THEME_NAME>',
   )
   print(r)
   "
   ```

   `ConvertResult` returns `slides_count`, `typefaces_total`, `typefaces_substituted`, `sans_families`, `alias_font_faces`, and `warnings` — surface these to the user. The theme directory will contain `package.json`, `layouts/`, and `assets/`. The deck directory will contain `package.json` and `slides.md` (one slide per layout, ready to preview).

   Then **skip steps 6–8** (the converter already produced a valid theme) and jump to step 9 (.gitignore, optional git init, report).

6. **Scaffold an empty theme** (only when `--from-pptx` was NOT given):
   ```bash
   mkdir -p "<THEME_DIR>/layouts"
   mkdir -p "<THEME_DIR>/styles"
   mkdir -p "<THEME_DIR>/components"
   mkdir -p "<THEME_DIR>/public"
   ```

7. **Write scaffold files**:

   `<THEME_DIR>/package.json`:
   ```json
   {
     "name": "slidev-theme-<THEME_NAME>",
     "version": "0.1.0",
     "keywords": ["slidev-theme", "slidev"],
     "engines": { "slidev": ">=0.48.0" },
     "slidev": {
       "colorSchema": "light",
       "defaults": {
         "aspectRatio": "16/9",
         "canvasWidth": 1280
       }
     }
   }
   ```

   `<THEME_DIR>/styles/index.css`:
   ```css
   /* Global theme styles — auto-injected by Slidev */
   ```

   `<THEME_DIR>/slides.md` (demo deck so the user can run `npx slidev` immediately):
   ```md
   ---
   theme: ./
   ---
   # Hello from slidev-theme-<THEME_NAME>

   Edit `<THEME_DIR>/slides.md` to flesh out the theme.
   ```

8. **(Skipped — only applies when scaffolding; covered by step 7)**

9. **Write `<THEME_DIR>/.gitignore`**:
   ```
   node_modules/
   dist/
   .slidev/
   *.log
   .DS_Store
   Thumbs.db
   ```

10. **Optionally git-init** (ask the user; default no):
    > Initialize a git repo in `<THEME_DIR>`?
    If yes:
    ```bash
    cd "<THEME_DIR>"
    git init
    ```

11. **Report to the user**:
    - Theme directory: `<THEME_DIR>`
    - Whether extraction ran (`--from-pptx`) or empty scaffold was used
    - If `--from-pptx` was used: include `slides_count`, `sans_families`, and any `warnings` from `ConvertResult`
    - Demo deck location (if `--from-pptx`): `<DECK_DIR>`
    - Preview commands:
      - For the from-pptx demo deck: `cd "<DECK_DIR>" && npm install && npx slidev`
      - For the scaffold-only demo: `cd "<THEME_DIR>" && npx slidev`
    - To consume this theme in a separate deck, run `/slidecraft:new-deck` and point it at `<THEME_DIR>`.
