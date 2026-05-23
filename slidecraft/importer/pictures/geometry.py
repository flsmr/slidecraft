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


# ---------------------------------------------------------------------------
# Custom geometry (<a:custGeom>) — freeform shapes
# ---------------------------------------------------------------------------

# OOXML drawingml namespace, used for lxml localname lookups.
_A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"


def _atag(name: str) -> str:
    return f"{{{_A_NS}}}{name}"


def cust_geom_to_clip_path(
    cust_geom_el,
    width_px: float,
    height_px: float,
) -> str | None:
    """Convert a PPT ``<a:custGeom>`` element to a CSS ``clip-path: path(...)``.

    PPT freeform shapes carry their geometry as one or more ``<a:path>``
    blocks inside ``<a:pathLst>``. Each path declares its local coordinate
    space via ``w`` / ``h`` attributes (in EMU); commands inside the path
    refer to that space, not the rendered pixel size. We map every point
    (``ppt_x``, ``ppt_y``) to a CSS pixel coordinate by

        css_x = (ppt_x / path_w) * width_px
        css_y = (ppt_y / path_h) * height_px

    and emit an SVG-compatible path string suitable for CSS
    ``clip-path: path("M ... Z")``.

    Supported PPT path commands:
      ``<a:moveTo>``   →  ``M``
      ``<a:lnTo>``     →  ``L``
      ``<a:cubicBezTo>`` → ``C`` (3 control/endpoint points)
      ``<a:quadBezTo>``  → ``Q`` (2 control/endpoint points)
      ``<a:close/>``   →  ``Z``

    ``<a:arcTo>`` is **not** translated — it has no direct SVG ``A`` analog
    without trig conversion (PPT uses ``wR``/``hR``/``stAng``/``swAng`` in
    60000ths of a degree). When an arcTo is encountered the command is
    skipped; that path segment will be missing from the clip. Caller can
    add a warning if useful.

    Multiple ``<a:path>`` blocks inside the pathLst are concatenated into
    one path string (separated by spaces, each starting with its own ``M``).

    Args:
        cust_geom_el: The ``<a:custGeom>`` lxml element. May be ``None`` —
                      returns ``None`` then.
        width_px:     Rendered width of the shape in CSS pixels.
        height_px:    Rendered height of the shape in CSS pixels.

    Returns:
        A CSS ``path("M ... Z")`` string, or ``None`` if the element is
        empty / malformed.
    """
    if cust_geom_el is None:
        return None

    path_lst = cust_geom_el.find(_atag("pathLst"))
    if path_lst is None:
        return None

    segments: list[str] = []
    for path_el in path_lst.findall(_atag("path")):
        try:
            path_w = float(path_el.get("w", "0"))
            path_h = float(path_el.get("h", "0"))
        except ValueError:
            continue
        if path_w <= 0 or path_h <= 0:
            continue

        def _pt(p) -> tuple[float, float]:
            """Map a single ``<a:pt>`` to pixel coordinates."""
            px = float(p.get("x", "0")) / path_w * width_px
            py = float(p.get("y", "0")) / path_h * height_px
            return px, py

        cmds: list[str] = []
        for child in path_el:
            tag = child.tag.rsplit("}", 1)[-1]
            if tag == "moveTo":
                pt = child.find(_atag("pt"))
                if pt is not None:
                    x, y = _pt(pt)
                    cmds.append(f"M {x:.4g} {y:.4g}")
            elif tag == "lnTo":
                pt = child.find(_atag("pt"))
                if pt is not None:
                    x, y = _pt(pt)
                    cmds.append(f"L {x:.4g} {y:.4g}")
            elif tag == "cubicBezTo":
                pts = child.findall(_atag("pt"))
                if len(pts) >= 3:
                    x1, y1 = _pt(pts[0])
                    x2, y2 = _pt(pts[1])
                    x3, y3 = _pt(pts[2])
                    cmds.append(
                        f"C {x1:.4g} {y1:.4g}, {x2:.4g} {y2:.4g}, "
                        f"{x3:.4g} {y3:.4g}"
                    )
            elif tag == "quadBezTo":
                pts = child.findall(_atag("pt"))
                if len(pts) >= 2:
                    x1, y1 = _pt(pts[0])
                    x2, y2 = _pt(pts[1])
                    cmds.append(f"Q {x1:.4g} {y1:.4g}, {x2:.4g} {y2:.4g}")
            elif tag == "close":
                cmds.append("Z")
            # arcTo deliberately skipped — see docstring.

        if cmds:
            segments.append(" ".join(cmds))

    if not segments:
        return None

    # Multiple <a:path> blocks concatenate (each carries its own M).
    # Single-quote the path so the value is safe to drop into an HTML
    # double-quoted style attribute without escaping. CSS accepts both.
    return f"path('{' '.join(segments)}')"
