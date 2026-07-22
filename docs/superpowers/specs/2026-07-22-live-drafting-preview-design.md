# Live drafting preview & progress — design

**Date:** 2026-07-22
**Status:** design, pending review
**Scope:** make `/draft-deck` *observable* — run the Slidev dev server in the
background while drafting, render informative skeletons for not-yet-composed
slides, and surface phase progress on a transient, uncounted status slide.
Guarantee that `npm install` finishes early (during `/init-deck`) so the server
can start instantly. **Out of scope:** streaming skeletons *during* mining, the
Workflow (`draft_deck.js`) form, changes to the double-click launchers, and the
`/improve-deck` chain.

## 1. Goal

When the user runs `/draft-deck`, they want to *watch it happen*: the deck opens
in a browser, a status slide reports which phase is running, and as the deck is
composed each slide first appears as a labelled skeleton (holding the distilled
knowledge and a "Composer is drafting this" banner) and then fills in with the
composed content. Nothing about the finished deck changes — the status slide is
removed on success and the slide budget is exactly `max_slides`.

## 2. What already exists (and is reused unchanged)

Grounding facts from the current pipeline — the feature wires these together, it
does not rebuild them:

- **`create-slide` already writes a skeleton file and rewrites `slides.md`.**
  `cmd_create` (`km.py:1314`) writes an initial body via `skeleton()`
  (`km.py:216`) and calls `write_order` (`km.py:1358`). So a created-but-uncomposed
  slide is already present in `slides.md` *before* the composer runs.
- **`write-slide` (compose) overwrites that file and rewrites `slides.md`.** The
  composer only fills an already-listed slide; it is not what first lists it.
- **The execute phase is a sequential per-slide loop.** `/draft-deck` walks
  `plan.json`'s `steps` in order (`draft-deck.md` §4), doing create→compose per
  slide. This per-slide cadence — not LLM token streaming — is what makes slides
  appear and fill one at a time.
- **Mining is coarse-grained.** The OWUI executor sends `"stream": False`
  (`invoke_shim.py:281`); one source = one atomic invoke = the whole nugget batch
  persisted at once (`persist-nuggets`). Progress during mining is therefore
  trackable only **per-source / per-image**, never per-nugget.
- **`init-deck` already starts `npm install` in the background** during the
  interview (`init-deck.md` §3, `scaffold_deck.py` `prewarm`). There is **no
  separate build step** — `npx slidev slides.md` renders straight from `slides.md`
  with hot-reload; the only prep is dependency install.
- **The backup divider proves the "inline, uncounted" pattern.** `write_order`
  emits the "Backup Slides" divider as **inline markdown in `slides.md`, not a
  slide file** (`km.py:196-200`), so `order()` / budget / `validate` never count
  it. The status slide rides this same mechanism.

## 3. Component A — background live server (`serve_deck.py`)

A new cross-platform helper, `slidecraft/scripts/serve_deck.py`, that `/draft-deck`
launches in the background at step 0, concurrently with mining. It encapsulates
the "ensure-ready, then serve" logic so the command doesn't orchestrate an
install-wait by hand, and so it is unit-testable.

### 3.1 Responsibilities

1. **Reuse check (first).** If a server is already serving this deck, do not start
   a second one — ensure the browser tab is open and exit 0. Reuse is tracked by a
   pidfile `logs/serve_deck.json` holding `{pid, port, started_at}`; the server is
   "live" iff the pid is running **and** the port answers. A stale pidfile (dead
   pid) is ignored and overwritten.
2. **Ensure `node_modules` is ready.**
   - If the `slidev` binary is present (`node_modules/.bin/slidev(.cmd)`), proceed.
   - Else, if an install appears to be in flight (a `node_modules/.package-lock.json`
     or `node_modules/.staging` marker exists, i.e. init-deck's background install
     is still running), **poll** for the binary up to a bounded timeout.
   - Else run `npm install --no-audit --no-fund` from the deck root and wait.
   - If Node/npm is unavailable or the install fails (offline), **exit non-zero
     with a clear machine-readable status** (`{"status": "no-preview",
     "reason": ...}` on stdout). `/draft-deck` treats this as "skip live preview"
     and drafts normally — files still update; the user previews later via the
     launcher.
3. **Serve.** Run `npx slidev slides.md --open` (opens the browser once). Write the
   pidfile. The process is left running after `/draft-deck` completes so the user
   keeps watching; the run report tells them how to stop it (close the window /
   Ctrl-C).

### 3.2 CLI

```
python serve_deck.py --deck <deck-root> [--no-open] [--ready-timeout SECONDS]
```

Emits one line of JSON on stdout describing the outcome
(`served` | `reused` | `no-preview`) so the orchestrator can branch and report.

### 3.3 Concurrency

`serve_deck.py` runs as a background process (the Bash/PowerShell tool's
`run_in_background`), so mining proceeds in the foreground while install + serve
spin up in parallel — matching the user's "workers start, server starts in the
meantime" intent. The double-click launchers (`show_slide_deck.{cmd,sh}`) are
**unchanged**; consolidating logic here does not touch them.

## 4. Component B — rich skeletons

Today `skeleton()` (`km.py:216`) emits only:

```
---
layout: default
title: <title>
---

<!-- awaiting composition; nuggets: a,b -->
```

which renders as a **blank** slide. Enrich it to render the **distilled nugget
information** under a visible **"🚧 Composer is drafting this slide…"** banner, so
a watched deck shows meaningful skeletons that then fill in.

### 4.1 New skeleton body

- A visible banner line (plain markdown / minimal HTML that renders on any theme —
  no theme-specific slots), e.g. a blockquote callout:
  `> 🚧 **Composer is drafting this slide…**`
- The distilled knowledge — the nuggets' `information` — so the user sees *what the
  slide will be about* while it is being composed.
- **The literal marker `awaiting composition` is preserved** (inside an HTML
  comment) because `needs_composition()` (`km.py:221`) keys off that exact
  substring for park/unpark bookkeeping. Keeping it means that logic — and every
  test that exercises it — is untouched. `digest_body` carries the *separate*
  `backup digest` marker (`DIGEST_MARK`, `km.py:213`); the skeleton must **not**
  emit that marker (it would make an active skeleton read as a parked digest to
  `needs_composition`).

### 4.2 Refactor needed to share the info assembly

The distilled-`information` rendering currently lives **inlined** inside
`digest_body` (`km.py:1601-1606`) — there is no reusable helper today, and
`skeleton()` (`km.py:216`) takes only `(title, nugget_ids)`, with **no `root`**, so
it cannot load nugget bodies. Two concrete changes:

1. **Factor out a small helper**, e.g. `nugget_info_section(root, nugget_ids) -> str`,
   holding the per-nugget `information` assembly (the loop at `km.py:1601-1606`,
   minus the `DIGEST_MARK` comment and the verbatim speaker-notes). Both
   `digest_body` and the enriched `skeleton` call it; `digest_body` still wraps it
   with `DIGEST_MARK` + notes, the skeleton wraps it with the banner + the
   `awaiting composition` comment. This keeps a single source of truth for "show
   the distilled info" and avoids the skeleton re-deriving it.
2. **Give `skeleton()` access to `root`** (signature change) so it can load the
   info. Update all call sites: `cmd_create:1346`, the reset path at `km.py:1419`,
   and the merge path at `km.py:1498` — each already has `root` in scope.

### 4.3 Invariants preserved

- `needs_composition(skeleton(root, ...))` still returns `True`.
- A directly-parked create still gets `digest_body` (with `DIGEST_MARK`), unchanged
  (`cmd_create:1345`).
- The skeleton remains valid Slidev headmatter + body; it carries **no** verbatim
  speaker-notes (kept light — notes are a `digest_body` concern only).

## 5. Component C — transient status slide

A phase-progress slide that is **inline and uncounted**, at the **front** of the
deck while drafting, and **auto-removed** on success.

### 5.1 State: `.draft-status.json`

A transient file in the deck root (added to `.gitignore`), e.g.:

```json
{ "phase": "compose", "detail": "4/20", "label": "Composing slides…",
  "updated_at": "2026-07-22T10:31:00" }
```

Its presence is the sole trigger for the status block. Absence = no status block.

### 5.2 Rendering in `write_order`

`write_order` (`km.py:172`) gains a status branch, analogous to the existing
`parked` tail:

- When `.draft-status.json` exists, prepend an **inline content block** as slide 1,
  built from the status fields. Because it is inline markdown (not a `src:` import
  and not a slide file), `order()` (`km.py:90`), the budget gate
  (`cmd_create:1324`), and `validate` never see it — the same guarantee the backup
  divider relies on (`km.py:196-200`).
- **Avoid the "blank slide 1" pitfall.** `write_order` currently folds the first
  real slide's `src` into the headmatter block to keep slide 1 from rendering
  blank (`km.py:177-186`). When a status block is present it becomes the headmatter
  block's own visible content (so slide 1 is the status slide, not blank), and the
  cover + rest follow as `src:` imports. When absent, the existing headmatter-fold
  behaviour is exactly as today.
- Ordering: status block → cover (first `src`) → body slides → backup tail.

### 5.3 `km` command surface

Two new subcommands, pure file operations (in km's spirit — "scripts move files;
they never write slide prose"):

- **`km set-status --phase <p> --detail <d> [--label <l>]`** — writes/updates
  `.draft-status.json` and calls `write_order(root, order(root))` so `slides.md`
  is rewritten with the fresh status block. Idempotent; cheap.
- **`km clear-status`** — deletes `.draft-status.json` and rewrites `slides.md`
  (status block gone). Called on successful completion, so the finished deck is
  clean. No-op if the file is already absent.

Both log to `logs/actions.jsonl` like other mutations.

### 5.4 Lifetime

The status slide exists only between the first `set-status` and `clear-status`.
On an **aborted** run (e.g. storyteller terminal, `draft-deck.md` §3) the command
should still `clear-status` (or leave a final "aborted — see report" status) so the
deck isn't left with a stale "Planning…" slide; the exact terminal behaviour is
specified in §6.

## 6. Component D — `/draft-deck` orchestration changes

Edits to `slidecraft/commands/draft-deck.md`. The pipeline steps are unchanged;
observability is threaded through them:

- **Step 0 (new).** Launch `serve_deck.py` in the background; read its JSON outcome
  to know whether live preview is active (and note it in the final report). Then
  `km set-status --phase convert --label "Converting inputs…"`.
- **Convert / Mine / Plan.** `set-status` at each transition; during mining update
  the detail per source/image completed, e.g.
  `set-status --phase mine --detail "3/5" --label "Mining sources…"`.
- **Execute.** No new status call is strictly required per slide (the skeletons
  are the per-slide signal), but the command sets
  `--phase compose --detail "<done>/<total>"` as slides are composed so the status
  slide shows a running count. The existing create→compose loop already produces
  the live skeleton→fill via `write_order`.
- **Finish.** On success, `km clear-status`, then `validate` + report; the report
  states whether live preview was active and how to stop the server. On abort,
  set a terminal status (`--phase aborted --label "<reason>"`) instead of clearing,
  so the browser reflects the stop, and surface the error as today.

**Ordering note:** `set-status`/`clear-status` and the create/compose steps all
call `write_order`, so they serialize naturally through the single `slides.md`
writer — no concurrent writers (the server only *reads* `slides.md`).

## 7. Component E — `/init-deck` (minimal)

`init-deck` already background-installs (`init-deck.md` §3). Changes are
documentation-level only:

- Make explicit that this background install is what lets `/draft-deck` start the
  live server instantly, and that there is **no separate build step**.
- Ensure `.gitignore` (written by `scaffold_deck.write_gitignore`, `:358`) also
  ignores the transient `.draft-status.json` and `logs/serve_deck.json`.

No change to the interview or the scaffold's structure.

## 8. Risks & mitigations (to verify during build)

1. **Vite HMR on new `src:` imports.** When `slides.md` gains a slide mid-run, does
   Slidev hot-reload cleanly or need a full refresh? *Verify with a live run;* if it
   doesn't pick up new imports, fall back to a periodic reload or document the
   limitation. This is the highest-uncertainty item.
2. **OneDrive file-watching latency.** Vite watching a cloud-synced folder can lag
   or miss events. *Verify;* if flaky, note it and/or increase the watch/poll
   interval.
3. **Background-server lifetime across turns.** The live view relies on the
   `run_in_background` process surviving after the turn; if the harness reaps it,
   the server stops (files still update correctly). *Document the actual behaviour;*
   the double-click launcher remains the always-available fallback.
4. **Reuse race.** Two `/draft-deck` runs in the same deck must not start two
   servers — the pidfile + port check (§3.1) guards this; a stale pidfile is
   ignored.

## 9. Testing

Unit (pytest, alongside the existing `test_km*.py`):

- **Rich skeleton:** `needs_composition(skeleton(root, title, ids))` is still
  `True`; the body contains the banner + the nuggets' `information`; the body does
  **not** contain `DIGEST_MARK`. `nugget_info_section` produces identical info text
  for `digest_body` and `skeleton` (shared-helper regression guard).
- **Status round-trip:** after `set-status`, `slides.md` contains the status block
  and `order(root)` / the slide count are **unchanged**; after `clear-status`,
  `slides.md` has no status block and is byte-clean of it. Assert the "blank slide
  1" guard still holds with and without a status block.
- **`serve_deck` readiness logic** via fakes/monkeypatch: binary-present → serve;
  install-in-flight → poll then serve; missing-node → `no-preview`; live
  pidfile → `reused`; stale pidfile → overwritten.

Integration: extend `test_draft_deck_integration.py` (drives the real sequence with
a fake executor) to assert `set-status` is called through the phases, `clear-status`
runs at the end, and the **final active slide count is exactly `max_slides`** (the
status slide never consumed a budget slot).

## 10. File-change summary

| File | Change |
|---|---|
| `slidecraft/scripts/serve_deck.py` | **new** — ensure-ready + background serve + pidfile reuse |
| `slidecraft/scripts/km.py` | enrich `skeleton()`; status branch in `write_order`; `set-status` / `clear-status` subcommands |
| `slidecraft/commands/draft-deck.md` | step 0 serve; `set-status` through phases; `clear-status` on finish; report live-preview state |
| `slidecraft/commands/init-deck.md` | wording: install ⇒ instant serve, no build step |
| `slidecraft/scripts/scaffold_deck.py` | `.gitignore` also ignores `.draft-status.json`, `logs/serve_deck.json` |
| `slidecraft/tests/test_km*.py`, `test_draft_deck_integration.py` | tests per §9 |
