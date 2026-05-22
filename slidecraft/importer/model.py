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
from typing import Literal, Optional, Union


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


@dataclass
class Slide:
    index: int                       # 1-based
    placeholders: list[Placeholder]
    background_fill: Fill = field(default_factory=NoFill)


@dataclass
class Presentation:
    slides: list[Slide]
    canvas_width_px: int             # from <p:sldSz>, EMU → px
    canvas_height_px: int
    typefaces_referenced: set[str]   # union of all font_family values appearing anywhere in the deck
