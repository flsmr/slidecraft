"""Transient status slide (2026-07-22 live-drafting-preview): an inline,
uncounted status block at the FRONT of slides.md while drafting, removed on
clear. It must never change order()/the slide budget."""
from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from slidecraft.scripts import km
from slidecraft.tests.conftest import deck  # noqa: F401


def _create(deck: Path, title: str) -> str:
    import contextlib, io, json
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        km.cmd_create(deck, Namespace(title=title, nuggets="", after="end",
                                      parked=False, intended_function=None))
    return json.loads(buf.getvalue())["slide_id"]


def test_set_status_adds_uncounted_front_block(deck, capsys):
    a = _create(deck, "Alpha")
    b = _create(deck, "Beta")
    capsys.readouterr()
    before = km.order(deck)

    km.cmd_set_status(deck, Namespace(phase="compose", detail="1/2",
                                      label="Composing slides…"))
    capsys.readouterr()

    md = (deck / "slides.md").read_text(encoding="utf-8")
    assert "Composing slides…" in md                   # status visible
    assert km.order(deck) == before                    # SAME active slides
    assert len(km.order(deck)) == 2                     # budget unchanged
    # The status block appears before the first real slide import.
    assert md.index("Composing slides…") < md.index(f"src: ./slides/{a}.md")


def test_status_block_when_no_slides_yet(deck, capsys):
    # During mining there are no slides; slides.md is status-only.
    km.cmd_set_status(deck, Namespace(phase="mine", detail="1/3",
                                      label="Mining sources…"))
    capsys.readouterr()
    md = (deck / "slides.md").read_text(encoding="utf-8")
    assert "Mining sources…" in md
    assert km.order(deck) == []
    assert "src: ./slides/" not in md


def test_clear_status_removes_the_block_cleanly(deck, capsys):
    a = _create(deck, "Alpha")
    km.cmd_set_status(deck, Namespace(phase="compose", detail="1/1", label="x"))
    km.cmd_clear_status(deck, Namespace())
    capsys.readouterr()
    md = (deck / "slides.md").read_text(encoding="utf-8")
    assert "Composing" not in md and "Temporary drafting status" not in md
    assert not (deck / ".draft-status.json").exists()
    assert km.order(deck) == [a]                        # untouched
    # The cover fold is restored: the slide is imported normally again.
    assert f"src: ./slides/{a}.md" in md
    assert md.startswith("---")                         # headmatter first, not a status body


def test_clear_status_is_noop_without_file(deck, capsys):
    _create(deck, "Alpha")
    km.cmd_clear_status(deck, Namespace())             # must not raise
    capsys.readouterr()
