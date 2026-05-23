"""Walk a slide's spTree for ``<p:graphicFrame>`` table elements.

Public entry point: :func:`walk_tables`.  Filters to graphic frames whose
``<a:graphicData>`` URI matches the table namespace; ignores chart frames,
diagram frames, etc.

Reuses Layer 1 helpers for text-body parsing, fill resolution, color
resolution, and the default-property cascade. Borders are parsed by a
small local helper modelled on shapes/parse._parse_border.
"""
from __future__ import annotations

from typing import Optional

from lxml import etree

from slidecraft.importer.inheritance import (
    _parse_color,
    _x,
    resolve_placeholder,
)
from slidecraft.importer.model import (
    Fill,
    LinearGradientFill,
    NoFill,
    Paragraph,
    RadialGradientFill,
    Run,
    SolidFill,
)
from slidecraft.importer.parse import (
    _emu_to_pt,
    _parse_grad_fill,
    _parse_text_frame,
    _read_cnv_pr,
    _resolve_fill,
)
from slidecraft.importer.shapes.model import BorderProps
from slidecraft.importer.tables.model import Table, TableCell


_TABLE_URI = "http://schemas.openxmlformats.org/drawingml/2006/table"
_EMU_PER_PX = 9525


def _emu_to_px(emu: int) -> float:
    return emu / _EMU_PER_PX


# ---------------------------------------------------------------------------
# Cell fill reader
# ---------------------------------------------------------------------------

def _resolve_tcpr_fill(
    tc_pr: Optional[etree._Element],
    theme_el: Optional[etree._Element],
    clr_map: Optional[dict[str, str]],
) -> Optional[Fill]:
    """Read a table cell's fill directly from ``<a:tcPr>``.

    Table cells declare their fill on ``<a:tcPr>`` (no ``p:`` prefix), so
    :func:`slidecraft.importer.parse._resolve_fill` — which looks under
    ``<p:spPr>`` — never sees it. This helper reads:
      - ``<a:solidFill>`` (the common case; e.g. accent2 on IU's chapter-
        number boxes)
      - ``<a:gradFill>``
      - ``<a:noFill/>`` (explicit no-fill)

    Returns ``None`` when no fill element is present (caller treats this as
    "inherit"). Returns :class:`NoFill` only for an explicit ``<a:noFill/>``.
    """
    if tc_pr is None:
        return None
    # Use inheritance._parse_color via the existing _resolve_fill path for
    # solid fills — but call it on the tcPr child explicitly.
    from slidecraft.importer.inheritance import _parse_color
    no_fill = tc_pr.find(_x("a:noFill"))
    if no_fill is not None:
        return NoFill()
    solid = tc_pr.find(_x("a:solidFill"))
    if solid is not None:
        color = _parse_color(solid, theme_el, clr_map)
        if color is not None:
            return SolidFill(color=color)
    grad = tc_pr.find(_x("a:gradFill"))
    if grad is not None:
        return _parse_grad_fill(grad, theme_el, clr_map)
    return None


# ---------------------------------------------------------------------------
# Border helper
# ---------------------------------------------------------------------------

_PRST_DASH_MAP = {
    "dash": "dashed", "lgDash": "dashed", "dashDot": "dashed",
    "lgDashDot": "dashed", "lgDashDotDot": "dashed",
    "dot": "dotted", "sysDot": "dotted",
    "sysDash": "dashed", "sysDashDot": "dashed", "sysDashDotDot": "dashed",
}


def _parse_ln(
    ln_el: Optional[etree._Element],
    theme_el: Optional[etree._Element],
    clr_map: Optional[dict[str, str]],
) -> Optional[BorderProps]:
    """Parse an ``<a:lnL>`` / ``<a:lnT>`` / etc. into a BorderProps.

    Returns ``None`` for explicitly empty strokes (``<a:noFill/>``), for
    strokes with no usable solid color, or when the input element is absent.
    """
    if ln_el is None:
        return None
    if ln_el.find(_x("a:noFill")) is not None:
        return None
    w_str = ln_el.get("w")
    if w_str is None:
        return None
    try:
        width_pt = _emu_to_pt(int(w_str))
    except ValueError:
        return None
    if width_pt <= 0:
        return None
    solid = ln_el.find(_x("a:solidFill"))
    if solid is None:
        return None
    color = _parse_color(solid, theme_el, clr_map)
    if color is None:
        return None
    dash = ln_el.find(_x("a:prstDash"))
    style: str = "solid"
    if dash is not None:
        val = dash.get("val", "")
        style = _PRST_DASH_MAP.get(val, "solid")
    return BorderProps(width_pt=width_pt, color=color, style=style)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Cell parser
# ---------------------------------------------------------------------------

def _parse_cell(
    tc_el: etree._Element,
    row: int,
    col: int,
    master_tx_styles: Optional[etree._Element],
    theme_el: Optional[etree._Element],
    clr_map: Optional[dict[str, str]],
) -> TableCell:
    """Construct a :class:`TableCell` from a single ``<a:tc>`` element."""
    tx_body = tc_el.find(_x("a:txBody"))
    tc_pr = tc_el.find(_x("a:tcPr"))

    # Default run / paragraph via the OOXML otherStyle cascade — cells are
    # non-placeholder content, same conventions as shapes/parse uses.
    default_run, default_para = resolve_placeholder(
        slide_sp=tc_el,             # tc_el carries its own txBody; treated as the shape
        layout_ph=None,
        master_ph=None,
        master_tx_styles=master_tx_styles,
        theme_el=theme_el,
        ph_type=None,
        level=0,
        clr_map=clr_map,
    )

    text_frame = None
    if tx_body is not None:
        text_frame = _parse_text_frame(
            tx_body,
            default_run,
            default_para,
            theme_el,
            clr_map,
        )

    # Anchor (vertical) — defaults to top per OOXML.
    anchor = tc_pr.get("anchor") if tc_pr is not None else None
    anchor = anchor if anchor in ("t", "ctr", "b") else "t"

    # Cell margins (l, t, r, b) — PPT defaults match general bodyPr defaults.
    def _margin_pt(name: str, default_pt: float) -> float:
        if tc_pr is None:
            return default_pt
        v = tc_pr.get(name)
        if v is None:
            return default_pt
        try:
            return _emu_to_pt(int(v))
        except ValueError:
            return default_pt

    l_pt = _margin_pt("marL", 7.2)
    t_pt = _margin_pt("marT", 3.6)
    r_pt = _margin_pt("marR", 7.2)
    b_pt = _margin_pt("marB", 3.6)

    # Fill — read directly from a:tcPr (cells don't have p:spPr).
    fill = NoFill()
    if tc_pr is not None:
        fill_resolved = _resolve_tcpr_fill(tc_pr, theme_el, clr_map)
        if fill_resolved is not None:
            fill = fill_resolved

    # Edge borders.
    border_left = _parse_ln(tc_pr.find(_x("a:lnL")) if tc_pr is not None else None, theme_el, clr_map)
    border_right = _parse_ln(tc_pr.find(_x("a:lnR")) if tc_pr is not None else None, theme_el, clr_map)
    border_top = _parse_ln(tc_pr.find(_x("a:lnT")) if tc_pr is not None else None, theme_el, clr_map)
    border_bottom = _parse_ln(tc_pr.find(_x("a:lnB")) if tc_pr is not None else None, theme_el, clr_map)

    return TableCell(
        row=row,
        col=col,
        text_frame=text_frame,
        default_run=default_run,
        default_para=default_para,
        anchor=anchor,  # type: ignore[arg-type]
        insets_pt=(l_pt, t_pt, r_pt, b_pt),
        fill=fill,
        border_left=border_left,
        border_right=border_right,
        border_top=border_top,
        border_bottom=border_bottom,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def walk_tables(
    slide_part,
    master_tx_styles: Optional[etree._Element],
    theme_el: Optional[etree._Element],
    clr_map: Optional[dict[str, str]],
    starting_order_index: int = 0,
) -> list[Table]:
    """Extract every table from a slide's ``<p:spTree>``.

    Walks only the slide's own spTree — layout/master tables are not
    inherited (PPT renders tables only at the level they're declared).
    Tables on the layout or master are extremely rare and out of scope.

    ``starting_order_index`` is incremented monotonically across the
    returned tables so emit can interleave them with placeholders /
    pictures / text shapes via the shared ``order_index`` field.
    """
    slide_root = slide_part._element
    c_sld = slide_root.find(_x("p:cSld"))
    if c_sld is None:
        return []
    sp_tree = c_sld.find(_x("p:spTree"))
    if sp_tree is None:
        return []

    out: list[Table] = []
    order_index = starting_order_index

    for gf in sp_tree.findall(_x("p:graphicFrame")):
        graphic = gf.find(_x("a:graphic"))
        if graphic is None:
            continue
        gdata = graphic.find(_x("a:graphicData"))
        if gdata is None:
            continue
        if gdata.get("uri") != _TABLE_URI:
            continue  # Charts, diagrams, etc. — handled elsewhere or skipped.
        tbl = gdata.find(_x("a:tbl"))
        if tbl is None:
            continue

        # Identity.
        nv_gf_pr = gf.find(_x("p:nvGraphicFramePr"))
        shape_id, _alt = _read_cnv_pr(nv_gf_pr)
        name = ""
        if nv_gf_pr is not None:
            c_nv_pr = nv_gf_pr.find(_x("p:cNvPr"))
            if c_nv_pr is not None:
                name = c_nv_pr.get("name") or ""

        # Position (graphicFrame uses <p:xfrm>, not <a:xfrm>).
        xfrm = gf.find(_x("p:xfrm"))
        x_px = y_px = w_px = h_px = 0.0
        rotation_deg = 0.0
        if xfrm is not None:
            off = xfrm.find(_x("a:off"))
            ext = xfrm.find(_x("a:ext"))
            if off is not None:
                try:
                    x_px = _emu_to_px(int(off.get("x", "0")))
                    y_px = _emu_to_px(int(off.get("y", "0")))
                except ValueError:
                    pass
            if ext is not None:
                try:
                    w_px = _emu_to_px(int(ext.get("cx", "0")))
                    h_px = _emu_to_px(int(ext.get("cy", "0")))
                except ValueError:
                    pass
            rot_str = xfrm.get("rot")
            if rot_str is not None:
                try:
                    rotation_deg = int(rot_str) / 60000.0
                except ValueError:
                    pass

        # Grid columns (widths in EMU → px).
        col_widths_px: list[float] = []
        tbl_grid = tbl.find(_x("a:tblGrid"))
        if tbl_grid is not None:
            for gc in tbl_grid.findall(_x("a:gridCol")):
                w = gc.get("w")
                if w is not None:
                    try:
                        col_widths_px.append(_emu_to_px(int(w)))
                    except ValueError:
                        col_widths_px.append(0.0)

        # Rows + cells.
        row_heights_px: list[float] = []
        cells_grid: list[list[TableCell]] = []
        for row_idx, tr in enumerate(tbl.findall(_x("a:tr"))):
            h = tr.get("h")
            if h is not None:
                try:
                    row_heights_px.append(_emu_to_px(int(h)))
                except ValueError:
                    row_heights_px.append(0.0)
            else:
                row_heights_px.append(0.0)
            row_cells: list[TableCell] = []
            for col_idx, tc in enumerate(tr.findall(_x("a:tc"))):
                # Skip cells that are part of a merge (hMerge / vMerge) — v1
                # doesn't span across; the master cell of the merge still
                # carries the visible content.
                if tc.get("hMerge") == "1" or tc.get("vMerge") == "1":
                    continue
                row_cells.append(_parse_cell(
                    tc, row_idx, col_idx,
                    master_tx_styles, theme_el, clr_map,
                ))
            cells_grid.append(row_cells)

        out.append(Table(
            shape_id=shape_id,
            name=name,
            x_px=x_px,
            y_px=y_px,
            width_px=w_px,
            height_px=h_px,
            rotation_deg=rotation_deg,
            col_widths_px=col_widths_px,
            row_heights_px=row_heights_px,
            cells=cells_grid,
            order_index=order_index,
        ))
        order_index += 1

    return out
