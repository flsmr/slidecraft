"""Tests for slidecraft.scripts.scaffold_deck.

Ticket 10 wiring:
  * T3 — the theme's ``styleguide.md`` path reaches the deck context: recorded
    in the ``theme`` block and injected as ``STYLE-GUIDE`` for both the
    slide-composer and the image-composer (empty when the theme has none). The
    enriched slot-role capabilities (roles/intent/defaults) flow through from
    ``scan_theme`` into ``theme.capabilities``.
  * T6 — the deck metadata the old skeleton substituted (presenter, institution,
    course, date) is captured into ``deck`` and exposed to the slide-composer,
    with a derived ``FOOTER``. These are optional — absence must not break.

Tests build a tiny local theme + answers file under ``tmp_path`` and call
``scaffold`` with an explicit root, so nothing depends on the real CWD.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from slidecraft.scripts import scaffold_deck


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_theme(root: Path, *, styleguide: bool = True) -> Path:
    """A minimal local theme with a semantic-layouts contract + styleguide."""
    layouts = root / "layouts"
    layouts.mkdir(parents=True)
    (layouts / "slide1.vue").write_text(
        '<template><slot name="body-26" /></template>', encoding="utf-8")
    (root / "semantic-layouts.json").write_text(json.dumps({
        "aliases": {
            "cover": {"layout": "slide1", "slots": {"title": "body-26"},
                      "intent": "Deck cover.", "defaults": {}},
        }
    }), encoding="utf-8")
    if styleguide:
        (root / "styleguide.md").write_text("# Style\n", encoding="utf-8")
    return root


def _answers(theme: dict, **extra) -> dict:
    base = {
        "topic": "Object Tracking",
        "audience": "students",
        "language": "en",
        "deck_type": "lecture",
        "setting": "university course",
        "max_slides": 20,
        "max_duration_minutes": 45,
        "theme": theme,
    }
    base.update(extra)
    return base


# ---------------------------------------------------------------------------
# T3 — style guide reaches theme block + both composer injections
# ---------------------------------------------------------------------------


def test_styleguide_recorded_and_injected_for_local_theme(tmp_path):
    theme_dir = _make_theme(tmp_path / "theme", styleguide=True)
    deck = tmp_path / "deck"
    deck.mkdir()
    ans = _answers({"type": "local", "source": str(theme_dir)})

    scaffold_deck.scaffold(deck, ans)
    ctx = json.loads((deck / "deck-context.json").read_text(encoding="utf-8"))

    sg = ctx["theme"]["styleguide"]
    assert sg.endswith("styleguide.md") and Path(sg).is_file()
    assert ctx["injection"]["slide-composer"]["STYLE-GUIDE"] == sg
    assert ctx["injection"]["image-composer"]["STYLE-GUIDE"] == sg


def test_enriched_capabilities_flow_into_theme_block(tmp_path):
    theme_dir = _make_theme(tmp_path / "theme")
    deck = tmp_path / "deck"
    deck.mkdir()
    ans = _answers({"type": "local", "source": str(theme_dir)})

    scaffold_deck.scaffold(deck, ans)
    ctx = json.loads((deck / "deck-context.json").read_text(encoding="utf-8"))

    layout = ctx["theme"]["capabilities"]["layouts"][0]
    assert layout["alias"] == "cover"
    assert layout["roles"] == {"title": "body-26"}


def test_styleguide_empty_for_builtin_theme(tmp_path):
    deck = tmp_path / "deck"
    deck.mkdir()
    ans = _answers({"type": "builtin", "source": "default"})

    scaffold_deck.scaffold(deck, ans)
    ctx = json.loads((deck / "deck-context.json").read_text(encoding="utf-8"))

    assert ctx["theme"]["styleguide"] == ""
    assert ctx["injection"]["slide-composer"]["STYLE-GUIDE"] == ""
    assert ctx["injection"]["image-composer"]["STYLE-GUIDE"] == ""


# ---------------------------------------------------------------------------
# T6 — deck metadata captured + exposed + FOOTER derived
# ---------------------------------------------------------------------------


def test_deck_metadata_captured_and_exposed(tmp_path):
    deck = tmp_path / "deck"
    deck.mkdir()
    ans = _answers(
        {"type": "builtin", "source": "default"},
        presenter="Dr. Jane Roe", institution="IU", course="DLBAI01",
        date="2026-07-18",
    )

    scaffold_deck.scaffold(deck, ans)
    ctx = json.loads((deck / "deck-context.json").read_text(encoding="utf-8"))

    d = ctx["deck"]
    assert d["presenter"] == "Dr. Jane Roe"
    assert d["institution"] == "IU"
    assert d["course"] == "DLBAI01"
    assert d["date"] == "2026-07-18"

    comp = ctx["injection"]["slide-composer"]
    assert comp["PRESENTER"] == "Dr. Jane Roe"
    assert comp["INSTITUTION"] == "IU"
    assert comp["COURSE"] == "DLBAI01"
    assert comp["DATE"] == "2026-07-18"
    # FOOTER derived as "presenter · date".
    assert comp["FOOTER"] == "Dr. Jane Roe · 2026-07-18"


def test_deck_metadata_optional_absent_is_empty(tmp_path):
    deck = tmp_path / "deck"
    deck.mkdir()
    ans = _answers({"type": "builtin", "source": "default"})

    scaffold_deck.scaffold(deck, ans)
    ctx = json.loads((deck / "deck-context.json").read_text(encoding="utf-8"))

    d = ctx["deck"]
    assert d["presenter"] == ""
    assert d["institution"] == ""
    assert d["date"] == ""
    comp = ctx["injection"]["slide-composer"]
    assert comp["PRESENTER"] == ""
    assert comp["FOOTER"] == ""


def test_footer_derived_from_presenter_only(tmp_path):
    deck = tmp_path / "deck"
    deck.mkdir()
    ans = _answers({"type": "builtin", "source": "default"},
                   presenter="Jane Roe")
    scaffold_deck.scaffold(deck, ans)
    ctx = json.loads((deck / "deck-context.json").read_text(encoding="utf-8"))
    assert ctx["injection"]["slide-composer"]["FOOTER"] == "Jane Roe"
