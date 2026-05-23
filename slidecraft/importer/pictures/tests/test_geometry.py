"""Tests for pictures/geometry.py — PPT prstGeom → CSS mapping.

All tests use a 200×100 box unless otherwise noted.  No PPTX dependency;
purely unit-testing the mapping logic.
"""
from __future__ import annotations

import pytest

from lxml import etree

from slidecraft.importer.pictures.geometry import (
    cust_geom_to_clip_path,
    preset_to_css,
)

_A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"

# Canonical test dimensions
W = 200
H = 100


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _css(preset: str, w: int = W, h: int = H, av: dict | None = None) -> dict | None:
    return preset_to_css(preset, w, h, av_lst=av)


# ---------------------------------------------------------------------------
# rect
# ---------------------------------------------------------------------------

class TestRect:
    def test_returns_both_none(self):
        result = _css("rect")
        assert result == {"clip_path": None, "border_radius": None}

    def test_clip_path_is_none(self):
        assert _css("rect")["clip_path"] is None

    def test_border_radius_is_none(self):
        assert _css("rect")["border_radius"] is None


# ---------------------------------------------------------------------------
# ellipse
# ---------------------------------------------------------------------------

class TestEllipse:
    def test_border_radius_50pct(self):
        result = _css("ellipse")
        assert result == {"clip_path": None, "border_radius": "50%"}

    def test_clip_path_is_none(self):
        assert _css("ellipse")["clip_path"] is None


# ---------------------------------------------------------------------------
# roundRect
# ---------------------------------------------------------------------------

class TestRoundRect:
    def test_default_adj(self):
        """Default adj=16667; min(200,100)=100 → radius = 16.667 → '16.7px'."""
        result = _css("roundRect")
        assert result["clip_path"] is None
        assert result["border_radius"] == "16.7px"

    def test_explicit_adj_overrides_default(self):
        """adj=30000 on 200×100 box → radius = 0.3 * 100 = 30.0px."""
        result = _css("roundRect", av={"adj": 30000})
        assert result["border_radius"] == "30.0px"

    def test_adj_50000_uses_half_min_dim(self):
        """adj=50000 should give radius = 0.5 * min(w,h)."""
        result = _css("roundRect", w=200, h=100, av={"adj": 50000})
        assert result["border_radius"] == "50.0px"

    def test_min_dimension_is_height(self):
        """For a 200×100 box the shorter side is 100; for 100×200 it's also 100."""
        r1 = _css("roundRect", w=200, h=100, av={"adj": 20000})
        r2 = _css("roundRect", w=100, h=200, av={"adj": 20000})
        assert r1["border_radius"] == r2["border_radius"] == "20.0px"

    def test_no_clip_path(self):
        assert _css("roundRect")["clip_path"] is None


# ---------------------------------------------------------------------------
# triangle
# ---------------------------------------------------------------------------

class TestTriangle:
    def test_clip_path_value(self):
        result = _css("triangle")
        assert result["clip_path"] == "polygon(50.0% 0.0%, 100.0% 100.0%, 0.0% 100.0%)"

    def test_border_radius_is_none(self):
        assert _css("triangle")["border_radius"] is None


# ---------------------------------------------------------------------------
# parallelogram
# ---------------------------------------------------------------------------

class TestParallelogram:
    def test_default_adj(self):
        """Default adj=25000 → 25% horizontal offset."""
        result = _css("parallelogram")
        assert result["clip_path"] == (
            "polygon(25.0% 0.0%, 100.0% 0.0%, 75.0% 100.0%, 0.0% 100.0%)"
        )

    def test_border_radius_is_none(self):
        assert _css("parallelogram")["border_radius"] is None

    def test_explicit_adj(self):
        """adj=50000 → 50% offset (a degenerate parallelogram / triangle at 45°)."""
        result = _css("parallelogram", av={"adj": 50000})
        assert result["clip_path"] == (
            "polygon(50.0% 0.0%, 100.0% 0.0%, 50.0% 100.0%, 0.0% 100.0%)"
        )


# ---------------------------------------------------------------------------
# trapezoid
# ---------------------------------------------------------------------------

class TestTrapezoid:
    def test_default_adj(self):
        """Default adj=25000 → 25% inset on each side of the top edge."""
        result = _css("trapezoid")
        assert result["clip_path"] == (
            "polygon(25.0% 0.0%, 75.0% 0.0%, 100.0% 100.0%, 0.0% 100.0%)"
        )

    def test_border_radius_is_none(self):
        assert _css("trapezoid")["border_radius"] is None

    def test_explicit_adj_zero(self):
        """adj=0 → top edge spans full width (same as rect, but via clip-path)."""
        result = _css("trapezoid", av={"adj": 0})
        assert result["clip_path"] == (
            "polygon(0.0% 0.0%, 100.0% 0.0%, 100.0% 100.0%, 0.0% 100.0%)"
        )


# ---------------------------------------------------------------------------
# diamond
# ---------------------------------------------------------------------------

class TestDiamond:
    def test_clip_path_value(self):
        result = _css("diamond")
        assert result["clip_path"] == (
            "polygon(50.0% 0.0%, 100.0% 50.0%, 50.0% 100.0%, 0.0% 50.0%)"
        )

    def test_border_radius_is_none(self):
        assert _css("diamond")["border_radius"] is None


# ---------------------------------------------------------------------------
# pentagon
# ---------------------------------------------------------------------------

class TestPentagon:
    def test_clip_path_value(self):
        """Regular pentagon, point at top, inscribed in bounding box."""
        result = _css("pentagon")
        assert result["clip_path"] == (
            "polygon(50.0% 0.0%, 97.6% 34.5%, 79.4% 90.5%, 20.6% 90.5%, 2.4% 34.5%)"
        )

    def test_border_radius_is_none(self):
        assert _css("pentagon")["border_radius"] is None


# ---------------------------------------------------------------------------
# hexagon
# ---------------------------------------------------------------------------

class TestHexagon:
    def test_clip_path_value(self):
        """Regular hexagon, flat left/right edges (pointy top and bottom)."""
        result = _css("hexagon")
        assert result["clip_path"] == (
            "polygon(100.0% 50.0%, 75.0% 93.3%, 25.0% 93.3%, "
            "0.0% 50.0%, 25.0% 6.7%, 75.0% 6.7%)"
        )

    def test_border_radius_is_none(self):
        assert _css("hexagon")["border_radius"] is None


# ---------------------------------------------------------------------------
# star5
# ---------------------------------------------------------------------------

class TestStar5:
    def test_clip_path_value(self):
        """5-pointed star with golden-ratio inner radius."""
        result = _css("star5")
        assert result["clip_path"] == (
            "polygon(50.0% 0.0%, 61.2% 34.5%, 97.6% 34.5%, 68.2% 55.9%, "
            "79.4% 90.5%, 50.0% 69.1%, 20.6% 90.5%, 31.8% 55.9%, "
            "2.4% 34.5%, 38.8% 34.5%)"
        )

    def test_border_radius_is_none(self):
        assert _css("star5")["border_radius"] is None

    def test_ten_vertices(self):
        """A 5-pointed star alternates 5 outer + 5 inner = 10 vertices."""
        result = _css("star5")
        assert result["clip_path"] is not None
        # polygon(p0, p1, ..., p9) → 9 commas separating the 10 point pairs
        # Each "x% y%" pair contains no comma; commas only appear between pairs.
        comma_count = result["clip_path"].count(",")
        assert comma_count == 9  # 9 commas between 10 points


# ---------------------------------------------------------------------------
# Unknown / unsupported preset
# ---------------------------------------------------------------------------

class TestUnknownPreset:
    def test_returns_none_for_unknown(self):
        result = _css("someUnknownShape")
        assert result is None

    def test_returns_none_for_rtTriangle(self):
        """rtTriangle is explicitly out of scope per ticket specification."""
        assert _css("rtTriangle") is None

    def test_returns_none_for_empty_string(self):
        assert _css("") is None

    def test_returns_none_for_flowChartProcess(self):
        assert _css("flowChartProcess") is None


# ---------------------------------------------------------------------------
# cust_geom_to_clip_path — custom geometry path conversion
# ---------------------------------------------------------------------------

def _cust_geom(inner_path_xml: str) -> etree._Element:
    """Wrap *inner_path_xml* in a <a:custGeom><a:pathLst><a:path>...</a:path></a:pathLst></a:custGeom>."""
    return etree.fromstring(
        f'<a:custGeom xmlns:a="{_A_NS}"><a:pathLst>{inner_path_xml}</a:pathLst></a:custGeom>'
    )


class TestCustGeomBasic:
    def test_returns_none_for_none_input(self):
        assert cust_geom_to_clip_path(None, 100, 50) is None

    def test_returns_none_when_pathlst_missing(self):
        el = etree.fromstring(f'<a:custGeom xmlns:a="{_A_NS}"><a:avLst/></a:custGeom>')
        assert cust_geom_to_clip_path(el, 100, 50) is None

    def test_returns_none_for_empty_path(self):
        el = _cust_geom('<a:path w="100" h="100"/>')
        assert cust_geom_to_clip_path(el, 100, 50) is None

    def test_skips_path_with_zero_dims(self):
        el = _cust_geom('<a:path w="0" h="100"><a:moveTo><a:pt x="50" y="50"/></a:moveTo></a:path>')
        assert cust_geom_to_clip_path(el, 100, 50) is None


class TestCustGeomCommands:
    def test_moveto_and_lineto(self):
        el = _cust_geom(
            '<a:path w="100" h="100">'
            '<a:moveTo><a:pt x="0" y="0"/></a:moveTo>'
            '<a:lnTo><a:pt x="100" y="0"/></a:lnTo>'
            '<a:lnTo><a:pt x="100" y="100"/></a:lnTo>'
            '<a:close/>'
            '</a:path>'
        )
        result = cust_geom_to_clip_path(el, 200, 100)
        # Coords scaled: (0,0) → (0,0); (100,0) → (200,0); (100,100) → (200,100)
        assert result == 'path("M 0 0 L 200 0 L 200 100 Z")'

    def test_cubic_bezier(self):
        el = _cust_geom(
            '<a:path w="1000" h="1000">'
            '<a:moveTo><a:pt x="0" y="500"/></a:moveTo>'
            '<a:cubicBezTo>'
            '<a:pt x="0" y="200"/>'
            '<a:pt x="200" y="0"/>'
            '<a:pt x="500" y="0"/>'
            '</a:cubicBezTo>'
            '</a:path>'
        )
        result = cust_geom_to_clip_path(el, 100, 100)
        # 1000-unit space → 100-px box: divide all coords by 10
        assert "M 0 50" in result
        assert "C 0 20, 20 0, 50 0" in result

    def test_quadratic_bezier(self):
        el = _cust_geom(
            '<a:path w="100" h="100">'
            '<a:moveTo><a:pt x="0" y="100"/></a:moveTo>'
            '<a:quadBezTo>'
            '<a:pt x="50" y="0"/>'
            '<a:pt x="100" y="100"/>'
            '</a:quadBezTo>'
            '</a:path>'
        )
        result = cust_geom_to_clip_path(el, 100, 100)
        assert "Q 50 0, 100 100" in result

    def test_arc_to_is_skipped(self):
        """arcTo is unsupported and should be silently skipped (other commands still emit)."""
        el = _cust_geom(
            '<a:path w="100" h="100">'
            '<a:moveTo><a:pt x="0" y="0"/></a:moveTo>'
            '<a:arcTo wR="50" hR="50" stAng="0" swAng="5400000"/>'
            '<a:lnTo><a:pt x="100" y="100"/></a:lnTo>'
            '<a:close/>'
            '</a:path>'
        )
        result = cust_geom_to_clip_path(el, 100, 100)
        # arcTo absent from output; moveTo + lnTo + close present.
        assert result == 'path("M 0 0 L 100 100 Z")'

    def test_multiple_paths_concatenate(self):
        el = etree.fromstring(
            f'<a:custGeom xmlns:a="{_A_NS}"><a:pathLst>'
            '<a:path w="100" h="100">'
            '<a:moveTo><a:pt x="0" y="0"/></a:moveTo>'
            '<a:lnTo><a:pt x="50" y="0"/></a:lnTo>'
            '<a:close/>'
            '</a:path>'
            '<a:path w="100" h="100">'
            '<a:moveTo><a:pt x="50" y="50"/></a:moveTo>'
            '<a:lnTo><a:pt x="100" y="100"/></a:lnTo>'
            '<a:close/>'
            '</a:path>'
            '</a:pathLst></a:custGeom>'
        )
        result = cust_geom_to_clip_path(el, 100, 100)
        # Two subpaths, each with their own M ... Z, space-joined.
        assert result == 'path("M 0 0 L 50 0 Z M 50 50 L 100 100 Z")'


class TestCustGeomCoordinateMapping:
    def test_scales_to_target_box(self):
        """Path coords in PPT EMU space scale to target pixel box."""
        el = _cust_geom(
            '<a:path w="10000" h="2000">'
            '<a:moveTo><a:pt x="0" y="0"/></a:moveTo>'
            '<a:lnTo><a:pt x="10000" y="2000"/></a:lnTo>'
            '<a:close/>'
            '</a:path>'
        )
        result = cust_geom_to_clip_path(el, 500, 100)
        # (10000, 2000) in EMU space → (500, 100) in pixel space
        assert "L 500 100" in result

    def test_aspect_ratio_change(self):
        """Path that is square in PPT space stretches when target box is wider."""
        el = _cust_geom(
            '<a:path w="100" h="100">'
            '<a:moveTo><a:pt x="50" y="50"/></a:moveTo>'
            '<a:lnTo><a:pt x="100" y="100"/></a:lnTo>'
            '</a:path>'
        )
        result = cust_geom_to_clip_path(el, 400, 100)
        # x scales by 4, y by 1
        assert "M 200 50" in result
        assert "L 400 100" in result
