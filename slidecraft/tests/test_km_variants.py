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
