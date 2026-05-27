"""Tests for slidecraft.scripts.lint_slides.

Fixtures synthesise a tiny theme + a deck-with-slides under ``tmp_path`` for
each test. The theme is a single ``semantic-layouts.json`` modeled on the
real ILSE theme — we don't need actual ``.vue`` files for the lint, only
the alias/slot map JSON.

Each rule has one positive test (lint fires) and the clean-slide test at the
end exercises the negative case for all rules at once.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from slidecraft.scripts.lint_slides import (
    ERROR,
    WARNING,
    lint_deck,
    main,
    parse_slide,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


ILSE_LIKE_LAYOUTS = {
    "version": "1.1",
    "theme": "slidev-theme-test",
    "aliases": {
        "cover": {
            "layout": "slide1",
            "slots": {"title": "body-26", "subtitle": "body-25",
                       "body": "body-12"},
            "intent": "Cover slide.",
        },
        "default": {
            "layout": "slide4",
            "slots": {"title": "title", "body": "ph-1",
                       "citations": "body-13"},
            "intent": "Default content slide.",
        },
        "content-image": {
            "layout": "slide5",
            "slots": {"title": "title", "body": "body-16",
                       "image": "picture-14", "citations": "body-13"},
            "intent": "Content with primary figure.",
        },
        "section": {
            "layout": "slide3",
            "slots": {"title": "title", "body": "body-21"},
            "intent": "Section divider.",
        },
        "end": {
            "layout": "slide9",
            "slots": {"title": "title", "body": "body-13"},
            "intent": "Closing slide.",
            "defaults": {"title": "Thank you"},
        },
    },
    "unmapped_layouts": [],
}


def _write_theme(themes_root: Path, theme_name: str) -> Path:
    """Write the synthetic theme under
    ``<themes_root>/<bundle>/<theme_name>/semantic-layouts.json``.

    Mirrors the real ILSE-theme/slidev-theme-ilse layout the resolver walks.
    """
    bundle = themes_root / "test-bundle"
    theme_dir = bundle / theme_name
    theme_dir.mkdir(parents=True)
    (theme_dir / "semantic-layouts.json").write_text(
        json.dumps(ILSE_LIKE_LAYOUTS), encoding="utf-8"
    )
    return theme_dir


def _make_deck(tmp_path: Path,
               *,
               theme_name: str = "slidev-theme-test",
               with_bib: bool = True,
               ) -> Path:
    """Scaffold a deck dir with theme, slides.md, references.bib.

    Layout matches the real OneDrive shape: a ``slidecraft-themes`` sibling
    of the deck's parent so the resolver finds it via the parent-walk.
    """
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    themes_root = workspace / "slidecraft-themes"
    _write_theme(themes_root, theme_name)

    decks_root = workspace / "decks"
    decks_root.mkdir()
    deck = decks_root / "my-deck"
    (deck / "slides").mkdir(parents=True)

    # Minimal slides.md so the theme resolver finds the theme name.
    (deck / "slides.md").write_text(
        f"---\ntheme: {theme_name}\ntitle: Test\n"
        f"src: ./slides/cover.md\n---\n",
        encoding="utf-8",
    )
    if with_bib:
        (deck / "references.bib").write_text(
            "@book{szeliski2022,\n"
            "  title = {Computer Vision},\n  year = {2022},\n}\n",
            encoding="utf-8",
        )
    return deck


def _write_slide(deck: Path, name: str, content: str) -> Path:
    path = deck / "slides" / f"{name}.md"
    path.write_text(content, encoding="utf-8")
    return path


# Speaker notes long enough to clear the L10 threshold (>= 50 chars).
LONG_NOTES = (
    "<!--\nSpeaker notes for the slide go here and are substantive "
    "enough to clear the fifty-character L10 threshold.\n-->"
)


def _clean_slide(layout: str = "slide5",
                 title_slot: str = "title",
                 body_slot: str = "body-16",
                 ) -> str:
    """Return a known-good slide body with everything the lint rules want."""
    return (
        "---\n"
        f"id: clean\nlayout: {layout}\n"
        "sources:\n  - key: szeliski2022\n    locator: \"§1\"\n"
        "    relevance: \"test\"\n"
        "---\n\n"
        f"::{title_slot}::\nClean slide title is a verbal claim\n\n"
        f"::{body_slot}::\n- one bullet\n- two bullet\n\n"
        + LONG_NOTES
    )


# ---------------------------------------------------------------------------
# Rule-by-rule tests
# ---------------------------------------------------------------------------


def test_l1_semantic_layout_name_errors(tmp_path):
    deck = _make_deck(tmp_path)
    _write_slide(deck, "bad-layout",
                 _clean_slide(layout="content-image"))
    findings, errors, _ = lint_deck(deck)
    l1 = [f for f in findings if f.rule == "L1"]
    assert len(l1) == 1
    assert l1[0].severity == ERROR
    assert "slide5" in l1[0].fix


def test_l2_semantic_slot_name_errors(tmp_path):
    deck = _make_deck(tmp_path)
    # layout slide5 == content-image alias whose body map is body → body-16.
    # Authoring ::body:: instead of ::body-16:: should fire L2.
    _write_slide(deck, "bad-slot",
                 _clean_slide(body_slot="body"))
    findings, _, _ = lint_deck(deck)
    l2 = [f for f in findings if f.rule == "L2"]
    assert any("body-16" in f.fix for f in l2)
    assert all(f.severity == ERROR for f in l2)


def test_l3_image_inside_slot_errors(tmp_path):
    deck = _make_deck(tmp_path)
    content = (
        "---\nid: with-img\nlayout: slide5\nsources: []\n---\n\n"
        "::title::\nA slide with image inside slot\n\n"
        "::picture-14::\n![alt](/figures/foo.png)\n\n"
        + LONG_NOTES
    )
    _write_slide(deck, "with-img", content)
    findings, _, _ = lint_deck(deck)
    l3 = [f for f in findings if f.rule == "L3"]
    assert len(l3) == 1
    assert l3[0].severity == ERROR
    assert "picture-14" in l3[0].message


def test_l3_html_img_inside_slot_errors(tmp_path):
    deck = _make_deck(tmp_path)
    content = (
        "---\nid: html-img\nlayout: slide5\nsources: []\n---\n\n"
        "::title::\nHTML image case\n\n"
        "::picture-14::\n<img src=\"/figures/foo.png\" alt=\"x\">\n\n"
        + LONG_NOTES
    )
    _write_slide(deck, "html-img", content)
    findings, _, _ = lint_deck(deck)
    assert any(f.rule == "L3" for f in findings)


def test_l4_blank_line_in_slot_errors(tmp_path):
    deck = _make_deck(tmp_path)
    # Two-paragraph slot body: MDC closes the block at the blank line.
    content = (
        "---\nid: blank-slot\nlayout: slide5\nsources: []\n---\n\n"
        "::title::\nBlank line inside slot test\n\n"
        "::body-16::\nFirst paragraph of body content.\n\n"
        "Second paragraph leaks into slide root.\n\n"
        + LONG_NOTES
    )
    _write_slide(deck, "blank-slot", content)
    findings, _, _ = lint_deck(deck)
    l4 = [f for f in findings if f.rule == "L4"]
    assert len(l4) == 1 and l4[0].severity == ERROR


def test_l5_bad_yaml_errors(tmp_path):
    deck = _make_deck(tmp_path)
    # Unbalanced quote on the title value — our regex-based YAML check
    # catches this without needing PyYAML.
    content = (
        "---\nid: bad-yaml\nlayout: slide4\n"
        "title: \"unclosed quote here\nsources: []\n---\n\n"
        "::title::\nBad YAML test\n\n"
        + LONG_NOTES
    )
    _write_slide(deck, "bad-yaml", content)
    findings, errors, _ = lint_deck(deck)
    assert any(f.rule == "L5" and f.severity == ERROR for f in findings)


def test_l6_formula_in_title_warns_then_promotes_with_strict(tmp_path):
    deck = _make_deck(tmp_path)
    content = (
        "---\nid: formula-title\nlayout: slide4\nsources: []\n---\n\n"
        "::title::\nP = K[R|t] composes the projection\n\n"
        "::ph-1::\nBody content here that is fine.\n\n"
        + LONG_NOTES
    )
    _write_slide(deck, "formula-title", content)

    findings, errors, warnings = lint_deck(deck)
    l6 = [f for f in findings if f.rule == "L6"]
    assert len(l6) == 1
    # Default severity is WARNING.
    assert l6[0].severity == WARNING

    # Under --strict, the exit code promotes; we test exit-code behaviour
    # through main() below.


def test_l6_strict_exit_code_is_2(tmp_path, capsys):
    deck = _make_deck(tmp_path)
    content = (
        "---\nid: formula-title\nlayout: slide4\nsources: []\n---\n\n"
        "::title::\nP = K[R|t] composes the projection\n\n"
        "::ph-1::\nBody content.\n\n"
        + LONG_NOTES
    )
    _write_slide(deck, "formula-title", content)
    exit_code = main(["--deck", str(deck), "--strict"])
    assert exit_code == 2


def test_l8_citations_slot_without_bib_warns(tmp_path):
    deck = _make_deck(tmp_path, with_bib=False)
    # body-13 is the physical name the ILSE-like theme maps citations to.
    content = (
        "---\nid: cite-no-bib\nlayout: slide4\nsources: []\n---\n\n"
        "::title::\nA slide with citation footer\n\n"
        "::ph-1::\n- bullet\n\n"
        "::body-13::\nSzeliski 2022, §1\n\n"
        + LONG_NOTES
    )
    _write_slide(deck, "cite-no-bib", content)
    findings, _, _ = lint_deck(deck)
    assert any(f.rule == "L8" and f.severity == WARNING for f in findings)


def test_l9_missing_cite_key_warns(tmp_path):
    deck = _make_deck(tmp_path)  # bib has only szeliski2022
    content = (
        "---\nid: bad-key\nlayout: slide4\n"
        "sources:\n  - key: notInBib2025\n"
        "    locator: \"§1\"\n    relevance: \"x\"\n"
        "---\n\n"
        "::title::\nA cited slide\n\n"
        "::ph-1::\n- bullet\n\n"
        + LONG_NOTES
    )
    _write_slide(deck, "bad-key", content)
    findings, _, _ = lint_deck(deck)
    l9 = [f for f in findings if f.rule == "L9"]
    assert len(l9) == 1
    assert "notInBib2025" in l9[0].message


def test_l10_missing_speaker_notes_warns(tmp_path):
    deck = _make_deck(tmp_path)
    # No trailing speaker-notes comment.
    content = (
        "---\nid: no-notes\nlayout: slide4\nsources: []\n---\n\n"
        "::title::\nNo notes here\n\n"
        "::ph-1::\n- bullet\n"
    )
    _write_slide(deck, "no-notes", content)
    findings, _, _ = lint_deck(deck)
    assert any(f.rule == "L10" and f.severity == WARNING for f in findings)


def test_l11_body_over_49_words_warns(tmp_path):
    deck = _make_deck(tmp_path)
    long_body = " ".join(f"word{i}" for i in range(60))
    content = (
        "---\nid: wordy\nlayout: slide4\nsources: []\n---\n\n"
        "::title::\nA wordy body\n\n"
        f"::ph-1::\n{long_body}\n\n"
        + LONG_NOTES
    )
    _write_slide(deck, "wordy", content)
    findings, _, _ = lint_deck(deck)
    l11 = [f for f in findings if f.rule == "L11"]
    assert len(l11) == 1
    assert "60 words" in l11[0].message


def test_l12_five_consecutive_same_layout_warns(tmp_path):
    deck = _make_deck(tmp_path)
    # Five clean slides all on layout slide4 — over the > 4 threshold.
    for i in range(5):
        _write_slide(deck, f"s{i}", _clean_slide(layout="slide4",
                                                  body_slot="ph-1"))
    # Rebuild slides.md so the order is deterministic for L12.
    (deck / "slides.md").write_text(
        "---\ntheme: slidev-theme-test\ntitle: Test\n"
        "src: ./slides/s0.md\n---\n"
        + "".join(f"---\nsrc: ./slides/s{i}.md\n---\n" for i in range(1, 5)),
        encoding="utf-8",
    )
    findings, _, _ = lint_deck(deck)
    l12 = [f for f in findings if f.rule == "L12"]
    assert len(l12) == 1
    assert "5 consecutive" in l12[0].message


def test_clean_slide_has_no_findings(tmp_path):
    deck = _make_deck(tmp_path)
    _write_slide(deck, "clean", _clean_slide())
    findings, errors, warnings = lint_deck(deck)
    # The deck-level theme-resolution warning may fire if our resolver
    # didn't find the theme — assert it found theme so we're testing the
    # positive path.
    assert not any(f.rule == "L0" for f in findings), \
        f"theme should resolve cleanly; got: {[f.message for f in findings]}"
    # Clean slide produces zero findings.
    slide_findings = [f for f in findings
                       if f.file.name == "clean.md"]
    assert slide_findings == [], \
        f"clean slide produced: {[(f.rule, f.message) for f in slide_findings]}"


def test_cli_happy_path_exits_zero(tmp_path, capsys):
    deck = _make_deck(tmp_path)
    _write_slide(deck, "clean", _clean_slide())
    exit_code = main(["--deck", str(deck)])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "linted 1 files" in captured.out
    assert "0 errors" in captured.out


def test_cli_missing_deck_dir_returns_1(capsys):
    exit_code = main(["--deck", "/no/such/path/qq"])
    captured = capsys.readouterr()
    assert exit_code == 1
    assert "error:" in captured.err


def test_cli_no_slides_dir_returns_1(tmp_path, capsys):
    # A deck dir that exists but has no slides/ subfolder.
    (tmp_path / "empty-deck").mkdir()
    exit_code = main(["--deck", str(tmp_path / "empty-deck")])
    captured = capsys.readouterr()
    assert exit_code == 1
    assert "no slides/ directory" in captured.err


def test_cli_error_exits_1(tmp_path, capsys):
    deck = _make_deck(tmp_path)
    _write_slide(deck, "bad", _clean_slide(layout="content-image"))
    exit_code = main(["--deck", str(deck)])
    assert exit_code == 1


def test_parse_slide_extracts_slots_and_layout(tmp_path):
    deck = _make_deck(tmp_path)
    path = _write_slide(deck, "probe", _clean_slide())
    slide = parse_slide(path)
    assert slide.layout == "slide5"
    assert {b.name for b in slide.slots} == {"title", "body-16"}
    assert slide.has_frontmatter
    assert any("szeliski2022" == k for k, _ in slide.sources_keys)
