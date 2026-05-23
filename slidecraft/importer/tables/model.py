"""Resolved table model.

A :class:`Table` represents one ``<a:tbl>`` inside a ``<p:graphicFrame>`` on a
slide. Tables sit alongside ``placeholders`` / ``pictures`` / ``text_shapes``
on :class:`slidecraft.importer.model.Slide`.

Each :class:`TableCell` carries its own text (full ``Paragraph`` / ``Run``
structure via :class:`slidecraft.importer.model.TextFrame`), background
fill, anchor, and four edge borders. v1 emits one absolutely-positioned
``<div>`` per cell on a CSS grid; merged cells are out of scope.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional

from slidecraft.importer.model import (
    Fill,
    NoFill,
    Paragraph,
    Run,
    TextFrame,
)
from slidecraft.importer.shapes.model import BorderProps


@dataclass
class TableCell:
    """A single ``<a:tc>`` cell, fully resolved."""
    row: int                                  # 0-based row index
    col: int                                  # 0-based column index
    # Per-cell text frame (reuses Layer 1's TextFrame: bodyPr + paragraphs).
    text_frame: Optional[TextFrame] = None
    # Cascade-resolved default run / paragraph props for this cell, used by
    # the deviation diff at emit time.
    default_run: Run = field(default_factory=lambda: Run(text=""))
    default_para: Paragraph = field(default_factory=lambda: Paragraph(runs=[]))
    # Vertical anchor of the cell's text frame (PPT ``tcPr@anchor``).
    anchor: Literal["t", "ctr", "b"] = "t"
    # Cell padding (PPT ``tcPr@marL/marT/marR/marB``) in pt.  Defaults match
    # PPT: marL=marR=91440 EMU = 7.2 pt; marT=marB=45720 EMU = 3.6 pt.
    insets_pt: tuple[float, float, float, float] = (7.2, 3.6, 7.2, 3.6)  # l, t, r, b
    # Cell background (solidFill / NoFill / gradient).
    fill: Fill = field(default_factory=NoFill)
    # Edge borders.  None means "no border drawn on this edge".
    border_left: Optional[BorderProps] = None
    border_right: Optional[BorderProps] = None
    border_top: Optional[BorderProps] = None
    border_bottom: Optional[BorderProps] = None


@dataclass
class Table:
    """A ``<a:tbl>`` inside a slide-level ``<p:graphicFrame>``."""
    # Identity (from the graphicFrame's ``<p:cNvPr id name>``).
    shape_id: int
    name: str = ""

    # Position (px) — from the graphicFrame's ``<p:xfrm>``.
    x_px: float = 0.0
    y_px: float = 0.0
    width_px: float = 0.0
    height_px: float = 0.0
    rotation_deg: float = 0.0

    # Column widths and row heights, in px.  The sums should equal width_px /
    # height_px but PPT sometimes rounds.
    col_widths_px: list[float] = field(default_factory=list)
    row_heights_px: list[float] = field(default_factory=list)

    # 2-D grid of cells, indexed cells[row][col].
    cells: list[list[TableCell]] = field(default_factory=list)

    # 0-based emit interleave index (matches Picture.order_index /
    # TextShape.order_index).  Tables typically sit between placeholders
    # and pictures in document order.
    order_index: int = 0
