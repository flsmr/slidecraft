"""Stage-2 assemble: km design-brief renders the right designer template with
routed nuggets (%NUGGETS%), the full slide raw material (%RAW-MATERIAL%, D13),
and type-specific values (component catalog / exact-text + aspect ratio)."""
from __future__ import annotations

import json
import re
from argparse import Namespace
from pathlib import Path

from slidecraft.scripts import km
from slidecraft.tests.test_km_plan import _add_nugget, _create
from slidecraft.tests.test_km_write_skeleton import _write_skeleton, _add_image_nugget


def _design_brief(deck: Path, sid: str, role: str, out: Path) -> str:
    km.cmd_design_brief(deck, Namespace(slide=sid, section=role, out=str(out)))
    return out.read_text(encoding="utf-8")


def test_text_design_brief_routes_nuggets_and_full_raw_material(deck, tmp_path, capsys):
    _add_nugget(deck, "n1", raw_text="Left verbatim.", page=1)
    _add_nugget(deck, "n2", raw_text="Right verbatim.", page=1)
    sid = _create(deck, "Compare", nuggets="n1,n2")
    _write_skeleton(deck, sid, {
        "layout": "two-cols", "concept_type": "compare", "title": "Compare A/B",
        "sections": {
            "left": {"type": "text", "instructions": "Make a table.", "nuggets": ["n1"]},
            "right": {"type": "text", "instructions": "Short prose.", "nuggets": ["n2"]}}})
    capsys.readouterr()

    brief = _design_brief(deck, sid, "left", tmp_path / "b.md")

    assert "Make a table." in brief                 # instructions
    assert "Left verbatim." in brief                # routed nugget (%NUGGETS%)
    assert "Right verbatim." in brief               # full raw material (D13)
    assert "Compare A/B" in brief                    # %CORE-MESSAGE% = plan title
    assert not re.search(r"%[A-Z][A-Z_-]*%", brief)


def test_diagram_design_brief_carries_component_catalog(deck, tmp_path, capsys):
    _add_nugget(deck, "n1", raw_text="Flow verbatim.", page=1)
    sid = _create(deck, "Flow", nuggets="n1")
    _write_skeleton(deck, sid, {
        "layout": "content", "concept_type": "process", "title": "The flow",
        "sections": {"body": {"type": "diagram",
                              "instructions": "A left-to-right pipeline …",
                              "nuggets": ["n1"]}}})
    capsys.readouterr()
    brief = _design_brief(deck, sid, "body", tmp_path / "b.md")
    assert "FlowDiagram" in brief                    # real catalog injected
    assert not re.search(r"%[A-Z][A-Z_-]*%", brief)


def test_image_design_brief_sets_aspect_and_exact_text(deck, tmp_path, capsys):
    img = _add_image_nugget(deck, "img1")            # visible_text ["Predict","Update"]
    _add_nugget(deck, "n1", raw_text="Loop verbatim.", page=1)
    sid = _create(deck, "Loop", nuggets="n1,img1")
    _write_skeleton(deck, sid, {
        "layout": "content", "concept_type": "process", "title": "The loop",
        "sections": {"body": {"type": "image",
                              "instructions": "Render the predict-update loop.",
                              "nuggets": ["n1", "img1"]}}})
    capsys.readouterr()
    brief = _design_brief(deck, sid, "body", tmp_path / "b.md")
    assert "16:9" in brief                            # body → 16:9 (D17)
    assert "Predict" in brief and "Update" in brief   # %EXACT-TEXT% from visible_text
