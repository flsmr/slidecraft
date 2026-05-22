"""Tests for pictures/geometry.py — PPT prstGeom → CSS mapping.

All tests use a 200×100 box unless otherwise noted.  No PPTX dependency;
purely unit-testing the mapping logic.
"""
from __future__ import annotations

import pytest

from slidecraft.importer.pictures.geometry import preset_to_css

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
