"""Walk a slide's effective spTree (master, layout, slide) for non-placeholder text shapes.

Scope: ``<p:sp>`` elements *without* a ``<p:ph>`` child that carry a
``<p:txBody>`` with at least one ``<a:t>`` containing non-whitespace text.
These are the template's decorative text boxes and any slide-level text boxes
the author added outside the placeholder system.

Cascade behaviour:
  - Master segment is suppressed when either the layout root
    (``<p:sldLayout showMasterSp="0"/>``) or the slide root
    (``<p:sld showMasterSp="0"/>``) sets the suppression flag, per the OOXML
    spec.
  - Property defaults (font / paragraph) are produced by reusing
    :func:`slidecraft.importer.inheritance.resolve_placeholder` with
    ``ph_type=None`` so the cascade flows through the master's
    ``<a:otherStyle>`` rather than ``<a:titleStyle>`` /
    ``<a:bodyStyle>``. ``layout_ph`` and ``master_ph`` are both ``None``
    because non-placeholder shapes have no cross-level cascade partner.

This module imports private helpers (``_emu_to_pt``, ``_parse_text_frame``,
``_resolve_fill``, ``_get_sp_position``, ``_read_cnv_pr``) from
``slidecraft.importer.parse``. That coupling is intentional — those helpers
are tested and stable, and Layer 1's polish session is locked out of
``parse.py``. Promoting them to public names would require touching that
file.
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
    NoFill,
    Paragraph,
    Run,
)
from slidecraft.importer.parse import (
    _emu_to_pt,
    _get_sp_position,
    _parse_text_frame,
    _read_cnv_pr,
    _resolve_fill,
)
from slidecraft.importer.pictures.geometry import cust_geom_to_svg_path
from slidecraft.importer.shapes.model import BorderProps, ShapeGeometry, TextShape


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------

def _is_placeholder(sp_el: etree._Element) -> bool:
    """Return True if ``sp_el`` is a placeholder shape (has ``<p:ph>``)."""
    nv_sp_pr = sp_el.find(_x("p:nvSpPr"))
    if nv_sp_pr is None:
        return False
    nv_pr = nv_sp_pr.find(_x("p:nvPr"))
    if nv_pr is None:
        return False
    return nv_pr.find(_x("p:ph")) is not None


def _has_nonwhitespace_text(tx_body: etree._Element) -> bool:
    """Return True if any ``<a:t>`` descendant carries non-whitespace text."""
    for t_el in tx_body.iter(_x("a:t")):
        if t_el.text and t_el.text.strip():
            return True
    return False


def _is_visible(
    sp_el: etree._Element,
    has_text: bool,
    fill,
    border: Optional[BorderProps],
) -> bool:
    """Return True if the shape contributes something visible to the slide.

    A shape is considered visible if any of the following hold:
      - It has non-whitespace text content, OR
      - It has a visible solid/gradient fill (anything other than NoFill /
        no-fill / inherit-no-fill), OR
      - It has a border / stroke.

    Pure decorative rectangles like the IU template's "Rechteck 16" pass on
    border alone; empty text boxes with no chrome are filtered out.
    """
    if has_text:
        return True
    if border is not None:
        return True
    # Treat anything that's not NoFill as visible. The fill helper returns
    # None when the shape doesn't declare a fill at all; we treat that as
    # invisible since OOXML "no fill set" inherits → typically transparent.
    if fill is not None:
        from slidecraft.importer.model import NoFill
        if not isinstance(fill, NoFill):
            return True
    return False


def _parse_geometry(
    sp_el: etree._Element,
    width_px: float,
    height_px: float,
) -> Optional[ShapeGeometry]:
    """Extract `<a:prstGeom>` / `<a:custGeom>` into a :class:`ShapeGeometry`.

    Returns ``None`` if the shape has no explicit geometry, or if the
    geometry is a plain ``prstGeom prst="rect"`` with no adjusts — both
    cases fall through to the simple-CSS-div fast path in emit.

    custGeom paths are materialised here against ``width_px`` /
    ``height_px`` since the OOXML coordinate space is path-local; the
    resulting SVG ``d=""`` string is suitable for direct inline use.
    """
    sp_pr = sp_el.find(_x("p:spPr"))
    if sp_pr is None:
        return None

    cust = sp_pr.find(_x("a:custGeom"))
    if cust is not None:
        path = cust_geom_to_svg_path(cust, width_px, height_px)
        if path is None:
            return None
        return ShapeGeometry(preset=None, svg_path=path)

    prst = sp_pr.find(_x("a:prstGeom"))
    if prst is None:
        return None
    preset_name = prst.get("prst")
    if not preset_name:
        return None

    av_lst_el = prst.find(_x("a:avLst"))
    adjusts: Optional[dict[str, int]] = None
    if av_lst_el is not None:
        adjusts = {}
        for gd in av_lst_el.findall(_x("a:gd")):
            gd_name = gd.get("name")
            fmla = gd.get("fmla", "")
            if gd_name and fmla.startswith("val "):
                try:
                    adjusts[gd_name] = int(fmla[4:])
                except ValueError:
                    pass
        if not adjusts:
            adjusts = None

    if preset_name == "rect" and adjusts is None:
        return None  # Fast path: simple rect renders as CSS div.

    return ShapeGeometry(preset=preset_name, preset_adjusts=adjusts)


def _is_degenerate_size(sp_el: etree._Element) -> bool:
    """Return True if the shape's bbox has cx=0 or cy=0.

    The IU master template carries three zero-size text-box artifacts that
    must be filtered out. Only the slide-level ``<a:ext>`` is inspected —
    non-placeholder shapes don't cascade geometry from their level peers.
    """
    sp_pr = sp_el.find(_x("p:spPr"))
    if sp_pr is None:
        return False
    xfrm = sp_pr.find(_x("a:xfrm"))
    if xfrm is None:
        # No xfrm at all → treat as degenerate (can't position it)
        return True
    ext = xfrm.find(_x("a:ext"))
    if ext is None:
        return True
    try:
        cx = int(ext.get("cx", "0"))
        cy = int(ext.get("cy", "0"))
    except ValueError:
        return True
    return cx == 0 or cy == 0


# ---------------------------------------------------------------------------
# Border parser
# ---------------------------------------------------------------------------

_PRST_DASH_MAP = {
    "dash": "dashed",
    "lgDash": "dashed",
    "dashDot": "dashed",
    "lgDashDot": "dashed",
    "lgDashDotDot": "dashed",
    "dot": "dotted",
    "sysDot": "dotted",
    "sysDash": "dashed",
    "sysDashDot": "dashed",
    "sysDashDotDot": "dashed",
}


def _parse_border(
    sp_el: etree._Element,
    theme_el: Optional[etree._Element],
    clr_map: Optional[dict[str, str]],
) -> Optional[BorderProps]:
    """Parse ``<p:spPr>/<a:ln>`` into a :class:`BorderProps` or ``None``.

    Returns ``None`` if there is no ``<a:ln>``, if it has no width attribute,
    or if it has no usable solid-fill color. Only ``<a:solidFill>`` strokes
    are rendered; gradient strokes fall through to ``None``.
    """
    sp_pr = sp_el.find(_x("p:spPr"))
    if sp_pr is None:
        return None
    ln = sp_pr.find(_x("a:ln"))
    if ln is None:
        return None

    # Explicit no-fill stroke means "no border"
    if ln.find(_x("a:noFill")) is not None:
        return None

    w_str = ln.get("w")
    if w_str is None:
        return None
    try:
        width_pt = _emu_to_pt(int(w_str))
    except ValueError:
        return None
    if width_pt <= 0:
        return None

    solid = ln.find(_x("a:solidFill"))
    if solid is None:
        return None
    color = _parse_color(solid, theme_el, clr_map)
    if color is None:
        return None

    dash = ln.find(_x("a:prstDash"))
    style: str = "solid"
    if dash is not None:
        val = dash.get("val", "")
        style = _PRST_DASH_MAP.get(val, "solid")

    return BorderProps(width_pt=width_pt, color=color, style=style)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# spTree access helpers
# ---------------------------------------------------------------------------

def _get_sp_tree(part_el: Optional[etree._Element]) -> Optional[etree._Element]:
    """Return the ``<p:spTree>`` child of a slide / layout / master root element."""
    if part_el is None:
        return None
    c_sld = part_el.find(_x("p:cSld"))
    if c_sld is None:
        return None
    return c_sld.find(_x("p:spTree"))


def _show_master_sp(root_el: Optional[etree._Element]) -> Optional[str]:
    """Read the ``showMasterSp`` attribute on a slide / slideLayout root, or ``None``."""
    if root_el is None:
        return None
    return root_el.get("showMasterSp")


# ---------------------------------------------------------------------------
# Shape → TextShape
# ---------------------------------------------------------------------------

def _build_text_shape(
    sp_el: etree._Element,
    source: str,
    order_index: int,
    master_tx_styles: Optional[etree._Element],
    theme_el: Optional[etree._Element],
    clr_map: Optional[dict[str, str]],
) -> Optional[TextShape]:
    """Construct a :class:`TextShape` for a non-placeholder ``<p:sp>``.

    Returns ``None`` if the shape fails the visibility filter (no text AND
    no visible chrome) — the placeholder / degenerate-size gates are
    handled in the caller.
    """
    nv_sp_pr = sp_el.find(_x("p:nvSpPr"))
    # _read_cnv_pr returns (id, alt_text from descr/title) — NOT the shape's
    # display name. Read @name directly for the debug field.
    shape_id, _alt_text = _read_cnv_pr(nv_sp_pr)
    name = ""
    if nv_sp_pr is not None:
        c_nv_pr = nv_sp_pr.find(_x("p:cNvPr"))
        if c_nv_pr is not None:
            name = c_nv_pr.get("name") or ""

    x_px, y_px, w_px, h_px, rotation_deg = _get_sp_position(sp_el)

    fill = _resolve_fill(sp_el, theme_el, clr_map, layout_sp=None)
    border = _parse_border(sp_el, theme_el, clr_map)

    # Visibility filter — must have text content OR visible chrome.
    tx_body = sp_el.find(_x("p:txBody"))
    has_text = tx_body is not None and _has_nonwhitespace_text(tx_body)
    if not _is_visible(sp_el, has_text, fill, border):
        return None

    # Defaults via the OOXML-spec-correct otherStyle cascade.
    # include_slide_paragraph=False: text shapes may come from layout/master
    # spTrees too, and their runs carry explicit rPr that the per-run diff
    # already preserves — defaults stay lstStyle-only here.
    default_run, default_para = resolve_placeholder(
        slide_sp=sp_el,
        layout_ph=None,
        master_ph=None,
        master_tx_styles=master_tx_styles,
        theme_el=theme_el,
        ph_type=None,
        level=0,
        clr_map=clr_map,
        include_slide_paragraph=False,
    )

    # Body — only parse when text is present. Decorative-only shapes don't
    # need a text_frame; emit treats text_frame=None as "render chrome only".
    text_frame = None
    if has_text and tx_body is not None:
        text_frame = _parse_text_frame(
            tx_body,
            default_run,
            default_para,
            theme_el,
            clr_map,
            layout_tx_body=None,
        )

    # Geometry — None means plain rectangle (renders as a CSS div); a
    # ShapeGeometry with preset/svg_path drives inline-SVG rendering.
    geometry = _parse_geometry(sp_el, w_px, h_px)

    # PPT renders strokes centered on the geometric edge (half inside, half
    # outside). CSS `border` always paints fully outside (content-box) or
    # fully inside (border-box), so a CSS-div with a thick border ends up
    # ~border/2 px offset from PPT. Forcing the SVG path for any stroked
    # rect routes the stroke through SVG `stroke-width`, which IS centered
    # on the path — matching PPT pixel-for-pixel.
    if geometry is None and border is not None:
        geometry = ShapeGeometry(preset="rect")

    return TextShape(
        source=source,  # type: ignore[arg-type]
        shape_id=shape_id,
        name=name,
        x_px=x_px,
        y_px=y_px,
        width_px=w_px,
        height_px=h_px,
        rotation_deg=rotation_deg,
        fill=fill if fill is not None else NoFill(),
        border=border,
        opacity=1.0,  # v1: opacity is not derived from <a:solidFill>/<a:alpha>
        text_frame=text_frame,
        default_run=default_run,
        default_para=default_para,
        geometry=geometry,
        order_index=order_index,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def walk_text_shapes(
    slide_part,
    master_tx_styles: Optional[etree._Element],
    theme_el: Optional[etree._Element],
    clr_map: Optional[dict[str, str]],
    starting_order_index: int = 0,
) -> list[TextShape]:
    """Collect non-placeholder text shapes from a slide's effective spTree.

    Walks three segments in document / z-order (master → layout → slide).
    The master segment is suppressed if either the slideLayout root or the
    slide root carries ``showMasterSp="0"``, matching OOXML semantics.

    Parameters
    ----------
    slide_part:
        A ``python-pptx`` slide part. Provides ``_element`` (the ``<p:sld>``
        root) plus ``slide_layout`` and ``slide_layout.slide_master`` for
        the upstream segments.
    master_tx_styles:
        ``<p:txStyles>`` element from the master, as produced by
        ``parse._get_master_tx_styles``. Passed through to the cascade
        resolver — non-placeholder shapes use the ``<a:otherStyle>`` branch.
    theme_el:
        ``<a:theme>`` root from the theme part associated with the master.
    clr_map:
        Master ``<p:clrMap>`` as a ``{logical: scheme}`` dict, used for
        scheme-color resolution.
    starting_order_index:
        First ``order_index`` to assign. Each shape that passes the filters
        increments this monotonically across all three segments. Master
        shapes receive the lowest indices and slide shapes the highest, so
        the emit-time sort produces bottom-to-top z-order.

    Returns
    -------
    list[TextShape]
        Shapes in walk order (master first, slide last). The list is *not*
        re-sorted; the input order already matches ``order_index``.
    """
    # Resolve the three roots and their spTrees.
    layout = slide_part.slide_layout
    master = layout.slide_master

    slide_root = slide_part._element
    layout_root = layout._element
    master_root = master._element

    slide_sp_tree = _get_sp_tree(slide_root)
    layout_sp_tree = _get_sp_tree(layout_root)
    master_sp_tree = _get_sp_tree(master_root)

    # Suppression: either layout or slide can hide master shapes.
    slide_show = _show_master_sp(slide_root)
    layout_show = _show_master_sp(layout_root)
    suppress_master = slide_show == "0" or layout_show == "0"

    segments: list[tuple[str, Optional[etree._Element]]] = []
    if not suppress_master:
        segments.append(("master", master_sp_tree))
    segments.append(("layout", layout_sp_tree))
    segments.append(("slide", slide_sp_tree))

    out: list[TextShape] = []
    order_index = starting_order_index

    for source, sp_tree in segments:
        if sp_tree is None:
            continue
        for sp_el in sp_tree.findall(_x("p:sp")):
            # Filter: skip placeholders (Layer 1's territory)
            if _is_placeholder(sp_el):
                continue
            # Filter: skip degenerate-size stubs (IU template carries these)
            if _is_degenerate_size(sp_el):
                continue

            # _build_text_shape applies the visibility filter (text OR
            # visible chrome) and returns None on rejection.
            shape = _build_text_shape(
                sp_el,
                source,
                order_index,
                master_tx_styles,
                theme_el,
                clr_map,
            )
            if shape is None:
                continue
            out.append(shape)
            order_index += 1

    return out
