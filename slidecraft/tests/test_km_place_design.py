"""Stage-2 persist: km place-design extracts + sanitizes + places a designer
reply and promotes the slide when the last section lands (design §6)."""
from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

from slidecraft.scripts import km
from slidecraft.tests.test_km_plan import _add_nugget, _create
from slidecraft.tests.test_km_write_skeleton import _write_skeleton, _md, _add_image_nugget


def _place(deck: Path, sid: str, role: str, stype: str, reply: str, asset=None):
    f = deck / f"reply-{role}.txt"
    f.write_text(reply, encoding="utf-8")
    km.cmd_place_design(deck, Namespace(slide=sid, section=role, type=stype,
                                        file=str(f), asset=asset))


def test_place_text_strips_fence_and_swaps_wireframe(deck, tmp_path, capsys):
    _add_nugget(deck, "n1", raw_text="x.", page=1)
    sid = _create(deck, "T", nuggets="n1")
    _write_skeleton(deck, sid, {
        "layout": "content", "concept_type": "define", "title": "T",
        "sections": {"body": {"type": "text", "instructions": "prose",
                              "nuggets": ["n1"]}}})
    capsys.readouterr()

    _place(deck, sid, "body", "text",
           "```markdown\n- point one\n- point two\n```")
    out = json.loads(capsys.readouterr().out)

    md = _md(deck, sid)
    assert "- point one" in md and "```" not in md   # fence stripped
    assert "pending" not in md                        # wireframe gone
    assert out["status"] == "placed"
    assert out["slide_state"] == "composed"           # last (only) section landed
    assert km.load_state(deck, sid)["plan"]["sections"]["body"]["status"] == "placed"


def test_place_diagram_writes_sfc_and_sanitizes_icons(deck, tmp_path, capsys):
    _add_nugget(deck, "n1", raw_text="x.", page=1)
    sid = _create(deck, "T", nuggets="n1")
    _write_skeleton(deck, sid, {
        "layout": "content", "concept_type": "process", "title": "T",
        "sections": {"body": {"type": "diagram", "instructions": "flow",
                              "nuggets": ["n1"]}}})
    capsys.readouterr()

    reply = ("```vue\n<template><div><carbon-not-a-real-icon/>"
             "<carbon-arrow-right/></div></template>\n```")
    _place(deck, sid, "body", "diagram", reply)

    sfc = (deck / "components" / f"Sec_{sid}_body.vue")
    assert sfc.exists()
    text = sfc.read_text(encoding="utf-8")
    assert "carbon-not-a-real-icon" not in text        # hallucinated icon replaced
    assert "carbon-arrow-right" in text                # allowlisted icon kept
    md = _md(deck, sid)
    assert f"<Sec_{sid}_body" in md


def test_place_diagram_inline_component_is_placed_verbatim(deck, tmp_path, capsys):
    _add_nugget(deck, "n1", raw_text="x.", page=1)
    sid = _create(deck, "T", nuggets="n1")
    _write_skeleton(deck, sid, {
        "layout": "content", "concept_type": "process", "title": "T",
        "sections": {"body": {"type": "diagram", "instructions": "flow",
                              "nuggets": ["n1"]}}})
    capsys.readouterr()
    reply = "<FlowDiagram>\n\n- Capture | in\n- Estimate | out\n\n</FlowDiagram>"
    _place(deck, sid, "body", "diagram", reply)
    md = _md(deck, sid)
    assert "<FlowDiagram>" in md and "Capture | in" in md
    assert not (deck / "components" / f"Sec_{sid}_body.vue").exists()  # no SFC file


def test_place_image_places_img_from_asset(deck, tmp_path, capsys):
    _add_nugget(deck, "n1", raw_text="x.", page=1)
    sid = _create(deck, "T", nuggets="n1")
    _write_skeleton(deck, sid, {
        "layout": "content", "concept_type": "finding", "title": "T",
        "sections": {"body": {"type": "image", "instructions": "render",
                              "nuggets": ["n1"]}}})
    capsys.readouterr()
    (deck / "public" / "gen").mkdir(parents=True, exist_ok=True)
    (deck / "public" / "gen" / f"{sid}_body.png").write_bytes(b"\x89PNG")
    _place(deck, sid, "body", "image", "ignored reply text",
           asset=f"/gen/{sid}_body.png")
    md = _md(deck, sid)
    assert f"/gen/{sid}_body.png" in md


def test_partial_placement_leaves_slide_planned(deck, tmp_path, capsys):
    _add_nugget(deck, "n1", raw_text="a.", page=1)
    _add_nugget(deck, "n2", raw_text="b.", page=1)
    sid = _create(deck, "T", nuggets="n1,n2")
    _write_skeleton(deck, sid, {
        "layout": "two-cols", "concept_type": "compare", "title": "T",
        "sections": {
            "left": {"type": "text", "instructions": "l", "nuggets": ["n1"]},
            "right": {"type": "text", "instructions": "r", "nuggets": ["n2"]}}})
    capsys.readouterr()
    _place(deck, sid, "left", "text", "- only left")
    out = json.loads(capsys.readouterr().out)
    assert out["slide_state"] == "planned"             # right still pending
