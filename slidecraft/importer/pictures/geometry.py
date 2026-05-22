"""PPT prstGeom preset → CSS clip-path / border-radius mapping.

Covers the 10 most-common shape presets.  For presets that translate cleanly
to a CSS border-radius (circles, rounded rectangles) the border-radius key is
populated; for all other polygonal shapes clip-path: polygon() is used with
percentage coordinates so the clip scales with the element's bounding box.

PPT coordinate reference for adjust values (av_lst):
  - roundRect  – single adjust value ``adj`` in 1/100 000ths of the shorter
                 dimension.  PPT calls these "basis-point-style" values where
                 50 000 = half the min(w,h).
  - parallelogram – ``adj`` in 1/100 000ths of the width (default ~25 000 =
                    25 % indent).
  - trapezoid  – ``adj`` in 1/100 000ths of the width for each side inset
                 (default ~25 000 = 25 % on each side, making the top edge
                 50 % of the bottom edge).
"""
from __future__ import annotations

import math


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _pct(value: float) -> str:
    """Format a float as a percentage string with one decimal place."""
    return f"{value:.1f}%"


def _polygon(*points: tuple[float, float]) -> str:
    """Render a sequence of (x_pct, y_pct) float pairs as a CSS polygon()."""
    parts = ", ".join(f"{_pct(x)} {_pct(y)}" for x, y in points)
    return f"polygon({parts})"


def _regular_polygon_points(n: int, start_deg: float = -90.0) -> list[tuple[float, float]]:
    """Return (x_pct, y_pct) vertices of a regular *n*-gon centred at (50,50).

    Vertices are spaced 360/n degrees apart, starting from *start_deg* and
    going clockwise (positive-y is down, matching CSS).  The polygon is
    inscribed in a circle of radius 50 %, so it exactly touches the bounding
    box edges along the primary axes when start_deg aligns a vertex with an
    axis.
    """
    points = []
    for i in range(n):
        angle_deg = start_deg + i * (360.0 / n)
        angle_rad = math.radians(angle_deg)
        x = 50.0 + 50.0 * math.cos(angle_rad)
        y = 50.0 + 50.0 * math.sin(angle_rad)
        points.append((x, y))
    return points


def _star5_points(
    outer_r: float = 50.0,
    inner_r: float = 19.1,
    start_deg: float = -90.0,
) -> list[tuple[float, float]]:
    """Return (x_pct, y_pct) vertices for a 5-pointed star.

    Alternates between outer and inner vertices.  *inner_r* defaults to the
    golden-ratio proportion (~38.2 % of outer_r) that produces a typical
    5-pointed star.
    """
    points = []
    for i in range(5):
        # outer point
        outer_deg = start_deg + i * 72.0
        outer_rad = math.radians(outer_deg)
        ox = 50.0 + outer_r * math.cos(outer_rad)
        oy = 50.0 + outer_r * math.sin(outer_rad)
        points.append((ox, oy))

        # inner point (halfway between consecutive outer angles)
        inner_deg = outer_deg + 36.0
        inner_rad = math.radians(inner_deg)
        ix = 50.0 + inner_r * math.cos(inner_rad)
        iy = 50.0 + inner_r * math.sin(inner_rad)
        points.append((ix, iy))

    return points


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def preset_to_css(
    preset_name: str,
    width_px: int,
    height_px: int,
    av_lst: dict[str, int] | None = None,
) -> dict | None:
    """Map a PPT prstGeom preset to CSS clip-path/border-radius.

    Args:
        preset_name: The OOXML ``prst`` attribute value from
                     ``<a:prstGeom prst="…">``, e.g. ``"ellipse"``,
                     ``"roundRect"``, ``"triangle"``.
        width_px:    Shape width in pixels (used for roundRect radius maths).
        height_px:   Shape height in pixels (used for roundRect radius maths).
        av_lst:      Optional dict of ``<a:gd name="adj" fmla="val N"/>``
                     adjust-value overrides keyed by adjust name (e.g.
                     ``{"adj": 15000}``).  Caller may pass ``None`` to use
                     preset defaults.  Values are in PPT "1/100 000ths"
                     units; for roundRect ``50 000`` means
                     ``radius = min(w,h) / 2``.

    Returns:
        A dict ``{"clip_path": str | None, "border_radius": str | None}``
        when the preset is supported, or ``None`` when it is not (the caller
        should log ``"unmapped_prstgeom:<preset_name>"``).
    """
    av = av_lst or {}

    # ------------------------------------------------------------------
    # rect — plain rectangle, no transformation needed
    # ------------------------------------------------------------------
    if preset_name == "rect":
        return {"clip_path": None, "border_radius": None}

    # ------------------------------------------------------------------
    # ellipse — full circle / ellipse via border-radius
    # ------------------------------------------------------------------
    if preset_name == "ellipse":
        return {"clip_path": None, "border_radius": "50%"}

    # ------------------------------------------------------------------
    # roundRect — border-radius computed from adj
    # PPT default adj = 16667 (approx 1/6 of the shorter dimension).
    # Effective radius = (adj / 100000) * min(w, h).
    # ------------------------------------------------------------------
    if preset_name == "roundRect":
        adj = av.get("adj", 16667)
        min_dim = min(width_px, height_px)
        radius_px = (adj / 100_000.0) * min_dim
        return {"clip_path": None, "border_radius": f"{radius_px:.1f}px"}

    # ------------------------------------------------------------------
    # triangle — isosceles, point at top-centre
    # ------------------------------------------------------------------
    if preset_name == "triangle":
        pts = [(50.0, 0.0), (100.0, 100.0), (0.0, 100.0)]
        return {"clip_path": _polygon(*pts), "border_radius": None}

    # ------------------------------------------------------------------
    # parallelogram — leans to the right; adj controls the horizontal
    # offset of the top-left corner as a fraction of width.
    # Default adj ≈ 25 000 → 25 % offset.
    # ------------------------------------------------------------------
    if preset_name == "parallelogram":
        adj = av.get("adj", 25000)
        offset = (adj / 100_000.0) * 100.0   # convert to percentage
        pts = [
            (offset, 0.0),
            (100.0, 0.0),
            (100.0 - offset, 100.0),
            (0.0, 100.0),
        ]
        return {"clip_path": _polygon(*pts), "border_radius": None}

    # ------------------------------------------------------------------
    # trapezoid — wider at the bottom; adj controls horizontal inset of
    # the top corners.  Default adj ≈ 25 000 → 25 % inset per side.
    # ------------------------------------------------------------------
    if preset_name == "trapezoid":
        adj = av.get("adj", 25000)
        inset = (adj / 100_000.0) * 100.0
        pts = [
            (inset, 0.0),
            (100.0 - inset, 0.0),
            (100.0, 100.0),
            (0.0, 100.0),
        ]
        return {"clip_path": _polygon(*pts), "border_radius": None}

    # ------------------------------------------------------------------
    # diamond — rotated square
    # ------------------------------------------------------------------
    if preset_name == "diamond":
        pts = [(50.0, 0.0), (100.0, 50.0), (50.0, 100.0), (0.0, 50.0)]
        return {"clip_path": _polygon(*pts), "border_radius": None}

    # ------------------------------------------------------------------
    # pentagon — regular 5-gon, point at top
    # ------------------------------------------------------------------
    if preset_name == "pentagon":
        pts = _regular_polygon_points(5, start_deg=-90.0)
        return {"clip_path": _polygon(*pts), "border_radius": None}

    # ------------------------------------------------------------------
    # hexagon — regular 6-gon, flat left/right edges (point top/bottom)
    # PPT's default hexagon orientation has flat sides on left and right.
    # start_deg=0 puts the first vertex at the right-centre (0°).
    # ------------------------------------------------------------------
    if preset_name == "hexagon":
        pts = _regular_polygon_points(6, start_deg=0.0)
        return {"clip_path": _polygon(*pts), "border_radius": None}

    # ------------------------------------------------------------------
    # star5 — 5-pointed star with golden-ratio inner radius
    # ------------------------------------------------------------------
    if preset_name == "star5":
        pts = _star5_points()
        return {"clip_path": _polygon(*pts), "border_radius": None}

    # Unknown / unsupported preset — caller should log unmapped_prstgeom:<name>
    return None
