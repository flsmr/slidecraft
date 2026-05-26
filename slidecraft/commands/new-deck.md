---
description: Scaffold a new Slidev presentation that consumes an existing theme
argument-hint: [deck-name]
---

# New Deck

Thin wrapper around `python -m slidecraft.scaffold.new_deck`. The script
does all the mechanics (mkdir, render templates, compute portable relative
path, npm install). Your job is just to gather three inputs from the user
and invoke it once.

## Steps

1. **Gather inputs.** Three pieces of information are needed:

   - **`DECK_NAME`** — Use the argument if provided, else ask:
     > What should the new deck be called?

     The deck folder name preserves what the user typed (so a name like `2026-05-26_ILSE` becomes the literal folder name they expect to see). The scaffolder lowercases it internally for the npm `name` field. If the user-supplied name still contains characters npm rejects after lowercasing (spaces, punctuation, leading `.`/`_`), ask the user to revise — the scaffolder will raise `ValueError` otherwise.

   - **`DECK_LOCATION`** — Where the deck folder will be created (the folder itself is `DECK_LOCATION/DECK_NAME`). Default to the current working directory:
     > Where should the deck folder be created? (default: current directory)

   - **`THEME_DIR`** — Discover existing themes, present candidates, let the user pick. Search in this order:
     1. Sibling directories of `DECK_LOCATION` matching `slidev-theme-*`
     2. Parent directory of `DECK_LOCATION` matching `slidev-theme-*`
     3. (Only if 1–2 yielded nothing) shallow search ≤ 2 levels deep under the user's home

     For each candidate, verify it contains `package.json` with a `"slidev"` key. Then present:
     > Found these themes:
     >   1. `<name>` at `<absolute-path>`
     >   2. …
     > Pick one, enter a custom absolute path, or press Enter for Slidev's built-in default.

     Store the chosen absolute path as `THEME_DIR`, or `null` if the user chose the default.

2. **Invoke the scaffolder.** One subprocess call does everything — directory creation, template rendering, portable forward-slash relative-path computation, and `npm install`:

   ```bash
   python -m slidecraft.scaffold.new_deck \
     --name "<DECK_NAME>" \
     --location "<DECK_LOCATION>" \
     --theme "<THEME_DIR>"
   ```

   Omit `--theme` entirely if the user chose Slidev's default. Pass `--no-install` to skip `npm install` (e.g. if the user wants to inspect the deck before installing). Pass `--overwrite` if the user explicitly wants to write into an existing directory.

   The script prints a key/value summary on stdout (`deck_dir`, `deck_name`, `theme_name`, `theme_dir`, `theme_rel`, `installed`, `preview`). It exits 0 on success, 1 with an `error:` stderr line on validation failure.

3. **Report to the user.** Echo the script's summary, then point them at the preview command from the `preview:` line (always of the form `cd "<deck_dir>" && npx slidev`).

That's it — no manual file creation, no per-step orchestration. Every detail of layout, templates, and dependency wiring lives in `slidecraft/scaffold/new_deck.py` (and is covered by its tests).
