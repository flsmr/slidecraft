"""Tests for the D47 slide-variant mechanics (get-variants + cycle-variant)."""
from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

from slidecraft.scripts import km


def _slide(deck: Path, sid: str, body: str) -> None:
    """Write a canonical slide file + its shared state (bypassing compose)."""
    (deck / "slides").mkdir(exist_ok=True)
    (deck / "slides" / f"{sid}.md").write_text(body, encoding="utf-8")
    (deck / "slides" / f"{sid}.json").write_text(
        json.dumps({"slide_id": sid, "state": "composed", "title": sid}),
        encoding="utf-8")


def _variant(deck: Path, sid: str, n: int, body: str) -> None:
    (deck / "slides" / f"{sid}_v{n}.md").write_text(body, encoding="utf-8")


def test_is_variant_file():
    assert km.is_variant_file("intro--20260722-1_v1")
    assert km.is_variant_file("intro--20260722-1_v12")
    assert not km.is_variant_file("intro--20260722-1")        # canonical stamp
    assert not km.is_variant_file("a-b--20260722-120000-000")  # hyphens only


def test_get_variants_lists_canonical_then_siblings(deck, capsys):
    _slide(deck, "sX", "# canonical\n")
    _variant(deck, "sX", 2, "# two\n")
    _variant(deck, "sX", 1, "# one\n")
    capsys.readouterr()

    km.cmd_get_variants(deck, Namespace(slide="sX"))
    out = json.loads(capsys.readouterr().out)

    assert out["count"] == 3
    assert out["files"] == ["sX.md", "sX_v1.md", "sX_v2.md"]  # numeric order


def test_slide_files_and_validate_ignore_variants(deck, capsys):
    _slide(deck, "sX", "# canonical\n")
    _variant(deck, "sX", 1, "# alt\n")

    stems = {p.stem for p in km.slide_files(deck)}
    assert "sX" in stems
    assert "sX_v1" not in stems  # variant is invisible to the slide enumerator


def _bodies(deck: Path, sid: str) -> dict[str, str]:
    return {p.name: p.read_text(encoding="utf-8")
            for p in km.variant_files(deck, sid)}


def test_cycle_up_makes_v1_the_active(deck, capsys):
    _slide(deck, "sX", "CANON")
    _variant(deck, "sX", 1, "V1")
    _variant(deck, "sX", 2, "V2")
    capsys.readouterr()

    km.cmd_cycle_variant(deck, Namespace(slide="sX", dir="up"))
    out = json.loads(capsys.readouterr().out)

    assert out == {"ok": True, "cycled": True, "count": 3, "dir": "up"}
    b = _bodies(deck, "sX")
    assert b["sX.md"] == "V1"        # former _v1 is now active
    assert b["sX_v2.md"] == "CANON"  # former active rotated to the last slot
    assert set(b.values()) == {"CANON", "V1", "V2"}  # nothing lost


def test_cycle_up_three_times_returns_to_start(deck, capsys):
    _slide(deck, "sX", "CANON")
    _variant(deck, "sX", 1, "V1")
    _variant(deck, "sX", 2, "V2")
    before = _bodies(deck, "sX")
    for _ in range(3):
        km.cmd_cycle_variant(deck, Namespace(slide="sX", dir="up"))
    capsys.readouterr()
    assert _bodies(deck, "sX") == before


def test_cycle_down_is_inverse_of_up(deck, capsys):
    _slide(deck, "sX", "CANON")
    _variant(deck, "sX", 1, "V1")
    _variant(deck, "sX", 2, "V2")
    before = _bodies(deck, "sX")
    km.cmd_cycle_variant(deck, Namespace(slide="sX", dir="up"))
    km.cmd_cycle_variant(deck, Namespace(slide="sX", dir="down"))
    capsys.readouterr()
    assert _bodies(deck, "sX") == before


def test_cycle_noop_when_no_siblings(deck, capsys):
    _slide(deck, "sX", "CANON")
    capsys.readouterr()
    km.cmd_cycle_variant(deck, Namespace(slide="sX", dir="up"))
    out = json.loads(capsys.readouterr().out)
    assert out == {"ok": True, "cycled": False, "count": 1}


def test_cycle_leaves_slides_md_and_state_untouched(deck, capsys):
    _slide(deck, "sX", "CANON")
    _variant(deck, "sX", 1, "V1")
    slides_md = (deck / "slides.md").read_text(encoding="utf-8")
    state = (deck / "slides" / "sX.json").read_text(encoding="utf-8")
    km.cmd_cycle_variant(deck, Namespace(slide="sX", dir="up"))
    capsys.readouterr()
    assert (deck / "slides.md").read_text(encoding="utf-8") == slides_md
    assert (deck / "slides" / "sX.json").read_text(encoding="utf-8") == state
    assert not list((deck / "slides").glob("*.cycletmp"))  # scratch cleaned


def _nugget(deck: Path, nid: str) -> None:
    (deck / "nuggets").mkdir(exist_ok=True)
    (deck / "nuggets" / f"{nid}.json").write_text(json.dumps(
        {"nugget_id": nid, "kind": "text", "source": "s.md", "page": 1,
         "title": nid, "information": "i", "raw_text": "r"}), encoding="utf-8")


def test_merge_preserves_predecessors_as_variants(deck, capsys):
    # Two content slides A (with its own variant) and B.
    _nugget(deck, "n1"); _nugget(deck, "n2")
    km.cmd_create(deck, Namespace(title="A", nuggets="n1", after="end",
                                  parked=False, intended_function=None))
    km.cmd_create(deck, Namespace(title="B", nuggets="n2", after="end",
                                  parked=False, intended_function=None))
    capsys.readouterr()
    a_id = next(p.stem for p in km.slide_files(deck) if p.stem.startswith("a--"))
    b_id = next(p.stem for p in km.slide_files(deck) if p.stem.startswith("b--"))
    # Give A a hand-made alternative rendering.
    (deck / "slides" / f"{a_id}.md").write_text("A-CANON", encoding="utf-8")
    (deck / "slides" / f"{a_id}_v1.md").write_text("A-ALT", encoding="utf-8")
    (deck / "slides" / f"{b_id}.md").write_text("B-CANON", encoding="utf-8")

    km.cmd_merge(deck, Namespace(slides=f"{a_id},{b_id}", title="Merged"))
    out = json.loads(capsys.readouterr().out)
    m_id = out["slide_id"]

    # Predecessor .md/.json gone; merged slide has 3 variant renderings.
    assert not (deck / "slides" / f"{a_id}.md").exists()
    assert not (deck / "slides" / f"{a_id}.json").exists()
    assert not (deck / "slides" / f"{b_id}.json").exists()
    variant_bodies = {p.read_text(encoding="utf-8")
                      for p in km.variant_files(deck, m_id)[1:]}  # the _vN
    assert variant_bodies == {"A-CANON", "A-ALT", "B-CANON"}
    # Union association + single active slide in order.
    assoc = json.loads((deck / "associations.json").read_text(encoding="utf-8"))
    assert assoc[m_id] == ["n1", "n2"]
    assert km.order(deck).count(m_id) == 1
