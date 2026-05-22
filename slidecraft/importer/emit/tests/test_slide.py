"""Tests for emit/slide.py."""
from __future__ import annotations

from pathlib import Path

import pytest

from slidecraft.importer.model import (
    NoFill,
    Paragraph,
    Placeholder,
    Presentation,
    RGB,
    Run,
    Slide,
    SolidFill,
    TextFrame,
)
from slidecraft.importer.emit.slide import emit_deck, _emit_paragraph


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ph(
    idx: int = 5,
    paragraphs=None,
    default_run: Run | None = None,
    default_para: Paragraph | None = None,
) -> Placeholder:
    tf = TextFrame(paragraphs=paragraphs or [])
    return Placeholder(
        idx=idx,
        type="body",
        x_px=0.0, y_px=0.0, width_px=100.0, height_px=100.0,
        text_frame=tf,
        default_run_props=default_run or Run(text=""),
        default_para_props=default_para or Paragraph(runs=[]),
    )


def _make_pres(slides) -> Presentation:
    return Presentation(
        slides=slides,
        canvas_width_px=1920, canvas_height_px=1080,
        typefaces_referenced=set(),
    )


def _emit_and_read(tmp_path: Path, pres: Presentation) -> str:
    emit_deck(pres, tmp_path / "deck", "../theme")
    return (tmp_path / "deck" / "slides.md").read_text()


# ---------------------------------------------------------------------------
# Paragraph-level emit helpers (unit tests on _emit_paragraph)
# ---------------------------------------------------------------------------

def _simple_ph(default_run=None, default_para=None) -> Placeholder:
    return _make_ph(default_run=default_run, default_para=default_para)


class TestSlidePlainText:
    def test_slide_plain_text(self, tmp_path):
        """Runs with no deviation → plain text."""
        para = Paragraph(runs=[Run(text="Hello world")])
        ph = _make_ph(idx=5, paragraphs=[para])
        slide = Slide(index=1, placeholders=[ph])
        pres = _make_pres([slide])
        content = _emit_and_read(tmp_path, pres)
        assert "Hello world" in content
        assert "**" not in content
        assert "<span" not in content

    def test_slide_layout_frontmatter(self, tmp_path):
        ph = _make_ph(idx=5, paragraphs=[Paragraph(runs=[Run(text="Hi")])])
        slide = Slide(index=1, placeholders=[ph])
        pres = _make_pres([slide])
        content = _emit_and_read(tmp_path, pres)
        assert "layout: slide1" in content
        assert "::ph_5::" in content

    def test_slide_global_theme_frontmatter(self, tmp_path):
        pres = _make_pres([])
        emit_deck(pres, tmp_path / "deck", "../theme", theme_name="slidev-theme-test")
        content = (tmp_path / "deck" / "slides.md").read_text()
        assert "theme: slidev-theme-test" in content

    def test_slide_package_json(self, tmp_path):
        import json
        pres = _make_pres([])
        emit_deck(pres, tmp_path / "deck", "../theme", theme_name="slidev-theme-x")
        pkg = json.loads((tmp_path / "deck" / "package.json").read_text())
        assert pkg["private"] is True
        assert "@slidev/cli" in pkg["dependencies"]
        assert "slidev-theme-x" in pkg["dependencies"]
        assert pkg["dependencies"]["slidev-theme-x"] == "file:../theme"
        assert "dev" in pkg["scripts"]


class TestSlideMarkdownBold:
    def test_slide_markdown_bold(self):
        """Bold-only deviation → **text**."""
        para = Paragraph(runs=[Run(text="strong", bold=True)])
        ph = _simple_ph()
        result = _emit_paragraph(para, ph)
        assert result == "**strong**"

    def test_slide_markdown_italic(self):
        para = Paragraph(runs=[Run(text="em", italic=True)])
        ph = _simple_ph()
        result = _emit_paragraph(para, ph)
        assert result == "*em*"

    def test_slide_markdown_bold_italic(self):
        para = Paragraph(runs=[Run(text="both", bold=True, italic=True)])
        ph = _simple_ph()
        result = _emit_paragraph(para, ph)
        assert result == "***both***"

    def test_slide_markdown_strike(self):
        para = Paragraph(runs=[Run(text="dead", strike=True)])
        ph = _simple_ph()
        result = _emit_paragraph(para, ph)
        assert result == "~~dead~~"

    def test_slide_markdown_underline(self):
        para = Paragraph(runs=[Run(text="uline", underline=True)])
        ph = _simple_ph()
        result = _emit_paragraph(para, ph)
        assert result == "<u>uline</u>"

    def test_slide_no_marker_when_matches_default(self):
        """Bold run where default is also bold → plain text."""
        para = Paragraph(runs=[Run(text="not bold relative to default", bold=True)])
        ph = _simple_ph(default_run=Run(text="", bold=True))
        result = _emit_paragraph(para, ph)
        assert result == "not bold relative to default"


class TestSlideSpanForColor:
    def test_slide_span_for_color(self):
        """Color deviation → <span style="color:…">."""
        para = Paragraph(runs=[Run(text="red text", color=RGB(255, 0, 0))])
        ph = _simple_ph()
        result = _emit_paragraph(para, ph)
        assert '<span style="color:#FF0000">red text</span>' == result

    def test_slide_span_for_font_size(self):
        para = Paragraph(runs=[Run(text="big", font_size_pt=24.0)])
        ph = _simple_ph()
        result = _emit_paragraph(para, ph)
        assert "<span style=" in result
        assert "font-size:" in result
        assert "big" in result

    def test_slide_span_for_font_family(self):
        para = Paragraph(runs=[Run(text="different font", font_family="Arial")])
        ph = _simple_ph()
        result = _emit_paragraph(para, ph)
        assert "<span" in result
        assert "Arial" in result

    def test_slide_span_bold_plus_color(self):
        """Bold + color together → span with both properties (span wins over **)."""
        para = Paragraph(runs=[Run(text="hi", bold=True, color=RGB(0, 0, 255))])
        ph = _simple_ph()
        result = _emit_paragraph(para, ph)
        assert "<span" in result
        assert "font-weight:700" in result
        assert "#0000FF" in result

    def test_slide_color_with_alpha(self):
        para = Paragraph(runs=[Run(text="faded", color=RGB(255, 0, 0, 0.5))])
        ph = _simple_ph()
        result = _emit_paragraph(para, ph)
        assert "rgba(255,0,0,0.5)" in result


class TestSlidePWrapperUsesHtmlInside:
    def test_slide_p_wrapper_uses_html_inside(self):
        """When paragraph has deviating alignment, runs inside must use HTML, not **."""
        para = Paragraph(
            runs=[Run(text="bold inside p", bold=True)],
            align="ctr",
        )
        ph = _simple_ph(default_para=Paragraph(runs=[], align="l"))
        result = _emit_paragraph(para, ph)
        # Must be wrapped in <p style="…">
        assert result.startswith("<p style=")
        assert result.endswith("</p>")
        # Inside must use <strong>, not **
        assert "<strong>" in result
        assert "**" not in result

    def test_slide_p_wrapper_color_uses_span_not_markdown(self):
        """Color inside a <p> wrapper must use <span>, not any markdown."""
        para = Paragraph(
            runs=[Run(text="colored", color=RGB(200, 100, 50))],
            align="r",
        )
        ph = _simple_ph(default_para=Paragraph(runs=[], align="l"))
        result = _emit_paragraph(para, ph)
        assert result.startswith("<p style=")
        assert "<span" in result
        assert "color:#C86432" in result

    def test_slide_p_wrapper_text_align(self):
        para = Paragraph(runs=[Run(text="centered")], align="ctr")
        ph = _simple_ph(default_para=Paragraph(runs=[], align="l"))
        result = _emit_paragraph(para, ph)
        assert "text-align:center" in result

    def test_slide_p_wrapper_line_spacing(self):
        para = Paragraph(runs=[Run(text="spacey")], line_spacing_pct=150.0)
        ph = _simple_ph()
        result = _emit_paragraph(para, ph)
        assert "line-height:1.5" in result

    def test_no_p_wrapper_when_no_para_deviations(self):
        """No paragraph deviations → no <p> wrapper even if run has markdown deviation."""
        para = Paragraph(runs=[Run(text="bold", bold=True)])
        ph = _simple_ph()
        result = _emit_paragraph(para, ph)
        assert not result.startswith("<p")
        assert "**bold**" == result


class TestSlideBulletsMarkdown:
    def test_slide_bullets_markdown(self):
        """char bullet → '- text' in markdown."""
        para = Paragraph(runs=[Run(text="item one")], bullet="char")
        ph = _simple_ph()
        result = _emit_paragraph(para, ph)
        assert result == "- item one"

    def test_slide_auto_num_bullet(self):
        para = Paragraph(runs=[Run(text="first")], bullet="auto-num")
        ph = _simple_ph()
        result = _emit_paragraph(para, ph)
        assert result == "1. first"

    def test_slide_nested_bullet(self):
        para = Paragraph(runs=[Run(text="nested")], bullet="char", level=1)
        ph = _simple_ph()
        result = _emit_paragraph(para, ph)
        assert result == "  - nested"

    def test_slide_deeply_nested_bullet(self):
        para = Paragraph(runs=[Run(text="deep")], bullet="char", level=2)
        ph = _simple_ph()
        result = _emit_paragraph(para, ph)
        assert result == "    - deep"

    def test_slide_bullets_in_full_emit(self, tmp_path):
        """End-to-end: bullets appear correctly in slides.md."""
        para1 = Paragraph(runs=[Run(text="first")], bullet="char")
        para2 = Paragraph(runs=[Run(text="second")], bullet="char")
        ph = _make_ph(idx=6, paragraphs=[para1, para2])
        slide = Slide(index=1, placeholders=[ph])
        pres = _make_pres([slide])
        content = _emit_and_read(tmp_path, pres)
        assert "- first" in content
        assert "- second" in content

    def test_slide_default_bullet_from_placeholder(self):
        """If default_para_props.bullet == 'char' and para.bullet is None → still bullet."""
        para = Paragraph(runs=[Run(text="inherited bullet")])
        ph = _simple_ph(default_para=Paragraph(runs=[], bullet="char"))
        result = _emit_paragraph(para, ph)
        assert result == "- inherited bullet"


class TestSlideSoftLineBreak:
    def test_soft_line_break(self):
        """\\n run text → <br/>."""
        para = Paragraph(runs=[Run(text="line one"), Run(text="\n"), Run(text="line two")])
        ph = _simple_ph()
        result = _emit_paragraph(para, ph)
        assert "<br/>" in result
        assert "line one" in result
        assert "line two" in result


class TestSlideMultipleParagraphs:
    def test_multiple_paragraphs_blank_line_separated(self, tmp_path):
        para1 = Paragraph(runs=[Run(text="first paragraph")])
        para2 = Paragraph(runs=[Run(text="second paragraph")])
        ph = _make_ph(idx=5, paragraphs=[para1, para2])
        slide = Slide(index=1, placeholders=[ph])
        pres = _make_pres([slide])
        content = _emit_and_read(tmp_path, pres)
        # There should be a blank line between them
        assert "first paragraph\n\nsecond paragraph" in content
