"""Tests for slidecraft.scripts.render_cif.

Every fixture here builds a synthetic CIF + theme directory in a temp
location — we never reach into the real ILSE3 theme or any other on-disk
asset. That keeps the tests deterministic and lets each one tweak the
mapping schema in isolation.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from slidecraft.scripts.render_cif import (
    RenderResult,
    main,
    render_cif,
)


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _build_deck(
    tmp_path: Path,
    *,
    theme_name: str = "slidev-theme-test",
    theme_subdir: str = "theme",
    semantic_layouts: dict | None = None,
    layout_files: list[str] | None = None,
    write_slidecraft_json: bool = True,
) -> tuple[Path, Path]:
    """Lay out ``<tmp_path>/deck/`` + a sibling theme directory.

    Returns ``(deck_dir, theme_dir)``. The CIF goes to
    ``<deck>/.slidecraft/cif.json`` (caller writes it). ``.slidecraft.json``
    is written when *write_slidecraft_json* is True (most tests want this;
    test #14 disables it).
    """
    deck_dir = tmp_path / "deck"
    deck_dir.mkdir(parents=True, exist_ok=True)
    (deck_dir / ".slidecraft").mkdir(exist_ok=True)

    theme_dir = tmp_path / theme_subdir
    theme_dir.mkdir(parents=True, exist_ok=True)
    (theme_dir / "layouts").mkdir(exist_ok=True)

    if semantic_layouts is not None:
        _write_json(theme_dir / "semantic-layouts.json", semantic_layouts)

    for name in (layout_files or []):
        (theme_dir / "layouts" / f"{name}.vue").write_text(
            "<template><div/></template>", encoding="utf-8")

    if write_slidecraft_json:
        rel = Path("..") / theme_subdir
        _write_json(deck_dir / ".slidecraft.json", {
            "theme": {"name": theme_name, "path": rel.as_posix()},
        })

    return deck_dir, theme_dir


def _write_cif(deck_dir: Path, cif: dict) -> Path:
    cif_path = deck_dir / ".slidecraft" / "cif.json"
    _write_json(cif_path, cif)
    return cif_path


# ---------------------------------------------------------------------------
# 1. Flavour A — semantic-layouts.json present
# ---------------------------------------------------------------------------


def test_flavour_a_emits_named_slot_blocks(tmp_path):
    deck_dir, _ = _build_deck(
        tmp_path,
        semantic_layouts={
            "aliases": {
                "cover": {
                    "layout": "slide1",
                    "slots": {"title": "title", "body": "body-19"},
                },
                "default": {
                    "layout": "slide3",
                    "slots": {"title": "body-26", "body": "body-19"},
                },
            },
        },
    )
    cif_path = _write_cif(deck_dir, {
        "meta": {"title": "Test Deck", "author": "Flo"},
        "slides": [
            {"id": "slide-01", "layout": "cover",
             "title": "Hello", "content": "Cover body",
             "notes": "Welcome"},
            {"id": "slide-02", "layout": "default",
             "title": "Topic", "content": "- a\n- b",
             "notes": "Talk about a and b"},
        ],
    })
    out = deck_dir / "slides.md"
    result = render_cif(cif_path, out)

    text = out.read_text(encoding="utf-8")
    assert result.mode == "A"
    assert result.status == "written"
    # First slide: Flavour A title slot + body-19 body slot.
    assert "::title::\nHello" in text
    assert "::body-19::\nCover body" in text
    # Second slide: default alias maps title to body-26.
    assert "::body-26::\nTopic" in text
    assert "::body-19::\n- a\n- b" in text
    # Layout names in per-slide frontmatter.
    assert "layout: slide1" in text
    assert "layout: slide3" in text


# ---------------------------------------------------------------------------
# 2. Flavour B — no semantic-layouts.json
# ---------------------------------------------------------------------------


def test_flavour_b_emits_default_slot_content(tmp_path):
    deck_dir, _ = _build_deck(
        tmp_path,
        layout_files=["cover", "default"],
    )
    cif_path = _write_cif(deck_dir, {
        "meta": {"title": "T", "author": "F", "theme": "slidev-theme-test"},
        "slides": [
            {"id": "slide-01", "layout": "cover",
             "title": "Welcome", "content": "Subtitle here",
             "notes": "n1"},
            {"id": "slide-02", "layout": "default",
             "title": "Body", "content": "- one\n- two",
             "notes": "n2"},
        ],
    })
    out = deck_dir / "slides.md"
    result = render_cif(cif_path, out)
    text = out.read_text(encoding="utf-8")

    assert result.mode == "B"
    # No slot blocks anywhere.
    assert "::" not in text or all(not line.startswith("::") for line in text.splitlines())
    # Title rendered as H1, content follows.
    assert "# Welcome" in text
    assert "Subtitle here" in text
    assert "# Body" in text
    assert "- one\n- two" in text


# ---------------------------------------------------------------------------
# 3. Mixed — some semantic-layouts entries, fall-through to literal layout
# ---------------------------------------------------------------------------


def test_mixed_falls_through_to_literal_layout_file(tmp_path):
    deck_dir, _ = _build_deck(
        tmp_path,
        semantic_layouts={
            "aliases": {
                "cover": {
                    "layout": "slide1",
                    "slots": {"title": "title", "body": "body-19"},
                },
            },
        },
        layout_files=["quote"],
    )
    cif_path = _write_cif(deck_dir, {
        "meta": {"title": "Mix"},
        "slides": [
            {"id": "slide-01", "layout": "cover",
             "title": "C", "content": "x", "notes": "n"},
            {"id": "slide-02", "layout": "quote",
             "title": "Q", "content": "Quoted line", "notes": "n"},
        ],
    })
    out = deck_dir / "slides.md"
    result = render_cif(cif_path, out)
    text = out.read_text(encoding="utf-8")

    assert result.mode == "mixed"
    assert "layout: slide1" in text
    assert "layout: quote" in text
    # Slide 2 uses Flavour B (no slot blocks).
    assert "# Q" in text


# ---------------------------------------------------------------------------
# 4. Slidev built-in fallback
# ---------------------------------------------------------------------------


def test_slidev_builtin_fallback(tmp_path):
    deck_dir, _ = _build_deck(tmp_path, semantic_layouts={"aliases": {}})
    cif_path = _write_cif(deck_dir, {
        "meta": {"title": "T"},
        "slides": [
            {"id": "slide-01", "layout": "section",
             "title": "Part 2", "content": "", "notes": "n"},
        ],
    })
    out = deck_dir / "slides.md"
    result = render_cif(cif_path, out)
    text = out.read_text(encoding="utf-8")

    assert result.mode == "B"
    assert "layout: section" in text


# ---------------------------------------------------------------------------
# 5. Unknown layout — explicit error with slide ID + theme name
# ---------------------------------------------------------------------------


def test_missing_layout_raises_with_context(tmp_path):
    deck_dir, _ = _build_deck(
        tmp_path,
        theme_name="slidev-theme-test",
        semantic_layouts={"aliases": {}},
    )
    cif_path = _write_cif(deck_dir, {
        "meta": {"title": "T"},
        "slides": [
            {"id": "slide-07", "layout": "imaginary",
             "title": "X", "content": "y", "notes": "n"},
        ],
    })
    out = deck_dir / "slides.md"

    with pytest.raises(ValueError) as exc_info:
        render_cif(cif_path, out)
    msg = str(exc_info.value)
    assert "slide-07" in msg
    assert "imaginary" in msg
    assert "slidev-theme-test" in msg
    # The output must not have been written.
    assert not out.exists()


def test_missing_layout_cli_returns_1(tmp_path, capsys):
    deck_dir, _ = _build_deck(
        tmp_path, theme_name="slidev-theme-test",
        semantic_layouts={"aliases": {}},
    )
    cif_path = _write_cif(deck_dir, {
        "meta": {"title": "T"},
        "slides": [{"id": "slide-07", "layout": "imaginary",
                    "title": "X", "content": "y", "notes": "n"}],
    })
    out = deck_dir / "slides.md"
    rc = main(["--input", str(cif_path), "--output", str(out)])
    assert rc == 1
    captured = capsys.readouterr()
    assert "error:" in captured.err
    assert "slide-07" in captured.err


# ---------------------------------------------------------------------------
# 6. Speaker notes wrapped in HTML comment
# ---------------------------------------------------------------------------


def test_speaker_notes_wrapped_in_html_comment(tmp_path):
    deck_dir, _ = _build_deck(tmp_path, layout_files=["default"])
    cif_path = _write_cif(deck_dir, {
        "meta": {"title": "T"},
        "slides": [
            {"id": "slide-01", "layout": "default",
             "title": "Title", "content": "Body",
             "notes": "Say this out loud."},
        ],
    })
    out = deck_dir / "slides.md"
    render_cif(cif_path, out)
    text = out.read_text(encoding="utf-8")
    assert "<!--\nSay this out loud.\n-->" in text


# ---------------------------------------------------------------------------
# 7. Slide separators
# ---------------------------------------------------------------------------


def test_slides_separated_by_blank_dashes(tmp_path):
    deck_dir, _ = _build_deck(tmp_path, layout_files=["default"])
    cif_path = _write_cif(deck_dir, {
        "meta": {"title": "T"},
        "slides": [
            {"id": "a", "layout": "default", "title": "A", "content": "",
             "notes": "n"},
            {"id": "b", "layout": "default", "title": "B", "content": "",
             "notes": "n"},
            {"id": "c", "layout": "default", "title": "C", "content": "",
             "notes": "n"},
        ],
    })
    out = deck_dir / "slides.md"
    render_cif(cif_path, out)
    text = out.read_text(encoding="utf-8")
    # Slides are joined with a single blank line. Each slide's own
    # frontmatter '---' fence doubles as the inter-slide separator AND the
    # opening of its YAML block; emitting an explicit '---' separator on
    # top creates a phantom empty slide between every real one (Slidev
    # parses three '---' in a row as end / empty / start).
    #
    # 3 slides => 3 frontmatter blocks => 6 fence lines total. Count lines
    # that are exactly '---' to be robust to surrounding whitespace.
    fence_lines = sum(1 for line in text.splitlines() if line == "---")
    assert fence_lines == 6
    # And no occurrence of the bad doubled-separator pattern.
    assert "\n\n---\n\n---\n" not in text


# ---------------------------------------------------------------------------
# 8. First-slide frontmatter contains deck-level fields; others don't
# ---------------------------------------------------------------------------


def test_deck_frontmatter_only_on_first_slide(tmp_path):
    deck_dir, _ = _build_deck(tmp_path, layout_files=["cover", "default"])
    cif_path = _write_cif(deck_dir, {
        "meta": {
            "title": "Deck Title", "author": "Flo", "date": "2026-01-01",
            "theme": "slidev-theme-test",
        },
        "slides": [
            {"id": "a", "layout": "cover", "title": "Cover", "content": "",
             "notes": "n"},
            {"id": "b", "layout": "default", "title": "Two", "content": "",
             "notes": "n"},
        ],
    })
    out = deck_dir / "slides.md"
    render_cif(cif_path, out)
    text = out.read_text(encoding="utf-8")
    # Slides are joined with '\n\n' and each starts with its own '---'
    # fence. Split on the blank-line-before-frontmatter boundary.
    first, rest = text.split("\n\n---\n", 1)
    rest = "---\n" + rest  # restore the fence we consumed
    assert "theme: slidev-theme-test" in first
    assert "title: Deck Title" in first
    assert "author: Flo" in first
    assert "date: 2026-01-01" in first
    # Second slide must not carry deck-level fields.
    assert "theme:" not in rest
    assert "author:" not in rest


# ---------------------------------------------------------------------------
# 9. Idempotency: re-render → unchanged + mtime preserved
# ---------------------------------------------------------------------------


def test_rerun_reports_unchanged_and_preserves_mtime(tmp_path):
    deck_dir, _ = _build_deck(tmp_path, layout_files=["default"])
    cif_path = _write_cif(deck_dir, {
        "meta": {"title": "T"},
        "slides": [{"id": "a", "layout": "default", "title": "A",
                    "content": "", "notes": "n"}],
    })
    out = deck_dir / "slides.md"
    r1 = render_cif(cif_path, out)
    assert r1.status == "written"
    mtime1 = out.stat().st_mtime_ns

    # Sleep briefly so a buggy implementation that rewrites would yield a
    # different mtime than the original.
    time.sleep(0.05)

    r2 = render_cif(cif_path, out)
    assert r2.status == "unchanged"
    assert out.stat().st_mtime_ns == mtime1


# ---------------------------------------------------------------------------
# 10. Per-slide meta passthrough
# ---------------------------------------------------------------------------


def test_per_slide_meta_appears_in_frontmatter(tmp_path):
    deck_dir, _ = _build_deck(tmp_path, layout_files=["default"])
    cif_path = _write_cif(deck_dir, {
        "meta": {"title": "T"},
        "slides": [
            {"id": "a", "layout": "default", "title": "A", "content": "",
             "notes": "n", "meta": {"transition": "fade"}},
        ],
    })
    out = deck_dir / "slides.md"
    render_cif(cif_path, out)
    text = out.read_text(encoding="utf-8")
    assert "transition: fade" in text


# ---------------------------------------------------------------------------
# 11. Multi-column slots (col1, col2 → physical names)
# ---------------------------------------------------------------------------


def test_multicolumn_slots_emitted(tmp_path):
    deck_dir, _ = _build_deck(
        tmp_path,
        semantic_layouts={
            "aliases": {
                "two-cols": {
                    "layout": "slide10",
                    "slots": {
                        "title": "title",
                        "col1": "body-left",
                        "col2": "body-right",
                    },
                },
            },
        },
    )
    cif_path = _write_cif(deck_dir, {
        "meta": {"title": "T"},
        "slides": [
            {"id": "a", "layout": "two-cols",
             "title": "Compare",
             "slots": {"col1": "Left side", "col2": "Right side"},
             "notes": "n"},
        ],
    })
    out = deck_dir / "slides.md"
    render_cif(cif_path, out)
    text = out.read_text(encoding="utf-8")
    assert "::title::\nCompare" in text
    assert "::body-left::\nLeft side" in text
    assert "::body-right::\nRight side" in text


# ---------------------------------------------------------------------------
# 12. Passthrough warning for unmapped slot
# ---------------------------------------------------------------------------


def test_unmapped_slot_passes_through_with_warning(tmp_path):
    deck_dir, _ = _build_deck(
        tmp_path,
        semantic_layouts={
            "aliases": {
                "default": {
                    "layout": "slide3",
                    "slots": {"title": "title", "body": "body-19"},
                },
            },
        },
    )
    cif_path = _write_cif(deck_dir, {
        "meta": {"title": "T"},
        "slides": [
            {"id": "a", "layout": "default",
             "title": "A", "content": "main body",
             "slots": {"sidebar": "Side text"},
             "notes": "n"},
        ],
    })
    out = deck_dir / "slides.md"
    messages: list[str] = []
    render_cif(cif_path, out, verbose=True, log=messages.append)

    text = out.read_text(encoding="utf-8")
    # Passthrough emits the CIF name as the physical slot.
    assert "::sidebar::\nSide text" in text
    # Verbose mode logs the unmapped-slot warning.
    assert any("sidebar" in m and "no mapping" in m for m in messages)


# ---------------------------------------------------------------------------
# 13. Edge cases — empty content, special chars
# ---------------------------------------------------------------------------


def test_empty_fields_do_not_emit_empty_slot_blocks(tmp_path):
    deck_dir, _ = _build_deck(
        tmp_path,
        semantic_layouts={
            "aliases": {
                "cover": {
                    "layout": "slide1",
                    "slots": {
                        "title": "title", "body": "body-19",
                        "subtitle": "body-21",
                    },
                },
            },
        },
    )
    cif_path = _write_cif(deck_dir, {
        "meta": {"title": "T"},
        "slides": [
            {"id": "a", "layout": "cover",
             "title": "Hi", "content": "",
             "slots": {"subtitle": "   "},  # whitespace-only also drops
             "notes": "n"},
        ],
    })
    out = deck_dir / "slides.md"
    render_cif(cif_path, out)
    text = out.read_text(encoding="utf-8")
    assert "::title::\nHi" in text
    assert "::body-19::" not in text
    assert "::body-21::" not in text


def test_special_characters_in_content_survive(tmp_path):
    deck_dir, _ = _build_deck(
        tmp_path,
        semantic_layouts={
            "aliases": {
                "default": {
                    "layout": "slide3",
                    "slots": {"title": "title", "body": "body-19"},
                },
            },
        },
    )
    weird = "Inline `code`, ::not-a-slot:: and a horizontal rule below:\n\n---inline---"
    cif_path = _write_cif(deck_dir, {
        "meta": {"title": "T"},
        "slides": [
            {"id": "a", "layout": "default",
             "title": "Edge", "content": weird, "notes": "n"},
        ],
    })
    out = deck_dir / "slides.md"
    render_cif(cif_path, out)
    text = out.read_text(encoding="utf-8")
    assert weird.rstrip() in text


# ---------------------------------------------------------------------------
# 14. No .slidecraft.json — fall back to CIF's meta.themePath
# ---------------------------------------------------------------------------


def test_falls_back_to_cif_meta_themepath(tmp_path):
    deck_dir, _ = _build_deck(
        tmp_path,
        write_slidecraft_json=False,
        layout_files=["default"],
    )
    cif_path = _write_cif(deck_dir, {
        "meta": {
            "title": "T",
            "theme": "slidev-theme-test",
            "themePath": "../theme",
        },
        "slides": [
            {"id": "a", "layout": "default", "title": "A",
             "content": "", "notes": "n"},
        ],
    })
    out = deck_dir / "slides.md"
    result = render_cif(cif_path, out)
    text = out.read_text(encoding="utf-8")
    assert result.theme == "slidev-theme-test"
    assert "theme: slidev-theme-test" in text


# ---------------------------------------------------------------------------
# 15. No meta.theme — theme frontmatter line omitted
# ---------------------------------------------------------------------------


def test_no_theme_in_meta_omits_theme_frontmatter(tmp_path):
    deck_dir, _ = _build_deck(
        tmp_path, write_slidecraft_json=False, layout_files=["default"])
    cif_path = _write_cif(deck_dir, {
        "meta": {"title": "Untemped Deck", "themePath": "../theme"},
        "slides": [
            {"id": "a", "layout": "default", "title": "Hi",
             "content": "body", "notes": "n"},
        ],
    })
    out = deck_dir / "slides.md"
    result = render_cif(cif_path, out)
    text = out.read_text(encoding="utf-8")
    assert result.theme is None
    # No theme: line at all.
    assert "theme:" not in text
    # But title still rendered.
    assert "title: Untemped Deck" in text


# ---------------------------------------------------------------------------
# CLI smoke test — happy path
# ---------------------------------------------------------------------------


def test_cli_happy_path_prints_summary(tmp_path, capsys):
    deck_dir, _ = _build_deck(tmp_path, layout_files=["default"])
    cif_path = _write_cif(deck_dir, {
        "meta": {"title": "T", "theme": "slidev-theme-test"},
        "slides": [
            {"id": "a", "layout": "default", "title": "A",
             "content": "", "notes": "n"},
        ],
    })
    out = deck_dir / "slides.md"
    rc = main(["--input", str(cif_path), "--output", str(out)])
    assert rc == 0
    captured = capsys.readouterr()
    assert "rendered 1 slides" in captured.out
    assert "status=written" in captured.out

    # Second run reports unchanged.
    rc2 = main(["--input", str(cif_path), "--output", str(out)])
    assert rc2 == 0
    captured2 = capsys.readouterr()
    assert "status=unchanged" in captured2.out


# ---------------------------------------------------------------------------
# Alias defaults — theme-declared fallback content for empty CIF slots
# ---------------------------------------------------------------------------


def test_alias_defaults_fill_empty_slots(tmp_path):
    """If the CIF leaves a slot empty AND the alias declares a default,
    the renderer emits the default into that slot. Used for closing-slide
    'Thank you' style fixed content."""
    aliases = {
        "aliases": {
            "end": {
                "layout": "closing",
                "slots": {"title": "title", "body": "contact"},
                "defaults": {
                    "title": "Thank you",
                    "body": "Questions welcome",
                },
            },
        },
    }
    deck_dir, _ = _build_deck(tmp_path, semantic_layouts=aliases,
                              layout_files=["closing"])
    cif_path = _write_cif(deck_dir, {
        "meta": {"theme": "slidev-theme-test"},
        "slides": [
            # CIF provides nothing for title/body — alias defaults should fill.
            {"id": "s1", "layout": "end", "notes": "n"},
        ],
    })
    out = deck_dir / "slides.md"
    render_cif(cif_path, out)
    text = out.read_text(encoding="utf-8")
    assert "::title::\nThank you" in text
    assert "::contact::\nQuestions welcome" in text


def test_cif_overrides_alias_default(tmp_path):
    """When the CIF provides slot content AND the alias has a default, the
    CIF wins."""
    aliases = {
        "aliases": {
            "end": {
                "layout": "closing",
                "slots": {"title": "title"},
                "defaults": {"title": "Thank you"},
            },
        },
    }
    deck_dir, _ = _build_deck(tmp_path, semantic_layouts=aliases,
                              layout_files=["closing"])
    cif_path = _write_cif(deck_dir, {
        "meta": {"theme": "slidev-theme-test"},
        "slides": [
            {"id": "s1", "layout": "end", "title": "Questions?",
             "notes": "n"},
        ],
    })
    out = deck_dir / "slides.md"
    render_cif(cif_path, out)
    text = out.read_text(encoding="utf-8")
    assert "::title::\nQuestions?" in text
    assert "Thank you" not in text


# ---------------------------------------------------------------------------
# Blank-line-in-slot safety — wrap to keep MDC from closing block early
# ---------------------------------------------------------------------------


def test_slot_with_blank_line_is_wrapped(tmp_path):
    """Slidev's MDC closes ``::slot-name::`` blocks at the first blank
    line. Multi-paragraph slot content was the root cause of the
    'error on slide 3' bug — slide 11 had two paragraphs in its
    picture-14 slot, the blank line broke the slot block, and the second
    paragraph leaked into the slide root. The renderer detects this and
    wraps the content in <div>...</div> so MDC sees one unambiguous block.
    """
    aliases = {
        "aliases": {
            "content-image": {
                "layout": "ci",
                "slots": {"title": "title", "image": "picture-14"},
            },
        },
    }
    deck_dir, _ = _build_deck(tmp_path, semantic_layouts=aliases,
                              layout_files=["ci"])
    multi = "*[TODO]*\n\nSecond paragraph with apostrophe C'."
    cif_path = _write_cif(deck_dir, {
        "meta": {"theme": "slidev-theme-test"},
        "slides": [
            {"id": "s1", "layout": "content-image", "title": "T",
             "slots": {"image": multi}, "notes": "n"},
        ],
    })
    out = deck_dir / "slides.md"
    render_cif(cif_path, out)
    text = out.read_text(encoding="utf-8")
    # Exactly one slot opener — the second paragraph didn't leak.
    assert text.count("::picture-14::") == 1
    # And the multi-paragraph content is now inside a <div> wrapper.
    slot_idx = text.index("::picture-14::")
    slot_section = text[slot_idx:slot_idx + 600]
    assert "<div>" in slot_section and "</div>" in slot_section
    assert "Second paragraph" in slot_section
