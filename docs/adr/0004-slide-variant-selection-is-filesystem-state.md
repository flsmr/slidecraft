# Slide-variant selection is filesystem state (filename postfix), not an index

A slide may have several alternative renderings ("variants"). We encode which one is
selected **purely in the filenames**: the **active** variant is the postfix-less
`slides/<sid>.md` that `slides.md` already includes, and alternatives coexist as
`slides/<sid>_v1.md`, `_v2.md`, …. Selecting a variant is a **rename** (`km cycle-variant`
ring-rotates which file is canonical); `slides.md` is never edited, and there is no manifest,
index file, per-variant state file, or frontmatter flag to keep in sync. The user auditions
variants **in place** in the live deck with ↑/↓ (a Vite dev-server endpoint + `shortcuts.ts`
POST a cycle; Slidev reloads the swapped include on the same slide), so whatever is active
when they move on *is* the selection — there is no separate commit step.

Status: accepted (2026-07-22, D47). Scope is the *mechanics*; differentiated *creation* of
variants (image-gen vs. diagram vs. text "lanes") is deferred, so today variants arise only
from a merge.

## Considered options

- **A selections/manifest index file** (`variants.json` mapping slide → chosen variant) —
  rejected: a second source of truth that must be kept in sync with the files, exactly the
  bookkeeping the filename convention avoids.
- **A per-variant frontmatter flag** (`variants: N`, current index) — rejected: cycling would
  have to rewrite frontmatter, so selection would no longer be a pure rename.
- **A separate generated review deck** (`slides-review.md` rendering all variants side by side
  with a picker component) — rejected once we realised in-place cycling on the real
  `slides.md` makes a second deck, a `<VariantPicker>` component, and a grouping manifest all
  unnecessary.

## Consequences

- **`slides.md` stays a clean deliverable** and is never touched by selection — it only ever
  references the canonical `<sid>.md`, so renames can't desync it.
- **Merge preserves provenance** (evolves ADR-implied D31): `merge-slides` renames each
  predecessor (and its variants) into the new slide's `_vN` variants instead of deleting them,
  so the user can cycle back to see what was merged.
- **Every `.md`-enumerating helper needs a filter** (`_v\d+\.md$` = variant, invisible to
  `order` / `validate` / budget); `.json`-keyed helpers are unaffected because a slide's
  variants share one state file.
- **One load-bearing assumption** must hold and is spiked before building: Slidev hot-reloads
  when an included `src:` file is swapped by **rename** (unlink+create) and returns to the same
  slide index. Fallbacks (`touch slides.md`, or `$nav.go(current)`) exist if it does not.
