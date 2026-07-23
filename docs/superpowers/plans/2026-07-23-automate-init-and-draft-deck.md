# Automate init-deck interview & draft-deck orchestration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove per-step interactive-LLM involvement from `/init-deck` and `/draft-deck` so each is a fast, mostly-scripted flow — `/init-deck` walks a declared question spec (LLM only for an "Other" branch), `/draft-deck` runs one `convert→mine→plan→compose` driver (LLM only on a hard error).

**Architecture:** Two independent tracks. **Track A** (`/draft-deck`) adds `draft_deck.py`, a batch driver that subprocesses the existing deterministic scripts exactly like `compose_deck.py` does, plus a port-fallback fix in `serve_deck.py`. **Track B** (`/init-deck`) adds a declared interview spec (`init_questions.json`) with a tiny walker module, a cover-slot→questions resolver in `scaffold_deck.py`, and rewrites both command markdown files. The tracks touch disjoint files (the only soft link is `scaffold_deck.py`'s answers-JSON shape) and can be built in either order.

**Tech Stack:** Python 3 (stdlib only in tests; `requests` only for the live OWUI path, never exercised by tests), pytest, Slidev/npm (deck runtime, not under test). Windows-first (PowerShell + Git Bash both available). No new orchestration primitive — the plain-Python-script idiom (D27), not a `Workflow`.

## Global Constraints

- **Scripts are invoked by absolute path** (D27/D33): a driver references sibling scripts via `str(Path(module.__file__))`, never by relative path or `cwd`. Copy the `compose_deck.py` header pattern (`KM = str(Path(km.__file__))`, `SHIM = str(Path(invoke_shim.__file__))`).
- **All file reads tolerate a BOM**: read text with `encoding="utf-8-sig"` when the file may have been written by PowerShell/Notepad (deck-context, briefs, source records); write with `encoding="utf-8"`. Follow the surrounding code's existing choice per call site.
- **The invoke shim is the only nondeterministic seam.** A driver never calls an LLM directly; it subprocesses `invoke_shim.py` (exit `0`=ok / `3`=exhausted / `4`=error) and reads the `result.json` it writes (`{"role","status","attempts","terminal","errors","output","executor"}`, where `status ∈ {"ok","exhausted","error"}`, `terminal ∈ {null,"drop","park","abort"}`).
- **Tests never touch a live LLM.** Fakes are wired through the deck-context `executors` block via `conftest.wire_fake_executor(deck, scratch, role, responses)`, which points a role at a scripted `cmd` executor — this works **across the subprocess boundary** because a subprocessed `invoke_shim.py` re-reads `deck-context.json`.
- **Deck root is passed explicitly** (`--deck <root>`); no reliance on CWD in library code. Do all transient work (briefs, result JSON) in a `tempfile.TemporaryDirectory`.
- **DRY, YAGNI, TDD, frequent commits.** Run tests from the repo root with `python -m pytest`.

---

## Coverage map (design § → task)

| Design section | Task |
|---|---|
| §6 Component D — `serve_deck.py` port fallback | A1 |
| §5 Component C — `draft_deck.py` convert + mine (digest mode), fail-fast, re-derive | A2 |
| §5 Component C — `draft_deck.py` plan + execute + compose + validate (full mode) | A3 |
| §8 Component F — `/draft-deck` command rewrite | A4 |
| §3 Component A — `init_questions.json` spec + walker | B1 |
| §4 Component B — cover-slot → questions resolver + answers storage | B2 |
| §7 Component E — `/init-deck` command rewrite | B3 |

**Design decisions locked here (where the design left an implementation choice):**
- **`draft_deck.py` calls `compose_deck.compose_deck()` in-process** (design §9.3 allows either) — matching how `compose_deck.py` itself imports `km`/`design_section`. Every *mutation* (convert, km subcommands, the shim) is a subprocess, exactly like `compose_deck.py`.
- **Fail-fast reads the shim's `result.json` `status` field** (not the raw exit code) — it is the source of truth §5.4/§10 speak in, and `wire_fake_executor` drives it.
- **The transient status slide (`km set-status`) is dropped from the driver.** The design's §5.2 phase list omits it; live-preview progress now comes from `compose_deck`'s incremental wireframes (rendered "the instant a slide is planned"), so no status threading is needed.
- **Component B stores cover answers verbatim under `deck.cover`; it does not re-plumb composer injection.** The design's §10 tests only assert the *question set* is generated correctly and explicitly drops any synonym/canonical mapping; consuming `deck.cover` in composer prompt templates is out of scope (a later change).

---

# TRACK A — `/draft-deck` automation

Depends on nothing outside the existing scripts. A1 is fully standalone; A2→A3→A4 build in order.

---

## Task A1: `serve_deck.py` port fallback (§6)

Today `main()` spawns Slidev on `a.port` (default 3030) unconditionally once this deck has no live server of its own — with no check that `3030` isn't already bound by *another* process. Add a probe over `3030–3040` using the existing `port_open()` helper.

**Files:**
- Modify: `slidecraft/scripts/serve_deck.py` (add `pick_port`, wire it into `main`)
- Test: `slidecraft/tests/test_serve_deck.py` (add port-fallback cases)

**Interfaces:**
- Consumes: `port_open(port, host="127.0.0.1", timeout=0.3) -> bool` (existing, `serve_deck.py:102`) — `True` when a port is **busy** (something is listening).
- Produces: `pick_port(*, is_port_open=port_open, ports=range(3030, 3041)) -> int | None` — first free port, or `None` if all are busy.

- [ ] **Step 1: Write the failing tests**

Add to `slidecraft/tests/test_serve_deck.py`:

```python
def test_pick_port_returns_start_when_all_free():
    assert serve_deck.pick_port(is_port_open=lambda p: False) == 3030


def test_pick_port_skips_busy_ports():
    busy = {3030, 3031}
    assert serve_deck.pick_port(is_port_open=lambda p: p in busy) == 3032


def test_pick_port_returns_none_when_all_busy():
    assert serve_deck.pick_port(is_port_open=lambda p: True) is None


def test_pick_port_honors_custom_range():
    assert serve_deck.pick_port(
        is_port_open=lambda p: p < 3035, ports=range(3030, 3041)) == 3035
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest slidecraft/tests/test_serve_deck.py -k pick_port -v`
Expected: FAIL with `AttributeError: module 'slidecraft.scripts.serve_deck' has no attribute 'pick_port'`

- [ ] **Step 3: Add `pick_port`**

In `slidecraft/scripts/serve_deck.py`, after `port_open` (around line 106), add:

```python
PORT_RANGE = range(3030, 3041)   # 3030–3040 inclusive (§6)


def pick_port(*, is_port_open=port_open, ports=PORT_RANGE) -> int | None:
    """First free port in `ports` (busy = something already listening), or
    None if every candidate is occupied (§6). Uses the same liveness probe
    as server_status so the choice is consistent with reuse detection."""
    for p in ports:
        if not is_port_open(p):
            return p
    return None
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest slidecraft/tests/test_serve_deck.py -k pick_port -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Wire `pick_port` into `main`**

In `slidecraft/scripts/serve_deck.py`, replace the spawn tail of `main` (currently lines 161-164):

```python
    pid = _spawn_slidev(root, a.port, open_browser=not a.no_open)
    write_pidfile(root, pid, a.port)
    _emit({"status": "served", "pid": pid, "port": a.port})
    return 0
```

with:

```python
    start = a.port
    port = pick_port(ports=range(start, start + 11))
    if port is None:
        _emit({"status": "no-preview",
               "reason": f"ports {start}-{start + 10} all in use"})
        return 1
    pid = _spawn_slidev(root, port, open_browser=not a.no_open)
    write_pidfile(root, pid, port)
    _emit({"status": "served", "pid": pid, "port": port})
    return 0
```

- [ ] **Step 6: Run the full serve_deck suite**

Run: `python -m pytest slidecraft/tests/test_serve_deck.py -v`
Expected: PASS (all prior tests + the 4 new ones)

- [ ] **Step 7: Commit**

```bash
git add slidecraft/scripts/serve_deck.py slidecraft/tests/test_serve_deck.py
git commit -m "feat(serve_deck): probe ports 3030-3040 before spawning (design §6)"
```

---

## Task A2: `draft_deck.py` — convert + mine loop (digest mode) (§5.1–§5.5)

Create the driver with the convert phase, the mine loop, the fail-fast boundary, filesystem-re-derivation, and the JSON report — enough for **digest mode** (stops after mining; no plan/compose/validate). Full mode is stubbed until A3.

**Files:**
- Create: `slidecraft/scripts/draft_deck.py`
- Test: `slidecraft/tests/test_draft_deck_integration.py` (add real-script tests; import the module under an alias to avoid the existing top-level `def draft_deck` in that file)

**Interfaces:**
- Consumes: `source_converter.py` CLI (`--deck`, prints `{"written":[...],"skipped":[...],"errors":[...]}`, exits 2 if any file errored but still writes the good ones); `km.py` subcommands `mine-brief`/`persist-nuggets`/`mark-mined`; `invoke_shim.py` CLI; `conftest.wire_fake_executor`.
- Produces (relied on by A3, A4, tests):
  - `run(deck, *, mode, run_label=None, max_workers=4) -> dict` — the driver; report shape §5.5.
  - `main(argv=None) -> int` — CLI (`--deck`, `--mode {digest,full}`, `--run-label`); prints the report, returns `0` when `status=="ok"` else `1`.
  - Report keys: `{"status","mode","convert","mine","plan","compose","validate","stopped_at"}`; on a stop also `"stopped_detail"`. In digest mode `plan`/`compose`/`validate` are `null`.

- [ ] **Step 1: Write the failing digest-mode test**

Add to `slidecraft/tests/test_draft_deck_integration.py`. Put the import alias near the top imports:

```python
from slidecraft.scripts import draft_deck as dd   # the real driver (A2/A3)
```

Then add:

```python
def test_digest_mode_mines_then_stops(deck, tmp_path):
    """Digest mode runs convert + mine and STOPS — plan/compose/validate are
    null (not run at all, §5.2). A re-run mines nothing (delta, §5.3)."""
    _seed_inputs(deck)
    wire_fake_executor(deck, tmp_path, "knowledge-miner", [CH9_MINE, EMPTY_MINE])
    wire_fake_executor(deck, tmp_path, "image-miner", [IMG_MINE], image_arg=True)

    report = dd.run(deck, mode="digest")

    assert report["status"] == "ok"
    assert report["mode"] == "digest"
    assert report["mine"]["sources_mined"] == 2
    assert report["mine"]["nuggets_created"] == 3      # 2 text + 1 image
    assert report["mine"]["dropped"] == []
    assert report["plan"] is None                      # not run at all
    assert report["compose"] is None
    assert report["validate"] is None
    assert list((deck / "slides").glob("*.md")) == []  # nothing composed

    # Re-run: every source is now marked mined → nothing to mine.
    report2 = dd.run(deck, mode="digest")
    assert report2["mine"]["sources_mined"] == 0
    assert report2["mine"]["nuggets_created"] == 0
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest slidecraft/tests/test_draft_deck_integration.py -k digest_mode -v`
Expected: FAIL with `ModuleNotFoundError` / `AttributeError` (no `draft_deck` module yet)

- [ ] **Step 3: Create `draft_deck.py` with convert + mine + digest report**

Create `slidecraft/scripts/draft_deck.py`:

```python
#!/usr/bin/env python
"""Unified /draft-deck pipeline driver (design 2026-07-23 §5).

One script the command calls once and reads one JSON report from — parallels
compose_deck.py's relationship to /draft-deck. Runs the whole
convert -> mine -> [full: plan -> execute -> compose -> validate] chain with
zero per-step interactive-LLM turns: every LLM role already runs behind the
invoke shim (a headless `claude -p` subprocess for the storyteller, OWUI over
HTTP for miners/composers). This driver only sequences the deterministic
scripts and reads their JSON, exactly like compose_deck.py.

Re-derive, don't track (§5.3): each invocation re-checks filesystem state
fresh — input/ minus input/processed/ for convert, a source's `mined_at` for
mine, slide state for plan/compose — so a re-run after a stop resumes by
construction; there is no run manifest.

Fail-fast (§5.4): a miner `drop` (a source's text or one figure yielded no
nugget) is expected and non-fatal (logged in `mine.dropped`, run continues).
A shim `status == "error"` (OWUI unreachable, transport failure, a
non-retryable gate) or a storyteller `status == "exhausted"` (invalid plan
after retries) stops the run immediately; the report names the phase it
stopped at, and the NEXT invocation resumes from there.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from slidecraft.scripts import compose_deck, invoke_shim, km, source_converter

KM = str(Path(km.__file__))
SHIM = str(Path(invoke_shim.__file__))
CONV = str(Path(source_converter.__file__))


class _Stop(Exception):
    """A fail-fast stop: `phase` is the report `stopped_at`, `detail` the
    partial context (§5.4)."""

    def __init__(self, phase: str, detail: dict):
        super().__init__(phase)
        self.phase = phase
        self.detail = detail


def _run(argv, **kw) -> subprocess.CompletedProcess:
    """subprocess.run with the toolkit's utf-8 defaults (matches compose_deck)."""
    return subprocess.run(argv, capture_output=True, text=True,
                          encoding="utf-8", **kw)


def _shim_status(result_path: Path) -> tuple[str, str | None, list]:
    """(status, terminal, errors) from a shim result.json — the source of
    truth for the fail-fast boundary (§5.4). A missing/unreadable file is
    itself an infra error."""
    try:
        r = json.loads(Path(result_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return "error", None, [f"unreadable shim result: {exc}"]
    return r.get("status", "error"), r.get("terminal"), r.get("errors") or []


def _unmined_sources(deck: Path) -> list[Path]:
    """Source records with no `mined_at` stamp, in deck order (§5.3)."""
    out = []
    for sp in sorted((deck / "sources").glob("*.json")):
        try:
            src = json.loads(sp.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not src.get("mined_at"):
            out.append(sp)
    return out


def _nugget_count(deck: Path) -> int:
    return len(list((deck / "nuggets").glob("*.json")))


# ---------- phases ----------

def _convert(deck: Path) -> dict:
    """Deterministic, idempotent convert. Per-file errors (exit 2) are surfaced
    but non-fatal — the sources that DID convert still mine (§5.2/§5.4)."""
    proc = _run([sys.executable, CONV, "--deck", str(deck)])
    try:
        rep = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        rep = {}
    return {"sources_created": len(rep.get("written", [])),
            "errors": rep.get("errors", [])}


def _mine(deck: Path, scratch: Path) -> dict:
    """Mine every unmined source: text (1 invoke) + each image (1 invoke).
    Raises _Stop on a shim `error`; a miner `exhausted` (drop) is recorded and
    the loop continues (§5.4)."""
    dropped: list[dict] = []
    before = _nugget_count(deck)
    sources = _unmined_sources(deck)
    for sp in sources:
        slug = sp.stem
        src = json.loads(sp.read_text(encoding="utf-8"))

        # a. text — one invoke over the whole source text
        tbrief = scratch / f"mine-{slug}.md"
        _run([sys.executable, KM, "--deck", str(deck), "mine-brief",
              "--source", slug, "--out", str(tbrief)], check=True)
        tres = scratch / f"mine-{slug}.result.json"
        _run([sys.executable, SHIM, "--role", "knowledge-miner",
              "--brief-file", str(tbrief), "--deck", str(deck),
              "--out", str(tres), "--",
              sys.executable, KM, "--deck", str(deck), "persist-nuggets",
              "--source", slug, "--file", "{out}"])
        status, _terminal, errors = _shim_status(tres)
        if status == "error":
            raise _Stop("mine", {"source": slug, "kind": "text",
                                 "errors": errors})
        if status == "exhausted":                 # miner terminal == drop
            dropped.append({"source": slug, "kind": "text"})

        # b. images — one invoke per extracted figure
        for img in src.get("images", []):
            iid = img["image_source_id"]
            ibrief = scratch / f"mine-{iid}.md"
            info = _run([sys.executable, KM, "--deck", str(deck), "mine-brief",
                         "--image", iid, "--out", str(ibrief)], check=True)
            asset = json.loads(info.stdout)["asset"]
            ires = scratch / f"mine-{iid}.result.json"
            _run([sys.executable, SHIM, "--role", "image-miner",
                  "--brief-file", str(ibrief), "--image", asset,
                  "--deck", str(deck), "--out", str(ires), "--",
                  sys.executable, KM, "--deck", str(deck), "persist-nuggets",
                  "--source", slug, "--image-source", iid, "--file", "{out}"])
            status, _terminal, errors = _shim_status(ires)
            if status == "error":
                raise _Stop("mine", {"image": iid, "kind": "image",
                                     "errors": errors})
            if status == "exhausted":
                dropped.append({"image": iid, "kind": "image"})

        # c. mark mined once text + every image were attempted (§5.4: only
        #    reached when nothing raised _Stop, so a stopped source stays
        #    unmined and the next run re-mines it — resume by construction).
        _run([sys.executable, KM, "--deck", str(deck), "mark-mined",
              "--source", slug], check=True)

    return {"sources_mined": len(sources),
            "nuggets_created": _nugget_count(deck) - before,
            "dropped": dropped}


# ---------- driver ----------

def run(deck, *, mode: str, run_label=None, max_workers: int = 4) -> dict:
    deck = Path(deck)
    report = {"status": "ok", "mode": mode, "convert": None, "mine": None,
              "plan": None, "compose": None, "validate": None,
              "stopped_at": None}
    with tempfile.TemporaryDirectory(prefix="draft-deck-") as td:
        scratch = Path(td)
        try:
            report["convert"] = _convert(deck)
            report["mine"] = _mine(deck, scratch)
            if mode == "full":
                _full(deck, scratch, report, run_label, max_workers)
        except _Stop as stop:
            report["status"] = "error"
            report["stopped_at"] = stop.phase
            report["stopped_detail"] = stop.detail
    return report


def _full(deck, scratch, report, run_label, max_workers):
    raise NotImplementedError("full mode lands in Task A3")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--deck", required=True)
    ap.add_argument("--mode", choices=["digest", "full"], required=True)
    ap.add_argument("--run-label", dest="run_label", default=None)
    ap.add_argument("--max-workers", dest="max_workers", type=int, default=4)
    a = ap.parse_args(argv)
    report = run(Path(a.deck), mode=a.mode, run_label=a.run_label,
                 max_workers=a.max_workers)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the digest test to verify it passes**

Run: `python -m pytest slidecraft/tests/test_draft_deck_integration.py -k digest_mode -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Write the failing mid-mine-error + resume test**

Add a boom-executor helper and the test to `slidecraft/tests/test_draft_deck_integration.py`. Note: `wire_fake_executor` calls `respdir.mkdir()` (no `parents=True`), so its scratch arg must already exist — pass pytest's `tmp_path` (which always exists) directly, and give each role a distinct dir name (the helper derives `responses-<role>`, so distinct roles never collide).

```python
def _count_nuggets(deck):
    return len(list((deck / "nuggets").glob("*.json")))


def _wire_boom(deck, tmp_path, role):
    """Point a role at a `cmd` executor that exits non-zero → the shim records
    status='error' (an infra failure no re-invoke can fix)."""
    respdir = tmp_path / f"boom-{role}"
    respdir.mkdir(parents=True)
    script = tmp_path / "boom.py"
    script.write_text("import sys; sys.exit(1)", encoding="utf-8")
    ctx_path = deck / "deck-context.json"
    ctx = json.loads(ctx_path.read_text(encoding="utf-8"))
    ctx.setdefault("executors", {})[role] = {
        "executor": "cmd", "command": [sys.executable, str(script)]}
    ctx_path.write_text(json.dumps(ctx, indent=2), encoding="utf-8")


def test_mine_infra_error_stops_then_resumes(deck, tmp_path):
    """A shim `error` mid-mine stops the run at `mine` (the source stays
    unmined); a re-run with a healthy executor resumes and mines it (§5.3/§5.4)."""
    _seed_inputs(deck)
    _wire_boom(deck, tmp_path, "knowledge-miner")

    stopped = dd.run(deck, mode="digest")
    assert stopped["status"] == "error"
    assert stopped["stopped_at"] == "mine"
    assert _count_nuggets(deck) == 0                   # nothing persisted
    # chapter-9 was never marked mined → still unmined.
    unmined = [p.stem for p in (deck / "sources").glob("*.json")
               if not json.loads(p.read_text(encoding="utf-8")).get("mined_at")]
    assert TEXT_SLUG in unmined

    # Heal the executor and resume (distinct role dirs → no mkdir collision).
    wire_fake_executor(deck, tmp_path, "knowledge-miner", [CH9_MINE, EMPTY_MINE])
    wire_fake_executor(deck, tmp_path, "image-miner", [IMG_MINE], image_arg=True)
    resumed = dd.run(deck, mode="digest")
    assert resumed["status"] == "ok"
    assert resumed["mine"]["sources_mined"] == 2
    assert _count_nuggets(deck) == 3
```

- [ ] **Step 6: Run the error/resume test to verify it fails, then passes**

Run: `python -m pytest slidecraft/tests/test_draft_deck_integration.py -k mine_infra_error -v`
Expected: PASS — the driver from Step 3 already implements this boundary; this step pins it. If it FAILS, fix `_mine`/`_shim_status` until green (do **not** weaken the test).

- [ ] **Step 7: Run the whole file to confirm no regressions**

Run: `python -m pytest slidecraft/tests/test_draft_deck_integration.py -v`
Expected: PASS (the pre-existing harness tests + the 2 new ones; full-mode driver tests come in A3)

- [ ] **Step 8: Commit**

```bash
git add slidecraft/scripts/draft_deck.py slidecraft/tests/test_draft_deck_integration.py
git commit -m "feat(draft_deck): convert+mine driver (digest mode) with fail-fast + resume (design §5)"
```

---

## Task A3: `draft_deck.py` — full mode (plan → execute → compose → validate) (§5.2)

Replace the `_full` stub with the plan/execute/compose/validate phases and the storyteller-abort fail-fast, plus the "nothing left to plan/compose" early exit.

**Files:**
- Modify: `slidecraft/scripts/draft_deck.py` (implement `_full`, `_plan`, `_execute_steps`, `_validate`, `_unplaced_nuggets`)
- Test: `slidecraft/tests/test_draft_deck_integration.py` (full-mode + abort tests driving the real driver)

**Interfaces:**
- Consumes: `plan.json` `steps` — each `{"op": ...}` with, per op: `create-slide` → `title`, `nuggets` (list), `after`, `parked` (bool), `intended_function`; `associate-nuggets` → `slide`, `nuggets`; `merge-slides` → `slides`, `title`; `park-slide` → `slide`, `reason`; `unpark-slide` → `slide`. `compose_deck.to_compose_set(deck) -> list[str]`; `compose_deck.compose_deck(deck, run_label=..., max_workers=...) -> dict`; `km validate` (prints JSON report; non-zero exit when not green).
- Produces (report §5.5): `plan={"slides_planned":N}`, `compose=<compose_deck report>`, `validate=<km validate report + {"exit_ok":bool}>`; each stays `null` when its phase didn't run.

- [ ] **Step 1: Write the failing full-mode test**

Add to `slidecraft/tests/test_draft_deck_integration.py`:

```python
def test_full_mode_via_real_driver_reaches_green(deck, tmp_path):
    """Digest first (mines → real nugget ids), then wire the storyteller/planner/
    designer fakes against those ids and run the REAL driver in full mode: it
    mines nothing new (all marked), plans, executes, composes, validates green."""
    _seed_inputs(deck)

    # 1. Mine everything (digest) so real nugget ids exist.
    wire_fake_executor(deck, tmp_path, "knowledge-miner", [CH9_MINE, EMPTY_MINE])
    wire_fake_executor(deck, tmp_path, "image-miner", [IMG_MINE], image_arg=True)
    assert dd.run(deck, mode="digest")["mine"]["sources_mined"] == 2

    # 2. Build the plan against the just-mined ids and wire the fakes (distinct
    #    roles → distinct responses-<role> dirs under tmp_path, no collision).
    by_kind = {"text": [], "image": []}
    for np_ in sorted((deck / "nuggets").glob("*.json")):
        n = json.loads(np_.read_text(encoding="utf-8"))
        by_kind.setdefault(n["kind"], []).append(n["nugget_id"])
    built = _full_plan(deck, by_kind)
    wire_fake_executor(deck, tmp_path, "storyteller", [json.dumps(built["plan"])])
    wire_fake_executor(deck, tmp_path, "slide-composer", built["planner"])
    wire_fake_executor(deck, tmp_path, "text-designer", built["text_designer"])

    # 3. Full run through the real driver (max_workers=1 → deterministic replay).
    report = dd.run(deck, mode="full", run_label="test", max_workers=1)

    assert report["status"] == "ok"
    assert report["plan"]["slides_planned"] == 4
    assert report["compose"]["parked"] == []
    assert report["validate"]["ok"] is True
    assert report["validate"]["exit_ok"] is True
    assert report["validate"]["slides"] == 4


def test_full_mode_storyteller_abort_composes_nothing(deck, tmp_path):
    """An invalid plan (unknown nugget id) → storyteller exhausted → stop at
    `plan`; nothing is composed and no plan.json survives (§5.4)."""
    _seed_inputs(deck)
    wire_fake_executor(deck, tmp_path, "knowledge-miner", [CH9_MINE, EMPTY_MINE])
    wire_fake_executor(deck, tmp_path, "image-miner", [IMG_MINE], image_arg=True)
    dd.run(deck, mode="digest")

    wire_fake_executor(deck, tmp_path, "storyteller", [json.dumps(
        {"plan": [{"action": "create", "title": "Ghost",
                   "nuggets": ["no-such-id"]}], "notes": ""})])

    report = dd.run(deck, mode="full")
    assert report["status"] == "error"
    assert report["stopped_at"] == "plan"
    assert list((deck / "slides").glob("*.md")) == []
    assert not (deck / "plan.json").exists()


def test_full_mode_nothing_to_do_reports_ok(deck, tmp_path):
    """A full run on a fully-composed deck re-derives clean state and reports ok
    without re-planning: plan stays null, compose composes nothing (§5.3)."""
    _seed_inputs(deck)
    # Reach a green deck first via the real driver.
    wire_fake_executor(deck, tmp_path, "knowledge-miner", [CH9_MINE, EMPTY_MINE])
    wire_fake_executor(deck, tmp_path, "image-miner", [IMG_MINE], image_arg=True)
    dd.run(deck, mode="digest")
    by_kind = {"text": [], "image": []}
    for np_ in sorted((deck / "nuggets").glob("*.json")):
        n = json.loads(np_.read_text(encoding="utf-8"))
        by_kind.setdefault(n["kind"], []).append(n["nugget_id"])
    built = _full_plan(deck, by_kind)
    wire_fake_executor(deck, tmp_path, "storyteller", [json.dumps(built["plan"])])
    wire_fake_executor(deck, tmp_path, "slide-composer", built["planner"])
    wire_fake_executor(deck, tmp_path, "text-designer", built["text_designer"])
    dd.run(deck, mode="full", max_workers=1)

    # Now nothing is unplaced and nothing is to-compose.
    report = dd.run(deck, mode="full", max_workers=1)
    assert report["status"] == "ok"
    assert report["plan"] is None                 # storyteller not re-invoked
    assert report["compose"] is None or report["compose"]["composed"] == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest slidecraft/tests/test_draft_deck_integration.py -k full_mode -v`
Expected: FAIL with `NotImplementedError: full mode lands in Task A3`

- [ ] **Step 3: Implement the full-mode phases**

In `slidecraft/scripts/draft_deck.py`, replace the `_full` stub with these functions (place them above `run`, and delete the stub):

```python
def _unplaced_nuggets(deck: Path) -> set[str]:
    """Nugget ids not yet placed on any slide — the signal that planning is
    needed. (`slide state for plan` in §5.3: an unplaced nugget has no slide.)"""
    try:
        assoc = json.loads((deck / "associations.json").read_text(
            encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        assoc = {}
    placed = {nid for nugs in assoc.values() for nid in nugs}
    alln = {p.stem for p in (deck / "nuggets").glob("*.json")}
    return alln - placed


def _plan(deck: Path, scratch: Path) -> dict:
    """One storyteller invoke → write-plan. Raises _Stop on a non-ok status —
    a deck is never composed off an invalid plan (§5.4 abort)."""
    pbrief = scratch / "plan.md"
    _run([sys.executable, KM, "--deck", str(deck), "plan-brief",
          "--out", str(pbrief)], check=True)
    pres = scratch / "plan.result.json"
    _run([sys.executable, SHIM, "--role", "storyteller",
          "--brief-file", str(pbrief), "--deck", str(deck),
          "--out", str(pres), "--",
          sys.executable, KM, "--deck", str(deck), "write-plan",
          "--file", "{out}"])
    status, _terminal, errors = _shim_status(pres)
    if status != "ok":
        raise _Stop("plan", {"errors": errors})
    steps = json.loads((deck / "plan.json").read_text(
        encoding="utf-8")).get("steps", [])
    return {"slides_planned": sum(1 for s in steps
                                  if s.get("op") == "create-slide")}


def _execute_steps(deck: Path) -> None:
    """Run plan.json's steps in order as km subcommands (NO per-create compose;
    the batch driver owns composition). The plan is pre-validated to respect the
    budget, so a step failure is infra — let check=True raise it."""
    steps = json.loads((deck / "plan.json").read_text(
        encoding="utf-8")).get("steps", [])
    for s in steps:
        op = s["op"]
        if op == "create-slide":
            argv = ["create-slide", "--title", s["title"],
                    "--after", s.get("after", "end")]
            if s.get("nuggets"):
                argv += ["--nuggets", ",".join(s["nuggets"])]
            if s.get("parked"):
                argv += ["--parked"]
            if s.get("intended_function"):
                argv += ["--intended-function", s["intended_function"]]
        elif op == "associate-nuggets":
            argv = ["associate-nuggets", "--slide", s["slide"],
                    "--nuggets", ",".join(s["nuggets"])]
        elif op == "merge-slides":
            argv = ["merge-slides", "--slides", ",".join(s["slides"])]
            if s.get("title"):
                argv += ["--title", s["title"]]
        elif op == "park-slide":
            argv = ["park-slide", "--slide", s["slide"]]
            if s.get("reason"):
                argv += ["--reason", s["reason"]]
        elif op == "unpark-slide":
            argv = ["unpark-slide", "--slide", s["slide"]]
        else:
            continue
        _run([sys.executable, KM, "--deck", str(deck), *argv], check=True)


def _validate(deck: Path) -> dict:
    """`km validate` as the orchestrator does — via the CLI, gating on the exit
    code. Not a fail-fast boundary: validate is a report the command surfaces."""
    proc = _run([sys.executable, KM, "--deck", str(deck), "validate"])
    try:
        rep = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        rep = {}
    rep["exit_ok"] = proc.returncode == 0
    return rep


def _full(deck, scratch, report, run_label, max_workers):
    """Full-mode tail: plan (only when nuggets are unplaced) → execute → compose
    → validate. If nothing is unplaced and nothing is to-compose, report ok
    without a no-op pass (§5.3)."""
    if not (_unplaced_nuggets(deck) or compose_deck.to_compose_set(deck)):
        return
    if _unplaced_nuggets(deck):
        report["plan"] = _plan(deck, scratch)        # may raise _Stop
        _execute_steps(deck)
    report["compose"] = compose_deck.compose_deck(
        deck, run_label=run_label, max_workers=max_workers)
    report["validate"] = _validate(deck)
```

- [ ] **Step 4: Run the full-mode tests to verify they pass**

Run: `python -m pytest slidecraft/tests/test_draft_deck_integration.py -k full_mode -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Run the whole integration file + the driver's siblings**

Run: `python -m pytest slidecraft/tests/test_draft_deck_integration.py slidecraft/tests/test_compose_deck.py -v`
Expected: PASS (no regressions)

- [ ] **Step 6: Smoke-test the CLI surface**

Run: `python -c "import argparse; from slidecraft.scripts import draft_deck; draft_deck.main(['--help'])"`
Expected: usage text listing `--deck`, `--mode {digest,full}`, `--run-label`, `--max-workers` (argparse exits 0 after printing help)

- [ ] **Step 7: Commit**

```bash
git add slidecraft/scripts/draft_deck.py slidecraft/tests/test_draft_deck_integration.py
git commit -m "feat(draft_deck): full-mode plan/execute/compose/validate + storyteller abort (design §5.2)"
```

---

## Task A4: `/draft-deck` command rewrite (§8)

Replace the step-by-step playbook with the 4-step form: ask mode, start the live preview for full mode, run `draft_deck.py` once, read the report.

**Files:**
- Modify: `slidecraft/commands/draft-deck.md` (full rewrite of the body; keep the frontmatter `description`/`argument-hint`)

**Interfaces:**
- Consumes: `draft_deck.py` (`--deck`, `--mode {digest,full}`, `--run-label`), `serve_deck.py` (`--deck`), the report shape from A2/A3.

- [ ] **Step 1: Rewrite the command body**

Replace everything in `slidecraft/commands/draft-deck.md` **after the frontmatter block** (keep lines 1-4, the `---`-delimited frontmatter) with:

````markdown
# Draft Deck

Draft (or extend) the deck **in the current working directory**. Requires an initialized deck
(`deck-context.json` present — else tell the user to run `/init-deck`). The whole pipeline is one
deterministic driver; you only pick the mode, start the preview, run the driver once, and read
its report. Every LLM role runs behind the invoke shim inside the driver — **you never mine,
plan, or compose in your own context.**

`<toolkit>` is the plugin root the wrapper passes:

- `<DRAFT>` = `<toolkit>/slidecraft/scripts/draft_deck.py`
- `<SERVE>` = `<toolkit>/slidecraft/scripts/serve_deck.py`

## 1. Ask the mode (one AskUserQuestion)

Ask, in the user's language, with **two** options:

- **"Process (chunk up) input knowledge only"** → `digest` — convert + mine; stops there. No
  slides are created. Use this to build up nuggets from new inputs without (re)composing.
- **"Process input knowledge and create slide deck"** → `full` — the whole
  convert→mine→plan→compose→validate pipeline.

## 2. Start the live preview (full mode only)

If the user chose **full**, start the background live server *before* the driver so the user can
watch the deck grow as slides compose:

    python "<SERVE>" --deck <deck>      # run with the tool's run_in_background

Read its one-line JSON: `served` (browser opening) / `reused` (already live) / `no-preview`
(Node/npm missing, or `ports 3030-3040 all in use` — continue drafting; the files still update
and the user can preview later via `show_slide_deck`). Record which, for the final report. In
**digest** mode, skip this — nothing gets composed.

## 3. Run the driver once

```
python "<DRAFT>" --deck <deck> --mode <digest|full> [--run-label <label>]
```

The driver re-derives all state from the filesystem each run (input/ vs input/processed/ for
convert, `mined_at` for mine, slide state for plan/compose), so a re-run after any stop resumes
by construction. It emits **one JSON report**:

```
{ "status": "ok"|"error", "mode": ..., "convert": {...}, "mine": {...},
  "plan": {...}|null, "compose": {...}|null, "validate": {...}|null,
  "stopped_at": null|"mine"|"plan", "stopped_detail"?: {...} }
```

## 4. Read the report

- **`status: "ok"`** — present the summary from the report:
  - `convert.sources_created`, `mine.sources_mined`, `mine.nuggets_created`;
  - any **dropped** miners (`mine.dropped` — a source's text or a figure that yielded no nugget
    after retries): flag each so the user knows what was skipped;
  - **full mode only:** `plan.slides_planned`; the composed slide list and the **Backup Slides**
    appendix from `compose.parked` (a slide whose *planner* exhausted → parked + flagged);
    `compose.failed_sections` (an *area* whose designer exhausted — its wireframe stays visible
    on an otherwise-valid slide; the user can re-run one area with
    `python "<toolkit>/slidecraft/scripts/compose_deck.py" --deck <deck> --slide <id> --section <role>`);
    `compose.figure_needed`; and `validate` (`ok` / `errors`). If `validate.exit_ok` is false,
    treat the deck as not green and surface `validate.errors`.
  - whether the live preview was `served`/`reused`/`no-preview`, and that a served preview stays
    running (close the window / Ctrl-C to stop it).
  - In **digest** mode, stop here — `plan`/`compose`/`validate` are `null` by design (not run).
- **`status: "error"`** — the one case you investigate. `stopped_at` names the phase (`mine` or
  `plan`) and `stopped_detail` carries the errors. A `mine` stop is a transport/infra failure
  (e.g. OWUI unreachable) — fix the cause and **re-run the same command**; it resumes from the
  un-mined source. A `plan` stop is an invalid plan after retries (nothing was composed) — surface
  the errors; re-running re-plans once the inputs/nuggets are sound.

Tell the user they can preview any time with `show_slide_deck.cmd` (Windows) / `show_slide_deck.sh`
(macOS/Linux). Every content slide traces to nuggets and the slide budget is respected.
````

- [ ] **Step 2: Verify the command references only real scripts and flags**

Run:

```bash
python -m slidecraft.scripts.draft_deck --help >/dev/null && \
grep -q -- "--mode" slidecraft/commands/draft-deck.md && \
grep -q "draft_deck.py" slidecraft/commands/draft-deck.md && \
grep -q "serve_deck.py" slidecraft/commands/draft-deck.md && \
echo OK
```

Expected: `OK` (the driver's `--mode` exists; the command names the real scripts). If `python -m slidecraft.scripts.draft_deck` fails, use `python slidecraft/scripts/draft_deck.py --help` instead.

- [ ] **Step 3: Confirm no stale references to the removed manual loop**

Run: `grep -nE "compose-brief|persist-nuggets|write-plan|set-status" slidecraft/commands/draft-deck.md`
Expected: no matches (the driver owns those seams now — the command must not hand-loop them). If any appear, remove them.

- [ ] **Step 4: Commit**

```bash
git add slidecraft/commands/draft-deck.md
git commit -m "docs(draft-deck): rewrite as 4-step driver command (design §8)"
```

---

# TRACK B — `/init-deck` automation

Independent of Track A. B1 and B2 are parallelizable; B3 depends on both.

---

## Task B1: `init_questions.json` spec + walker (§3)

The standard interview becomes data. Add the spec file and a tiny walker module that resolves the one branch rule (§3.1) so the command stays on rails and the rule is unit-tested.

**Files:**
- Create: `slidecraft/data/init_questions.json`
- Create: `slidecraft/scripts/init_interview.py`
- Create: `slidecraft/tests/test_init_interview.py`

**Interfaces:**
- Produces: `load_spec(path=None) -> dict`; `question(spec, qid) -> dict | None`; `follow_up(spec, qid, answer) -> dict | None | LLM_DECIDES` where `LLM_DECIDES` is a module-level sentinel string; a CLI `follow-up --qid <id> --answer <text> [--spec <path>]` printing `{"follow_up": <question|null>, "llm_decides": <bool>}`.

- [ ] **Step 1: Create the spec file**

Create `slidecraft/data/init_questions.json`:

```json
{
  "questions": [
    { "id": "topic", "prompt": "Deck topic / working title", "options": ["Skip"] },
    {
      "id": "audience",
      "prompt": "Who is this deck for?",
      "options": ["Students", "Experts", "Management", "General public"],
      "follow_up": {
        "Students": {
          "id": "deck_subtype",
          "prompt": "What kind of session?",
          "options": ["University lecture", "High school class"]
        }
      }
    },
    { "id": "language", "prompt": "Language for all composed content", "options": ["English", "German"] },
    { "id": "deck_type", "prompt": "Deck type", "options": ["Lecture", "Pitch", "Executive meeting", "Workshop"] },
    { "id": "setting", "prompt": "Where is it presented?", "options": ["University course", "Conference", "Internal meeting", "Trade fair"] },
    { "id": "max_duration_minutes", "prompt": "Maximum duration in minutes", "options": ["30", "45", "60", "90"] }
  ]
}
```

> Note: the **theme** question is intentionally *not* in this spec — it has a compound answer (`type` + `source`) and drives the prewarm/scan sequencing, so the command handles it specially (Task B3, §4.3). The spec grows more `follow_up` rules later without touching the walker.

- [ ] **Step 2: Write the failing walker tests**

Create `slidecraft/tests/test_init_interview.py`:

```python
"""The /init-deck question-spec walker (design §3): one branch rule, tested."""
from __future__ import annotations

from slidecraft.scripts import init_interview as iv

SPEC = {
    "questions": [
        {"id": "topic", "prompt": "Topic", "options": ["Skip"]},          # leaf
        {"id": "audience", "prompt": "Who?",
         "options": ["Students", "Experts"],
         "follow_up": {"Students": {"id": "deck_subtype", "prompt": "Kind?",
                                    "options": ["Lecture", "Class"]}}},    # branching
    ]
}


def test_branching_preset_with_followup_returns_it():
    fu = iv.follow_up(SPEC, "audience", "Students")
    assert isinstance(fu, dict) and fu["id"] == "deck_subtype"


def test_branching_preset_without_followup_returns_none():
    assert iv.follow_up(SPEC, "audience", "Experts") is None


def test_branching_other_defers_to_llm():
    assert iv.follow_up(SPEC, "audience", "Investors") is iv.LLM_DECIDES


def test_leaf_preset_returns_none():
    assert iv.follow_up(SPEC, "topic", "Skip") is None


def test_leaf_other_triggers_nothing():
    # The whole point of §3.1: a leaf "Other" is just the answer — never LLM.
    assert iv.follow_up(SPEC, "topic", "Object Tracking") is None


def test_unknown_question_raises():
    import pytest
    with pytest.raises(KeyError):
        iv.follow_up(SPEC, "nope", "x")


def test_shipped_spec_loads_and_has_audience_branch():
    spec = iv.load_spec()
    assert iv.follow_up(spec, "audience", "Students")["id"] == "deck_subtype"
    assert iv.follow_up(spec, "topic", "anything") is None
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python -m pytest slidecraft/tests/test_init_interview.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'slidecraft.scripts.init_interview'`

- [ ] **Step 4: Create the walker module**

Create `slidecraft/scripts/init_interview.py`:

```python
#!/usr/bin/env python
"""The /init-deck question-spec walker (design 2026-07-23 §3).

The standard interview is DATA (slidecraft/data/init_questions.json), not
improvised wording. This module is the single source of truth for the ONE
branch rule the spec encodes (§3.1):

  - A *branching* question carries a `follow_up` table keyed by option value.
    A preset answer resolves deterministically (table lookup). An **"Other"**
    (free-text) answer isn't in the table — this is the one interview-time LLM
    branch point: the caller (the /init-deck command) decides what follow-up,
    if any, applies.
  - A *leaf* question has no `follow_up` at all. "Other" here triggers
    nothing — the typed text is simply the answer. Without this asymmetry,
    "Other → LLM" would be read too broadly and route nearly every metadata
    answer through the LLM, defeating the point.

Deterministic, no LLM. The command calls the `follow-up` CLI between
AskUserQuestion calls to stay on rails.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

# Sentinel: a branching "Other" answer — the caller (LLM) decides the follow-up.
LLM_DECIDES = "__llm_decides__"

DATA = Path(__file__).resolve().parent.parent / "data" / "init_questions.json"


def load_spec(path=None) -> dict:
    p = Path(path) if path else DATA
    return json.loads(p.read_text(encoding="utf-8-sig"))


def question(spec: dict, qid: str) -> dict | None:
    """The top-level question with id `qid` (None if absent)."""
    for q in spec.get("questions", []):
        if q.get("id") == qid:
            return q
    return None


def follow_up(spec: dict, qid: str, answer: str):
    """Resolve the follow-up for answering question `qid` with `answer` (§3.1).

    Returns:
      - a follow-up question dict — a *branching* question answered with a
        PRESET option that maps to one;
      - ``None`` — a *leaf* question (no follow_up table), OR a branching
        question whose preset answer has no follow-up entry;
      - ``LLM_DECIDES`` — a *branching* question answered via **"Other"** (the
        answer isn't a preset option): the caller decides.
    """
    q = question(spec, qid)
    if q is None:
        raise KeyError(f"no question with id {qid!r}")
    table = q.get("follow_up")
    if not table:                            # leaf: "Other" triggers nothing
        return None
    if answer in table:                      # preset option with a follow-up
        return table[answer]
    if answer in (q.get("options") or []):   # preset option, no follow-up
        return None
    return LLM_DECIDES                        # "Other" on a branching question


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    fu = sub.add_parser("follow-up")
    fu.add_argument("--spec", default=None)
    fu.add_argument("--qid", required=True)
    fu.add_argument("--answer", required=True)
    a = ap.parse_args(argv)
    res = follow_up(load_spec(a.spec), a.qid, a.answer)
    print(json.dumps({"follow_up": None if res is LLM_DECIDES else res,
                      "llm_decides": res is LLM_DECIDES}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest slidecraft/tests/test_init_interview.py -v`
Expected: PASS (7 passed)

- [ ] **Step 6: Smoke-test the CLI both branches**

Run:

```bash
python slidecraft/scripts/init_interview.py follow-up --qid audience --answer Students
python slidecraft/scripts/init_interview.py follow-up --qid audience --answer Investors
```

Expected: first prints `{"follow_up": {...deck_subtype...}, "llm_decides": false}`; second prints `{"follow_up": null, "llm_decides": true}`.

- [ ] **Step 7: Commit**

```bash
git add slidecraft/data/init_questions.json slidecraft/scripts/init_interview.py slidecraft/tests/test_init_interview.py
git commit -m "feat(init-deck): declared interview spec + walker (design §3)"
```

---

## Task B2: cover-slot → questions resolver + answers storage (§4)

Replace the fixed presenter/institution/course/date question with theme-derived questions. Add a pure resolver to `scaffold_deck.py` and store the collected cover answers verbatim under `deck.cover`.

**Files:**
- Modify: `slidecraft/scripts/scaffold_deck.py` (add `cover_layout`, `cover_slot_questions`; store `deck.cover`)
- Test: `slidecraft/tests/test_scaffold_deck.py` (add cover-slot fixtures)

**Interfaces:**
- Consumes: scanned capabilities (`scan_theme.scan`) — each layout entry `{"name","slots":[...], "alias"?, "roles"?:{role:physical}, "intent"?, "defaults"?}`.
- Produces:
  - `cover_layout(capabilities) -> dict | None` — the cover layout entry (§4.1).
  - `cover_slot_questions(capabilities) -> list[dict]` — one `{"id","prompt","options":["Skip"]}` per askable cover slot (§4.2); `[]` when none.
  - `deck-context.deck.cover` — a `{slot: value}` map stored verbatim from `ans.get("cover", {})`.

- [ ] **Step 1: Write the failing resolver tests**

Add to `slidecraft/tests/test_scaffold_deck.py`:

```python
# ---------------------------------------------------------------------------
# Cover-slot resolution (design §4)
# ---------------------------------------------------------------------------

def _caps(*layouts):
    return {"layouts": list(layouts), "components": []}


def test_cover_layout_prefers_semantic_alias():
    caps = _caps({"name": "slide1", "slots": ["body-26"], "alias": "cover",
                  "roles": {"title": "body-26"}, "intent": "Deck cover."},
                 {"name": "cover", "slots": ["default"]})
    assert scaffold_deck.cover_layout(caps)["name"] == "slide1"   # alias wins


def test_cover_layout_falls_back_to_physical_name():
    caps = _caps({"name": "content", "slots": ["heading"]},
                 {"name": "cover", "slots": ["default"]})
    assert scaffold_deck.cover_layout(caps)["name"] == "cover"


def test_cover_layout_none_when_absent():
    caps = _caps({"name": "content", "slots": ["heading"]})
    assert scaffold_deck.cover_layout(caps) is None


def test_cover_questions_semantic_combined_field_asked_verbatim():
    # `meta` is a combined field — with the synonym table dropped it is asked
    # verbatim like any other slot (no composition). `title`/`date` are dropped.
    caps = _caps({"name": "slide1", "slots": ["body-26", "body-12", "body-1"],
                  "alias": "cover",
                  "roles": {"title": "body-26", "meta": "body-12",
                            "date": "body-1"},
                  "intent": "Deck cover: title; author+date in meta."})
    ids = [q["id"] for q in scaffold_deck.cover_slot_questions(caps)]
    assert ids == ["meta"]                       # title + date dropped


def test_cover_questions_semantic_standalone_field():
    caps = _caps({"name": "slide1", "slots": ["h", "p"], "alias": "cover",
                  "roles": {"title": "h", "presenter": "p"},
                  "intent": "Cover."})
    ids = [q["id"] for q in scaffold_deck.cover_slot_questions(caps)]
    assert ids == ["presenter"]


def test_cover_questions_physical_fallback():
    caps = _caps({"name": "cover", "slots": ["default", "author", "title"]})
    ids = [q["id"] for q in scaffold_deck.cover_slot_questions(caps)]
    assert ids == ["author"]                     # default + title dropped


def test_cover_questions_empty_when_no_cover_layout():
    caps = _caps({"name": "content", "slots": ["heading"]})
    assert scaffold_deck.cover_slot_questions(caps) == []


def test_cover_answers_stored_verbatim_in_deck_context(tmp_path):
    theme_dir = _make_theme(tmp_path / "theme", styleguide=False)
    deck = tmp_path / "deck"
    deck.mkdir()
    ans = _answers({"type": "local", "source": str(theme_dir)},
                   cover={"meta": "Dr. Jane Roe · 2026-07-23"})
    scaffold_deck.scaffold(deck, ans)
    ctx = json.loads((deck / "deck-context.json").read_text(encoding="utf-8"))
    assert ctx["deck"]["cover"] == {"meta": "Dr. Jane Roe · 2026-07-23"}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest slidecraft/tests/test_scaffold_deck.py -k cover -v`
Expected: FAIL with `AttributeError: module 'slidecraft.scripts.scaffold_deck' has no attribute 'cover_layout'` (and the storage test fails on the missing `deck.cover` key)

- [ ] **Step 3: Add the resolver functions**

In `slidecraft/scripts/scaffold_deck.py`, after `theme_name` (around line 191), add:

```python
# ---------------------------------------------------------------------------
# Cover-slot resolution (design 2026-07-23 §4)
# ---------------------------------------------------------------------------
# Replaces the fixed presenter/institution/course/date question with
# theme-derived questions, run after the theme is scanned. Slots never asked:
# `date` (filled with today), `title` (reuses the topic), and a bare `default`
# (one freeform area — nothing structured to ask). No synonym table, no
# canonicalization — whatever the theme calls a slot is asked verbatim (§4.2).
_COVER_SLOT_SKIP = {"date", "title", "default"}


def cover_layout(capabilities: dict):
    """The theme's cover layout entry from scanned capabilities (§4.1):
    the layout whose semantic ``alias == "cover"``, else the layout whose
    physical ``name == "cover"``, else ``None`` (no identifiable cover layout —
    the caller skips cover questions entirely)."""
    layouts = capabilities.get("layouts", [])
    for entry in layouts:
        if entry.get("alias") == "cover":
            return entry
    for entry in layouts:
        if entry.get("name") == "cover":
            return entry
    return None


def cover_slot_questions(capabilities: dict) -> list:
    """The metadata questions derived from the cover layout's slots (§4.2).

    Iterate the cover layout's semantic role names (when aliased) else its
    physical slot names; drop the never-asked slots; every other slot becomes
    one leaf/free-text question keyed by the slot name, verbatim. Returns ``[]``
    when there is no cover layout or nothing askable."""
    layout = cover_layout(capabilities)
    if not layout:
        return []
    roles = layout.get("roles")          # semantic role -> physical (aliased)
    slot_names = list(roles.keys()) if roles else list(layout.get("slots", []))
    intent = layout.get("intent", "")
    questions = []
    for slot in slot_names:
        if slot in _COVER_SLOT_SKIP:
            continue
        prompt = f'Cover slot "{slot}"'
        if intent:
            prompt += f" — {intent}"
        questions.append({"id": slot, "prompt": prompt, "options": ["Skip"]})
    return questions
```

- [ ] **Step 4: Store the cover answers in the deck block**

In `slidecraft/scripts/scaffold_deck.py`, in `build_deck_block` (around line 301), add the `cover` key to the returned dict (after the `date` line):

```python
        "date": str(ans.get("date", "")),
        # Theme-derived cover-slot answers, stored verbatim (§4.2). Absent when
        # the theme has no identifiable cover layout, or nothing was captured.
        "cover": dict(ans.get("cover", {})),
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest slidecraft/tests/test_scaffold_deck.py -k cover -v`
Expected: PASS (8 passed)

- [ ] **Step 6: Run the whole scaffold + scan suites (no regressions)**

Run: `python -m pytest slidecraft/tests/test_scaffold_deck.py slidecraft/tests/test_scan_theme.py -v`
Expected: PASS (existing tests + the 8 new ones)

- [ ] **Step 7: Commit**

```bash
git add slidecraft/scripts/scaffold_deck.py slidecraft/tests/test_scaffold_deck.py
git commit -m "feat(scaffold): cover-slot->questions resolver + deck.cover storage (design §4)"
```

---

## Task B3: `/init-deck` command rewrite (§7)

Rewrite the command as a thin spec-walker: walk `init_questions.json` for topic/theme, prewarm + scan on the theme answer to derive cover-slot questions, walk the rest + the cover questions, then one full scaffold call.

**Files:**
- Modify: `slidecraft/commands/init-deck.md` (full rewrite of the body; keep the frontmatter)

**Interfaces:**
- Consumes: `init_interview.py` (`load_spec`, `follow-up` CLI, B1); `scaffold_deck.py` (`--prewarm`, then full `--answers`; `cover_slot_questions`, B2); `scan_theme.py` (`--type`, `--source`).

- [ ] **Step 1: Rewrite the command body**

Replace everything in `slidecraft/commands/init-deck.md` **after the frontmatter block** (keep lines 1-4) with:

````markdown
# Init Deck

Initialize a deck **in the current working directory** (D25 — the deck root *is* the folder
Claude was launched in). The interview is **declared data**, walked mechanically: you call
`AskUserQuestion` exactly as the spec declares, resolve each branch with a deterministic helper,
and never improvise wording or research anything. The **only** time you exercise judgement is a
branching question answered via **"Other"** (§ step 4).

`<toolkit>` is the plugin root the wrapper passes. Scripts used:

- `<SCAFFOLD>` = `<toolkit>/slidecraft/scripts/scaffold_deck.py`
- `<SCAN>`     = `<toolkit>/slidecraft/scripts/scan_theme.py`
- `<IV>`       = `<toolkit>/slidecraft/scripts/init_interview.py`
- Spec: `<toolkit>/slidecraft/data/init_questions.json`

## 1. Guard (fast — a single-file check)

Check **only** whether `deck-context.json` already exists in the CWD (one stat / one `Glob`). If
it does, this folder is already a deck: **stop**, tell the user, offer to open it or pick another
folder. Do **not** re-scaffold and do **not** recursively scan the tree (slow on OneDrive, and
unnecessary — the folder need not be empty).

## 2. Interview part 1 — topic + theme (so the install can start early)

Walk the spec's `topic` question, then ask the **theme** question (handled specially — it is *not*
in the spec because its answer is compound). Ask both with **AskUserQuestion**, in the user's
language:

1. **`topic`** — the deck's working title / thematic focus. In the help text explain the *user
   benefit* (this focus guides which knowledge is extracted and keeps slides on-topic). Never
   expose internal terms.
2. **Theme** — where the Slidev theme comes from: built-in `default`, a local folder
   (`slidev-theme-<brand>/`), an npm package (`slidev-theme-*`), or a GitHub URL. Capture its
   `type` (builtin | local | npm | github) and `source`. (A **local** theme is copied into the
   deck's `theme/` subfolder by the scaffold, so the deck stays self-contained.)

## 3. Prewarm + background install + scan (on the theme answer)

As soon as topic + theme are known:

1. Write a partial answers JSON (`topic` + `theme`) to a temp file and run:
   ```
   python "<SCAFFOLD>" --answers <partial.json> --prewarm
   ```
   This creates folders, **copies a local theme into `theme/`**, and writes `package.json` /
   `.gitignore` / launchers. Its JSON output includes `node_modules_present`.
2. If `node_modules_present` is `false` **and** Node/npm is available, start `npm install
   --no-audit --no-fund` **in the background** from the deck root (CWD) with the tool's
   `run_in_background`. Do not block on it. Best-effort: skip silently if npm is missing/offline.
3. **Scan the now-copied theme** to derive the cover-slot questions for part 2 — this rides the
   same background window the install uses, so it adds no latency. For a **local** theme:
   ```
   python "<SCAN>" --type local --source ./theme
   ```
   (for builtin/npm/github pass the captured `type`/`source`). Feed the resulting `capabilities`
   to `scaffold_deck.cover_slot_questions` — either import it, or replicate its rule: find the
   layout whose `alias == "cover"` (else physical `name == "cover"`, else none); ask one
   free-text question per role/slot name it exposes, **skipping** `date`, `title`, and a bare
   `default`. If there is no cover layout, ask no metadata questions.

## 4. Interview part 2 — length, type, setting, cover metadata

Continue with **AskUserQuestion** (batched, up to 4 per call) while the install runs. Walk the
remaining spec questions in order — `language`, `deck_type`, `setting`, `max_duration_minutes` —
plus any **cover-slot questions** from step 3. For each spec question:

- Ask it exactly as declared. After the answer, resolve the follow-up deterministically:
  ```
  python "<IV>" follow-up --qid <question-id> --answer "<the answer>"
  ```
  - `follow_up` non-null → ask that follow-up question next.
  - `llm_decides: true` → the user answered a **branching** question via **"Other"**: *this* is
    where you (the LLM) decide whether a follow-up applies and, if so, ask a sensible one. This is
    the sole judgement call in the whole command.
  - both null/false → record the answer and move on (a leaf "Other" is just the answer — never a
    branch).
- **Length:** ask for the **maximum duration in minutes**; the slide budget is *derived* from it
  (~1.5 min/slide; the scaffold does the maths) — do not ask for a slide count. Only if the user
  volunteers a specific maximum, pass it as `max_slides`.
- **Cover metadata:** the cover-slot questions replace the old fixed presenter/institution/course/
  date batch. Fill a `date` slot programmatically with **today**; a `title` slot reuses the topic
  (both are never asked). Collect the cover-slot answers into a `cover` object keyed by slot name.

## 5. Scaffold (deterministic, full)

Write the complete answers to a temp JSON and run from the deck root:

```
python "<SCAFFOLD>" --answers <answers.json>
```

`answers.json` keys: `topic, audience, language, deck_type, setting, max_duration_minutes,
max_slides?, theme:{type, source}`, plus a `cover` object `{slot: value}` for the theme-derived
metadata (omit slots the user skipped). `max_slides` is optional (derived from the duration when
absent). This phase is idempotent over the prewarm and additionally writes `associations.json`,
`slides.md`, and **`deck-context.json`** (the `deck` block incl. the derived `max_slides` and the
`cover` map, the `theme` block with scanned `capabilities` + `styleguide.md` path, and the derived
per-agent `injection` blocks). Do not hand-write any of these files — the script owns the format.
The script reports the derived `max_slides` / `minutes_per_slide`; surface those so the budget is
transparent.

## 6. Close

If the background install is still running, mention it's finishing (the launcher waits either
way). Show the scaffold summary and instruct:

> Deck initialized (~{max_slides} slides for {duration} min at ~1.5 min/slide). Put your source
> files (PDF, Markdown, text) into `input/`, then run `/draft-deck`. To preview at any time,
> double-click `show_slide_deck.cmd` (Windows) or `show_slide_deck.sh` (macOS/Linux).

No content is generated at this stage — `/init-deck` runs no LLM role. The convert→mine→plan
chain lives in `/draft-deck`.
````

- [ ] **Step 2: Verify the command references only real scripts, flags, and spec ids**

Run:

```bash
python slidecraft/scripts/init_interview.py follow-up --qid audience --answer Students >/dev/null && \
python slidecraft/scripts/scan_theme.py --type builtin --source default >/dev/null && \
grep -q -- "--prewarm" slidecraft/commands/init-deck.md && \
grep -q "cover_slot_questions" slidecraft/commands/init-deck.md && \
grep -q "init_questions.json" slidecraft/commands/init-deck.md && \
echo OK
```

Expected: `OK`.

- [ ] **Step 3: Confirm the fixed metadata batch is gone**

Run: `grep -niE "presenter name.*institution.*course|batched question" slidecraft/commands/init-deck.md`
Expected: no matches (the fixed presenter/institution/course/date batch was replaced by cover-slot questions). If matches appear, remove that stale guidance.

- [ ] **Step 4: Commit**

```bash
git add slidecraft/commands/init-deck.md
git commit -m "docs(init-deck): rewrite as declared spec-walker with cover-slot questions (design §7)"
```

---

## Final verification (run after all tasks in a track)

- [ ] **Track A full suite:**

Run: `python -m pytest slidecraft/tests/test_serve_deck.py slidecraft/tests/test_draft_deck_integration.py slidecraft/tests/test_compose_deck.py -v`
Expected: all PASS.

- [ ] **Track B full suite:**

Run: `python -m pytest slidecraft/tests/test_init_interview.py slidecraft/tests/test_scaffold_deck.py slidecraft/tests/test_scan_theme.py -v`
Expected: all PASS.

- [ ] **Whole test suite (guard against cross-cutting regressions):**

Run: `python -m pytest slidecraft/tests -q`
Expected: all PASS.
