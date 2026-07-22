"""Regression tests for slidecraft.scripts.km.

Guards the theme reference in ``slides.md``. ``km.write_order`` runs on every
``create-slide`` / ``merge-slides`` and rewrites the ``slides.md`` headmatter;
it must **preserve** the deck's theme from ``deck-context.json`` rather than
hardcode ``theme: default``. When a local-theme deck's manifest reverts to
``theme: default``, Slidev prompts to install ``@slidev/theme-default`` at
launch (regression seen 2026-07-18: drafting a deck clobbered the scaffold's
localized ``./theme`` reference).

Tests build a tiny local theme under ``tmp_path`` and scaffold a real deck, so
nothing depends on the real CWD.
"""
from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

from slidecraft.scripts import scaffold_deck, km


def _make_theme(root: Path) -> Path:
    """A minimal local theme with a semantic-layouts contract."""
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
    return root


def _answers(theme: dict) -> dict:
    return {
        "topic": "Object Tracking",
        "audience": "students",
        "language": "en",
        "deck_type": "lecture",
        "setting": "university course",
        "max_slides": 20,
        "max_duration_minutes": 45,
        "theme": theme,
    }


def _scaffold(tmp_path: Path, theme: dict) -> Path:
    deck = tmp_path / "deck"
    deck.mkdir()
    scaffold_deck.scaffold(deck, _answers(theme))
    return deck


def _create_slide(deck: Path, title: str = "Intro") -> None:
    km.cmd_create(deck, Namespace(title=title, nuggets="", after="end"))


def test_create_slide_preserves_local_theme(tmp_path):
    theme_dir = _make_theme(tmp_path / "theme")
    deck = _scaffold(tmp_path, {"type": "local", "source": str(theme_dir)})

    # Scaffold writes the localized ``./theme`` reference…
    assert "theme: ./theme" in (deck / "slides.md").read_text(encoding="utf-8")

    # …and creating a slide must not clobber it back to ``theme: default``.
    _create_slide(deck)
    md = (deck / "slides.md").read_text(encoding="utf-8")
    assert "theme: ./theme" in md
    assert "theme: default" not in md


def test_repeated_creates_keep_local_theme(tmp_path):
    theme_dir = _make_theme(tmp_path / "theme")
    deck = _scaffold(tmp_path, {"type": "local", "source": str(theme_dir)})
    for i in range(3):
        _create_slide(deck, title=f"Slide {i}")
    md = (deck / "slides.md").read_text(encoding="utf-8")
    assert md.count("theme: ./theme") == 1
    assert "theme: default" not in md


def test_create_slide_preserves_builtin_theme(tmp_path):
    deck = _scaffold(tmp_path, {"type": "builtin", "source": "default"})
    _create_slide(deck)
    md = (deck / "slides.md").read_text(encoding="utf-8")
    assert "theme: default" in md


# ---------------------------------------------------------------------------
# Presenter-notes auto-fill (D39)
# ---------------------------------------------------------------------------
# ``set-content`` fills empty Slidev speaker notes from the slide's nuggets'
# raw knowledge (verbatim), so a presenter has the full source behind the
# telegraphic body. The composer's own notes win; structural slides get none.

def _write_nugget(deck: Path, nid: str, **fields) -> str:
    """Write a nugget JSON straight to nuggets/ (bypassing the miner/guard)."""
    (deck / "nuggets" / f"{nid}.json").write_text(
        json.dumps({"nugget_id": nid, **fields}, ensure_ascii=False),
        encoding="utf-8")
    return nid


def _create_slide_with(deck: Path, title: str, nuggets: str):
    """Create a slide associated with the given comma-separated nugget ids,
    returning its stamped slide id (read back from associations)."""
    km.cmd_create(deck, Namespace(title=title, nuggets=nuggets, after="end"))
    assoc = json.loads((deck / "associations.json").read_text(encoding="utf-8"))
    # The just-created slide is the one whose association matches our nuggets.
    want = [n for n in nuggets.split(",") if n]
    return next(sid for sid, nugs in assoc.items() if nugs == want)


def _set_content(deck: Path, sid: str, body: str):
    body_file = deck / "logs" / "body.tmp"
    body_file.write_text(body, encoding="utf-8")
    km.cmd_set_content(deck, Namespace(slide=sid, body_file=str(body_file)))


_BODY = "---\nlayout: slide1\ntitle: Intro\n---\n\n# The claim\n\n- one bullet\n"


def _deck_with_theme(tmp_path: Path) -> Path:
    theme_dir = _make_theme(tmp_path / "theme")
    return _scaffold(tmp_path, {"type": "local", "source": str(theme_dir)})


def test_set_content_fills_notes_from_text_raw(tmp_path):
    deck = _deck_with_theme(tmp_path)
    _write_nugget(deck, "n1", kind="text", source="chapter_4.pdf", page=2,
                  title="T", information="digest",
                  raw_text="LiDAR measures distance via laser travel time.")
    sid = _create_slide_with(deck, "Intro", "n1")

    _set_content(deck, sid, _BODY)
    md = (deck / "slides" / f"{sid}.md").read_text(encoding="utf-8")

    # The telegraphic body is preserved…
    assert "# The claim" in md
    # …and a trailing speaker-notes comment carries the verbatim raw_text + locator.
    assert md.rstrip().endswith("-->")
    note = md[md.rindex("<!--"):]
    assert "LiDAR measures distance via laser travel time." in note
    assert "chapter_4.pdf p.2" in note


def test_set_content_fills_notes_from_image_visible_text(tmp_path):
    deck = _deck_with_theme(tmp_path)
    _write_nugget(deck, "img1", kind="image", source="diagram.png", page=4,
                  title="Fig", information="a flow diagram",
                  visible_text=["Sensor", "Filter", "Estimate"])
    sid = _create_slide_with(deck, "Figure", "img1")

    _set_content(deck, sid, _BODY)
    note = (deck / "slides" / f"{sid}.md").read_text(encoding="utf-8")
    note = note[note.rindex("<!--"):]
    for label in ("Sensor", "Filter", "Estimate"):
        assert label in note
    assert "diagram.png p.4 · figure" in note


def test_set_content_preserves_composer_authored_notes(tmp_path):
    deck = _deck_with_theme(tmp_path)
    _write_nugget(deck, "n1", kind="text", source="chapter_4.pdf", page=2,
                  title="T", information="digest", raw_text="Raw source passage.")
    sid = _create_slide_with(deck, "Intro", "n1")

    authored = _BODY + "\n<!--\nMy own speaker notes.\n-->\n"
    _set_content(deck, sid, authored)
    md = (deck / "slides" / f"{sid}.md").read_text(encoding="utf-8")

    assert "My own speaker notes." in md
    # The raw fallback must NOT be appended when the composer wrote notes.
    assert "Raw source passage." not in md
    assert md.count("<!--") == 1


def test_set_content_no_notes_for_structural_slide(tmp_path):
    deck = _deck_with_theme(tmp_path)
    sid = _create_slide_with(deck, "Agenda", "")  # structural: no nuggets

    _set_content(deck, sid, _BODY)
    md = (deck / "slides" / f"{sid}.md").read_text(encoding="utf-8")

    assert "<!--" not in md  # nothing to source; notes stay empty


def test_set_content_notes_cover_all_nuggets(tmp_path):
    deck = _deck_with_theme(tmp_path)
    _write_nugget(deck, "n1", kind="text", source="a.pdf", page=1,
                  title="A", information="d", raw_text="First passage.")
    _write_nugget(deck, "n2", kind="text", source="b.pdf", page=3,
                  title="B", information="d", raw_text="Second passage.")
    sid = _create_slide_with(deck, "Merged topic", "n1,n2")

    _set_content(deck, sid, _BODY)
    note = (deck / "slides" / f"{sid}.md").read_text(encoding="utf-8")
    note = note[note.rindex("<!--"):]
    assert "First passage." in note
    assert "Second passage." in note


def test_set_content_reports_notes_added(tmp_path, capsys):
    deck = _deck_with_theme(tmp_path)
    _write_nugget(deck, "n1", kind="text", source="a.pdf", page=1,
                  title="A", information="d", raw_text="A passage.")
    sid = _create_slide_with(deck, "Intro", "n1")

    capsys.readouterr()  # drop the create-slide output
    _set_content(deck, sid, _BODY)
    assert json.loads(capsys.readouterr().out.strip())["notes_added"] is True


# ---------------------------------------------------------------------------
# Manifest hygiene — no blank leading slide, no ``---`` in slide ids
# ---------------------------------------------------------------------------
# Two Slidev gotchas the generated slides.md must avoid: a standalone headmatter
# block opens the deck on a blank slide; and a ``src:`` path containing ``---``
# is silently dropped, so that slide vanishes from the deck.

def test_write_order_folds_first_import_into_headmatter(tmp_path):
    deck = _deck_with_theme(tmp_path)
    _create_slide(deck, title="First")
    _create_slide(deck, title="Second")
    md = (deck / "slides.md").read_text(encoding="utf-8")
    assert md.startswith("---\n")
    headmatter = md[4:md.index("\n---\n", 3)]
    # The first slide is imported inside the headmatter -> no blank leading slide.
    assert "src: ./slides/" in headmatter


def test_slugify_no_trailing_hyphen_after_truncation():
    # A 60-char cut landing on a hyphen must not leave a trailing hyphen:
    # ``slug`` + ``--`` stamp would become ``---`` and Slidev drops that import.
    title = "Erfolgreiche Automatisierung braucht drei zusammenspielende Ebenen"
    slug = km.slugify(title)
    assert len(slug) <= 60
    assert not slug.startswith("-") and not slug.endswith("-")


def test_create_slide_id_has_no_triple_dash(tmp_path):
    deck = _deck_with_theme(tmp_path)
    km.cmd_create(deck, Namespace(
        title="Erfolgreiche Automatisierung braucht drei zusammenspielende Ebenen",
        nuggets="", after="end"))
    A = json.loads((deck / "associations.json").read_text(encoding="utf-8"))
    sid = next(iter(A))
    assert "---" not in sid                       # would be dropped by Slidev
    assert sid in (deck / "slides.md").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Template rendering — leftover placeholder guard (widened regex)
# ---------------------------------------------------------------------------

import pytest


def test_render_template_guard_catches_underscore_placeholder():
    # A hyphen-style placeholder resolves; an UNRESOLVED underscore-style name
    # must still trip the leftover guard (widened regex).
    with pytest.raises(SystemExit) as exc:
        km.render_template("Hello %NAME% and %DECK_TYPE%", {"NAME": "x"})
    assert "%DECK_TYPE%" in str(exc.value)


def test_render_template_resolves_underscore_named_value():
    # A value whose KEY has an underscore still substitutes (only the leftover
    # SCAN changed, not substitution).
    out = km.render_template("v=%DECK_TYPE%", {"DECK_TYPE": "lecture"})
    assert out == "v=lecture"
