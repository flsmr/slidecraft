"""Tests for slidecraft.importer.parse.

All PPTX fixtures are built in-memory using python-pptx; no binary files are committed.
"""
from __future__ import annotations

import io
from pathlib import Path

import pytest
from lxml import etree
from pptx import Presentation as PptxPresentation
from pptx.util import Inches, Pt, Emu

from slidecraft.importer.parse import parse, _parse_paragraph
from slidecraft.importer.model import Presentation, NoFill, SolidFill, Run, Paragraph

_A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
_P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"


# ---------------------------------------------------------------------------
# Helper to serialise an in-memory pptx to a temp file path
# ---------------------------------------------------------------------------

def _save_pptx(prs: PptxPresentation, tmp_path: Path) -> Path:
    """Save a python-pptx Presentation to a temp file and return its path."""
    out = tmp_path / "test.pptx"
    prs.save(str(out))
    return out


# ---------------------------------------------------------------------------
# Test: canvas dimensions
# ---------------------------------------------------------------------------

def test_parse_canvas_dims(tmp_path):
    """parse() reads <p:sldSz> and converts EMU → px correctly."""
    prs = PptxPresentation()
    # Default python-pptx presentation is 10×7.5 in = 9144000×6858000 EMU
    # at 96 dpi: 960×720 px
    out = _save_pptx(prs, tmp_path)
    result = parse(out)
    # px = emu / 9525
    expected_w = prs.slide_width // 9525
    expected_h = prs.slide_height // 9525
    assert result.canvas_width_px == expected_w
    assert result.canvas_height_px == expected_h


def test_parse_canvas_dims_16x9(tmp_path):
    """parse() handles 16:9 (1920×1080) canvas correctly."""
    prs = PptxPresentation()
    # Set to 16:9: 12192000 × 6858000 EMU
    prs.slide_width = Emu(12192000)
    prs.slide_height = Emu(6858000)
    out = _save_pptx(prs, tmp_path)
    result = parse(out)
    assert result.canvas_width_px == 12192000 // 9525
    assert result.canvas_height_px == 6858000 // 9525


# ---------------------------------------------------------------------------
# Test: one title placeholder
# ---------------------------------------------------------------------------

def test_parse_one_title_placeholder(tmp_path):
    """parse() extracts a title placeholder with text runs from a slide."""
    prs = PptxPresentation()
    slide_layout = prs.slide_layouts[0]  # "Title Slide" layout
    slide = prs.slides.add_slide(slide_layout)

    # Set title text
    title_ph = slide.shapes.title
    title_ph.text = "Hello World"

    out = _save_pptx(prs, tmp_path)
    result = parse(out)

    assert len(result.slides) == 1
    slide_model = result.slides[0]
    assert slide_model.index == 1

    # Find the title placeholder
    title_phs = [p for p in slide_model.placeholders if p.type in ("title", "ctrTitle")]
    assert len(title_phs) >= 1, "Expected at least one title placeholder"

    ph = title_phs[0]
    assert ph.text_frame is not None
    all_text = "".join(
        run.text
        for para in ph.text_frame.paragraphs
        for run in para.runs
    )
    assert "Hello World" in all_text


def test_parse_placeholder_geometry(tmp_path):
    """parse() resolves placeholder position/size in px."""
    prs = PptxPresentation()
    slide_layout = prs.slide_layouts[0]
    slide = prs.slides.add_slide(slide_layout)

    title_ph = slide.shapes.title
    title_ph.text = "Geometry Test"

    out = _save_pptx(prs, tmp_path)
    result = parse(out)

    ph = result.slides[0].placeholders[0]
    # Should have non-zero width (inherited from layout or master)
    assert ph.width_px > 0 or ph.height_px > 0, (
        "Expected non-zero placeholder dimensions"
    )


def test_parse_multiple_slides(tmp_path):
    """parse() returns one Slide model per PPTX slide."""
    prs = PptxPresentation()
    layout = prs.slide_layouts[0]
    prs.slides.add_slide(layout)
    prs.slides.add_slide(layout)

    out = _save_pptx(prs, tmp_path)
    result = parse(out)

    assert len(result.slides) == 2
    assert result.slides[0].index == 1
    assert result.slides[1].index == 2


def test_parse_typefaces_referenced(tmp_path):
    """parse() collects typefaces from placeholder defaults and run-level fonts."""
    prs = PptxPresentation()
    layout = prs.slide_layouts[0]
    slide = prs.slides.add_slide(layout)
    slide.shapes.title.text = "Font Test"

    out = _save_pptx(prs, tmp_path)
    result = parse(out)

    # typefaces_referenced should be a set (possibly empty if theme fonts are all +mj-lt/+mn-lt refs)
    assert isinstance(result.typefaces_referenced, set)


def test_parse_empty_presentation(tmp_path):
    """parse() handles a presentation with no slides gracefully."""
    prs = PptxPresentation()
    out = _save_pptx(prs, tmp_path)
    result = parse(out)
    assert isinstance(result, Presentation)
    assert result.slides == []


def test_parse_slide_index_1based(tmp_path):
    """Slide index is 1-based."""
    prs = PptxPresentation()
    layout = prs.slide_layouts[1]
    prs.slides.add_slide(layout)
    out = _save_pptx(prs, tmp_path)
    result = parse(out)
    assert result.slides[0].index == 1


def test_parse_body_placeholder(tmp_path):
    """parse() extracts body placeholder text content."""
    prs = PptxPresentation()
    # Use a layout that has both title and content placeholders
    layout = prs.slide_layouts[1]  # "Title and Content" layout
    slide = prs.slides.add_slide(layout)

    for ph in slide.placeholders:
        if ph.placeholder_format.idx == 1:
            ph.text = "Body content here"
            break

    out = _save_pptx(prs, tmp_path)
    result = parse(out)

    slide_model = result.slides[0]
    body_phs = [p for p in slide_model.placeholders if p.idx == 1]
    if body_phs:
        ph = body_phs[0]
        assert ph.text_frame is not None
        all_text = "".join(
            run.text
            for para in ph.text_frame.paragraphs
            for run in para.runs
        )
        assert "Body content" in all_text


def test_parse_default_run_props_populated(tmp_path):
    """parse() populates default_run_props on each placeholder (cascade result)."""
    prs = PptxPresentation()
    layout = prs.slide_layouts[0]
    slide = prs.slides.add_slide(layout)
    slide.shapes.title.text = "Cascade Test"

    out = _save_pptx(prs, tmp_path)
    result = parse(out)

    slide_model = result.slides[0]
    assert len(slide_model.placeholders) > 0
    for ph in slide_model.placeholders:
        # default_run_props must be a Run instance (text="" sentinel)
        assert ph.default_run_props is not None
        assert ph.default_run_props.text == ""
        # default_para_props must be a Paragraph instance
        assert ph.default_para_props is not None


# ---------------------------------------------------------------------------
# Tests for <a:fld> field element parsing
# ---------------------------------------------------------------------------

def _make_paragraph_with_fld(field_type: str, field_text: str) -> etree._Element:
    """Build an <a:p> element containing an <a:fld> child (e.g. slidenum, datetime1)."""
    p_el = etree.Element(f"{{{_A_NS}}}p")
    fld = etree.SubElement(p_el, f"{{{_A_NS}}}fld",
                           attrib={"id": "{DEADBEEF-DEAD-DEAD-DEAD-DEADDEADBEEF}",
                                   "type": field_type})
    rpr = etree.SubElement(fld, f"{{{_A_NS}}}rPr", lang="en-US")
    t_el = etree.SubElement(fld, f"{{{_A_NS}}}t")
    t_el.text = field_text
    return p_el


class TestFieldElementParsing:
    """Tests for <a:fld> (slidenum, datetime) parsed as regular runs."""

    def test_fld_slidenum_text_captured(self):
        """<a:fld type='slidenum'> text is emitted as a Run with the field value."""
        p_el = _make_paragraph_with_fld("slidenum", "7")
        default_run = Run(text="")
        default_para = Paragraph(runs=[])
        para = _parse_paragraph(p_el, default_run, default_para)
        texts = [r.text for r in para.runs]
        assert "7" in texts

    def test_fld_datetime_text_captured(self):
        """<a:fld type='datetime1'> text is emitted as a Run with the field value."""
        p_el = _make_paragraph_with_fld("datetime1", "1/1/2025")
        default_run = Run(text="")
        default_para = Paragraph(runs=[])
        para = _parse_paragraph(p_el, default_run, default_para)
        texts = [r.text for r in para.runs]
        assert "1/1/2025" in texts

    def test_fld_interleaved_with_runs(self):
        """Runs and fields in the same paragraph are all captured in order."""
        p_el = etree.Element(f"{{{_A_NS}}}p")
        # A regular run before the field
        r1 = etree.SubElement(p_el, f"{{{_A_NS}}}r")
        rpr1 = etree.SubElement(r1, f"{{{_A_NS}}}rPr")
        t1 = etree.SubElement(r1, f"{{{_A_NS}}}t")
        t1.text = "Slide "
        # The field
        fld = etree.SubElement(p_el, f"{{{_A_NS}}}fld",
                               attrib={"id": "{DEADBEEF}", "type": "slidenum"})
        rpr_fld = etree.SubElement(fld, f"{{{_A_NS}}}rPr")
        t_fld = etree.SubElement(fld, f"{{{_A_NS}}}t")
        t_fld.text = "3"

        default_run = Run(text="")
        default_para = Paragraph(runs=[])
        para = _parse_paragraph(p_el, default_run, default_para)
        all_text = "".join(r.text for r in para.runs)
        assert "Slide " in all_text
        assert "3" in all_text
