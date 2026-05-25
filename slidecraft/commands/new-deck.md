---
description: Create a new Slidev presentation that consumes an existing theme
argument-hint: [deck-name]
---

# New Deck

Scaffold a new Slidev presentation that consumes a theme produced by
`/slidecraft:import-template` (or any other Slidev theme available on disk).

The command is fully portable — it does **not** assume any particular project
root, drive letter, or directory layout. All paths are prompted from the
user, with sensible defaults derived from the current working directory.

## Steps

1. **Deck name**: If the user passed `[deck-name]` as an argument, use it. Otherwise ask:
   > What should the new deck be called? (used as the folder name and the `name` field in `package.json`)
   Store as `DECK_NAME`.

2. **Deck location**: Ask the user where the deck folder should be created. Suggest the current working directory as the default:
   > Where should `<DECK_NAME>/` be created?
   > Default: `<CWD>` (creates `<CWD>/<DECK_NAME>/`)
   Resolve to an absolute path and store as `DECK_DIR = <chosen-base>/<DECK_NAME>`. Abort and ask the user to confirm overwrite if `DECK_DIR` already exists.

3. **Theme location**: Help the user point at an existing Slidev theme. Search in this order and present the candidates:
   1. Sibling directories of the chosen deck base (`<deck-base>/slidev-theme-*`)
   2. The parent of the deck base (`<deck-base>/../slidev-theme-*`)
   3. Any `slidev-theme-*` directory under the user's home (only if the previous two yielded nothing — keep the search shallow, max two levels deep, to avoid scanning huge trees)

   For every candidate verify it contains `package.json` with a `"slidev"` key. Then ask:
   > I found these themes:
   >   1. `<package.json name>` at `<absolute path>`
   >   2. …
   > Which one would you like to use? You can also enter a custom absolute path, or press Enter to use Slidev's built-in default theme.

   Store:
   - `THEME_DIR` — absolute path to the chosen theme directory (or `null` if using the Slidev default)
   - `THEME_NAME` — the `"name"` field from the theme's `package.json` (e.g. `slidev-theme-ILSE`), or `"@slidev/theme-default"` if the default was chosen
   - `THEME_REL` — `THEME_DIR` expressed relative to `DECK_DIR` using forward slashes (`os.path.relpath(...).replace("\\", "/")`); set to `null` if using the default theme

4. **Create the deck directory**:
   ```bash
   mkdir -p "<DECK_DIR>/public"
   ```
   (`public/` is Slidev's convention for static assets — images you reference as `/foo.png` in markdown.)

5. **Write `<DECK_DIR>/slides.md`** with a minimal starter deck. Use `THEME_NAME` in the frontmatter so npm resolves it via the `file:` dependency declared in the next step:

   ```markdown
   ---
   theme: <THEME_NAME>
   title: <DECK_NAME>
   ---

   # <DECK_NAME>

   Replace this with your opening slide.

   ---

   # Slide 2

   - Bullet one
   - Bullet two

   ---

   # Slot overrides

   When a layout exposes named slots (e.g. `slide14` from an imported theme),
   override them with `::slot-name::` blocks:

   ```
   ::title::
   My custom title

   ::body-19::
   My custom body

   ::picture-22::
   ![](/my-image.png)
   ```
   ```

6. **Write `<DECK_DIR>/package.json`**. Reference the chosen theme via a `file:` dependency so npm symlinks it locally — this is the portable equivalent of publishing the theme to a registry:

   ```json
   {
     "name": "<DECK_NAME>",
     "private": true,
     "scripts": {
       "dev": "slidev",
       "build": "slidev build",
       "export": "slidev export"
     },
     "dependencies": {
       "@slidev/cli": "^52.0.0",
       "<THEME_NAME>": "file:<THEME_REL>"
     }
   }
   ```

   If the user chose the Slidev default theme (`THEME_DIR` is null), omit the second dependency and drop the `theme:` line from the frontmatter in step 5.

7. **Write `<DECK_DIR>/.gitignore`**:
   ```
   node_modules/
   dist/
   .slidev/
   *.log
   .DS_Store
   Thumbs.db
   ```

8. **Install npm dependencies**:
   ```bash
   cd "<DECK_DIR>"
   npm install
   ```
   This pulls in `@slidev/cli` and symlinks the local theme via the `file:` dependency.

9. **Optionally git-init** (ask the user; default no):
   > Initialize a git repo in `<DECK_DIR>`?
   If yes:
   ```bash
   cd "<DECK_DIR>"
   git init
   ```

10. **Report to the user**:
    - Deck directory: `<DECK_DIR>`
    - Theme used: `<THEME_NAME>` at `<THEME_DIR or "Slidev built-in default">`
    - Preview command: `cd "<DECK_DIR>" && npx slidev`
    - To add custom material: edit `<DECK_DIR>/slides.md`, drop assets into `<DECK_DIR>/public/`, reference them as `/filename.ext`
