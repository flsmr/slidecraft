"""Tests for slidecraft.importer.inheritance.

All PPTX fixtures are built in-memory; no binary files are committed.
Tests focus on the cascade semantics of resolve_placeholder().
"""
from __future__ import annotations

import io
from pathlib import Path

import pytest
from lxml import etree
from pptx import Presentation as PptxPresentation
from pptx.util import Pt

from slidecraft.importer.inheritance import (
    _extract_rpr,
    _extract_ppr,
    _merge_run,
    _merge_para,
    _txstyles_defaults,
    _theme_run_defaults,
    resolve_placeholder,
    diff_run,
    diff_para,
    _x,
)
from slidecraft.importer.model import Run, Paragraph


# ---------------------------------------------------------------------------
# Helpers to build minimal XML elements
# ---------------------------------------------------------------------------

_A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
_P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"


def _make_rpr(**attrs) -> etree._Element:
    """Build a minimal <a:rPr> element with given attributes."""
    el = etree.Element(f"{{{_A_NS}}}rPr", attrib={k: str(v) for k, v in attrs.items()})
    return el


def _make_rpr_with_font(typeface: str, **attrs) -> etree._Element:
    rpr = _make_rpr(**attrs)
    latin = etree.SubElement(rpr, f"{{{_A_NS}}}latin", typeface=typeface)
    return rpr


def _make_rpr_with_color(r: int, g: int, b: int, **attrs) -> etree._Element:
    rpr = _make_rpr(**attrs)
    solid = etree.SubElement(rpr, f"{{{_A_NS}}}solidFill")
    srgb = etree.SubElement(solid, f"{{{_A_NS}}}srgbClr", val=f"{r:02X}{g:02X}{b:02X}")
    return rpr


def _make_ppr(**attrs) -> etree._Element:
    el = etree.Element(f"{{{_A_NS}}}pPr", attrib={k: str(v) for k, v in attrs.items()})
    return el


def _make_sp_with_txbody(rpr_el=None, ppr_el=None, lvl: int = 1) -> etree._Element:
    """Build a minimal <p:sp> with a txBody containing lstStyle/lvlNpPr."""
    sp = etree.Element(f"{{{_P_NS}}}sp")
    tx_body = etree.SubElement(sp, f"{{{_P_NS}}}txBody")
    lst_style = etree.SubElement(tx_body, f"{{{_A_NS}}}lstStyle")

    lvl_el = etree.SubElement(lst_style, f"{{{_A_NS}}}lvl{lvl}pPr")
    if ppr_el is not None:
        # Copy attributes from ppr_el into lvl_el
        for k, v in ppr_el.attrib.items():
            lvl_el.set(k, v)
        for child in ppr_el:
            lvl_el.append(child)
    if rpr_el is not None:
        def_rpr = etree.SubElement(lvl_el, f"{{{_A_NS}}}defRPr")
        for k, v in rpr_el.attrib.items():
            def_rpr.set(k, v)
        for child in rpr_el:
            import copy
            def_rpr.append(copy.deepcopy(child))

    # Add a paragraph so _apply_sp_defaults can also read it
    p_el = etree.SubElement(tx_body, f"{{{_A_NS}}}p")
    return sp


def _make_sp_with_paragraph(rpr_attrs: dict = None, ppr_attrs: dict = None) -> etree._Element:
    """Build <p:sp> with a txBody containing a real paragraph."""
    sp = etree.Element(f"{{{_P_NS}}}sp")
    tx_body = etree.SubElement(sp, f"{{{_P_NS}}}txBody")
    etree.SubElement(tx_body, f"{{{_A_NS}}}lstStyle")
    p_el = etree.SubElement(tx_body, f"{{{_A_NS}}}p")
    if ppr_attrs:
        ppr = etree.SubElement(p_el, f"{{{_A_NS}}}pPr", attrib={k: str(v) for k, v in ppr_attrs.items()})
    r_el = etree.SubElement(p_el, f"{{{_A_NS}}}r")
    if rpr_attrs:
        rpr = etree.SubElement(r_el, f"{{{_A_NS}}}rPr", attrib={k: str(v) for k, v in rpr_attrs.items()})
    t_el = etree.SubElement(r_el, f"{{{_A_NS}}}t")
    t_el.text = "test"
    return sp


# ---------------------------------------------------------------------------
# Unit tests for low-level helpers
# ---------------------------------------------------------------------------

class TestExtractRpr:
    def test_bold(self):
        rpr = _make_rpr(b="1")
        run = _extract_rpr(rpr)
        assert run.bold is True

    def test_not_bold(self):
        rpr = _make_rpr(b="0")
        run = _extract_rpr(rpr)
        assert run.bold is False

    def test_italic(self):
        rpr = _make_rpr(i="1")
        run = _extract_rpr(rpr)
        assert run.italic is True

    def test_underline(self):
        rpr = _make_rpr(u="sng")
        run = _extract_rpr(rpr)
        assert run.underline is True

    def test_underline_none_value(self):
        rpr = _make_rpr(u="none")
        run = _extract_rpr(rpr)
        assert run.underline is False

    def test_font_size(self):
        rpr = _make_rpr(sz="2400")  # 24pt
        run = _extract_rpr(rpr)
        assert run.font_size_pt == pytest.approx(24.0)

    def test_font_family(self):
        rpr = _make_rpr_with_font("Calibri")
        run = _extract_rpr(rpr)
        assert run.font_family == "Calibri"

    def test_theme_font_ref_skipped(self):
        rpr = _make_rpr_with_font("+mj-lt")
        run = _extract_rpr(rpr)
        assert run.font_family is None

    def test_color(self):
        rpr = _make_rpr_with_color(255, 0, 0)
        run = _extract_rpr(rpr)
        assert run.color is not None
        assert run.color.r == 255
        assert run.color.g == 0
        assert run.color.b == 0

    def test_none_element_returns_empty_run(self):
        run = _extract_rpr(None)
        assert run.bold is None
        assert run.font_family is None


class TestExtractPpr:
    def test_alignment(self):
        ppr = _make_ppr(algn="ctr")
        para = _extract_ppr(ppr)
        assert para.align == "ctr"

    def test_margin_left(self):
        ppr = _make_ppr(marL="457200")  # 36 pt
        para = _extract_ppr(ppr)
        assert para.margin_left_pt == pytest.approx(36.0, rel=1e-3)

    def test_none_element_returns_empty_para(self):
        para = _extract_ppr(None)
        assert para.align is None


class TestMerge:
    def test_merge_run_override_wins(self):
        base = Run(text="", bold=False, font_family="Arial")
        override = Run(text="", bold=True)
        merged = _merge_run(base, override)
        assert merged.bold is True
        assert merged.font_family == "Arial"  # kept from base

    def test_merge_run_none_override_keeps_base(self):
        base = Run(text="", font_size_pt=18.0)
        override = Run(text="")  # all None
        merged = _merge_run(base, override)
        assert merged.font_size_pt == pytest.approx(18.0)

    def test_merge_para_override_wins(self):
        base = Paragraph(runs=[], align="l")
        override = Paragraph(runs=[], align="ctr")
        merged = _merge_para(base, override)
        assert merged.align == "ctr"

    def test_merge_para_none_keeps_base(self):
        base = Paragraph(runs=[], line_spacing_pct=120.0)
        override = Paragraph(runs=[])
        merged = _merge_para(base, override)
        assert merged.line_spacing_pct == pytest.approx(120.0)


class TestDiff:
    def test_diff_run_same_returns_none_fields(self):
        default = Run(text="", bold=True, font_family="Calibri")
        run = Run(text="hello", bold=True, font_family="Calibri")
        diffed = diff_run(run, default)
        assert diffed.bold is None
        assert diffed.font_family is None
        assert diffed.text == "hello"

    def test_diff_run_different_kept(self):
        default = Run(text="", bold=False)
        run = Run(text="x", bold=True)
        diffed = diff_run(run, default)
        assert diffed.bold is True

    def test_diff_para_same_returns_none(self):
        default = Paragraph(runs=[], align="l")
        para = Paragraph(runs=[], align="l")
        diffed = diff_para(para, default)
        assert diffed.align is None

    def test_diff_para_different_kept(self):
        default = Paragraph(runs=[], align="l")
        para = Paragraph(runs=[], align="ctr")
        diffed = diff_para(para, default)
        assert diffed.align == "ctr"


# ---------------------------------------------------------------------------
# Integration-level cascade tests using resolve_placeholder
# ---------------------------------------------------------------------------

class TestInheritanceSlideOverridesLayout:
    """test_inheritance_slide_overrides_layout: slide-level sp wins over layout sp."""

    def test_slide_overrides_layout(self):
        """When slide sp has explicit font size, it overrides the layout's font size."""
        # Layout sp has font size 24pt at lvl1
        layout_sp = _make_sp_with_txbody(
            rpr_el=_make_rpr(sz="2400"),  # 24pt
            lvl=1,
        )
        # Slide sp has font size 32pt
        slide_sp = _make_sp_with_txbody(
            rpr_el=_make_rpr(sz="3200"),  # 32pt
            lvl=1,
        )

        run, para = resolve_placeholder(
            slide_sp=slide_sp,
            layout_ph=layout_sp,
            master_ph=None,
            master_tx_styles=None,
            theme_el=None,
            ph_type="title",
        )
        # Slide wins: 32pt
        assert run.font_size_pt == pytest.approx(32.0)

    def test_slide_paragraph_alignment_overrides_layout(self):
        """Slide-level paragraph alignment overrides layout alignment."""
        layout_sp = _make_sp_with_txbody(
            ppr_el=_make_ppr(algn="ctr"),
            lvl=1,
        )
        slide_sp = _make_sp_with_paragraph(ppr_attrs={"algn": "r"})

        run, para = resolve_placeholder(
            slide_sp=slide_sp,
            layout_ph=layout_sp,
            master_ph=None,
            master_tx_styles=None,
            theme_el=None,
            ph_type="body",
        )
        assert para.align == "r"

    def test_slide_bold_overrides_layout(self):
        """Slide-level bold=True overrides layout bold=False."""
        layout_sp = _make_sp_with_txbody(
            rpr_el=_make_rpr(b="0"),
            lvl=1,
        )
        slide_sp = _make_sp_with_paragraph(rpr_attrs={"b": "1"})

        run, para = resolve_placeholder(
            slide_sp=slide_sp,
            layout_ph=layout_sp,
            master_ph=None,
            master_tx_styles=None,
            theme_el=None,
            ph_type="title",
        )
        assert run.bold is True


class TestInheritanceLayoutInheritsMaster:
    """test_inheritance_layout_inherits_master: layout inherits from master when slide doesn't override."""

    def test_layout_inherits_master_font(self):
        """When slide has no font spec, layout inherits master's font family."""
        master_sp = _make_sp_with_txbody(
            rpr_el=_make_rpr_with_font("Times New Roman"),
            lvl=1,
        )
        # Layout sp has no font info
        layout_sp = _make_sp_with_txbody(lvl=1)
        # Slide sp has no font info
        slide_sp = _make_sp_with_paragraph()

        run, para = resolve_placeholder(
            slide_sp=slide_sp,
            layout_ph=layout_sp,
            master_ph=master_sp,
            master_tx_styles=None,
            theme_el=None,
            ph_type="title",
        )
        assert run.font_family == "Times New Roman"

    def test_layout_overrides_master_font(self):
        """Layout's font overrides master's font; slide has no font spec."""
        master_sp = _make_sp_with_txbody(
            rpr_el=_make_rpr_with_font("Arial"),
            lvl=1,
        )
        layout_sp = _make_sp_with_txbody(
            rpr_el=_make_rpr_with_font("Calibri"),
            lvl=1,
        )
        slide_sp = _make_sp_with_paragraph()

        run, para = resolve_placeholder(
            slide_sp=slide_sp,
            layout_ph=layout_sp,
            master_ph=master_sp,
            master_tx_styles=None,
            theme_el=None,
            ph_type="body",
        )
        assert run.font_family == "Calibri"

    def test_all_none_when_no_sources(self):
        """With no cascade sources, defaults are None/empty."""
        run, para = resolve_placeholder(
            slide_sp=None,
            layout_ph=None,
            master_ph=None,
            master_tx_styles=None,
            theme_el=None,
            ph_type="title",
        )
        assert run.bold is None
        assert run.font_family is None
        assert para.align is None


class TestTxStylesDefaults:
    """Tests for master txStyles extraction."""

    def _make_tx_styles(self, style_tag: str, font: str, sz: int = 2400) -> etree._Element:
        """Build a minimal <p:txStyles> element."""
        tx_styles = etree.Element(f"{{{_P_NS}}}txStyles")
        style_el = etree.SubElement(tx_styles, f"{{{_P_NS}}}{style_tag}")
        lvl1 = etree.SubElement(style_el, f"{{{_A_NS}}}lvl1pPr")
        def_rpr = etree.SubElement(lvl1, f"{{{_A_NS}}}defRPr", sz=str(sz))
        latin = etree.SubElement(def_rpr, f"{{{_A_NS}}}latin", typeface=font)
        return tx_styles

    def test_title_style_used_for_title(self):
        tx_styles = self._make_tx_styles("titleStyle", "Georgia", sz=4000)
        run, para = _txstyles_defaults(tx_styles, ph_type="title", level=0)
        assert run.font_family == "Georgia"
        assert run.font_size_pt == pytest.approx(40.0)

    def test_body_style_used_for_body(self):
        tx_styles = self._make_tx_styles("bodyStyle", "Verdana", sz=1800)
        run, para = _txstyles_defaults(tx_styles, ph_type="body", level=0)
        assert run.font_family == "Verdana"

    def test_other_style_used_for_footer(self):
        tx_styles = self._make_tx_styles("otherStyle", "Courier New")
        run, para = _txstyles_defaults(tx_styles, ph_type="ftr", level=0)
        assert run.font_family == "Courier New"

    def test_missing_tx_styles_returns_empty(self):
        run, para = _txstyles_defaults(None, ph_type="title")
        assert run.font_family is None

    def test_ctr_title_maps_to_title_style(self):
        tx_styles = self._make_tx_styles("titleStyle", "Impact")
        run, para = _txstyles_defaults(tx_styles, ph_type="ctrTitle", level=0)
        assert run.font_family == "Impact"


class TestThemeDefaults:
    """Tests for theme font scheme extraction."""

    def _make_theme(self, major_font: str, minor_font: str) -> etree._Element:
        """Build a minimal <a:theme> element."""
        theme = etree.Element(f"{{{_A_NS}}}theme")
        theme_els = etree.SubElement(theme, f"{{{_A_NS}}}themeElements")
        font_scheme = etree.SubElement(theme_els, f"{{{_A_NS}}}fontScheme")
        major = etree.SubElement(font_scheme, f"{{{_A_NS}}}majorFont")
        latin_major = etree.SubElement(major, f"{{{_A_NS}}}latin", typeface=major_font)
        minor = etree.SubElement(font_scheme, f"{{{_A_NS}}}minorFont")
        latin_minor = etree.SubElement(minor, f"{{{_A_NS}}}latin", typeface=minor_font)
        return theme

    def test_title_uses_major_font(self):
        theme = self._make_theme("Calibri Light", "Calibri")
        run = _theme_run_defaults(theme, ph_type="title")
        assert run.font_family == "Calibri Light"

    def test_body_uses_minor_font(self):
        theme = self._make_theme("Calibri Light", "Calibri")
        run = _theme_run_defaults(theme, ph_type="body")
        assert run.font_family == "Calibri"

    def test_ctr_title_uses_major_font(self):
        theme = self._make_theme("Calibri Light", "Calibri")
        run = _theme_run_defaults(theme, ph_type="ctrTitle")
        assert run.font_family == "Calibri Light"

    def test_none_theme_returns_empty(self):
        run = _theme_run_defaults(None, ph_type="title")
        assert run.font_family is None

    def test_full_cascade_theme_lowest_priority(self):
        """Theme font is lowest priority — overridden by master txStyles."""
        theme = self._make_theme("Calibri Light", "Calibri")
        # txStyles sets a different font
        tx_styles = etree.Element(f"{{{_P_NS}}}txStyles")
        title_style = etree.SubElement(tx_styles, f"{{{_P_NS}}}titleStyle")
        lvl1 = etree.SubElement(title_style, f"{{{_A_NS}}}lvl1pPr")
        def_rpr = etree.SubElement(lvl1, f"{{{_A_NS}}}defRPr")
        latin = etree.SubElement(def_rpr, f"{{{_A_NS}}}latin", typeface="Georgia")

        run, para = resolve_placeholder(
            slide_sp=None,
            layout_ph=None,
            master_ph=None,
            master_tx_styles=tx_styles,
            theme_el=theme,
            ph_type="title",
        )
        # txStyles (level 4) wins over theme (level 5)
        assert run.font_family == "Georgia"
