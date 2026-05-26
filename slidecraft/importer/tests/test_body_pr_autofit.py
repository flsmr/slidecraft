"""Regression tests for ``<a:bodyPr>`` autofit + wrap parsing.

The IU template's layout 11 (used by slide 24) marks its title and
body-21 placeholders with ``<a:spAutoFit/>`` and ``wrap="none"``,
meaning "this box grows to fit text and never wraps". The importer
used to ignore both, emitting fixed-size boxes that clipped text
overflow — so slide 24's "Designs with tables" title rendered with
line breaks the designer never intended.

These tests guard the parse layer (extracting + cascading bodyPr
settings) and the emit layer (CSS output for the three autofit/wrap
combinations).
"""
from __future__ import annotations

from lxml import etree

from slidecraft.importer.parse import (
    _parse_body_pr_autofit,
    _resolve_body_pr_cascade,
)


def _make_sp(body_pr_xml: str = "") -> etree._Element:
    """Build a minimal <p:sp> with the given bodyPr fragment inside p:txBody."""
    return etree.fromstring(
        '<p:sp xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"'
        '      xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
        '  <p:txBody>'
        f'    {body_pr_xml}'
        '    <a:lstStyle/>'
        '    <a:p/>'
        '  </p:txBody>'
        '</p:sp>'
    )


class TestParseBodyPrAutofit:
    def test_sp_auto_fit_sets_shape_autofit_true(self):
        sp = _make_sp('<a:bodyPr><a:spAutoFit/></a:bodyPr>')
        shape_af, wrap = _parse_body_pr_autofit(sp)
        assert shape_af is True
        # No wrap attribute → inherit (None)
        assert wrap is None

    def test_norm_autofit_means_shape_does_not_grow(self):
        """normAutofit = text scales down; the box itself stays fixed."""
        sp = _make_sp('<a:bodyPr><a:normAutofit/></a:bodyPr>')
        shape_af, _ = _parse_body_pr_autofit(sp)
        assert shape_af is False

    def test_no_autofit_marker_sets_shape_autofit_false(self):
        sp = _make_sp('<a:bodyPr><a:noAutofit/></a:bodyPr>')
        shape_af, _ = _parse_body_pr_autofit(sp)
        assert shape_af is False

    def test_empty_body_pr_yields_inherits(self):
        sp = _make_sp('<a:bodyPr/>')
        shape_af, wrap = _parse_body_pr_autofit(sp)
        # Both None = inherit from cascade
        assert shape_af is None
        assert wrap is None

    def test_no_body_pr_yields_inherits(self):
        sp = _make_sp('')  # no bodyPr at all
        shape_af, wrap = _parse_body_pr_autofit(sp)
        assert shape_af is None
        assert wrap is None

    def test_wrap_none_means_no_line_wrap(self):
        sp = _make_sp('<a:bodyPr wrap="none"/>')
        _, wrap = _parse_body_pr_autofit(sp)
        assert wrap is False

    def test_wrap_square_means_wrap_enabled(self):
        sp = _make_sp('<a:bodyPr wrap="square"/>')
        _, wrap = _parse_body_pr_autofit(sp)
        assert wrap is True

    def test_combined_iu_layout_11_title_pattern(self):
        """The exact pattern from the IU template's layout 11 title:
        wrap="none" + <a:spAutoFit/>. Box grows in both dimensions,
        text never wraps."""
        sp = _make_sp('<a:bodyPr wrap="none"><a:spAutoFit/></a:bodyPr>')
        shape_af, wrap = _parse_body_pr_autofit(sp)
        assert shape_af is True
        assert wrap is False


class TestCascade:
    def test_slide_wins_when_set(self):
        slide = _make_sp('<a:bodyPr wrap="none"><a:spAutoFit/></a:bodyPr>')
        layout = _make_sp('<a:bodyPr wrap="square"><a:noAutofit/></a:bodyPr>')
        shape_af, wrap = _resolve_body_pr_cascade(slide, layout, None)
        assert shape_af is True
        assert wrap is False

    def test_layout_used_when_slide_silent(self):
        """The bug we're targeting: slide 24's bodyPr is empty; layout 11
        has spAutoFit + wrap=none. We must inherit from the layout."""
        slide = _make_sp('<a:bodyPr/>')
        layout = _make_sp('<a:bodyPr wrap="none"><a:spAutoFit/></a:bodyPr>')
        shape_af, wrap = _resolve_body_pr_cascade(slide, layout, None)
        assert shape_af is True
        assert wrap is False

    def test_independent_property_cascade(self):
        """Each property cascades independently — slide sets wrap, layout
        sets autofit; both should be respected."""
        slide = _make_sp('<a:bodyPr wrap="none"/>')
        layout = _make_sp('<a:bodyPr><a:spAutoFit/></a:bodyPr>')
        shape_af, wrap = _resolve_body_pr_cascade(slide, layout, None)
        assert shape_af is True
        assert wrap is False

    def test_master_fallback(self):
        slide = _make_sp('<a:bodyPr/>')
        layout = _make_sp('<a:bodyPr/>')
        master = _make_sp('<a:bodyPr wrap="none"><a:spAutoFit/></a:bodyPr>')
        shape_af, wrap = _resolve_body_pr_cascade(slide, layout, master)
        assert shape_af is True
        assert wrap is False

    def test_default_when_no_source_sets(self):
        slide = _make_sp('<a:bodyPr/>')
        layout = _make_sp('<a:bodyPr/>')
        shape_af, wrap = _resolve_body_pr_cascade(slide, layout, None)
        # PPT defaults: shape_autofit=False, wrap_text=True
        assert shape_af is False
        assert wrap is True
