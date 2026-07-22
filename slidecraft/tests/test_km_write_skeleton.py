"""Stage-1 persist: km write-skeleton validates the plan JSON, renders a
wireframe, places source-image areas, and persists the plan sidecar (design §4/§6)."""
from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

import pytest

from slidecraft.scripts import km
from slidecraft.tests.test_km_plan import _add_nugget, _create


def _write_skeleton(deck: Path, sid: str, plan: dict):
    f = deck / "plan-out.json"
    f.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    km.cmd_write_skeleton(deck, Namespace(slide=sid, file=str(f)))


def _md(deck: Path, sid: str) -> str:
    return (deck / "slides" / f"{sid}.md").read_text(encoding="utf-8")


def _add_image_nugget(deck: Path, nid: str, name="fig1.png"):
    (deck / "public" / "extracted").mkdir(parents=True, exist_ok=True)
    (deck / "public" / "extracted" / name).write_bytes(b"\x89PNG fake")
    (deck / "nuggets").mkdir(exist_ok=True)
    (deck / "nuggets" / f"{nid}.json").write_text(json.dumps({
        "nugget_id": nid, "kind": "image", "title": "Fig",
        "information": "- x", "visible_text": ["Predict", "Update"],
        "description": "predict-update loop", "asset": f"/extracted/{name}",
        "source": "chapter_4.md", "page": 2}), encoding="utf-8")
    return nid


def test_two_cols_plan_writes_wireframe_and_pending_sections(deck, tmp_path, capsys):
    _add_nugget(deck, "n1", raw_text="Left passage.", page=1)
    _add_nugget(deck, "n2", raw_text="Right passage.", page=1)
    sid = _create(deck, "SLA vs FDM", nuggets="n1,n2")
    capsys.readouterr()

    _write_skeleton(deck, sid, {
        "layout": "two-cols", "concept_type": "compare",
        "title": "SLA ist präziser, FDM skaliert",
        "sections": {
            "left": {"type": "text", "instructions": "Table of tradeoffs.",
                     "nuggets": ["n1"]},
            "right": {"type": "diagram", "instructions": "A decision tree …",
                      "nuggets": ["n2"]}}})
    out = json.loads(capsys.readouterr().out)

    assert out["state"] == "planned"
    assert sorted(out["pending_sections"]) == ["left", "right"]
    md = _md(deck, sid)
    assert "layout: cols" in md                 # physical layout (theme)
    assert "SLA ist präziser" in md             # title in frontmatter
    assert "::col-a::" in md and "::col-b::" in md   # physical slots
    assert "pending" in md                       # wireframe marker
    assert "decision tree" in md.lower()         # instruction shown as blockquote
    stj = km.load_state(deck, sid)
    assert stj["plan"]["sections"]["left"]["status"] == "pending"


def test_source_image_section_is_placed_without_a_designer(deck, tmp_path, capsys):
    img = _add_image_nugget(deck, "img1")
    sid = _create(deck, "The tracking loop", nuggets="img1")
    capsys.readouterr()

    _write_skeleton(deck, sid, {
        "layout": "content", "concept_type": "process",
        "title": "The tracking loop",
        "sections": {"body": {"type": "source-image",
                              "instructions": "Reference photo.",
                              "nuggets": ["img1"]}}})
    out = json.loads(capsys.readouterr().out)

    assert out["pending_sections"] == []
    assert out["placed_sections"] == ["body"]
    md = _md(deck, sid)
    assert "/extracted/fig1.png" in md          # the real asset placed
    stj = km.load_state(deck, sid)
    assert stj["plan"]["sections"]["body"]["status"] == "placed"


def test_structural_slide_bypasses_sections(deck, tmp_path, capsys):
    sid = _create(deck, "Object Tracking", nuggets="")     # structural: no nuggets
    capsys.readouterr()
    _write_skeleton(deck, sid, {"layout": "content", "concept_type": "structural",
                                "title": "Object Tracking", "sections": {}})
    out = json.loads(capsys.readouterr().out)
    assert out["pending_sections"] == []
    assert "Object Tracking" in _md(deck, sid)


def test_invalid_layout_is_a_rejection(deck, tmp_path, capsys):
    _add_nugget(deck, "n1", raw_text="x.", page=1)
    sid = _create(deck, "T", nuggets="n1")
    capsys.readouterr()
    with pytest.raises(SystemExit) as exc:
        _write_skeleton(deck, sid, {
            "layout": "no-such", "concept_type": "define", "title": "T",
            "sections": {"body": {"type": "text", "instructions": "x",
                                  "nuggets": ["n1"]}}})
    assert "layout" in str(exc.value) and str(exc.value) != "2"   # exit 1 (Rejection)


def test_content_slide_rejects_out_of_scope_layout(deck, tmp_path, capsys):
    # image-split IS an offered theme layout (D43 composer scope) but carries
    # an "image" role, so it's OUT of D4 scope for the planner — a content
    # slide (non-empty sections) must be validated against planner_layouts,
    # not the wider offered_layouts.
    _add_nugget(deck, "n1", raw_text="x.", page=1)
    sid = _create(deck, "T", nuggets="n1")
    capsys.readouterr()
    with pytest.raises(SystemExit) as exc:
        _write_skeleton(deck, sid, {
            "layout": "image-split", "concept_type": "define", "title": "T",
            "sections": {"body": {"type": "text", "instructions": "x",
                                  "nuggets": ["n1"]}}})
    assert "layout" in str(exc.value) and str(exc.value) != "2"   # exit 1 (Rejection)


def test_source_image_without_a_figure_nugget_is_rejected(deck, tmp_path, capsys):
    _add_nugget(deck, "n1", raw_text="x.", page=1)             # text, not a figure
    sid = _create(deck, "T", nuggets="n1")
    capsys.readouterr()
    with pytest.raises(SystemExit) as exc:
        _write_skeleton(deck, sid, {
            "layout": "content", "concept_type": "define", "title": "T",
            "sections": {"body": {"type": "source-image",
                                  "instructions": "x", "nuggets": ["n1"]}}})
    assert "figure" in str(exc.value).lower()
