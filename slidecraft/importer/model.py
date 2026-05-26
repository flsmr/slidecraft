"""Resolved slide model — the contract between parse, inheritance, fonts, and emit.

Conventions:
- Distances: floats in px (after EMU → px conversion using the canvas pixel size).
- Angles: floats in degrees (PPT stores 60000ths-of-a-degree; divide before storing).
- Font sizes / paragraph spacing: floats in pt (emit/layout converts to px at output time).
- Colors: RGB with optional alpha (0.0–1.0).
- Cascade resolution lives in inheritance.py; this model carries fully-resolved values.

Run.* and Paragraph.* fields use Optional[T] = None to mean "inherits from the
placeholder default". Emit/slide.py diffs each run/paragraph against
Placeholder.default_run_props / default_para_props and emits CSS only for
fields that differ from the default.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal, Optional, Union

if TYPE_CHECKING:
    # Avoid circular import — shapes.model / tables.model depend on this
    # file's primitives (RGB, Run, Paragraph, Fill, TextFrame), so they
    # can't be imported at module-load time. The dataclasses only appear
    # as type annotations on Slide; runtime stores the lists opaquely.
    from slidecraft.importer.shapes.model import TextShape
    from slidecraft.importer.tables.model import Table


@dataclass(frozen=True)
class RGB:
    r: int   # 0–255
    g: int
    b: int
    alpha: float = 1.0


@dataclass
class SolidFill:
    color: RGB


@dataclass
class GradientStop:
    position: float   # 0.0–1.0
    color: RGB


@dataclass
class LinearGradientFill:
    angle_deg: float
    stops: list[GradientStop]


@dataclass
class RadialGradientFill:
    stops: list[GradientStop]


@dataclass
class NoFill:
    pass


Fill = Union[SolidFill, LinearGradientFill, RadialGradientFill, NoFill]


@dataclass
class Run:
    """Text run. None fields = inherit from the placeholder default."""
    text: str
    bold: Optional[bool] = None
    italic: Optional[bool] = None
    underline: Optional[bool] = None
    strike: Optional[bool] = None
    color: Optional[RGB] = None
    font_family: Optional[str] = None
    font_size_pt: Optional[float] = None
    # cap: "all" → text-transform:uppercase, "small" → text-transform:lowercase, None → inherit
    cap: Optional[str] = None


@dataclass
class Paragraph:
    runs: list[Run]
    align: Optional[Literal["l", "ctr", "r", "just"]] = None
    line_spacing_pct: Optional[float] = None      # 100 = single, 150 = 1.5x
    space_before_pt: Optional[float] = None
    space_after_pt: Optional[float] = None
    indent_pt: Optional[float] = None             # first-line indent
    margin_left_pt: Optional[float] = None        # hanging margin
    bullet: Optional[Literal["none", "char", "auto-num"]] = None
    bullet_char: Optional[str] = None
    # Bullet styling — extracted from the cascade so emit can render the
    # marker faithfully via CSS ::marker. None on any field means "inherit".
    bullet_color: Optional[RGB] = None            # from <a:buClr> (scheme-resolved)
    bullet_font: Optional[str] = None             # from <a:buFont @typeface>
    bullet_size_pct: Optional[float] = None       # from <a:buSzPct @val>; 100 = same as text
    # OOXML auto-num type (e.g. "arabicPeriod", "romanLcParenR"); only set
    # when bullet == "auto-num". Maps to a CSS list-style-type at emit time.
    bullet_autonum_type: Optional[str] = None
    level: int = 0                                # 0–8 (PPT lvl)


@dataclass
class TextFrame:
    paragraphs: list[Paragraph]
    anchor: Literal["t", "ctr", "b"] = "t"
    insets_pt: tuple[float, float, float, float] = (7.2, 3.6, 7.2, 3.6)  # l, t, r, b
    rotation_deg: float = 0.0
    autofit_font_scale: float = 1.0               # from <a:normAutofit fontScale>


@dataclass
class Placeholder:
    """A text-bearing placeholder, fully resolved at slide level."""
    idx: int
    type: Optional[str]              # title, body, ctrTitle, dt, ftr, sldNum, or None
    x_px: float
    y_px: float
    width_px: float
    height_px: float
    rotation_deg: float = 0.0
    fill: Fill = field(default_factory=NoFill)
    opacity: float = 1.0
    text_frame: Optional[TextFrame] = None
    # Baked-in defaults the layout .vue carries; emit/slide.py diffs runs/paragraphs
    # against these to decide what to emit on each one.
    default_run_props: Run = field(default_factory=lambda: Run(text=""))
    default_para_props: Paragraph = field(default_factory=lambda: Paragraph(runs=[]))
    # When True, text_frame content came from the layout's hasCustomPrompt placeholder
    # (slide-level txBody was empty).  Emit layer may style this differently (e.g. lighter
    # opacity or italic) in future; for v1 it is rendered as normal text.
    is_prompt_fallback: bool = False
    # CSS clip-path value for the placeholder wrapper, set when the shape's
    # geometry is a custGeom or a non-rect prstGeom (cascade: slide → layout →
    # master). ``None`` for plain rectangles. The wrapper's text content and
    # background are both clipped to this path. Set by parse.py via
    # pictures.geometry.cust_geom_to_clip_path / preset_to_css.
    clip_path: Optional[str] = None
    # OOXML <a:bodyPr> autofit + wrap settings, cascaded slide → layout. They
    # control whether the box's width/height should be FIXED (the default —
    # text overflows and gets clipped) or DYNAMIC (grow to fit text content).
    # ``shape_autofit`` mirrors <a:spAutoFit/>; when True the wrapper's
    # height grows with content. ``wrap_text`` mirrors bodyPr.@wrap; False
    # (PPT's ``wrap="none"``) means the wrapper grows horizontally and never
    # line-wraps the text. Both False is the spec default — caller emits a
    # fixed-size box with overflow:hidden.
    shape_autofit: bool = False
    wrap_text: bool = True


@dataclass
class Picture:
    """A `<p:pic>` shape or picture-typed placeholder, fully resolved at slide level.

    Geometry (x/y/w/h) is in px. Rotation, flips, opacity, filters, and pre-bake
    derivatives all live in the ``effects`` dict (output of
    ``pictures.effects.parse_effects``) — emit reads them from there.

    ``asset_ref`` is the basename written into ``deck/public/assets/`` by
    ``pictures.extract.extract_pictures`` (preserves the original
    ``ppt/media/<name>``). It is ``None`` only for a picture-typed placeholder
    that has no image bound on either slide or layout (empty box rendering).
    """
    asset_ref: Optional[str]
    x_px: float
    y_px: float
    width_px: float
    height_px: float
    # Shape geometry mask (prstGeom). None means rectangular (no clip).
    preset_geom: Optional[str] = None
    preset_geom_av: Optional[dict[str, int]] = None
    # Output of pictures.effects.parse_effects (transforms/css_filter/opacity/
    # derivatives_needed/box_reflect/mask_image/warnings). Empty when not parsed.
    effects: dict = field(default_factory=dict)
    alt_text: str = ""
    shape_id: int = 0                # cNvPr/@id — used as `pic-<id>` wrapper class
    # Placeholder marker. True iff parsed from `<p:sp>` with `<p:ph type="pic"/>`.
    is_placeholder: bool = False
    ph_idx: Optional[int] = None     # set iff is_placeholder; used as `ph_<idx>` slot name
    # 0-based index in slide XML document order; lets emit interleave pics + placeholders.
    order_index: int = 0


@dataclass
class Slide:
    index: int                       # 1-based
    placeholders: list[Placeholder]
    background_fill: Fill = field(default_factory=NoFill)
    pictures: list[Picture] = field(default_factory=list)
    # Layer 3 — non-placeholder text-bearing shapes (slide/layout/master).
    # See slidecraft/importer/shapes/ for the TextShape model and the
    # walk_text_shapes() / render_text_shape_host() pipeline.
    text_shapes: list["TextShape"] = field(default_factory=list)
    # Layer 4 — tables (<p:graphicFrame>/<a:tbl>). See importer/tables/.
    tables: list["Table"] = field(default_factory=list)


@dataclass
class Presentation:
    slides: list[Slide]
    canvas_width_px: int             # from <p:sldSz>, EMU → px
    canvas_height_px: int
    typefaces_referenced: set[str]   # union of all font_family values appearing anywhere in the deck
