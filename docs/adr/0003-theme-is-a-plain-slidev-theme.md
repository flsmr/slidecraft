# A theme is a plain Slidev theme carrying its own style guide

Under the agentic framework (`architecture_proposal.md`, D19), deck *shape* comes from the
storyteller and storytelling skills, and a theme is **its own repository, visuals-only**. We
decided a theme is a plain `slidev-theme-<slug>/` npm package — `package.json` (with
`slidev.defaults`), `layouts/*.vue` (physical-name `<slot name="…">` regions), optional
`components/*.vue`, `styles/`, served assets (`public/` or `assets/`) — plus three theme-owned
authoring artifacts:

- **`semantic-layouts.json`** — the REQUIRED slot-role contract: each semantic alias maps to a
  physical `layout`, a `slots` map (role → physical slot), an `intent`, and `defaults`. It is the
  only thing that tells a composer that a cryptic physical slot (`::body-26::`, `::ph-1::`) plays
  a role, how to fill it, and its default value. `scan_theme.py` surfaces it into the deck's theme
  capabilities; the slide-composer authors from it.
- **`styleguide.md`** — the theme's visual contract (palette, typography, figure/diagram
  consistency), consumed by the image-composer via its `%STYLE-GUIDE%` injection and by the
  image-critic. There is no separate `diagram-style.md`.
- **`example.md`** — a first-class *standard deck* exercising every layout idiomatically (cover ·
  agenda · content · section · figure · closing) in physical names. It is the composer's "how a
  deck looks in this theme" reference and the theme's render sanity-check.

A deck references a theme by **local path or npm** in its `slides.md` headmatter and `package.json`
(`/init-deck` scaffolds this and runs `scan_theme.py`). The **physical-names rule survives** from
ADR-0001: rendered `.vue`/`example.md`/`slides.md` use the theme's real layout/slot names;
semantic aliases live only in `semantic-layouts.json` (the May-2026 render-time-failure lesson).

**Culled:** theme *packs* (the `<slug>-theme-pack/` wrapper + `pack.json`) and **skeletons**
(`skeletons/<name>/` — `skeleton.json`, `framing_slides[]`, `decision_points[]`, `workflow`
toggles, per-theme `templates/*.md`, `author-guide.md`, `diagram-style.md`). Everything a skeleton
held has a new home: deck shape → the storyteller (runtime, any theme) + the theme's `example.md`;
slot roles/defaults → `semantic-layouts.json`; deck metadata (presenter/date/institution) →
`deck-context` captured by `/init-deck`; writing craft → the `compose-slide` skill; figure
consistency → `styleguide.md`; deck scaffolding → `scaffold_deck.py`. The `workflow` enhancement
toggles (mindmap, quiz, galleries) defer to future `/improve-deck` skills (v1.1); the knowledge is
preserved under `legacy/skills/`.

Considered and rejected: keeping a slimmed "theme pack" that still bundles per-theme deck templates
— it re-buries deck shape in the theme (the thing D19 moved out) and duplicates knowledge across
themes. A theme-agnostic skeleton library projected through each theme's `semantic-layouts.json`
was already rejected in ADR-0001 as speculative generality; that reasoning still holds.

Consequences: `new-theme.md` drops its `pack` scope and Phase 4 (skeletons + `pack.json`) and
always outputs a plain `slidev-theme-<slug>/`; the PPTX importer (`convert.py`) already emits a
plain theme (no `theme-manifest.json`); `theme-import/SKILL.md` is aligned to it. Existing packs
under the user's `slidecraft-themes/` are used today by pointing `/init-deck` at their **inner**
`slidev-theme-<slug>/` folder; the sibling `skeletons/` + `pack.json` are dead and can be deleted
when convenient (see `docs/theme-pack-migration.md`).

Status: accepted (2026-07-18). Supersedes the pack/skeleton parts of the previous `new-theme.md`
and completes ADR-0001 (skeletons) and ADR-0002 (workflow extension points), both already marked
superseded by D19.
