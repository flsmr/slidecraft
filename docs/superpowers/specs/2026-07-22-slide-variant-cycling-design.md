# Slide-variant cycling — design

**Date:** 2026-07-22
**Status:** design, pending review
**Scope:** the *mechanics* of holding multiple design proposals for one slide and
letting the user pick one live in the browser. Content-differentiation (the
"lanes" that make v1 look different from v2 — image-gen, diagram, plain text) is
**explicitly out of scope** and deferred to a future feature.

## 1. Goal

During drafting, a single slide may have several alternative renderings. The user
runs the normal dev server on `slides.md`, navigates to a slide, and presses
**↑ / ↓** to audition the alternatives *in place*. Whatever alternative is showing
when they move on **is** the selection. No gallery, no picker button, no commit
step, no index files.

## 2. Core principle — the filesystem is the state

There is **no bookkeeping** beyond the slide files themselves.

- The **active** variant has **no postfix**: `slides/<sid>.md`. This is the file
  `slides.md` already includes via `src: ./slides/<sid>.md`.
- **Alternatives coexist** with a numeric postfix: `slides/<sid>_v1.md`,
  `slides/<sid>_v2.md`, … They are never deleted.
- A slide "has variants" **iff** `_vN` siblings exist on disk. Nothing else
  records this — it is derived by globbing. There is no `variants:` frontmatter
  key, no manifest, no state field.
- A **canonical** slide file is any `slides/*.md` **not** matching `_v\d+\.md$`.
  A **variant** file is one that matches it.

Slug note: `slugify` (km.py:61) maps `[^a-z0-9]+ → -`, so a `<sid>` never contains
`_`; the `_v` postfix is therefore unambiguous. The `<sid>` itself is
`<title-slug>--<stamp>`; the postfix is appended at the very end, before `.md`:
`<title-slug>--<stamp>_v1.md`.

## 3. State file — one shared `<sid>.json`

All variants of a slide are the *same* slide (same nuggets, title, plan slot,
lifecycle state); they differ only in the rendered `.md` body. They therefore
**share one `slides/<sid>.json`**. Variant `.md` files have no `.json` of their
own.

Consequence: the park / lock / order / budget machinery — which keys off `.json`
state (`parked_ids` km.py:105, `load_state`, etc.) — is **completely unaffected**
by variants. `concept_type` in `<sid>.json` reflects the active variant only;
per-variant `concept_type` is not tracked (irrelevant until lanes exist).

## 4. Enumeration filter

The `.md`-globbing helpers must treat variant files as invisible — they are
alternative renderings of an *existing* slide, not new slides.

- Add one predicate, e.g. `is_variant_file(p) = bool(re.search(r"_v\d+$", p.stem))`.
- `slide_files` (km.py:87) and any other `slides/*.md` enumerator exclude variant
  files, so `order` (km.py:90), `validate`, and the slide budget each see exactly
  one entry per slide.
- `.json`-keyed helpers (`parked_ids`, `load_state`) need **no** change — there is
  only ever one `.json` per slide (§3).

`slides.md` includes only the canonical path, so `order`'s regex
(`src:\s*\./slides/(.+?)\.md`) never sees a variant file regardless.

## 5. `km` command surface

Two new subcommands, both pure file operations, in the spirit of km.py's
invariant ("scripts move files and associations; they never write slide prose").

### 5.1 `km get-variants --slide <sid>` (pure read)

Globs `slides/` for `<sid>.md` + `<sid>_v*.md` and prints
`{"ok": true, "slide": <sid>, "count": N, "files": [ordered names]}`.
`count == 1` (or the canonical missing → error) means "no variants". Writes
nothing. This is what the browser asks on slide entry to decide whether to
intercept ↑/↓.

### 5.2 `km cycle-variant --slide <sid> --dir up|down`

**Ring-rotate** which physical file is canonical, among
`[<sid>.md, <sid>_v1.md, …, <sid>_v(k-1).md]` (k renderings total).

- `--dir up` shifts the ring forward by one: the current active moves aside and
  the next alternative becomes active.
- `--dir down` is the exact inverse.
- After `k` rotations in one direction the arrangement returns to the start, so
  ↑ cycles through every rendering and ↓ walks back.
- `k < 2` (no siblings) → **no-op**, print `{"ok": true, "cycled": false, "count": k}`.
- Order of the `_vN` numbers "rotates" as a side effect; this is intended and
  harmless (§2 — numbers carry no meaning).

**Algorithm** (one temp file, cascade so each destination is vacated first):

```
forward (up):
  os.replace(<sid>.md,          <sid>.cycletmp)    # active -> temp (non-.md)
  os.replace(<sid>_v1.md,       <sid>.md)          # v1 -> active
  os.replace(<sid>_v2.md,       <sid>_v1.md)       # v2 -> v1
  ...
  os.replace(<sid>_v(k-1).md,   <sid>_v(k-2).md)
  os.replace(<sid>.cycletmp,    <sid>_v(k-1).md)   # old active -> last slot
```

`down` runs the reverse cascade. `os.replace` is used for atomicity per rename
(correct on Windows and POSIX). The scratch name deliberately ends in
`.cycletmp`, **not** `.md`, so it is invisible to every `slides/*.md` glob — a
crash mid-cascade leaves an inert leftover that never renders and never counts as
a slide. `cycle-variant` clears any stale `<sid>.cycletmp` on entry.

`<sid>.json` is **not** touched by cycling (§3).

Every mutation appends to `logs/actions.jsonl` via `log` (km.py:69), as all km
mutations do.

## 6. Browser wiring (deck scaffold)

The scaffold (`scaffold_deck.py`) gains two small, self-contained pieces. Both
live in the deck, run only under the dev server, and touch no deck state
directly — they shell out to `km`.

### 6.1 Vite middleware (`vite.config.*`)

Slidev is Vite-based; a `configureServer` plugin (~30 lines) mounts:

- `GET  /__variants?slide=<sid>` → runs `km get-variants`, returns its JSON.
- `POST /__variant  {slide, dir}` → runs `km cycle-variant`, returns its JSON.

The endpoint resolves `km` and the deck root the same way the launcher does. It
serves only these two local routes; no external network.

### 6.2 `setup/shortcuts.ts`

A Slidev-supported hook returning `{key, fn}` bindings. On the current slide:

1. Resolve the current slide's `<sid>` from **Slidev's per-slide source path**
   (`nav.currentSlideRoute.meta.slide.filepath` or equivalent) — the basename of
   the `src:`-imported file is `<sid>.md`. No frontmatter, no manifest. That this
   path is exposed per slide is the **second** thing the §9 spike confirms; if it
   is not, the fallback is a single minimal marker (a comment carrying `<sid>`
   emitted by the composer, read from the slide DOM) — still no separate index.
2. `GET /__variants` for that `<sid>` (cache per slide).
3. If `count > 1`: bind **↑ → POST dir=up**, **↓ → POST dir=down**. After the
   POST resolves, the swapped `slides/<sid>.md` triggers Slidev's reload and the
   alternative renders in place; the URL keeps the slide index so the view stays
   put.
4. If `count <= 1`: fall through to Slidev's **default** ↑/↓ navigation, so
   ordinary slides behave exactly as today.

No component, no overlay is required for v1. (An optional non-load-bearing
"N options — ↑/↓" hint overlay can be added later; it would read `count` from the
same GET.)

## 7. Merge behavior

The storyteller may merge slides. The nugget/association logic is **unchanged**
(`cmd_merge`, km.py:1442: stamp a new id `M`, union the nuggets, one-image guard,
rewrite `associations.json` and `slides.md`, record `merged_from`). The **only**
change is at km.py:1478-1480, where predecessors are currently *deleted*:

- Instead of `unlink`, **rename each predecessor's renderings into `M`'s
  variants**. For every predecessor `P` in the merge, collect its canonical
  `P.md` *and* its existing `P_v*.md` siblings, and rename them all to the next
  free `M_vN.md`. Then delete each predecessor's `P.json` (its state is subsumed
  by the single shared `M.json`).
- `M.md` is written as the usual `skeleton()` placeholder (km.py:1471) and the
  orchestrator **recomposes it as normal** — so the active canonical `M.md`
  becomes a **fresh composition of the merged union of nuggets**.

Result — merge A + B where neither has variants:

```
slides/M.md      ← fresh union-of-nuggets composition (canonical/active)
slides/M_v1.md   ← former A.md   (frozen predecessor snapshot)
slides/M_v2.md   ← former B.md   (frozen predecessor snapshot)
slides/M.json    ← shared state, merged_from:[A,B];  A.json / B.json deleted
```

`M` "shows up with two variants of its predecessors" (`M_v1`, `M_v2`), letting the
user cycle back to see exactly what was merged, while the canonical slide is the
real merged composition. If A had carried `A_v1`, it rides along as an additional
`M_vN`. The variant files are invisible to `order`/`validate`/budget (§4), so a
merge still nets `active -= (parts - 1)` exactly as today.

The frozen predecessor snapshots reference assets under `public/` that still
exist, so they keep rendering.

## 8. What is explicitly untouched / out of scope

- `slides.md` — never edited by cycling or by selection. It is already a generated
  artifact (`write_order`, km.py:145) and continues to reference only canonical
  paths. Selection happens purely by rename.
- `show_slide_deck.cmd` / launcher — unchanged.
- **Variant *creation* from lanes** (image-gen vs diagram vs text) — deferred.
  Until then, variants arise only from **merge** (§7). New lanes will add their own
  creation path later without touching `cycle-variant` / `get-variants`.
- No review deck, no `<VariantPicker>` component, no manifest, no per-variant
  `.json`, no frontmatter flag — all considered and rejected in favor of the
  filesystem-as-state model.

## 9. Load-bearing assumption — spike first (step 0)

The whole in-place UX rests on **two** Slidev behaviors that must be verified
**before** building the rest:

> **(a)** When an included `src:` markdown file is **swapped by rename** (unlink +
> create at the same path, which some file watchers treat differently from an
> edit), the dev server **reloads the deck** and **returns to the same slide
> index**.
>
> **(b)** `shortcuts.ts` can read the **current slide's source file path** (to
> derive `<sid>`) from Slidev's nav/slide meta.

**Spike:** with the dev server running, hand-create `slides/a.md` and
`slides/a_v1.md`, `slides.md` including `a.md`; navigate to that slide; rename-swap
the two files by hand; confirm the deck re-renders the alternative in place on the
same slide. Expected to pass (Slidev persists nav in the URL). If **(a)** does not
reload cleanly, fall back options (in order): `touch` `slides.md` after the rename
to force a reload; or have `shortcuts.ts` call `$nav.go(current)` /
`location.reload()` after the swap resolves. If **(b)** is not exposed, use the
composer-emitted `<sid>` marker fallback (§6.2).

## 10. Test plan

Deterministic `km` logic is unit-tested like the existing `test_km_*.py`; browser
glue is verified manually (plus the §9 spike).

**Unit — `test_km_variants.py`:**

- `get-variants`: correct count/ordered list; excludes non-variant `.md`;
  canonical vs `_v\d+` distinction; `count==1` when no siblings.
- `cycle-variant up` on a 3-rendering slide: the former `_v1` content is now in
  `<sid>.md`; all three files still present; contents preserved (assert by body
  content, not filename).
- `cycle-variant up` × k returns to the original arrangement; `down` is the
  inverse of `up`.
- no-op on a slide with no siblings (`cycled:false`); stale `__tmp` cleared.
- `<sid>.json` byte-identical before/after a cycle; `slides.md` unchanged;
  `order()` and `validate` see exactly one slide.

**Unit — extend `test_km*.py` merge coverage:**

- merge A(+`A_v1`) and B → `M.md` skeleton; `{M_v1,M_v2,M_v3}` carry the bodies of
  `{A, A_v1, B}` (membership by content, order unasserted); `A.json`/`B.json`
  gone; `M.json.merged_from == [A,B]`; associations = union; `slides.md` replaces
  A,B with M; `order()` shows M once; budget nets -1.

**Integration — extend `test_draft_deck_integration.py`:**

- a plan containing a `merge` of two composed slides → after execute+compose, the
  deck is green, `M.md` is a freshly-composed slide, and predecessors are present
  as `M_vN` variants.

**Manual:**

- §9 spike (reload-on-rename + nav persistence).
- End-to-end in the browser: seed a slide with 2–3 fixture variant files, run the
  dev server, ↑/↓ cycles the rendering in place, ending on the chosen one leaves
  it canonical in `slides.md`.

## 11. Build order

0. **Spike** the reload-on-rename assumption (§9). Gate the rest on it.
1. Enumeration filter + `get-variants` + `cycle-variant` in `km.py`, with unit
   tests (§10). Pure, no browser needed.
2. Merge change (§7) + merge tests.
3. Scaffold wiring: Vite middleware + `setup/shortcuts.ts` (§6); manual browser
   verification.
