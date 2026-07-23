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


def _clear_source_nuggets(deck: Path, original_file: str) -> None:
    """Delete any nuggets already persisted for a source before (re-)mining it.
    Only ever called for an UNMINED source, whose nuggets — if any — are
    leftovers from a prior run that stopped mid-source before mark-mined, and
    were therefore never planned or placed. Clearing them makes resume
    duplicate-free without ever touching a fully-mined source's nuggets."""
    for np in (deck / "nuggets").glob("*.json"):
        try:
            n = json.loads(np.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if n.get("source") == original_file:
            np.unlink()


def _checked(argv, phase: str, detail: dict | None = None):
    """Run a deterministic km/converter subprocess; on a non-zero exit raise
    _Stop(phase) instead of letting an uncaught CalledProcessError escape — so
    the driver always returns its JSON report (honors main()'s contract even
    under a transient OneDrive file lock). Returns the CompletedProcess on
    success (callers that need stdout read it)."""
    proc = _run(argv)
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or f"exited {proc.returncode}").strip()
        raise _Stop(phase, {**(detail or {}), "errors": [err]})
    return proc


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
        # Resume-safe: drop any nuggets a prior stopped run already persisted
        # for this (still-unmined) source, so re-mining never duplicates them.
        _clear_source_nuggets(deck, src["original_file"])

        # a. text — one invoke over the whole source text
        tbrief = scratch / f"mine-{slug}.md"
        _checked([sys.executable, KM, "--deck", str(deck), "mine-brief",
                  "--source", slug, "--out", str(tbrief)], "mine",
                 {"source": slug})
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
            info = _checked([sys.executable, KM, "--deck", str(deck),
                             "mine-brief", "--image", iid, "--out", str(ibrief)],
                            "mine", {"image": iid})
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
        _checked([sys.executable, KM, "--deck", str(deck), "mark-mined",
                  "--source", slug], "mine", {"source": slug})

    return {"sources_mined": len(sources),
            "nuggets_created": _nugget_count(deck) - before,
            "dropped": dropped}


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
    _checked([sys.executable, KM, "--deck", str(deck), "plan-brief",
              "--out", str(pbrief)], "plan")
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
    budget, so a step failure is infra — route through _checked so it still
    reports rather than escaping as an uncaught error."""
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
        _checked([sys.executable, KM, "--deck", str(deck), *argv], "plan")


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
