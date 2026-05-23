"""Render a :class:`Table` into a positioned CSS-grid ``<div>`` block.

Why CSS Grid: PPT tables are pixel-positioned with explicit column widths
and row heights, and cells are uniquely addressable by (row, col). CSS Grid
natively supports both. Each cell becomes a child ``<div>`` placed at its
grid coordinates; its own border, fill, anchor, and text content live on
that child.

The outer wrapper carries:
  - ``position:absolute`` at the table's slide coords
  - ``display:grid`` with explicit ``grid-template-columns`` / ``-rows``

Each cell ``<div>`` carries:
  - ``grid-column``/``grid-row`` (1-based)
  - ``background``, ``border-{l,t,r,b}`` from the parsed BorderProps
  - ``padding`` from the cell's marL/T/R/B
  - ``display:flex; align-items:`` from the cell's anchor
  - Cascade-resolved default font / colour from the cell's defaults
  - Inner text via the shared ``emit_slot_body`` helper used elsewhere

Out of scope for this iteration:
  - Merged cells (gridSpan / rowSpan / hMerge / vMerge)
  - Table-level style references (tblStyle)
  - Diagonal borders
"""
from __future__ import annotations

from slidecraft.importer.model import LinearGradientFill, NoFill, RadialGradientFill, SolidFill
from slidecraft.importer.shapes.model import BorderProps
from slidecraft.importer.tables.model import Table, TableCell


_PT_TO_PX = 96.0 / 72.0
_ANCHOR_ALIGN = {"t": "flex-start", "ctr": "center", "b": "flex-end"}


def _fmt(n: float) -> str:
    if n == int(n):
        return f"{int(n)}"
    return f"{n:.4g}"


def _hex(c) -> str:
    return f"#{c.r:02X}{c.g:02X}{c.b:02X}"


def _border_decl(side: str, b: BorderProps | None) -> str | None:
    """Return e.g. ``"border-top:1.5px solid #FF0000"`` or ``None`` if no border."""
    if b is None:
        return None
    width_px = b.width_pt * _PT_TO_PX
    return f"border-{side}:{_fmt(width_px)}px {b.style} {_hex(b.color)}"


def _fill_decl(fill) -> str:
    if fill is None or isinstance(fill, NoFill):
        return "background:transparent"
    if isinstance(fill, SolidFill):
        return f"background:{_hex(fill.color)}"
    if isinstance(fill, (LinearGradientFill, RadialGradientFill)) and fill.stops:
        return f"background:{_hex(fill.stops[0].color)}"
    return "background:transparent"


def _cell_style(cell: TableCell) -> str:
    parts: list[str] = []
    # CSS Grid placement — grid-row / grid-column are 1-based.
    parts.append(f"grid-row:{cell.row + 1}")
    parts.append(f"grid-column:{cell.col + 1}")

    # Fill + borders.
    parts.append(_fill_decl(cell.fill))
    for side, b in (
        ("left", cell.border_left),
        ("right", cell.border_right),
        ("top", cell.border_top),
        ("bottom", cell.border_bottom),
    ):
        decl = _border_decl(side, b)
        if decl is not None:
            parts.append(decl)

    # Padding (insets are l, t, r, b in pt; CSS order is t r b l).
    l_pt, t_pt, r_pt, b_pt = cell.insets_pt
    parts.append(
        f"padding:{_fmt(t_pt * _PT_TO_PX)}px {_fmt(r_pt * _PT_TO_PX)}px "
        f"{_fmt(b_pt * _PT_TO_PX)}px {_fmt(l_pt * _PT_TO_PX)}px"
    )

    # Vertical anchor via flex.  flex-direction:column is required:
    #
    #   (1) Multi-paragraph cells (e.g. IU agenda's "Agenda item / If
    #       necessary with sub-item") must stack VERTICALLY, not lay out as
    #       horizontal flex items.
    #   (2) Per-paragraph text-align (e.g. text-align:center on the chapter
    #       number "1") only works when each <p> takes the FULL cell width.
    #       With flex-direction:row, the <p> shrinks to fit and text-align
    #       has no width to center within. With flex-direction:column +
    #       default align-items:stretch, each <p> stretches to fill the
    #       cell horizontally so its inner text-align centers properly.
    #
    # Cross-axis (align-items) stays at the default `stretch` — children
    # become full-width.  Main-axis (justify-content) carries the PPT
    # tcPr@anchor semantics (top / center / bottom).
    parts.append("display:flex")
    parts.append("flex-direction:column")
    parts.append(f"justify-content:{_ANCHOR_ALIGN.get(cell.anchor, 'flex-start')}")

    # Default text styling (lazy import to avoid the emit-cycle issues we
    # had with shapes/emit.py).
    from slidecraft.importer.emit.layout import _para_to_css, _run_to_css
    parts.extend(_para_to_css(cell.default_para, spc_var_prefix="tbl"))
    parts.extend(_run_to_css(cell.default_run))

    parts.append("overflow:hidden")
    return "; ".join(parts)


def _cell_inner_html(cell: TableCell) -> str:
    """Render the cell's text content as inline HTML — baked, not markdown.

    Table cells live inside a Vue ``<template>`` (the generated slide layout
    ``.vue``). Markdown markers like ``**bold**`` are NOT parsed there, so
    the markdown-form output from ``emit_slot_body`` won't render
    correctly. Bake to HTML instead, paragraph-by-paragraph, mirroring the
    pattern used in :mod:`slidecraft.importer.shapes.emit` for layout /
    master text shapes:

      - Each paragraph becomes a ``<p>``, with paragraph-level deviations
        applied as inline ``style="..."``.
      - Each run is rendered via the existing HTML emitter
        (:func:`slidecraft.importer.emit.slide._emit_run_html`), producing
        ``<span>``/``<strong>``/``<em>``/``<u>``/``<s>`` wrappers with
        properly-quoted ``font-family`` and pt→px-converted ``font-size``.
      - Soft line breaks inside a run (text ``"\n"``) emit as ``<br/>``.

    Returns the joined paragraph HTML; empty string when the cell has no
    text frame or only blank paragraphs.
    """
    if cell.text_frame is None or not cell.text_frame.paragraphs:
        return ""

    from slidecraft.importer.emit.slide import (
        _emit_run_html,
        _para_deviations,
        _para_style,
        _run_deviations,
    )

    out_paras: list[str] = []
    for para in cell.text_frame.paragraphs:
        # Drop paragraphs with no actual text content (blank lines that
        # exist only to carry pPr — same filter as emit_slot_body).
        if not any(
            run.text and run.text != "\n" and run.text.strip()
            for run in para.runs
        ):
            continue

        # Render run pieces, merging adjacent runs that share a deviation
        # set (mirrors emit/slide._emit_paragraph's emit_runs).
        pieces: list[str] = []
        grouped: list[tuple[str, dict | None, str]] = []
        for run in para.runs:
            if run.text == "\n":
                grouped.append(("br", None, ""))
                continue
            devs = _run_deviations(run, cell.default_run)
            if grouped and grouped[-1][0] == "run" and grouped[-1][1] == devs:
                grouped[-1] = ("run", devs, grouped[-1][2] + run.text)
            else:
                grouped.append(("run", devs, run.text))
        for kind, devs, text in grouped:
            if kind == "br":
                pieces.append("<br/>")
            else:
                pieces.append(_emit_run_html(text, devs or {}))
        inner = "".join(pieces)

        # Paragraph-level deviations → inline <p style="...">
        para_devs = _para_deviations(para, cell.default_para)
        style = _para_style(para_devs) if para_devs else ""
        # PPT paragraphs inside table cells default to no top/bottom margin
        # — without this they get the browser <p> default (~1em above and
        # below), pushing centered text off-center.
        margin_reset = "margin:0"
        full_style = f"{margin_reset};{style}" if style else margin_reset
        out_paras.append(f'<p style="{full_style}">{inner}</p>')

    return "".join(out_paras)


def render_table(table: Table) -> str:
    """Render a :class:`Table` as a positioned CSS-grid ``<div>`` snippet.

    The result is intended for direct interpolation into a generated
    ``slide<N>.vue`` template's ``<div class="slide-root">`` body. No
    leading or trailing newline is added; the caller controls indentation.
    """
    # Outer wrapper.
    #
    # Row heights use `minmax(<h>px, max-content)` so each row can GROW to
    # fit overflowing content. PPT tables behave the same way: the row
    # height attribute is a MINIMUM; cells expand the row when their text
    # is too tall. Without minmax, our cells overflowed the fixed pixel
    # height and content was clipped (slide 4 of tmp2). Columns stay fixed
    # because PPT column widths ARE fixed (text wraps within them).
    wrapper_parts: list[str] = [
        "position:absolute",
        f"left:{_fmt(table.x_px)}px",
        f"top:{_fmt(table.y_px)}px",
        f"width:{_fmt(table.width_px)}px",
        # height stays as a minimum via min-height; the grid rows can grow.
        f"min-height:{_fmt(table.height_px)}px",
        "display:grid",
        # Explicit columns (no fr/auto — match PPT pixel widths).
        f"grid-template-columns:{' '.join(f'{_fmt(w)}px' for w in table.col_widths_px)}",
        # minmax(min, max-content) → row's at least PPT's height, can grow.
        f"grid-template-rows:{' '.join(f'minmax({_fmt(h)}px, max-content)' for h in table.row_heights_px)}",
    ]
    if table.rotation_deg != 0.0:
        wrapper_parts.append(f"transform:rotate({_fmt(table.rotation_deg)}deg)")
    wrapper_parts.append("overflow:visible")
    wrapper_style = "; ".join(wrapper_parts)

    cls = f"tbl-{table.shape_id}"
    out: list[str] = [f'<div class="{cls}" style="{wrapper_style}">']

    for row in table.cells:
        for cell in row:
            cell_style = _cell_style(cell)
            inner = _cell_inner_html(cell)
            out.append(f'  <div style="{cell_style}">{inner}</div>')

    out.append("</div>")
    return "\n".join(out)
