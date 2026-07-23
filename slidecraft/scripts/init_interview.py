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
