---
description: Create a new slide deck under the slidecraft-slide-decks workspace, optionally seeded from a PPTX
argument-hint: <deck-name> [--theme <theme-name>] [--from-pptx <path>]
---

# New Deck

Create a new slide deck at
`D:\Archive\03_Freizeit\Projects\slidecraft-slide-decks\<deck-name>\`.

## Steps

1. **Parse arguments**: Extract `<deck-name>`. Check for:
   - `--theme <theme-name>` (default: `iu`)
   - `--from-pptx <path>` (optional)
   Store as `DECK_NAME`, `THEME_NAME`, and optionally `PPTX_PATH`.

2. **Resolve paths**:
   ```
   DECK_DIR  = D:\Archive\03_Freizeit\Projects\slidecraft-slide-decks\<DECK_NAME>
   THEME_DIR = D:\Archive\03_Freizeit\Projects\slidev-theme-<THEME_NAME>
   ```
   Abort if `DECK_DIR` already exists (confirm overwrite first).
   Warn if `THEME_DIR` does not exist yet.

3. **Create directory structure**:
   ```
   mkdir DECK_DIR\resources
   mkdir DECK_DIR\assets
   mkdir DECK_DIR\content
   mkdir DECK_DIR\intermediate
   mkdir DECK_DIR\exports
   ```

4. **Write `content/slides.md`** with a minimal frontmatter:
   ```markdown
   ---
   theme: ../../../slidev-theme-<THEME_NAME>
   title: <DECK_NAME>
   layout: cover
   ---

   # <DECK_NAME>

   ---

   # Slide 2
   ```

5. **Write `package.json`**:
   ```json
   {
     "name": "<DECK_NAME>",
     "version": "0.1.0",
     "private": true,
     "scripts": {
       "dev": "slidev content/slides.md",
       "build": "slidev build content/slides.md",
       "export": "slidev export content/slides.md"
     },
     "devDependencies": {
       "@slidev/cli": "^0.50.0",
       "@slidev/types": "^0.50.0",
       "slidev-theme-<THEME_NAME>": "file:../../slidev-theme-<THEME_NAME>"
     }
   }
   ```

6. **Write `.gitignore`**:
   ```
   node_modules/
   dist/
   .slidev/
   *.log
   exports/
   .DS_Store
   Thumbs.db
   ```

7. **Write `README.md`**: brief description of the deck, the theme used, and
   how to run it (`npx slidev content\slides.md`).

8. **If `--from-pptx <PPTX_PATH>` was given**:
   - Copy the PPTX to `DECK_DIR\resources\` (keep the original filename).
   - Run the test-deck generator (find `<plugin-dir>` as the parent of `commands/`):
     ```bash
     python <plugin-dir>/scripts/generate-test-deck.py \
       --pptx "<PPTX_PATH>" \
       --theme-dir "<THEME_DIR>" \
       --out "<DECK_DIR>"
     ```
   - This overwrites `content/slides.md` and populates `assets/` with
     per-slide images referenced in the generated deck.

9. **Git init**:
   ```bash
   cd DECK_DIR
   git init
   ```

10. **Install npm dependencies**:
    ```bash
    cd DECK_DIR
    npm install
    ```

11. **Report to the user**:
    - Deck directory created at `DECK_DIR`
    - Theme referenced: `THEME_DIR`
    - Next step: `cd DECK_DIR && npx slidev content\slides.md`
