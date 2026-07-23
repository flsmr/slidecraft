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


def test_scoped_section_redo_preserves_sibling_and_placed_work(deck, tmp_path, capsys):
    """A --slide/--section redo on an already-`composed` two-cols slide must
    NOT re-plan (which would call write-skeleton and reset every section back
    to a pending wireframe). It should rebuild only the scoped section off the
    existing plan sidecar, leaving the sibling section's placed content — and
    the slide's `composed` state — untouched."""
    _add_nugget(deck, "n1", raw_text="Left verbatim.", page=1)
    _add_nugget(deck, "n2", raw_text="Right verbatim.", page=1)
    sid = _create(deck, "Compare SLA and FDM", nuggets="n1,n2")
    capsys.readouterr()

    plan = json.dumps({
        "layout": "two-cols", "concept_type": "compare",
        "title": "SLA präziser, FDM günstiger",
        "sections": {
            "left": {"type": "text", "instructions": "table", "nuggets": ["n1"]},
            "right": {"type": "text", "instructions": "prose", "nuggets": ["n2"]}}})
    wire_fake_executor(deck, tmp_path, "slide-composer", [plan])
    wire_fake_executor(deck, tmp_path, "text-designer",
                       ["- left original", "- right original"])

    report = compose_deck.compose_deck(deck, run_label="run-A", max_workers=1)
    assert sid in report["composed"]
    assert report["parked"] == [] and report["failed_sections"] == []
    md_before = _md(deck, sid)
    assert "left original" in md_before and "right original" in md_before
    assert km.load_state(deck, sid)["state"] == "composed"

    # Re-wire text-designer to a fresh response set (fresh counter) for the
    # scoped redo of the `left` section only. A new base dir avoids clashing
    # with the first wiring's already-created responses-text-designer/ dir.
    redo_base = tmp_path / "redo"
    redo_base.mkdir()
    wire_fake_executor(deck, redo_base, "text-designer", ["- left REDONE"])

    redo_report = compose_deck.compose_deck(deck, slide=sid, section="left",
                                            run_label="redo", max_workers=1)
    assert redo_report["parked"] == [] and redo_report["failed_sections"] == []

    md_after = _md(deck, sid)
    assert "left REDONE" in md_after
    assert "left original" not in md_after           # left slot was rebuilt
    assert "right original" in md_after               # sibling untouched
    assert "pending" not in md_after                  # not reset to wireframe
    assert km.load_state(deck, sid)["state"] == "composed"
