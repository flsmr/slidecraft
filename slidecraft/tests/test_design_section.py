"""design_section.py — the atomic expert unit (design §7): design-brief → OWUI
→ (image: download) → place-design, with per-attempt logging."""
from __future__ import annotations

import base64
import json
from argparse import Namespace
from pathlib import Path

from slidecraft.scripts import km, design_section
from slidecraft.tests.conftest import wire_fake_executor
from slidecraft.tests.test_km_plan import _add_nugget, _create
from slidecraft.tests.test_km_write_skeleton import _write_skeleton, _md, _add_image_nugget


def test_download_image_from_data_uri(tmp_path):
    raw = base64.b64encode(b"\x89PNG-bytes").decode()
    reply = f"data:image/png;base64,{raw}"
    dest = design_section.download_image(reply, tmp_path / "out.png")
    assert dest.exists() and dest.read_bytes() == b"\x89PNG-bytes"


def test_design_one_text_section_places_and_promotes(deck, tmp_path, capsys):
    _add_nugget(deck, "n1", raw_text="x.", page=1)
    sid = _create(deck, "T", nuggets="n1")
    _write_skeleton(deck, sid, {
        "layout": "content", "concept_type": "define", "title": "T",
        "sections": {"body": {"type": "text", "instructions": "prose",
                              "nuggets": ["n1"]}}})
    capsys.readouterr()
    wire_fake_executor(deck, tmp_path, "text-designer", ["- built point"])

    res = design_section.design_one(deck, sid, "body")
    assert res["status"] == "placed"
    assert "- built point" in _md(deck, sid)
    assert km.load_state(deck, sid)["state"] == "composed"


def test_design_one_image_downloads_and_places(deck, tmp_path, capsys):
    _add_nugget(deck, "n1", raw_text="x.", page=1)
    sid = _create(deck, "T", nuggets="n1")
    _write_skeleton(deck, sid, {
        "layout": "content", "concept_type": "finding", "title": "T",
        "sections": {"body": {"type": "image", "instructions": "render",
                              "nuggets": ["n1"]}}})
    capsys.readouterr()
    raw = base64.b64encode(b"\x89PNGgen").decode()
    wire_fake_executor(deck, tmp_path, "image-designer",
                       [f"data:image/png;base64,{raw}"], image_arg=False)

    res = design_section.design_one(deck, sid, "body")
    assert res["status"] == "placed"
    assert (deck / "public" / "gen" / f"{sid}_body.png").exists()
    assert f"/gen/{sid}_body.png" in _md(deck, sid)
