"""compose_deck.py — the batch driver (design §7): plan every to-compose slide,
then build each pending section concurrently, to a green deck."""
from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

from slidecraft.scripts import km, compose_deck
from slidecraft.tests.conftest import wire_fake_executor
from slidecraft.tests.test_km_plan import _add_nugget, _create
from slidecraft.tests.test_km_write_skeleton import _md


def test_compose_deck_plans_then_builds_sections(deck, tmp_path, capsys):
    _add_nugget(deck, "n1", raw_text="Left verbatim.", page=1)
    _add_nugget(deck, "n2", raw_text="Right verbatim.", page=1)
    sid = _create(deck, "Compare SLA and FDM", nuggets="n1,n2")
    capsys.readouterr()

    # Planner returns a two-section plan (both text); both designers return prose.
    plan = json.dumps({
        "layout": "two-cols", "concept_type": "compare",
        "title": "SLA präziser, FDM günstiger",
        "sections": {
            "left": {"type": "text", "instructions": "table", "nuggets": ["n1"]},
            "right": {"type": "text", "instructions": "prose", "nuggets": ["n2"]}}})
    wire_fake_executor(deck, tmp_path, "slide-composer", [plan])
    wire_fake_executor(deck, tmp_path, "text-designer",
                       ["- left built", "- right built"])

    report = compose_deck.compose_deck(deck, run_label="run-A", max_workers=2)

    assert sid in report["composed"]
    assert report["parked"] == [] and report["failed_sections"] == []
    md = _md(deck, sid)
    assert "left built" in md and "right built" in md
    assert km.load_state(deck, sid)["state"] == "composed"


def test_compose_deck_structural_slide_stops_after_skeleton(deck, tmp_path, capsys):
    sid = _create(deck, "Object Tracking", nuggets="")     # structural
    capsys.readouterr()
    plan = json.dumps({"layout": "content", "concept_type": "structural",
                       "title": "Object Tracking", "sections": {}})
    wire_fake_executor(deck, tmp_path, "slide-composer", [plan])

    report = compose_deck.compose_deck(deck, max_workers=2)
    assert sid in report["composed"]
    assert km.load_state(deck, sid)["state"] == "composed"
