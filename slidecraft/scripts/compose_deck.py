#!/usr/bin/env python
"""The batch driver (design §7): plan every to-compose slide, then build each
pending content section concurrently. Scope flags (--slide/--section) make the
batch path and the interactive-redo path the same code.

  per to-compose slide:
    km compose-brief  →  invoke_shim(slide-composer)  →  km write-skeleton
  per pending section (concurrent):
    design_section.design_one   (design-brief → OWUI → [image: download] → place)

The lead launches THIS and reads its report; it never hand-loops OWUI (D7).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from slidecraft.scripts import invoke_shim, km, design_section

KM = str(Path(km.__file__))
SHIM = str(Path(invoke_shim.__file__))


def to_compose_set(deck: Path) -> list[str]:
    """Active, unlocked slides not yet composed, in deck order."""
    out = []
    for sid in km.order(deck):
        stj = km.load_state(deck, sid)
        if stj.get("state") in ("locked", "composed", "parked"):
            continue
        out.append(sid)
    return out


def _plan_slide(deck: Path, sid: str, scratch: Path, run_label) -> dict:
    """compose-brief → planner invoke → write-skeleton. Returns write-skeleton's
    JSON (pending_sections), or {} and parks the slide on the planner terminal."""
    brief = scratch / f"plan-{sid}.md"
    subprocess.run([sys.executable, KM, "--deck", str(deck), "compose-brief",
                    "--slide", sid, "--out", str(brief)],
                   check=True, capture_output=True, text=True, encoding="utf-8")
    result = scratch / f"plan-{sid}.result.json"
    rc = subprocess.run(
        [sys.executable, SHIM, "--role", "slide-composer",
         "--brief-file", str(brief), "--deck", str(deck), "--slide", sid,
         *(["--run-label", run_label] if run_label else []),
         "--out", str(result), "--",
         sys.executable, KM, "--deck", str(deck), "write-skeleton",
         "--slide", sid, "--file", "{out}"],
        capture_output=True, text=True, encoding="utf-8").returncode
    if rc != 0:                                    # planner terminal → park
        subprocess.run([sys.executable, KM, "--deck", str(deck), "park-slide",
                        "--slide", sid, "--reason",
                        "planning failed after retries"],
                       capture_output=True, text=True, encoding="utf-8")
        return {}
    # write-skeleton wrote the sidecar; read pending sections from state.
    plan = km.load_state(deck, sid).get("plan") or {}
    pending = [r for r, s in (plan.get("sections") or {}).items()
               if s.get("status") == "pending"]
    return {"pending_sections": pending}


def _design_one_serialized(deck, sid, sec, run_label, lock: threading.Lock):
    """design_section.design_one, serialized per slide.

    Two sections of the SAME slide share one JSON state sidecar
    (slides/<sid>.json); km's place-design does an unlocked
    read-modify-write on it (last writer wins). Running both sections of one
    slide truly concurrently races that file — a lost update leaves one
    section's "placed" status clobbered back to "pending". Different slides
    have independent sidecars and stay fully parallel across the pool; only
    section-builds that share a slide are serialized here."""
    with lock:
        return design_section.design_one(deck, sid, sec, run_label=run_label)


def compose_deck(deck, *, slide=None, section=None, run_label=None,
                 max_workers=4) -> dict:
    deck = Path(deck)
    report = {"composed": [], "parked": [], "failed_sections": [],
              "figure_needed": [], "run_label": run_label}
    with tempfile.TemporaryDirectory(prefix="compose-deck-") as td:
        scratch = Path(td)
        slides = [slide] if slide else to_compose_set(deck)
        # Stage 1: plan slides that have no plan yet (writes wireframes; places
        # source-image). A slide that is ALREADY planned is resumed rather than
        # re-planned — re-planning would re-run write-skeleton, which rewrites
        # the whole slide from scratch and resets every section (including
        # already-placed siblings) to a pending wireframe. This makes a scoped
        # `--section` redo safe (siblings + placed work untouched) and makes
        # the batch driver itself resumable (an interrupted/re-run batch picks
        # up pending — and retries failed — sections instead of wiping them).
        pending_by_slide: dict[str, list[str]] = {}
        for sid in slides:
            stj = km.load_state(deck, sid)
            if stj.get("state") == "parked":
                continue
            existing = stj.get("plan")
            if existing:
                pending = [r for r, s in (existing.get("sections") or {}).items()
                          if s.get("status") in ("pending", "failed")]
            else:
                res = _plan_slide(deck, sid, scratch, run_label)
                if not res:
                    report["parked"].append(sid)
                    continue
                pending = res["pending_sections"]
            secs = [section] if section else pending
            pending_by_slide[sid] = secs

        # Stage 2: build every pending section concurrently (bounded). Sections
        # of the same slide are serialized against each other (see
        # _design_one_serialized) since they share one state sidecar file;
        # different slides still run fully in parallel across the pool.
        jobs = [(sid, sec) for sid, secs in pending_by_slide.items()
                for sec in secs]
        slide_locks: dict[str, threading.Lock] = defaultdict(threading.Lock)
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(_design_one_serialized, deck, sid, sec,
                                   run_label, slide_locks[sid]): (sid, sec)
                       for sid, sec in jobs}
            for fut in futures:
                sid, sec = futures[fut]
                try:
                    r = fut.result()
                except Exception as exc:               # never crash the batch
                    r = {"status": "failed", "errors": [str(exc)]}
                if r.get("status") != "placed":
                    report["failed_sections"].append(
                        {"slide": sid, "section": sec, "errors": r.get("errors")})

        # Finalize: every slide the driver planned (excluding parked ones) that
        # ends in state `composed` lands in report["composed"] exactly once —
        # this covers BOTH structural slides (no pending sections, promoted to
        # composed at write-skeleton time, so they never entered
        # pending_by_slide with any jobs) AND content slides whose sections all
        # placed. Building the set from `slides` (the planned scope) rather
        # than looping pending_by_slide + a second structural-only loop avoids
        # ever appending the same slide twice.
        parked_set = set(report["parked"])
        for sid in slides:
            if sid in parked_set:
                continue
            if km.load_state(deck, sid).get("state") == "composed":
                report["composed"].append(sid)
    return report


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--deck", required=True)
    ap.add_argument("--slide", default=None)
    ap.add_argument("--section", default=None)
    ap.add_argument("--run-label", dest="run_label", default=None)
    ap.add_argument("--max-workers", dest="max_workers", type=int, default=4)
    a = ap.parse_args(argv)
    report = compose_deck(Path(a.deck), slide=a.slide, section=a.section,
                          run_label=a.run_label, max_workers=a.max_workers)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
