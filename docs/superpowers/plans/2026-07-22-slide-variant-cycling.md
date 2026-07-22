# Slide-Variant Cycling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a slide hold several coexisting renderings and let the user audition them in place in the live Slidev deck with ↑/↓, where whatever is active when they move on is the selection.

**Architecture:** The filesystem is the only state — the active variant is the postfix-less `slides/<sid>.md` that `slides.md` includes; alternatives coexist as `slides/<sid>_vN.md`. Selection is a pure **rename** (`km cycle-variant` ring-rotates which file is canonical); `slides.md` is never edited. A tiny Vite dev-server endpoint + a Slidev `setup/shortcuts.ts` remap ↑/↓ to POST a cycle, and the swapped include triggers Slidev's reload in place.

**Tech Stack:** Python 3 (`slidecraft/scripts/km.py`, pytest), Slidev/Vite (deck scaffold: `vite.config.ts`, `setup/shortcuts.ts`).

## Global Constraints

- **Mechanics only.** Do NOT implement variant *creation* from composer "lanes" (image-gen / diagram / text). Until that later feature, variants arise only from a **merge**. (design §8)
- **`km.py`'s invariant:** scripts move files, never write slide prose. `cycle-variant` and `get-variants` are pure file operations. (design §5)
- **`slides.md` is never edited by selection** — it already references only the canonical `slides/<sid>.md`; renames must not touch it. (design §2)
- **One shared state file** per slide: variants of a slide share one `slides/<sid>.json`. Never create per-variant `.json`. (design §3)
- **Canonical vs variant** is derived, never stored: a variant file's stem matches `_v\d+$`; a canonical file's does not. No `variants:` frontmatter, no manifest, no index. (design §2, §4)
- **Renames use `Path.replace`** (atomic on Windows + POSIX). The cycle scratch file ends in **`.cycletmp`** (NOT `.md`) so it is invisible to every `slides/*.md` glob. (design §5.2)
- Test style: call `km.cmd_*(deck, argparse.Namespace(...))` against a real scaffolded deck (see `slidecraft/tests/test_km.py`, `conftest.py`). Assert on files/`capsys` JSON.
- Reference design doc: `docs/superpowers/specs/2026-07-22-slide-variant-cycling-design.md`. Decision **D47** (SPEC.md), **ADR-0004**.

---

## Task 0: Spike — verify the load-bearing Slidev assumptions (manual gate)

**No code. This gates every later task — do it first and record the result.** The whole in-place UX rests on two Slidev behaviors (design §9). If either fails, use the documented fallback before proceeding.

**Files:**
- Scratch only (a throwaway deck); no repo files change.

- [ ] **Step 1: Scaffold or reuse a deck with the dev server running**

Use any existing scaffolded deck (or make one with `/init-deck`). Start the dev server via `show_slide_deck.cmd` (Windows) / `show_slide_deck.sh`, or `npm run dev` in the deck. Confirm it opens at `http://localhost:3030/`.

- [ ] **Step 2: Hand-create two renderings of one slide**

In the deck's `slides/` folder, pick an existing slide file `X.md`. Copy it to `X_v1.md` and edit `X_v1.md` so its visible content is obviously different (e.g. change the H1 to "VARIANT ONE"). Leave `slides.md` unchanged (it includes `X.md`).

- [ ] **Step 3: Assumption (a) — reload-on-rename in place**

With the dev server running and the browser on slide `X`, rename by hand at the shell (Git Bash):

```bash
cd <deck>/slides
mv X.md X.cycletmp && mv X_v1.md X.md && mv X.cycletmp X_v1.md
```

Expected: the deck **hot-reloads** and the browser shows "VARIANT ONE" **on the same slide index** (does not jump to slide 1).
- If it does NOT reload: fallback A — `touch <deck>/slides.md` after the swap forces a reload. Record that the endpoint (Task 4) must `touch slides.md`.
- If it reloads but jumps to slide 1: fallback B — record that `shortcuts.ts` (Task 4) must call `$nav.go(current)` after the swap.

- [ ] **Step 4: Assumption (b) — per-slide source path is readable**

In the browser devtools console on the running deck, inspect the Slidev nav object for the current slide's source file path. Try:

```js
// In the browser console on the running Slidev deck:
__slidev__?.nav?.currentSlideRoute?.meta?.slide?.filepath
```

Expected: a path ending in `slides/<sid>.md`. If present, `shortcuts.ts` can derive `<sid>` from it (Task 4). If `undefined`, record that Task 4 must use the composer-emitted `<sid>` marker fallback (design §6.2) — note this and continue; it does not block Tasks 1–3.

- [ ] **Step 5: Record the result**

Write a one-paragraph note (in the PR description or a scratch file) stating: reload-on-rename works / needs fallback A or B; per-slide filepath available / needs marker fallback. Tasks 1–3 proceed regardless; Task 4 consumes this result.

---

## Task 1: Enumeration filter + `get-variants` (read side)

Add the canonical-vs-variant predicate, make `.md`-enumerators ignore variant files, and add the pure-read `get-variants` subcommand.

**Files:**
- Modify: `slidecraft/scripts/km.py` (add helpers near `slide_files` ~line 87; add `cmd_get_variants`; register subcommand in `main()` ~line 1691 and the dispatch dict ~line 1709)
- Test: `slidecraft/tests/test_km_variants.py` (new)

**Interfaces:**
- Produces:
  - `is_variant_file(stem: str) -> bool` — True iff `stem` ends in `_v<digits>`.
  - `variant_files(root: Path, sid: str) -> list[Path]` — ring order `[<sid>.md, <sid>_v1.md, …]`; `[]` if the canonical file is absent.
  - `cmd_get_variants(root: Path, a)` — prints `{"ok": true, "slide", "count", "files": [names]}`.
  - CLI: `python km.py get-variants --slide <sid>`.

- [ ] **Step 1: Write the failing test**

Create `slidecraft/tests/test_km_variants.py`:

```python
"""Tests for the D47 slide-variant mechanics (get-variants + cycle-variant)."""
from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

from slidecraft.scripts import km


def _slide(deck: Path, sid: str, body: str) -> None:
    """Write a canonical slide file + its shared state (bypassing compose)."""
    (deck / "slides").mkdir(exist_ok=True)
    (deck / "slides" / f"{sid}.md").write_text(body, encoding="utf-8")
    (deck / "slides" / f"{sid}.json").write_text(
        json.dumps({"slide_id": sid, "state": "composed", "title": sid}),
        encoding="utf-8")


def _variant(deck: Path, sid: str, n: int, body: str) -> None:
    (deck / "slides" / f"{sid}_v{n}.md").write_text(body, encoding="utf-8")


def test_is_variant_file():
    assert km.is_variant_file("intro--20260722-1_v1")
    assert km.is_variant_file("intro--20260722-1_v12")
    assert not km.is_variant_file("intro--20260722-1")        # canonical stamp
    assert not km.is_variant_file("a-b--20260722-120000-000")  # hyphens only


def test_get_variants_lists_canonical_then_siblings(deck, capsys):
    _slide(deck, "sX", "# canonical\n")
    _variant(deck, "sX", 2, "# two\n")
    _variant(deck, "sX", 1, "# one\n")
    capsys.readouterr()

    km.cmd_get_variants(deck, Namespace(slide="sX"))
    out = json.loads(capsys.readouterr().out)

    assert out["count"] == 3
    assert out["files"] == ["sX.md", "sX_v1.md", "sX_v2.md"]  # numeric order


def test_slide_files_and_validate_ignore_variants(deck, capsys):
    _slide(deck, "sX", "# canonical\n")
    _variant(deck, "sX", 1, "# alt\n")

    stems = {p.stem for p in km.slide_files(deck)}
    assert "sX" in stems
    assert "sX_v1" not in stems  # variant is invisible to the slide enumerator
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest slidecraft/tests/test_km_variants.py -q`
Expected: FAIL — `AttributeError: module 'km' has no attribute 'is_variant_file'`.

- [ ] **Step 3: Add the helpers and command in `km.py`**

Add near `slide_files` (after line ~89):

```python
VARIANT_RE = re.compile(r"_v\d+$")


def is_variant_file(stem: str) -> bool:
    """True when a slide-file stem is an alternative rendering (``<sid>_vN``),
    not a canonical slide. Canonical stems never end in ``_v<digits>`` — a title
    slug contains no underscore (slugify maps to hyphens), so the match is
    unambiguous (D47)."""
    return bool(VARIANT_RE.search(stem))


def variant_files(root: Path, sid: str) -> list[Path]:
    """A slide's renderings in ring order: canonical ``<sid>.md`` first, then
    ``<sid>_v1.md``, ``<sid>_v2.md`` … in numeric order. Empty when the
    canonical file is absent (D47)."""
    canonical = root / "slides" / f"{sid}.md"
    if not canonical.exists():
        return []
    sibs = [p for p in (root / "slides").glob(f"{sid}_v*.md")
            if re.fullmatch(rf"{re.escape(sid)}_v\d+", p.stem)]
    sibs.sort(key=lambda p: int(re.search(r"_v(\d+)$", p.stem).group(1)))
    return [canonical, *sibs]
```

Change `slide_files` (currently `return sorted((root / "slides").glob("*.md"))`) to:

```python
def slide_files(root: Path) -> list[Path]:
    # Variant files (<sid>_vN.md) are alternative renderings of an existing
    # slide, not slides — invisible to order/validate/budget (D47).
    return sorted(p for p in (root / "slides").glob("*.md")
                  if not is_variant_file(p.stem))
```

Add the command (near `cmd_validate`, before the dispatch section):

```python
def cmd_get_variants(root: Path, a):
    """Pure read: a slide's renderings (canonical + ``_vN``) by glob (D47)."""
    files = variant_files(root, a.slide)
    if not files:
        sys.exit(f"ERROR: slide {a.slide} has no canonical slide file")
    print(json.dumps({"ok": True, "slide": a.slide, "count": len(files),
                      "files": [p.name for p in files]}))
```

Register in `main()` — add beside the other `sub.add_parser` lines (~1706):

```python
    gv = sub.add_parser("get-variants"); gv.add_argument("--slide", required=True)
```

And add to the dispatch dict (~1716), before `"validate"`:

```python
     "get-variants": cmd_get_variants,
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest slidecraft/tests/test_km_variants.py -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Run the full km suite (no regressions from the `slide_files` change)**

Run: `python -m pytest slidecraft/tests/ -q`
Expected: PASS (all existing tests still green).

- [ ] **Step 6: Commit**

```bash
git add slidecraft/scripts/km.py slidecraft/tests/test_km_variants.py
git commit -m "feat(km): variant enumeration filter + get-variants (D47)"
```

---

## Task 2: `cycle-variant` — ring-rotate the active variant by rename

**Files:**
- Modify: `slidecraft/scripts/km.py` (add `CYCLE_TMP_SUFFIX`, `cmd_cycle_variant`; register subcommand)
- Test: `slidecraft/tests/test_km_variants.py` (extend)

**Interfaces:**
- Consumes: `variant_files` (Task 1).
- Produces:
  - `cmd_cycle_variant(root: Path, a)` where `a.slide: str`, `a.dir: "up"|"down"`. Prints `{"ok": true, "cycled": bool, "count": int, "dir"?}`. No-op (`cycled: false`) when `< 2` renderings.
  - CLI: `python km.py cycle-variant --slide <sid> --dir up|down`.

- [ ] **Step 1: Write the failing tests**

Append to `slidecraft/tests/test_km_variants.py`:

```python
def _bodies(deck: Path, sid: str) -> dict[str, str]:
    return {p.name: p.read_text(encoding="utf-8")
            for p in km.variant_files(deck, sid)}


def test_cycle_up_makes_v1_the_active(deck, capsys):
    _slide(deck, "sX", "CANON")
    _variant(deck, "sX", 1, "V1")
    _variant(deck, "sX", 2, "V2")
    capsys.readouterr()

    km.cmd_cycle_variant(deck, Namespace(slide="sX", dir="up"))
    out = json.loads(capsys.readouterr().out)

    assert out == {"ok": True, "cycled": True, "count": 3, "dir": "up"}
    b = _bodies(deck, "sX")
    assert b["sX.md"] == "V1"        # former _v1 is now active
    assert b["sX_v2.md"] == "CANON"  # former active rotated to the last slot
    assert set(b.values()) == {"CANON", "V1", "V2"}  # nothing lost


def test_cycle_up_three_times_returns_to_start(deck, capsys):
    _slide(deck, "sX", "CANON")
    _variant(deck, "sX", 1, "V1")
    _variant(deck, "sX", 2, "V2")
    before = _bodies(deck, "sX")
    for _ in range(3):
        km.cmd_cycle_variant(deck, Namespace(slide="sX", dir="up"))
    capsys.readouterr()
    assert _bodies(deck, "sX") == before


def test_cycle_down_is_inverse_of_up(deck, capsys):
    _slide(deck, "sX", "CANON")
    _variant(deck, "sX", 1, "V1")
    _variant(deck, "sX", 2, "V2")
    before = _bodies(deck, "sX")
    km.cmd_cycle_variant(deck, Namespace(slide="sX", dir="up"))
    km.cmd_cycle_variant(deck, Namespace(slide="sX", dir="down"))
    capsys.readouterr()
    assert _bodies(deck, "sX") == before


def test_cycle_noop_when_no_siblings(deck, capsys):
    _slide(deck, "sX", "CANON")
    capsys.readouterr()
    km.cmd_cycle_variant(deck, Namespace(slide="sX", dir="up"))
    out = json.loads(capsys.readouterr().out)
    assert out == {"ok": True, "cycled": False, "count": 1}


def test_cycle_leaves_slides_md_and_state_untouched(deck, capsys):
    _slide(deck, "sX", "CANON")
    _variant(deck, "sX", 1, "V1")
    slides_md = (deck / "slides.md").read_text(encoding="utf-8")
    state = (deck / "slides" / "sX.json").read_text(encoding="utf-8")
    km.cmd_cycle_variant(deck, Namespace(slide="sX", dir="up"))
    capsys.readouterr()
    assert (deck / "slides.md").read_text(encoding="utf-8") == slides_md
    assert (deck / "slides" / "sX.json").read_text(encoding="utf-8") == state
    assert not list((deck / "slides").glob("*.cycletmp"))  # scratch cleaned
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest slidecraft/tests/test_km_variants.py -q`
Expected: FAIL — `module 'km' has no attribute 'cmd_cycle_variant'`.

- [ ] **Step 3: Implement `cmd_cycle_variant`**

Add to `km.py` (near `cmd_get_variants`):

```python
CYCLE_TMP_SUFFIX = ".cycletmp"


def cmd_cycle_variant(root: Path, a):
    """Ring-rotate which of a slide's renderings is the canonical
    ``slides/<sid>.md``, among it + its ``_vN`` siblings, by rename (D47).

    ``up`` shifts forward (the next alternative becomes active); ``down`` is the
    exact inverse. ``Path.replace`` is atomic per rename; a single ``.cycletmp``
    scratch (not ``.md``, so no glob ever sees it) carries the file that would be
    overwritten first. ``slides.md`` and the shared state ``.json`` are never
    touched — the active file IS the selection."""
    sd = root / "slides"
    tmp = sd / f"{a.slide}{CYCLE_TMP_SUFFIX}"
    tmp.unlink(missing_ok=True)                 # clear a stale interrupted cycle
    paths = variant_files(root, a.slide)        # [canonical, _v1, …, _v(k-1)]
    if len(paths) < 2:
        print(json.dumps({"ok": True, "cycled": False, "count": len(paths)}))
        return
    if a.dir == "up":
        paths[0].replace(tmp)                   # active -> temp
        for i in range(1, len(paths)):
            paths[i].replace(paths[i - 1])      # _vi -> _v(i-1) (v1 -> active)
        tmp.replace(paths[-1])                  # old active -> last slot
    else:                                       # down: reverse cascade
        paths[-1].replace(tmp)                  # last -> temp
        for i in range(len(paths) - 1, 0, -1):
            paths[i - 1].replace(paths[i])      # _v(i-1) -> _vi (active -> v1)
        tmp.replace(paths[0])                   # old last -> active
    log(root, "km", "cycle-variant", slide=a.slide, dir=a.dir, count=len(paths))
    print(json.dumps({"ok": True, "cycled": True, "count": len(paths),
                      "dir": a.dir}))
```

Register in `main()`:

```python
    cv = sub.add_parser("cycle-variant"); cv.add_argument("--slide", required=True); cv.add_argument("--dir", required=True, choices=["up", "down"])
```

Dispatch dict:

```python
     "cycle-variant": cmd_cycle_variant,
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest slidecraft/tests/test_km_variants.py -q`
Expected: PASS (all Task 1 + Task 2 tests).

- [ ] **Step 5: Commit**

```bash
git add slidecraft/scripts/km.py slidecraft/tests/test_km_variants.py
git commit -m "feat(km): cycle-variant ring-rotate by rename (D47)"
```

---

## Task 3: Merge preserves predecessors as variants (evolves D31)

Change `cmd_merge` so predecessors (and their existing variants) are **renamed into the new slide's `_vN` variants** instead of being deleted. The fresh union compose (run by the orchestrator after merge, unchanged) stays the active canonical.

**Files:**
- Modify: `slidecraft/scripts/km.py` — `cmd_merge`, the predecessor-cleanup loop (currently ~lines 1478-1482, the `.unlink(...)` block)
- Test: `slidecraft/tests/test_km_variants.py` (extend)

**Interfaces:**
- Consumes: `variant_files` (Task 1).
- Produces: after `merge-slides`, the new slide `M` has `M.md` (skeleton, active) + `M_v1.md…M_vk.md` carrying each predecessor's renderings; predecessor `.json` files are removed; `associations.json[M]` = union of nuggets.

- [ ] **Step 1: Write the failing test**

Append to `slidecraft/tests/test_km_variants.py`:

```python
def _nugget(deck: Path, nid: str) -> None:
    (deck / "nuggets").mkdir(exist_ok=True)
    (deck / "nuggets" / f"{nid}.json").write_text(json.dumps(
        {"nugget_id": nid, "kind": "text", "source": "s.md", "page": 1,
         "title": nid, "information": "i", "raw_text": "r"}), encoding="utf-8")


def test_merge_preserves_predecessors_as_variants(deck, capsys):
    # Two content slides A (with its own variant) and B.
    _nugget(deck, "n1"); _nugget(deck, "n2")
    km.cmd_create(deck, Namespace(title="A", nuggets="n1", after="end",
                                  parked=False, intended_function=None))
    km.cmd_create(deck, Namespace(title="B", nuggets="n2", after="end",
                                  parked=False, intended_function=None))
    capsys.readouterr()
    a_id = next(p.stem for p in km.slide_files(deck) if p.stem.startswith("a--"))
    b_id = next(p.stem for p in km.slide_files(deck) if p.stem.startswith("b--"))
    # Give A a hand-made alternative rendering.
    (deck / "slides" / f"{a_id}.md").write_text("A-CANON", encoding="utf-8")
    (deck / "slides" / f"{a_id}_v1.md").write_text("A-ALT", encoding="utf-8")
    (deck / "slides" / f"{b_id}.md").write_text("B-CANON", encoding="utf-8")

    km.cmd_merge(deck, Namespace(slides=f"{a_id},{b_id}", title="Merged"))
    out = json.loads(capsys.readouterr().out)
    m_id = out["slide_id"]

    # Predecessor .md/.json gone; merged slide has 3 variant renderings.
    assert not (deck / "slides" / f"{a_id}.md").exists()
    assert not (deck / "slides" / f"{a_id}.json").exists()
    assert not (deck / "slides" / f"{b_id}.json").exists()
    variant_bodies = {p.read_text(encoding="utf-8")
                      for p in km.variant_files(deck, m_id)[1:]}  # the _vN
    assert variant_bodies == {"A-CANON", "A-ALT", "B-CANON"}
    # Union association + single active slide in order.
    assoc = json.loads((deck / "associations.json").read_text(encoding="utf-8"))
    assert assoc[m_id] == ["n1", "n2"]
    assert km.order(deck).count(m_id) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest slidecraft/tests/test_km_variants.py::test_merge_preserves_predecessors_as_variants -q`
Expected: FAIL — the predecessor `.md` is deleted, so `variant_files(m_id)` has no `_vN` and the body-set assertion fails.

- [ ] **Step 3: Change the predecessor loop in `cmd_merge`**

Replace the current cleanup loop (the block that unlinks predecessor `.md`/`.json`):

```python
    for s in parts:
        (root / "slides" / f"{s}.md").unlink(missing_ok=True)
        (root / "slides" / f"{s}.json").unlink(missing_ok=True)
        A.pop(s, None)
        if s in ids: ids.remove(s)
```

with:

```python
    # D47: preserve each predecessor (and its existing variants) as a variant of
    # the new merged slide, for provenance — the user can cycle back to see what
    # was merged. The fresh union compose (orchestrator runs it after merge, D31)
    # stays the active canonical <sid>.md. Renames only; the state .json is
    # subsumed by the merged slide's single shared state file.
    vn = 0
    for s in parts:
        for rendering in variant_files(root, s):   # canonical + its _vN, in order
            vn += 1
            rendering.replace(root / "slides" / f"{sid}_v{vn}.md")
        (root / "slides" / f"{s}.json").unlink(missing_ok=True)
        A.pop(s, None)
        if s in ids: ids.remove(s)
```

(Note: `sid` and `ids` are already defined above this loop in `cmd_merge`; `sid` is the new merged slide id whose skeleton `sid.md` was already written, so it stays the canonical active file.)

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest slidecraft/tests/test_km_variants.py::test_merge_preserves_predecessors_as_variants -q`
Expected: PASS.

- [ ] **Step 5: Run the full suite (merge is exercised elsewhere)**

Run: `python -m pytest slidecraft/tests/ -q`
Expected: PASS. If a pre-existing merge test asserted predecessor `.md` deletion, update it to assert the predecessor is now a `_vN` of the merged slide (search: `git grep -n "unlink\|merged_from\|cmd_merge" slidecraft/tests/`).

- [ ] **Step 6: Commit**

```bash
git add slidecraft/scripts/km.py slidecraft/tests/test_km_variants.py
git commit -m "feat(km): merge preserves predecessors as variants (D47, evolves D31)"
```

---

## Task 4: Scaffold the browser wiring (Vite endpoint + ↑/↓ shortcuts)

Add the two dev-server pieces to the deck scaffold: a Vite `configureServer` endpoint that shells out to `km`, and a `setup/shortcuts.ts` that remaps ↑/↓ to POST a cycle. Unit-test that the scaffold writes them; verify behavior manually in the browser (consuming Task 0's spike result for any fallback).

**Files:**
- Create: `slidecraft/templates/slidev-base/vite.config.ts`
- Create: `slidecraft/templates/slidev-base/setup/shortcuts.ts`
- Modify: `slidecraft/scripts/scaffold_deck.py` — add a `write_variant_scaffold(root, created)` helper and call it from `scaffold` (beside `write_launchers`, ~line 441/467)
- Test: `slidecraft/tests/test_scaffold_deck.py` (extend)

**Interfaces:**
- Consumes: `km get-variants` / `km cycle-variant` (Tasks 1-2) via subprocess.
- Produces: a scaffolded deck containing `vite.config.ts` + `setup/shortcuts.ts`.

- [ ] **Step 1: Write the failing test**

Add to `slidecraft/tests/test_scaffold_deck.py` (match its existing scaffold-fixture style):

```python
def test_scaffold_writes_variant_browser_wiring(tmp_path):
    from slidecraft.scripts import scaffold_deck
    deck = tmp_path / "deck"
    deck.mkdir()
    scaffold_deck.scaffold(deck, _minimal_answers(tmp_path))  # reuse this file's helper

    assert (deck / "vite.config.ts").exists()
    assert (deck / "setup" / "shortcuts.ts").exists()
    vite = (deck / "vite.config.ts").read_text(encoding="utf-8")
    assert "/__variant" in vite            # the cycle endpoint
    assert "cycle-variant" in vite         # shells out to km
```

(If `test_scaffold_deck.py` has no `_minimal_answers`, reuse the `ANSWERS`/theme setup already in that file or in `conftest.py`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest slidecraft/tests/test_scaffold_deck.py::test_scaffold_writes_variant_browser_wiring -q`
Expected: FAIL — files not created.

- [ ] **Step 3: Create the Vite endpoint template**

Create `slidecraft/templates/slidev-base/vite.config.ts`:

```ts
// Slidecraft variant-cycling endpoint (D47). Slidev merges this Vite config.
// GET  /__variants?slide=<sid>   -> km get-variants
// POST /__variant  {slide, dir}  -> km cycle-variant  (rename in place)
// km path: SLIDECRAFT_KM env, else the default install location.
import { defineConfig } from 'vite'
import { spawnSync } from 'node:child_process'
import { homedir } from 'node:os'
import { join } from 'node:path'

const KM = process.env.SLIDECRAFT_KM
  || join(homedir(), '.claude', 'slidecraft', 'scripts', 'km.py')

function km(args: string[]) {
  const r = spawnSync('python', [KM, '--deck', process.cwd(), ...args],
    { encoding: 'utf-8' })
  return { code: r.status ?? 1, out: (r.stdout || '').trim(), err: r.stderr || '' }
}

export default defineConfig({
  plugins: [{
    name: 'slidecraft-variants',
    configureServer(server) {
      server.middlewares.use('/__variants', (req, res) => {
        const slide = new URL(req.url || '', 'http://x').searchParams.get('slide') || ''
        const r = km(['get-variants', '--slide', slide])
        res.setHeader('Content-Type', 'application/json')
        res.statusCode = r.code === 0 ? 200 : 404
        res.end(r.code === 0 ? r.out : JSON.stringify({ ok: false, err: r.err }))
      })
      server.middlewares.use('/__variant', (req, res) => {
        if (req.method !== 'POST') { res.statusCode = 405; return res.end() }
        let body = ''
        req.on('data', (c) => (body += c))
        req.on('end', () => {
          const { slide, dir } = JSON.parse(body || '{}')
          const r = km(['cycle-variant', '--slide', slide, '--dir', dir])
          res.setHeader('Content-Type', 'application/json')
          res.statusCode = r.code === 0 ? 200 : 400
          res.end(r.code === 0 ? r.out : JSON.stringify({ ok: false, err: r.err }))
        })
      })
    },
  }],
})
```

> **Task 0 fallback A:** if the spike found the deck does not reload on rename, append `km(['--', 'noop'])`-style `touch` — simplest: after a successful cycle, `spawnSync` a touch of `slides.md`: `spawnSync('node', ['-e', 'require("fs").utimesSync("slides.md", new Date(), new Date())'])`. Add only if the spike required it.

- [ ] **Step 4: Create the shortcuts template**

Create `slidecraft/templates/slidev-base/setup/shortcuts.ts`:

```ts
// Slidecraft: remap ArrowUp/ArrowDown to audition slide variants in place (D47).
// On a slide with >1 rendering, Up/Down POST a cycle and Slidev reloads the
// swapped include; on a normal slide they fall through to Slidev's default nav.
import { defineShortcutsSetup } from '@slidev/types'

function sidOf(nav: any): string | null {
  // Task 0 assumption (b): current slide's source file path -> <sid>.
  const fp = nav?.currentSlideRoute?.meta?.slide?.filepath as string | undefined
  if (!fp) return null           // fallback: use the composer-emitted marker (spike result)
  const m = fp.replace(/\\/g, '/').match(/slides\/(.+?)\.md$/)
  return m ? m[1] : null
}

async function count(sid: string): Promise<number> {
  try {
    const r = await fetch(`/__variants?slide=${encodeURIComponent(sid)}`)
    if (!r.ok) return 1
    return (await r.json()).count ?? 1
  } catch { return 1 }
}

export default defineShortcutsSetup((nav: any, base: any[]) => {
  async function cycle(dir: 'up' | 'down', fallback: () => void) {
    const sid = sidOf(nav)
    if (!sid || (await count(sid)) < 2) return fallback()   // normal nav
    await fetch('/__variant', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ slide: sid, dir }),
    })
    // Slidev reloads on the file swap; URL keeps the slide index. If the spike
    // found it jumps to slide 1, uncomment: nav.go(nav.currentPage)
  }
  return [
    ...base,
    { key: 'up', fn: () => cycle('up', () => nav.prevSlide()), autoRepeat: true },
    { key: 'down', fn: () => cycle('down', () => nav.nextSlide()), autoRepeat: true },
  ]
})
```

> Confirm the exact `@slidev/types` shortcut hook name/signature against the installed Slidev version during the manual step; adjust `defineShortcutsSetup` / `nav` fields to match. The structure (return `{key, fn}` bindings, fall through to `nav.prevSlide/nextSlide`) is what matters.

- [ ] **Step 5: Copy them in the scaffold**

In `slidecraft/scripts/scaffold_deck.py`, add a helper modeled on `write_launchers` (which copies from `Path(__file__).resolve().parent.parent / "templates"`):

```python
def write_variant_scaffold(root: Path, created: list):
    """Copy the D47 variant-cycling dev-server wiring into the deck:
    vite.config.ts (the /__variant endpoint) + setup/shortcuts.ts (↑/↓ remap)."""
    base = Path(__file__).resolve().parent.parent / "templates" / "slidev-base"
    (root / "setup").mkdir(exist_ok=True)
    for rel in ("vite.config.ts", "setup/shortcuts.ts"):
        tpl = base / rel
        dest = root / rel
        if tpl.is_file():
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(tpl, dest)
            created.append(str(dest.relative_to(root)))
        else:
            created.append(f"(WARNING: variant template not found at {tpl})")
```

Call it from `scaffold` right after `write_launchers(root, created)` (the full-scaffold path, ~line 467 — NOT the `--prewarm` path):

```python
    write_variant_scaffold(root, created)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest slidecraft/tests/test_scaffold_deck.py -q`
Expected: PASS.

- [ ] **Step 7: Manual browser verification (the real proof)**

Scaffold a fresh deck, add 2-3 `_vN` files to one slide by hand (as in Task 0), start the dev server, and:
- Navigate to that slide; press ↑ — the alternative renders in place; press ↑ again — the next; ↓ walks back.
- Navigate to a slide with **no** variants; ↑/↓ still navigate slides normally.
- Leave a slide on your chosen variant, stop the server, confirm `slides/<sid>.md` holds that variant's body (so `slides.md` renders it).

Apply any Task 0 fallback (touch `slides.md`, or `nav.go(current)`) if needed. Capture a screenshot of a cycled slide as proof.

- [ ] **Step 8: Commit**

```bash
git add slidecraft/templates/slidev-base/ slidecraft/scripts/scaffold_deck.py slidecraft/tests/test_scaffold_deck.py
git commit -m "feat(scaffold): variant-cycling dev-server endpoint + up/down shortcuts (D47)"
```

---

## Self-review notes (author)

- **Spec coverage:** design §2 filename convention → Task 1; §4 enumeration filter → Task 1; §5.1 get-variants → Task 1; §5.2 cycle-variant → Task 2; §7 merge → Task 3; §6 browser wiring → Task 4; §9 spike → Task 0. All covered.
- **Type consistency:** `is_variant_file(stem)`, `variant_files(root, sid) -> list[Path]`, `cmd_get_variants`/`cmd_cycle_variant(root, a)`, `CYCLE_TMP_SUFFIX` — used identically across Tasks 1-3.
- **Deferred (out of scope, per Global Constraints):** variant *creation* from composer lanes; a `<VariantPicker>` overlay; per-variant `concept_type`. Not in any task by design.
