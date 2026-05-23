"""Resolved model for non-placeholder text-bearing shapes.

A `TextShape` is a `<p:sp>` (without `<p:ph>`) that carries non-empty text,
collected from any cascade level (slide / slideLayout / slideMaster).

The wrapping `Slide` model in `slidecraft.importer.model` will, once Layer 1's
polish session releases `model.py`, gain a `text_shapes: list[TextShape]`
field paralleling the existing `pictures: list[Picture]` field. Until then,
`TextShape` is built and consumed by the shapes subpackage only.

Conventions match the rest of the importer:
- Distances/sizes: px (post-EMU conversion)
- Rotation: degrees
- Font sizes / paragraph spacing: pt
- Colors: model.RGB
- Cascade-resolved defaults live in default_run / default_para; per-run and
  per-paragraph deviations are diffed against them at emit time.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional

from slidecraft.importer.model import (
    Fill,
    NoFill,
    Paragraph,
    RGB,
    Run,
    TextFrame,
)


@dataclass
class BorderProps:
    """Stroke around a text shape (`<a:ln>` element).

    Maps to a single CSS `border` declaration. `<a:ln>` can carry far more
    properties (dash patterns, line joins, gradient strokes) but the IU
    template only uses solid uniform strokes; we render those and ignore
    the rest for now.
    """
    width_pt: float                      # `<a:ln w>` is EMU → pt
    color: RGB
    style: Literal["solid", "dashed", "dotted"] = "solid"


@dataclass
class ShapeGeometry:
    """Drawn shape geometry derived from `<a:prstGeom>` or `<a:custGeom>`.

    Two render modes are encoded:
      - ``preset`` carries an OOXML `prstGeom prst="..."` value (e.g.
        ``"rect"``, ``"rtTriangle"``, ``"ellipse"``).  Caller resolves this
        against :func:`pictures.geometry.preset_to_svg_path` to obtain SVG
        path data, or falls back to a CSS-styled `<div>` when the preset is
        ``"rect"`` with no custom adjustments.
      - ``svg_path`` carries pre-resolved SVG ``d=""`` path data, populated
        when the source element is `<a:custGeom>` (or when the preset has
        already been expanded to a path).

    When both are ``None``, the shape has no explicit geometry and renders
    as the bounding-box rectangle (the OOXML default).
    """
    preset: Optional[str] = None             # `prstGeom prst="..."`
    preset_adjusts: Optional[dict[str, int]] = None
    svg_path: Optional[str] = None           # bare SVG d="..." path data


@dataclass
class TextShape:
    """A non-placeholder shape, fully resolved at slide level.

    Despite the historical name, a ``TextShape`` may carry no text at all —
    it is the model for any non-placeholder visible shape (text boxes,
    decorative rectangles, custom-geometry freeforms).  The filter is now
    "visible chrome OR text" rather than "text only"; see
    :func:`shapes.parse._is_visible`.

    The `source` field drives the emission split for text-bearing shapes:
      - "slide"  → text content surfaces as a `::txt_<shape_id>::` slot in
                   `slides.md`; the layout `.vue` carries only the wrapper
                   div (chrome + position + cascade defaults baked in).
      - "layout" / "master" → text content is baked directly into the
                              layout `.vue` (template decoration, not
                              user-editable from `slides.md`).

    Decorative-only shapes (no text frame, or empty paragraphs) skip the
    slot mechanism entirely — the wrapper div renders chrome alone.

    `order_index` mirrors `Picture.order_index` so emit can interleave
    text shapes with placeholders and pictures in PPT document / z-order.
    """
    # Source level — drives slot-vs-baked emission.
    source: Literal["slide", "layout", "master"]

    # Identity (from `<p:cNvPr id name>`).  Used for slot naming (`txt_<id>`)
    # and CSS class names (`.txt-<id>`).  PPT guarantees `id` uniqueness
    # within a single slide XML; cross-source duplicates are rare but
    # possible — emit prefixes the source level internally to deduplicate
    # CSS class names if it ever encounters a collision.
    shape_id: int
    name: str = ""                       # PPT cNvPr/@name — debug only

    # Position / size (px) and rotation (deg) — same as Placeholder.
    x_px: float = 0.0
    y_px: float = 0.0
    width_px: float = 0.0
    height_px: float = 0.0
    rotation_deg: float = 0.0

    # Box chrome.  fill is the shape's solidFill (or NoFill); border is the
    # `<a:ln>` stroke (or None).  geometry carries the prstGeom preset or
    # custGeom path so emit can render non-rect shapes as inline SVG.
    fill: Fill = field(default_factory=NoFill)
    border: Optional[BorderProps] = None
    opacity: float = 1.0
    geometry: Optional[ShapeGeometry] = None

    # Body — bodyPr (insets, anchor, autofit, rotation) + paragraphs.
    # Reuses the same TextFrame the placeholder pipeline already builds.
    text_frame: Optional[TextFrame] = None

    # Cascade-resolved defaults (theme → master otherStyle → shape txBody
    # lstStyle / first-pPr / first-rPr).  Used by emit/slide.py to diff
    # per-run and per-paragraph values for the markdown-vs-HTML policy.
    default_run: Run = field(default_factory=lambda: Run(text=""))
    default_para: Paragraph = field(default_factory=lambda: Paragraph(runs=[]))

    # 0-based document-order index across this slide's effective spTree
    # walk (master segment → layout segment → slide segment).  Emit merges
    # text_shapes, placeholders, and pictures into a single list sorted by
    # order_index before rendering.
    order_index: int = 0
