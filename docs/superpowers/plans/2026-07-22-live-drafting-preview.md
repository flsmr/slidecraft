# Live Drafting Preview & Progress Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `/draft-deck` observable — run the Slidev dev server live during drafting, render informative skeletons for not-yet-composed slides, and show phase progress on a transient, uncounted status slide.

**Architecture:** Reuse mechanisms that already exist. `create-slide` already writes a skeleton and rewrites `slides.md` (`km.py:1287`), and the compose step overwrites it — so slides already appear then fill at the file level; nothing watches them. We (1) enrich the skeleton with the distilled nugget info + a "drafting" banner, (2) add a transient `.draft-status.json` that `write_order` renders as an **inline, uncounted** status slide at the front (same "not a slide file" trick as the backup divider, `km.py:145`), and (3) add a `serve_deck.py` helper that `/draft-deck` launches in the background to install-if-needed then serve. Slidev's Vite HMR reflects each `slides.md` rewrite live.

**Tech Stack:** Python 3.13 (stdlib only — `argparse`, `subprocess`, `socket`, `pathlib`, `json`), pytest, Node/npm + Slidev (invoked as a subprocess). Windows-first (PowerShell) but code stays cross-platform.

## Global Constraints

- **Deck root is CWD**; every script resolves the deck by walking up for `deck-context.json` (`find_deck_root`, `km.py:46`). Tests scaffold a real tmp deck — never mock deck state.
- **Payloads travel as files, never CLI args** (D28) — not directly relevant here but keep new subcommands flag-based.
- **`km` never writes slide prose** — the status slide and skeleton are mechanical assembly of *already-distilled* miner `information`, the same carve-out as `digest_body`/presenter-notes (D39/D46). No composition in `km`.
- **The literal marker `awaiting composition` MUST remain in the skeleton body** — `needs_composition()` (`km.py:194`) keys off that exact substring for park/unpark. The skeleton MUST NOT emit `DIGEST_MARK` (`"backup digest"`, defined near `km.py:186`), which would make an active skeleton read as a parked digest.
- **The status slide must never consume a budget slot** — it is inline markdown in `slides.md`, not a `src:` import and not a slide file, so `order()` (`km.py:90`), the budget gate, and `validate` never see it.
- **File encoding:** always `encoding="utf-8"` on writes (repo runs on OneDrive/Windows; BOM tolerated on reads via `utf-8-sig` where the code already does so).
- **No new dependencies.** Everything is Python stdlib + the existing Slidev toolchain.
- **Run the full suite** after each task: `python -m pytest slidecraft/tests -q` (from repo root). The repo already has `pytest.ini`.

---

### Task 1: Rich skeletons — shared `nugget_info_section` helper + enriched `skeleton()`

Factor the distilled-`information` rendering out of `digest_body` into a shared helper, then make `skeleton()` show that info under a "Composer is drafting" banner. `skeleton()` gains a `root` parameter (it must load nuggets), so all three call sites are updated.

**Files:**
- Modify: `slidecraft/scripts/km.py` — `skeleton` (`:189`), `digest_body` (`:1553`), 3 skeleton call sites (`:1319`, `:1392`, `:1471`); add `nugget_info_section`.
- Test: `slidecraft/tests/test_km_skeleton.py` (new)

**Interfaces:**
- Produces:
  - `nugget_info_section(root: Path, title: str, nugget_ids: list[str]) -> str` — markdown body section: a `# <title>` heading, then per-nugget (`## <nugget title>` when >1 nugget) the nugget's `information`. No frontmatter, no markers, no notes.
  - `skeleton(root: Path, title: str, nugget_ids: list[str]) -> str` — **signature changed** (added `root` as first arg). Returns frontmatter + drafting banner + `awaiting composition` comment + `nugget_info_section(...)`.
  - `digest_body(root, title, nugget_ids) -> str` — unchanged signature and unchanged output bytes; internally now calls `nugget_info_section`.

- [ ] **Step 1: Write the failing test**

Create `slidecraft/tests/test_km_skeleton.py`:

```python
"""Rich skeletons (2026-07-22 live-drafting-preview): a created-but-uncomposed
slide shows the distilled nugget information + a 'drafting' banner, and still
trips needs_composition(). digest_body keeps byte-identical output via the
shared nugget_info_section helper."""
from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

from slidecraft.scripts import km
from slidecraft.tests.conftest import deck  # noqa: F401  (pytest fixture)


def _seed_nugget(deck: Path, nid: str, title: str, info: str,
                 raw: str = "verbatim source line") -> str:
    (deck / "nuggets").mkdir(exist_ok=True)
    (deck / "nuggets" / f"{nid}.json").write_text(json.dumps({
        "nugget_id": nid, "kind": "text", "title": title,
        "information": info, "raw_text": raw, "source": "chapter_4.md",
        "page": 1,
    }), encoding="utf-8")
    return nid


def test_skeleton_shows_banner_and_info_and_trips_needs_composition(deck):
    n1 = _seed_nugget(deck, "n-1", "Tracking", "- estimates object state")
    body = km.skeleton(deck, "Core idea", [n1])
    assert km.needs_composition(body) is True          # marker preserved
    assert "Composer is drafting" in body              # visible banner
    assert "estimates object state" in body            # distilled info shown
    assert km.DIGEST_MARK not in body                  # NOT a parked digest
    assert body.lstrip().startswith("---")             # valid Slidev frontmatter


def test_skeleton_with_no_nuggets_is_still_a_valid_placeholder(deck):
    body = km.skeleton(deck, "Cover", [])
    assert km.needs_composition(body) is True
    assert "# Cover" in body


def test_nugget_info_section_is_the_shared_source_of_truth(deck):
    n1 = _seed_nugget(deck, "n-1", "A", "- alpha")
    n2 = _seed_nugget(deck, "n-2", "B", "- beta")
    section = km.nugget_info_section(deck, "T", [n1, n2])
    # digest_body embeds the same section verbatim.
    assert section in km.digest_body(deck, "T", [n1, n2])
    assert "alpha" in section and "beta" in section
    assert "## A" in section and "## B" in section     # subtitles when multi
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest slidecraft/tests/test_km_skeleton.py -q`
Expected: FAIL — `km.skeleton()` takes 2 args not 3 (TypeError), and `nugget_info_section` does not exist (AttributeError).

- [ ] **Step 3: Add `nugget_info_section` and rewrite `digest_body` to use it**

In `km.py`, replace the body of `digest_body` (`:1553`) and add the helper just above it:

```python
def nugget_info_section(root: Path, title: str, nugget_ids: list[str]) -> str:
    """Distilled `information` for each nugget as a markdown section: an
    `# <title>` heading, then per-nugget (a `## <nugget title>` subhead when
    there is more than one) the nugget's already-distilled `information`. The
    single source of truth for "show the knowledge" — shared by digest_body
    (Backup preview, D46) and skeleton (awaiting-composition placeholder). No
    frontmatter, no markers, no speaker notes — the callers wrap it."""
    nugs = [n for n in (load_nugget(root, nid) for nid in nugget_ids) if n]
    parts = [f"\n# {title}\n"]
    multi = len(nugs) > 1
    for n in nugs:
        if multi:
            parts.append(f"\n## {n.get('title', '')}\n")
        info = str(n.get("information", "")).strip()
        if info:
            parts.append("\n" + info + "\n")
    return "".join(parts)


def digest_body(root: Path, title: str, nugget_ids: list[str]) -> str:
    """A deterministic preview body for a Backup slide (D46): the miner's
    distilled `information` per nugget, so a human roughly knows what the parked
    knowledge is about. NOT composed prose. Verbatim source rides in speaker
    notes. Carries :data:`DIGEST_MARK` so park/unpark can tell it from a real
    slide."""
    nugs = [n for n in (load_nugget(root, nid) for nid in nugget_ids) if n]
    body = (f"---\nlayout: default\ntitle: {yaml_str(title)}\n---\n"
            f"<!-- {DIGEST_MARK}: distilled nugget information, awaiting review -->\n"
            + nugget_info_section(root, title, nugget_ids))
    notes = [f"[{nugget_locator(n)}]\n{raw}"
             for n in nugs if (raw := nugget_raw(n))]
    if notes:
        body = body.rstrip() + "\n\n" + notes_comment(
            "Source material (verbatim) — presenter reference:\n\n"
            + "\n\n".join(notes))
    return body
```

- [ ] **Step 4: Enrich `skeleton()` (signature change)**

Replace `skeleton` (`km.py:189`):

```python
def skeleton(root: Path, title: str, nugget_ids: list[str]) -> str:
    """Placeholder body for a created-but-uncomposed slide. Shows a banner and
    the distilled nugget information, so a live-watched deck reveals what the
    slide will be about while the composer works. Keeps the literal
    `awaiting composition` marker (inside a comment) that needs_composition()
    keys off; MUST NOT emit DIGEST_MARK (that reads as a parked digest)."""
    return (f"---\nlayout: default\ntitle: {yaml_str(title)}\n---\n\n"
            f"> 🚧 **Composer is drafting this slide…**\n"
            f"<!-- awaiting composition; nuggets: {','.join(nugget_ids)} -->\n"
            + nugget_info_section(root, title, nugget_ids))
```

- [ ] **Step 5: Update the three `skeleton()` call sites to pass `root`**

`km.py:1319` (in `cmd_create`):

```python
    initial_body = (digest_body(root, a.title, nugs) if parked_flag
                    else skeleton(root, a.title, nugs))
```

`km.py:1392` (the unpark reset path) — currently `sp.write_text(skeleton(stj.get("title", sid), ...))`; add `root`:

```python
        sp.write_text(skeleton(root, stj.get("title", sid),
                               assoc(root).get(sid, [])), encoding="utf-8")
```

(Confirm the exact nugget-ids expression already present at that call; keep it, only prepend `root`.)

`km.py:1471` (the merge path):

```python
    (root / "slides" / f"{sid}.md").write_text(
        skeleton(root, title, merged_nugs), encoding="utf-8")
```

- [ ] **Step 6: Run the new test + the full suite**

Run: `python -m pytest slidecraft/tests/test_km_skeleton.py slidecraft/tests/test_km_plan.py -q`
Expected: PASS. Then `python -m pytest slidecraft/tests -q` — Expected: all PASS (existing `needs_composition` and colon-title-in-skeleton tests still green; the skeleton is longer now but the colon test only checks the frontmatter `title:` line, which is unchanged).

- [ ] **Step 7: Commit**

```bash
git add slidecraft/scripts/km.py slidecraft/tests/test_km_skeleton.py
git commit -m "feat(km): rich skeletons show distilled nugget info + drafting banner

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Transient status slide — `set-status` / `clear-status` + `write_order` branch

Add a `.draft-status.json`-driven inline status slide at the front of `slides.md`, plus the two subcommands the orchestrator calls. The status block is inline markdown, so it never counts against the budget.

**Files:**
- Modify: `slidecraft/scripts/km.py` — `write_order` (`:145`); add `status_block`, `cmd_set_status`, `cmd_clear_status`; register subparsers (`:1706`) + dispatch (`:1716`).
- Modify: `slidecraft/scripts/scaffold_deck.py` — none here (gitignore is Task 4).
- Test: `slidecraft/tests/test_km_status.py` (new)

**Interfaces:**
- Consumes: `order(root)`, `write_order(root, ids)` from km.
- Produces:
  - `status_block(root: Path) -> str` — the inline status markdown (no frontmatter fences; it is body content placed after the headmatter). Returns `""` when `.draft-status.json` is absent or unreadable.
  - `cmd_set_status(root, a)` — writes `.draft-status.json` (`phase`, `detail`, `label`, `updated_at`) and rewrites `slides.md`. CLI: `set-status --phase P [--detail D] [--label L]`.
  - `cmd_clear_status(root, a)` — deletes `.draft-status.json` and rewrites `slides.md`. CLI: `clear-status`.

- [ ] **Step 1: Write the failing test**

Create `slidecraft/tests/test_km_status.py`:

```python
"""Transient status slide (2026-07-22 live-drafting-preview): an inline,
uncounted status block at the FRONT of slides.md while drafting, removed on
clear. It must never change order()/the slide budget."""
from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from slidecraft.scripts import km
from slidecraft.tests.conftest import deck  # noqa: F401


def _create(deck: Path, title: str) -> str:
    import contextlib, io, json
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        km.cmd_create(deck, Namespace(title=title, nuggets="", after="end",
                                      parked=False, intended_function=None))
    return json.loads(buf.getvalue())["slide_id"]


def test_set_status_adds_uncounted_front_block(deck, capsys):
    a = _create(deck, "Alpha")
    b = _create(deck, "Beta")
    capsys.readouterr()
    before = km.order(deck)

    km.cmd_set_status(deck, Namespace(phase="compose", detail="1/2",
                                      label="Composing slides…"))
    capsys.readouterr()

    md = (deck / "slides.md").read_text(encoding="utf-8")
    assert "Composing slides…" in md                   # status visible
    assert km.order(deck) == before                    # SAME active slides
    assert len(km.order(deck)) == 2                     # budget unchanged
    # The status block appears before the first real slide import.
    assert md.index("Composing slides…") < md.index(f"src: ./slides/{a}.md")


def test_status_block_when_no_slides_yet(deck, capsys):
    # During mining there are no slides; slides.md is status-only.
    km.cmd_set_status(deck, Namespace(phase="mine", detail="1/3",
                                      label="Mining sources…"))
    capsys.readouterr()
    md = (deck / "slides.md").read_text(encoding="utf-8")
    assert "Mining sources…" in md
    assert km.order(deck) == []
    assert "src: ./slides/" not in md


def test_clear_status_removes_the_block_cleanly(deck, capsys):
    a = _create(deck, "Alpha")
    km.cmd_set_status(deck, Namespace(phase="compose", detail="1/1", label="x"))
    km.cmd_clear_status(deck, Namespace())
    capsys.readouterr()
    md = (deck / "slides.md").read_text(encoding="utf-8")
    assert "Composing" not in md and "Temporary drafting status" not in md
    assert not (deck / ".draft-status.json").exists()
    assert km.order(deck) == [a]                        # untouched
    # The cover fold is restored: the slide is imported normally again.
    assert f"src: ./slides/{a}.md" in md
    assert md.startswith("---")                         # headmatter first, not a status body


def test_clear_status_is_noop_without_file(deck, capsys):
    _create(deck, "Alpha")
    km.cmd_clear_status(deck, Namespace())             # must not raise
    capsys.readouterr()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest slidecraft/tests/test_km_status.py -q`
Expected: FAIL — `cmd_set_status` / `cmd_clear_status` / `status_block` do not exist.

- [ ] **Step 3: Add `status_block` and the status branch in `write_order`**

In `km.py`, add above `write_order` (`:145`):

```python
STATUS_FILE = ".draft-status.json"


def status_block(root: Path) -> str:
    """Inline markdown for the transient status slide (body content placed after
    the headmatter block, so it becomes slide 1). Empty string when there is no
    `.draft-status.json` — the sole trigger. Never a `src:` import and never a
    slide file, so order()/budget/validate never count it."""
    p = root / STATUS_FILE
    if not p.exists():
        return ""
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return ""
    label = str(d.get("label", "")).strip() or "Drafting…"
    phase = str(d.get("phase", "")).strip()
    detail = str(d.get("detail", "")).strip()
    phase_line = " ".join(x for x in (phase, detail) if x)
    lines = [f"# ⏳ {label}", ""]
    if phase_line:
        lines.append(f"**Phase:** {phase_line}")
        lines.append("")
    lines.append("_Temporary drafting status — removed when the deck is done._")
    return "\n".join(lines) + "\n"
```

Then modify `write_order` (`:145`). Replace the head/body construction (the block from `head_lines = [...]` through the `body = ...` line, currently `:155`–`:160`) with a status-aware version:

```python
    head_lines = [f"theme: {theme_ref}", f"title: {title}"]
    head_lines += preserved_headmatter_lines(root)
    status = status_block(root)
    if status:
        # Status slide is slide 1 (the headmatter block's own body); do NOT
        # fold a slide src into the headmatter. Every real slide follows as a
        # src import (including what would have been the folded first slide).
        head = "---\n" + "\n".join(head_lines) + "\n---\n\n" + status + "\n"
        body = "".join(f"\n---\nsrc: ./slides/{i}.md\n---\n" for i in ids)
    else:
        if ids:
            head_lines.append(f"src: ./slides/{ids[0]}.md")
        head = "---\n" + "\n".join(head_lines) + "\n---\n"
        body = "".join(f"\n---\nsrc: ./slides/{i}.md\n---\n" for i in ids[1:])
```

(The parked-tail block that follows is unchanged.)

- [ ] **Step 4: Add the two command functions**

Add near the other `cmd_*` functions in `km.py` (e.g. just after `cmd_create`):

```python
def cmd_set_status(root: Path, a):
    data = {"phase": a.phase, "detail": getattr(a, "detail", "") or "",
            "label": getattr(a, "label", "") or "",
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    (root / STATUS_FILE).write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8")
    write_order(root, order(root))
    log(root, "orchestrator", "set-status", **data)
    print(json.dumps({"status": "set", **data}, ensure_ascii=False))


def cmd_clear_status(root: Path, a):
    p = root / STATUS_FILE
    existed = p.exists()
    if existed:
        p.unlink()
    write_order(root, order(root))
    log(root, "orchestrator", "clear-status", existed=existed)
    print(json.dumps({"status": "cleared", "existed": existed}))
```

- [ ] **Step 5: Register subparsers + dispatch**

In `main()`, after the `set-content` parser (`km.py:1705`) and before `sub.add_parser("validate")`:

```python
    stp = sub.add_parser("set-status"); stp.add_argument("--phase", required=True); stp.add_argument("--detail", default=""); stp.add_argument("--label", default="")
    sub.add_parser("clear-status")
```

In the dispatch dict (`km.py:1716`), add entries:

```python
     "set-status": cmd_set_status, "clear-status": cmd_clear_status,
```

- [ ] **Step 6: Run the new test + full suite**

Run: `python -m pytest slidecraft/tests/test_km_status.py -q`
Expected: PASS.
Run: `python -m pytest slidecraft/tests -q`
Expected: all PASS (write_order's non-status path is byte-identical to before, so existing headmatter/theme tests stay green).

- [ ] **Step 7: Commit**

```bash
git add slidecraft/scripts/km.py slidecraft/tests/test_km_status.py
git commit -m "feat(km): transient uncounted status slide (set-status/clear-status)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: `serve_deck.py` — ensure-ready + background serve with reuse

A cross-platform helper `/draft-deck` launches in the background. Its decision logic (readiness, reuse) is pure and unit-tested; the `npx slidev` spawn + browser open is the thin, documented tail.

**Files:**
- Create: `slidecraft/scripts/serve_deck.py`
- Test: `slidecraft/tests/test_serve_deck.py` (new)

**Interfaces:**
- Produces:
  - `slidev_bin(root: Path) -> Path | None` — the installed slidev binary (`node_modules/.bin/slidev.cmd` on Windows, `slidev` elsewhere) or `None`.
  - `npm_executable() -> str | None` — `shutil.which("npm")` (or `npm.cmd`).
  - `ensure_ready(root, *, poll_attempts=120, poll_interval=1.0, sleep=time.sleep, bin_check=slidev_bin, npm_lookup=npm_executable, runner=subprocess.run) -> str` — returns `"ready" | "no-npm" | "install-failed"`.
  - `read_pidfile(root) -> dict | None`, `write_pidfile(root, pid: int, port: int) -> None`.
  - `pid_alive(pid: int) -> bool`, `port_open(port: int, host="127.0.0.1", timeout=0.3) -> bool`.
  - `server_status(root, *, alive=pid_alive, is_port_open=port_open) -> tuple[str, dict | None]` — `("live"|"stale"|"none", pidfile_or_None)`.
  - `main(argv=None) -> int` — CLI; prints one JSON line (`served`|`reused`|`no-preview`); exit 0 on served/reused, non-zero on no-preview.

- [ ] **Step 1: Write the failing test**

Create `slidecraft/tests/test_serve_deck.py`:

```python
"""serve_deck decision logic (2026-07-22 live-drafting-preview). The npx-slidev
spawn is not exercised here; the readiness + reuse decisions are."""
from __future__ import annotations

import json
from pathlib import Path

from slidecraft.scripts import serve_deck


def _mk_deck(tmp_path: Path) -> Path:
    (tmp_path / "logs").mkdir()
    (tmp_path / "slides.md").write_text("---\ntheme: default\n---\n",
                                        encoding="utf-8")
    return tmp_path


def _make_bin(root: Path) -> Path:
    d = root / "node_modules" / ".bin"
    d.mkdir(parents=True)
    b = d / ("slidev.cmd" if serve_deck.IS_WINDOWS else "slidev")
    b.write_text("", encoding="utf-8")
    return b


def test_ready_when_bin_present(tmp_path):
    root = _mk_deck(tmp_path)
    _make_bin(root)
    calls = []
    assert serve_deck.ensure_ready(
        root, sleep=lambda _s: calls.append("sleep"),
        runner=lambda *a, **k: calls.append("run")) == "ready"
    assert calls == []                                  # no poll, no install


def test_polls_then_ready_when_install_in_flight(tmp_path):
    root = _mk_deck(tmp_path)
    (root / "node_modules").mkdir()                     # npm started; no bin yet
    seq = [None, None, root / "node_modules" / ".bin" / "slidev"]
    it = iter(seq)
    ran = []
    status = serve_deck.ensure_ready(
        root, poll_attempts=5, sleep=lambda _s: None,
        bin_check=lambda _r: next(it),
        runner=lambda *a, **k: ran.append(a) or _Rc(0))
    assert status == "ready"
    assert ran == []                                    # never installed ourselves


def test_installs_when_no_node_modules(tmp_path):
    root = _mk_deck(tmp_path)

    def fake_run(cmd, **k):
        _make_bin(root)                                 # the install "succeeds"
        return _Rc(0)

    assert serve_deck.ensure_ready(
        root, sleep=lambda _s: None,
        npm_lookup=lambda: "npm", runner=fake_run) == "ready"


def test_no_npm_returns_no_npm(tmp_path):
    root = _mk_deck(tmp_path)
    assert serve_deck.ensure_ready(
        root, sleep=lambda _s: None, npm_lookup=lambda: None,
        runner=lambda *a, **k: _Rc(0)) == "no-npm"


def test_install_failure_returns_install_failed(tmp_path):
    root = _mk_deck(tmp_path)
    assert serve_deck.ensure_ready(
        root, sleep=lambda _s: None, npm_lookup=lambda: "npm",
        runner=lambda *a, **k: _Rc(1)) == "install-failed"


def test_server_status_none_stale_live(tmp_path):
    root = _mk_deck(tmp_path)
    assert serve_deck.server_status(root)[0] == "none"

    serve_deck.write_pidfile(root, 4242, 3030)
    assert serve_deck.server_status(
        root, alive=lambda _p: False)[0] == "stale"
    assert serve_deck.server_status(
        root, alive=lambda _p: True, is_port_open=lambda *a, **k: True
    )[0] == "live"


class _Rc:
    def __init__(self, code): self.returncode = code
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest slidecraft/tests/test_serve_deck.py -q`
Expected: FAIL — `slidecraft.scripts.serve_deck` does not exist (ImportError).

- [ ] **Step 3: Write `serve_deck.py`**

Create `slidecraft/scripts/serve_deck.py`:

```python
#!/usr/bin/env python
"""Background live Slidev server for /draft-deck — ensure-ready, then serve.

Launched in the background at the start of /draft-deck, concurrently with mining
(2026-07-22 live-drafting-preview). It:

  1. Reuses an already-running server for this deck (pidfile + port check) so a
     re-draft never starts a second one.
  2. Ensures node_modules is installed: if the slidev binary is present, serve;
     if an install looks in-flight (node_modules/ exists but no binary yet, i.e.
     /init-deck's background `npm install`), poll for the binary; otherwise run
     `npm install` here. If Node/npm is unavailable, report 'no-preview' so
     /draft-deck skips live preview and drafts normally.
  3. Serves `npx slidev slides.md --open` and records logs/serve_deck.json.

Decision logic (readiness, reuse) is pure and unit-tested; the spawn is a thin
documented tail.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

IS_WINDOWS = os.name == "nt"
PIDFILE = "logs/serve_deck.json"
DEFAULT_PORT = 3030


def slidev_bin(root: Path) -> Path | None:
    name = "slidev.cmd" if IS_WINDOWS else "slidev"
    p = root / "node_modules" / ".bin" / name
    return p if p.exists() else None


def npm_executable() -> str | None:
    return shutil.which("npm.cmd" if IS_WINDOWS else "npm") or shutil.which("npm")


def ensure_ready(root: Path, *, poll_attempts: int = 120, poll_interval: float = 1.0,
                 sleep=time.sleep, bin_check=slidev_bin,
                 npm_lookup=npm_executable, runner=subprocess.run) -> str:
    """Return 'ready' | 'no-npm' | 'install-failed'. Waits for an in-flight
    install (node_modules present, binary not yet), else installs here."""
    if bin_check(root):
        return "ready"
    if (root / "node_modules").is_dir():
        for _ in range(poll_attempts):
            sleep(poll_interval)
            if bin_check(root):
                return "ready"
        # install stalled/never finished — fall through and repair below.
    npm = npm_lookup()
    if not npm:
        return "no-npm"
    proc = runner([npm, "install", "--no-audit", "--no-fund"],
                  cwd=str(root))
    if getattr(proc, "returncode", 1) != 0:
        return "install-failed"
    return "ready" if bin_check(root) else "install-failed"


def read_pidfile(root: Path) -> dict | None:
    p = root / PIDFILE
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def write_pidfile(root: Path, pid: int, port: int) -> None:
    (root / "logs").mkdir(exist_ok=True)
    (root / PIDFILE).write_text(json.dumps(
        {"pid": pid, "port": port, "started_at": time.strftime("%Y-%m-%dT%H:%M:%S")}),
        encoding="utf-8")


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if IS_WINDOWS:
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"],
                             capture_output=True, text=True)
        return str(pid) in out.stdout
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def port_open(port: int, host: str = "127.0.0.1", timeout: float = 0.3) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        return s.connect_ex((host, port)) == 0


def server_status(root: Path, *, alive=pid_alive, is_port_open=port_open):
    """('live'|'stale'|'none', pidfile_or_None). Live iff the recorded pid is
    running AND its port answers."""
    info = read_pidfile(root)
    if not info:
        return "none", None
    pid, port = int(info.get("pid", 0)), int(info.get("port", 0))
    if alive(pid) and port and is_port_open(port):
        return "live", info
    return "stale", info


def _spawn_slidev(root: Path, port: int, open_browser: bool) -> int:
    """Start `npx slidev slides.md --open --port <port>` detached. Returns pid.
    This is the untested tail — verified by a live /draft-deck run."""
    cmd = ["npx", "slidev", "slides.md", "--port", str(port)]
    if open_browser:
        cmd.append("--open")
    if IS_WINDOWS:
        cmd[0] = "npx.cmd"
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | 0x00000008  # DETACHED_PROCESS
        proc = subprocess.Popen(cmd, cwd=str(root), creationflags=flags,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        proc = subprocess.Popen(cmd, cwd=str(root), start_new_session=True,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return proc.pid


def _emit(obj: dict) -> None:
    print(json.dumps(obj, ensure_ascii=False))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--deck", default=".")
    ap.add_argument("--no-open", action="store_true")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--ready-timeout", type=int, default=120,
                    help="seconds to wait for an in-flight npm install")
    a = ap.parse_args(argv)
    root = Path(a.deck).resolve()

    state, info = server_status(root)
    if state == "live":
        _emit({"status": "reused", "port": info.get("port")})
        return 0

    ready = ensure_ready(root, poll_attempts=max(1, a.ready_timeout))
    if ready != "ready":
        _emit({"status": "no-preview", "reason": ready})
        return 1

    pid = _spawn_slidev(root, a.port, open_browser=not a.no_open)
    write_pidfile(root, pid, a.port)
    _emit({"status": "served", "pid": pid, "port": a.port})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the new test + full suite**

Run: `python -m pytest slidecraft/tests/test_serve_deck.py -q`
Expected: PASS (7 tests).
Run: `python -m pytest slidecraft/tests -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add slidecraft/scripts/serve_deck.py slidecraft/tests/test_serve_deck.py
git commit -m "feat: serve_deck.py — background live server (ensure-ready + reuse)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: Ignore the transient files in scaffolded decks

Add the transient status/pidfile to the `.gitignore` written by the scaffold, so a deck under git never accidentally tracks them.

**Files:**
- Modify: `slidecraft/scripts/scaffold_deck.py` — `write_gitignore` (`:358`)
- Test: `slidecraft/tests/test_scaffold_deck.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `.gitignore` content now also ignoring `.draft-status.json` and `logs/serve_deck.json`.

- [ ] **Step 1: Write the failing test**

Add to `slidecraft/tests/test_scaffold_deck.py` (near the existing scaffold assertions):

```python
def test_gitignore_excludes_transient_preview_files(tmp_path):
    from slidecraft.scripts import scaffold_deck
    created = []
    scaffold_deck.write_gitignore(tmp_path, created)
    gi = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert "node_modules/" in gi                        # unchanged
    assert ".draft-status.json" in gi                   # transient status
    assert "logs/serve_deck.json" in gi                 # server pidfile
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest slidecraft/tests/test_scaffold_deck.py::test_gitignore_excludes_transient_preview_files -q`
Expected: FAIL — the two new lines are absent.

- [ ] **Step 3: Update `write_gitignore`**

Replace the write in `scaffold_deck.py:361`:

```python
    (root / ".gitignore").write_text(
        "node_modules/\ndist/\n.draft-status.json\nlogs/serve_deck.json\n",
        encoding="utf-8")
```

- [ ] **Step 4: Run test + full suite**

Run: `python -m pytest slidecraft/tests/test_scaffold_deck.py -q`
Expected: PASS.
Run: `python -m pytest slidecraft/tests -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add slidecraft/scripts/scaffold_deck.py slidecraft/tests/test_scaffold_deck.py
git commit -m "chore(scaffold): gitignore .draft-status.json + serve_deck pidfile

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: Wire observability into the `/draft-deck` and `/init-deck` command docs

These commands are Markdown instruction files the LLM lead follows. Thread the server launch + status calls through `/draft-deck`, and clarify `/init-deck`'s install wording. Behavior is asserted by the integration test in Task 6.

**Files:**
- Modify: `slidecraft/commands/draft-deck.md`
- Modify: `slidecraft/commands/init-deck.md`

**Interfaces:**
- Consumes: `serve_deck.py`, `km set-status`, `km clear-status` (Tasks 2–3).
- Produces: no code; the documented orchestration the integration test mirrors.

- [ ] **Step 1: Add the server-launch + status-init step to `draft-deck.md`**

Add `<SERVE> = <toolkit>/slidecraft/scripts/serve_deck.py` to the shorthands list (near `<CONV>`). Insert a new section **before** "## 1. Convert":

```markdown
## 0. Start the live preview (background) + status

Kick this off first, concurrently with the pipeline — it must not block mining:

    python "<SERVE>" --deck <deck>         # run with the tool's run_in_background

Read its one-line JSON: `served` (browser opening) / `reused` (already live) /
`no-preview` (Node or npm missing — continue drafting; files still update, the
user previews later via `show_slide_deck`). Record which, for the final report.

Then set the first status so the browser shows progress immediately:

    python "<KM>" --deck <deck> set-status --phase convert --label "Converting inputs…"

The status slide is inline and **uncounted** (never consumes a budget slot).
Update it at each phase transition below; clear it at the end.
```

- [ ] **Step 2: Thread `set-status` through Convert / Mine / Plan / Execute**

Add these `set-status` calls into the existing steps (as instruction lines, not new mechanics):

- End of **§1 Convert** (renumbered — keep existing numbering, just add a line):
  `python "<KM>" --deck <deck> set-status --phase mine --detail "0/<N sources>" --label "Mining sources…"`
- In **§2 Mine**, after each source's `mark-mined`, bump the detail:
  `python "<KM>" --deck <deck> set-status --phase mine --detail "<done>/<N>" --label "Mining sources…"`
- Before **§3 Plan**'s storyteller invoke:
  `python "<KM>" --deck <deck> set-status --phase plan --label "Planning deck structure…"`
- In **§4 Execute**, as slides are composed, keep a running count:
  `python "<KM>" --deck <deck> set-status --phase compose --detail "<composed>/<total>" --label "Composing slides…"`

- [ ] **Step 3: Clear (or terminalize) status at the end of `draft-deck.md`**

In **§5 Validate + report**, add before `validate`:

```markdown
On success, clear the transient status slide so the finished deck is clean:

    python "<KM>" --deck <deck> clear-status

On an **aborted** run (storyteller terminal, §3), do NOT clear — instead set a
terminal status so the browser reflects the stop, then surface the error:

    python "<KM>" --deck <deck> set-status --phase aborted --label "Draft aborted — see report"
```

Also extend the final report bullet list with: "whether the live preview was
active (served / reused / no-preview) and, if serving, that it stays running —
close the window / Ctrl-C to stop it."

- [ ] **Step 4: Clarify install wording in `init-deck.md`**

In `init-deck.md` §3 (the prewarm/background-install step), append a sentence:

```markdown
This background `npm install` is the **only** preparation the preview needs —
there is no separate "build" step; `/draft-deck` starts the Slidev dev server
directly from `slides.md`. Finishing it here is what lets that server start
instantly.
```

In §6 Close, note that `/draft-deck` now opens the live preview itself, so the
double-click launcher is the manual/fallback path.

- [ ] **Step 5: Sanity-check the docs render and cross-references resolve**

Run: `python -c "import pathlib; [print(p, pathlib.Path(p).read_text(encoding='utf-8').count('<SERVE>')) for p in ['slidecraft/commands/draft-deck.md']]"`
Expected: prints the file with a count ≥ 2 (shorthand definition + usage). Manually re-read both files to confirm `<SERVE>`, `set-status`, and `clear-status` are all defined where referenced.

- [ ] **Step 6: Commit**

```bash
git add slidecraft/commands/draft-deck.md slidecraft/commands/init-deck.md
git commit -m "docs(commands): live preview + status in draft-deck; init-deck install wording

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 6: Integration test — status is threaded and cleared, budget intact

Extend the end-to-end harness so it exercises `set-status`/`clear-status` at the phase boundaries the command doc now specifies, and assert the finished deck is clean and exactly `max_slides`-budgeted despite a status slide existing mid-run.

**Files:**
- Modify: `slidecraft/tests/test_draft_deck_integration.py` — `draft_deck` harness (`:145`) + a new test.

**Interfaces:**
- Consumes: `km.cmd_set_status`, `km.cmd_clear_status` (Task 2).
- Produces: a regression guard that the status slide never costs a budget slot and is gone on completion.

- [ ] **Step 1: Write the failing test**

Add to `test_draft_deck_integration.py`:

```python
def test_status_slide_is_threaded_and_cleared_without_costing_budget(deck, tmp_path):
    """The transient status slide appears mid-run and is removed at the end; it
    never consumes a budget slot (final active count == the plan's real slides)."""
    _seed_inputs(deck)

    # Set a status BEFORE drafting (as /draft-deck §0 does) and assert it shows
    # up uncounted, then run the normal draft which clears it at the end.
    km.cmd_set_status(deck, Namespace(phase="mine", detail="0/2",
                                      label="Mining sources…"))
    mid = (deck / "slides.md").read_text(encoding="utf-8")
    assert "Mining sources…" in mid
    assert km.order(deck) == []                        # status alone counts 0

    report = draft_deck(deck, tmp_path / "run1",
                        text_responses=[CH9_MINE, EMPTY_MINE],
                        image_responses=[IMG_MINE], build=_full_plan)
    km.cmd_clear_status(deck, Namespace())             # as §5 does on success

    assert report["validate_ok"] is True
    assert report["validate"]["slides"] == 4           # exactly the 4 real slides
    final = (deck / "slides.md").read_text(encoding="utf-8")
    assert "Mining sources…" not in final              # cleared
    assert not (deck / ".draft-status.json").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest slidecraft/tests/test_draft_deck_integration.py::test_status_slide_is_threaded_and_cleared_without_costing_budget -q`
Expected: FAIL if Task 2 is not yet merged (AttributeError on `cmd_set_status`); PASS once Task 2 is in. (If executing tasks in order, this test both drives and confirms the wiring — run it after Task 2.)

- [ ] **Step 3: No implementation needed**

This task adds a test only; the behavior it asserts is implemented in Task 2. If the assertion about `report["validate"]["slides"] == 4` fails because a status slide leaked into the count, that is a real regression in `write_order`/`order` — fix it in `km.py` (the status block must remain inline, never a `src:` import).

- [ ] **Step 4: Run the full suite**

Run: `python -m pytest slidecraft/tests -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add slidecraft/tests/test_draft_deck_integration.py
git commit -m "test(draft-deck): status slide threaded+cleared, budget intact

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Manual verification (after all tasks)

Automated tests cover the decision logic and file transforms; the live loop needs one real run to close the spec's risk items:

1. In a scratch deck with a couple of input files, run `/init-deck` then `/draft-deck`.
2. Confirm the browser opens, the status slide shows phase progress, skeletons appear with the distilled info + "Composer is drafting" banner, and each fills in when composed.
3. Confirm the finished deck has no status slide and the slide count matches the budget.
4. **Risk checks:** does Vite HMR pick up newly `src:`-imported slides without a manual refresh (spec §8.1)? Is there noticeable OneDrive watch latency (§8.2)? Does the background server survive after the turn (§8.3)? Record findings; if HMR misses new imports, add a periodic reload or document the manual-refresh workaround.

---

## Self-review notes

- **Spec coverage:** A (serve_deck) → Task 3; B (rich skeletons) → Task 1; C (status slide) → Task 2; D (draft-deck wiring) → Task 5 + Task 6; E (init-deck wording + gitignore) → Task 4 + Task 5; risks → Manual verification. All spec sections map to a task.
- **Signature consistency:** `skeleton(root, title, nugget_ids)` is defined in Task 1 and every caller updated in the same task; `nugget_info_section(root, title, nugget_ids)` is used by both `digest_body` and `skeleton`; `ensure_ready`/`server_status` keyword-injected dependencies match between the test and the implementation in Task 3.
- **Budget invariant** is asserted twice (Task 2 unit + Task 6 integration) because it is the subtlest failure mode.
