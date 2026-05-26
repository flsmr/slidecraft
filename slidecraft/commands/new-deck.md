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

   Omit `--theme` entirely if the user chose Slidev's default.

   **Default behaviour is gallery mode.** When a theme exposes layouts (`<theme>/layouts/*.vue`), the scaffolder emits **one starter slide per layout** with the correct `layout: slideN` frontmatter. This matters: a slide without an explicit `layout:` frontmatter uses Slidev's **built-in default layout**, NOT the theme's — so a deck full of un-tagged slides would render with zero theme styling. Gallery mode guarantees the theme actually loads on first `npx slidev`, and it doubles as a layout reference the user can browse and delete from.

   Useful flags:
   - `--minimal` — opt out of gallery mode; emit a 2-slide starter pinned to the first available theme layout. Use when the user already knows which layouts they want and prefers a blank slate.
   - `--no-install` — skip `npm install`.
   - `--overwrite` — allow writing into an existing directory.

   The script prints a key/value summary on stdout (`deck_dir`, `deck_name`, `theme_name`, `theme_dir`, `theme_rel`, `mode`, `slide_count`, `installed`, `preview`). It exits 0 on success, 1 with an `error:` stderr line on validation failure.

3. **Report to the user.** Echo the script's summary, then point them at the preview command from the `preview:` line (always of the form `cd "<deck_dir>" && npx slidev`). Mention the two scaffolded folders:
   - `public/` — runtime-served by Slidev; drop here any image/video referenced from a slide as `/file.ext`.
   - `resources/` — source material the deck is based on (papers, raw images, outlines, meeting notes). NOT served by Slidev; this is the user's input archive. A `README.md` inside explains the convention.

That's it — no manual file creation, no per-step orchestration. Every detail of layout, templates, and dependency wiring lives in `slidecraft/scaffold/new_deck.py` (and is covered by its tests).
