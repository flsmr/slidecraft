"""PPTX parser — Stage 0 of the PPTX → Slidev pipeline.

parse(pptx_path) → Presentation

Parses text-bearing placeholders only (v1 scope).  Drops to lxml for properties
that python-pptx doesn't surface (bodyPr insets, normAutofit fontScale, line/para
spacing, bullet chars, etc.).
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from lxml import etree
import pptx
from pptx import Presentation as PptxPresentation
from pptx.util import Emu

from slidecraft.importer.model import (
    Fill,
    GradientStop,
    LinearGradientFill,
    NoFill,
    Paragraph,
    Picture,
    Placeholder,
    Presentation,
    RGB,
    RadialGradientFill,
    Run,
    Slide,
    SolidFill,
    TextFrame,
)
from slidecraft.importer.inheritance import (
    _extract_rpr,
    _extract_ppr,
    _find,
    _get,
    _parse_color,
    _x,
    diff_run,
    diff_para,
    get_clr_map,
    resolve_placeholder,
)
from slidecraft.importer.pictures.effects import parse_effects

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_EMU_PER_PX = 9525          # 914400 EMU/inch ÷ 96 px/inch
_EMU_PER_PT = 12700         # 914400 EMU/inch ÷ 72 pt/inch

# Placeholder types considered text-bearing
_TEXT_PH_TYPES = {
    "title", "ctrTitle", "body", "subTitle", "dt", "ftr", "sldNum", None
}

# ---------------------------------------------------------------------------
# EMU converters
# ---------------------------------------------------------------------------

def _emu_to_px(emu: int) -> float:
    return emu / _EMU_PER_PX


def _emu_to_pt(emu: int) -> float:
    return emu / _EMU_PER_PT


# ---------------------------------------------------------------------------
# Fill resolver
# ---------------------------------------------------------------------------

def _resolve_fill(
    sp_el: etree._Element,
    theme_el: Optional[etree._Element],
    clr_map: Optional[dict[str, str]] = None,
    layout_sp: Optional[etree._Element] = None,
) -> Fill:
    """Resolve placeholder fill using a slide → layout cascade.

    For placeholder shapes the OOXML spec says that if the slide-level <p:spPr>
    contains no fill directive (no <a:solidFill>, <a:gradFill>, or <a:noFill>),
    the fill should be inherited from the corresponding layout placeholder.  We
    implement that two-level cascade here so that layout-defined solid fills
    (like the ``bg2`` band boxes on IU slide 1) appear correctly.
    """
    def _read_fill_from_sp_pr(sp_pr: Optional[etree._Element]) -> Optional[Fill]:
        """Return a Fill or None if sp_pr carries no fill directive."""
        if sp_pr is None:
            return None
        if sp_pr.find(_x("a:noFill")) is not None:
            return NoFill()
        solid = sp_pr.find(_x("a:solidFill"))
        if solid is not None:
            color = _parse_color(solid, theme_el, clr_map)
            if color:
                return SolidFill(color)
        grad = sp_pr.find(_x("a:gradFill"))
        if grad is not None:
            return _parse_grad_fill(grad, theme_el, clr_map)
        return None  # no directive found

    # Level 1: slide-level shape
    slide_sp_pr = sp_el.find(_x("p:spPr"))
    fill = _read_fill_from_sp_pr(slide_sp_pr)
    if fill is not None:
        return fill

    # Level 2: layout placeholder (cascade fallback)
    if layout_sp is not None:
        layout_sp_pr = layout_sp.find(_x("p:spPr"))
        fill = _read_fill_from_sp_pr(layout_sp_pr)
        if fill is not None:
            return fill

    return NoFill()


def _parse_grad_fill(
    grad_el: etree._Element,
    theme_el: Optional[etree._Element] = None,
    clr_map: Optional[dict[str, str]] = None,
) -> Fill:
    """Parse <a:gradFill> into LinearGradientFill or RadialGradientFill."""
    stops: list[GradientStop] = []
    gs_lst = grad_el.find(_x("a:gsLst"))
    if gs_lst is not None:
        for gs in gs_lst.findall(_x("a:gs")):
            pos_str = gs.get("pos", "0")
            pos = int(pos_str) / 100000.0
            solid = gs.find(_x("a:solidFill"))
            color = _parse_color(solid, theme_el, clr_map) if solid is not None else RGB(0, 0, 0)
            if color:
                stops.append(GradientStop(position=pos, color=color))

    # Linear vs radial
    lin = grad_el.find(_x("a:lin"))
    path_el = grad_el.find(_x("a:path"))
    if lin is not None:
        ang_str = lin.get("ang", "0")
        # PPT angle is in 60000ths of a degree, measured clockwise from the top
        angle_deg = int(ang_str) / 60000.0
        return LinearGradientFill(angle_deg=angle_deg, stops=stops)
    elif path_el is not None and path_el.get("path") == "circle":
        return RadialGradientFill(stops=stops)
    else:
        return LinearGradientFill(angle_deg=0.0, stops=stops)


# ---------------------------------------------------------------------------
# Slide background resolver
# ---------------------------------------------------------------------------

def _resolve_background(
    slide_part,
    pptx_prs: PptxPresentation,
    theme_el: Optional[etree._Element],
    clr_map: Optional[dict[str, str]] = None,
) -> Fill:
    """Walk slide → layout → master for <p:bg> / <p:bgRef> to find the background fill."""
    for part in [slide_part, slide_part.slide_layout, slide_part.slide_layout.slide_master]:
        sp_tree = part._element.find(_x("p:cSld"))
        if sp_tree is None:
            continue
        bg = sp_tree.find(_x("p:bg"))
        if bg is None:
            continue
        bg_pr = bg.find(_x("p:bgPr"))
        if bg_pr is not None:
            no_fill = bg_pr.find(_x("a:noFill"))
            if no_fill is not None:
                return NoFill()
            solid = bg_pr.find(_x("a:solidFill"))
            if solid is not None:
                color = _parse_color(solid, theme_el, clr_map)
                if color:
                    return SolidFill(color)
            grad = bg_pr.find(_x("a:gradFill"))
            if grad is not None:
                return _parse_grad_fill(grad, theme_el, clr_map)
        # bgRef references a fill style in the theme — not resolved in v1
        bg_ref = bg.find(_x("p:bgRef"))
        if bg_ref is not None:
            solid = bg_ref.find(_x("a:solidFill"))
            if solid is None:
                # srgbClr directly under bgRef (unusual but valid)
                pass
            else:
                color = _parse_color(solid, theme_el, clr_map)
                if color:
                    return SolidFill(color)
    return NoFill()


# ---------------------------------------------------------------------------
# TextFrame parser
# ---------------------------------------------------------------------------

def _parse_text_frame(
    tx_body: etree._Element,
    default_run: Run,
    default_para: Paragraph,
    theme_el: Optional[etree._Element] = None,
    clr_map: Optional[dict[str, str]] = None,
    layout_tx_body: Optional[etree._Element] = None,
) -> TextFrame:
    """Parse <p:txBody> into a TextFrame, diffing each run/paragraph against the defaults.

    bodyPr attributes (anchor, insets, rotation, autofit) cascade slide → layout
    per OOXML semantics: a missing or unset attribute on the slide-level bodyPr
    inherits from the layout's bodyPr. Hardcoded OOXML defaults apply only when
    neither slide nor layout sets the attribute.
    """
    # Collect slide- and layout-level bodyPr (either may be None or empty).
    slide_body_pr = tx_body.find(_x("a:bodyPr"))
    layout_body_pr = (
        layout_tx_body.find(_x("a:bodyPr")) if layout_tx_body is not None else None
    )

    def _attr_cascade(name: str) -> Optional[str]:
        """Return the first non-None occurrence of bodyPr@name across slide → layout."""
        for src in (slide_body_pr, layout_body_pr):
            if src is not None:
                v = src.get(name)
                if v is not None:
                    return v
        return None

    def _child_cascade(local_name: str) -> Optional[etree._Element]:
        """Return the first child element with the given local name across slide → layout."""
        for src in (slide_body_pr, layout_body_pr):
            if src is not None:
                el = src.find(_x(f"a:{local_name}"))
                if el is not None:
                    return el
        return None

    anchor_val = _attr_cascade("anchor") or "t"
    anchor = anchor_val  # "t", "ctr", "b"

    l_ins = _attr_cascade("lIns")
    t_ins = _attr_cascade("tIns")
    r_ins = _attr_cascade("rIns")
    b_ins = _attr_cascade("bIns")
    # Hardcoded OOXML defaults: lIns=91440, tIns=45720, rIns=91440, bIns=45720
    l_pt = _emu_to_pt(int(l_ins)) if l_ins is not None else 7.2
    t_pt = _emu_to_pt(int(t_ins)) if t_ins is not None else 3.6
    r_pt = _emu_to_pt(int(r_ins)) if r_ins is not None else 7.2
    b_pt = _emu_to_pt(int(b_ins)) if b_ins is not None else 3.6
    insets_pt = (l_pt, t_pt, r_pt, b_pt)

    rot = _attr_cascade("rot")
    rotation_deg = int(rot) / 60000.0 if rot is not None else 0.0

    norm_auto = _child_cascade("normAutofit")
    autofit_font_scale = 1.0
    if norm_auto is not None:
        fs_str = norm_auto.get("fontScale", "100000")
        autofit_font_scale = int(fs_str) / 100000.0

    # Parse paragraphs
    paragraphs: list[Paragraph] = []
    for p_el in tx_body.findall(_x("a:p")):
        para = _parse_paragraph(p_el, default_run, default_para, theme_el, clr_map)
        paragraphs.append(para)

    return TextFrame(
        paragraphs=paragraphs,
        anchor=anchor,  # type: ignore[arg-type]
        insets_pt=insets_pt,
        rotation_deg=rotation_deg,
        autofit_font_scale=autofit_font_scale,
    )


def _parse_paragraph(
    p_el: etree._Element,
    default_run: Run,
    default_para: Paragraph,
    theme_el: Optional[etree._Element] = None,
    clr_map: Optional[dict[str, str]] = None,
) -> Paragraph:
    """Parse a single <a:p> element, returning a Paragraph with diffed properties."""
    ppr_el = p_el.find(_x("a:pPr"))
    para_props = _extract_ppr(ppr_el)

    # Level (indent level, 0-based)
    level = 0
    if ppr_el is not None:
        lvl_str = ppr_el.get("lvl", "0")
        level = int(lvl_str)

    # Build diffed paragraph (only emit fields that differ from default)
    diffed = diff_para(para_props, default_para)
    diffed.level = level

    # Parse runs
    runs: list[Run] = []
    for r_el in p_el.findall(_x("a:r")):
        t_el = r_el.find(_x("a:t"))
        text = t_el.text or "" if t_el is not None else ""
        rpr_el = r_el.find(_x("a:rPr"))
        run_props = _extract_rpr(rpr_el)
        run_props.text = text
        diffed_run = diff_run(run_props, default_run)
        diffed_run.text = text
        runs.append(diffed_run)

    # Handle line breaks <a:br/> and field runs <a:fld/> — emit in document order
    # <a:fld> elements (date, slide number, footer) contain <a:t> with their
    # auto-populated text; we emit the field value as a regular run.
    runs_ordered: list[Run] = []
    for child in p_el:
        tag = etree.QName(child.tag).localname
        if tag == "r":
            t_el = child.find(_x("a:t"))
            text = t_el.text or "" if t_el is not None else ""
            rpr_el = child.find(_x("a:rPr"))
            run_props = _extract_rpr(rpr_el, theme_el, clr_map)
            run_props.text = text
            diffed_run = diff_run(run_props, default_run)
            diffed_run.text = text
            runs_ordered.append(diffed_run)
        elif tag == "fld":
            # Field element: <a:fld type="slidenum"|"datetime1"|…>
            # Extract the current field value from <a:t>, and run props from <a:rPr>.
            t_el = child.find(_x("a:t"))
            text = t_el.text or "" if t_el is not None else ""
            rpr_el = child.find(_x("a:rPr"))
            run_props = _extract_rpr(rpr_el, theme_el, clr_map)
            run_props.text = text
            diffed_run = diff_run(run_props, default_run)
            diffed_run.text = text
            runs_ordered.append(diffed_run)
        elif tag == "br":
            runs_ordered.append(Run(text="\n"))

    diffed.runs = runs_ordered if runs_ordered else runs
    return diffed


# ---------------------------------------------------------------------------
# Placeholder locator helpers
# ---------------------------------------------------------------------------

def _ph_idx(sp_el: etree._Element) -> Optional[int]:
    """Return the idx of a <p:sp>'s placeholder, or None if not a placeholder."""
    nv_sp_pr = sp_el.find(_x("p:nvSpPr"))
    if nv_sp_pr is None:
        return None
    nv_pr = nv_sp_pr.find(_x("p:nvPr"))
    if nv_pr is None:
        return None
    ph = nv_pr.find(_x("p:ph"))
    if ph is None:
        return None
    return int(ph.get("idx", "0"))


def _ph_type(sp_el: etree._Element) -> Optional[str]:
    """Return the type attribute of a placeholder (may be None for body/generic)."""
    nv_sp_pr = sp_el.find(_x("p:nvSpPr"))
    if nv_sp_pr is None:
        return None
    nv_pr = nv_sp_pr.find(_x("p:nvPr"))
    if nv_pr is None:
        return None
    ph = nv_pr.find(_x("p:ph"))
    if ph is None:
        return None
    return ph.get("type")  # e.g. "title", "body", None


def _ph_has_text(sp_el: etree._Element) -> bool:
    """Return True if the <p:sp> has a <p:txBody> with at least one <a:t> with text."""
    tx_body = sp_el.find(_x("p:txBody"))
    if tx_body is None:
        return False
    for t_el in tx_body.iter(_x("a:t")):
        if t_el.text:
            return True
    return False


def _txbody_is_empty(tx_body: etree._Element) -> bool:
    """Return True if all <a:t> runs in a txBody are missing or contain only whitespace."""
    for t_el in tx_body.iter(_x("a:t")):
        if t_el.text and t_el.text.strip():
            return False
    return True


def _layout_ph_has_custom_prompt(layout_sp: etree._Element) -> bool:
    """Return True if the layout <p:sp> has hasCustomPrompt='1' on its <p:ph>."""
    nv_sp_pr = layout_sp.find(_x("p:nvSpPr"))
    if nv_sp_pr is None:
        return False
    nv_pr = nv_sp_pr.find(_x("p:nvPr"))
    if nv_pr is None:
        return False
    ph = nv_pr.find(_x("p:ph"))
    if ph is None:
        return False
    return ph.get("hasCustomPrompt") == "1"


def _get_sp_position(sp_el: etree._Element) -> tuple[float, float, float, float, float]:
    """Return (x_px, y_px, width_px, height_px, rotation_deg) from <p:spPr><a:xfrm>."""
    sp_pr = sp_el.find(_x("p:spPr"))
    if sp_pr is None:
        return 0.0, 0.0, 0.0, 0.0, 0.0
    xfrm = sp_pr.find(_x("a:xfrm"))
    if xfrm is None:
        return 0.0, 0.0, 0.0, 0.0, 0.0
    off = xfrm.find(_x("a:off"))
    ext = xfrm.find(_x("a:ext"))
    x = _emu_to_px(int(off.get("x", "0"))) if off is not None else 0.0
    y = _emu_to_px(int(off.get("y", "0"))) if off is not None else 0.0
    w = _emu_to_px(int(ext.get("cx", "0"))) if ext is not None else 0.0
    h = _emu_to_px(int(ext.get("cy", "0"))) if ext is not None else 0.0
    rot = int(xfrm.get("rot", "0")) / 60000.0
    return x, y, w, h, rot


def _find_layout_sp(layout_part, idx: int) -> Optional[etree._Element]:
    """Find the <p:sp> in a slideLayout that has <p:ph idx='idx'>."""
    sp_tree = layout_part._element.find(_x("p:cSld"))
    if sp_tree is None:
        return None
    sp_tree = sp_tree.find(_x("p:spTree"))
    if sp_tree is None:
        return None
    for sp in sp_tree.findall(_x("p:sp")):
        if _ph_idx(sp) == idx:
            return sp
    return None


def _find_master_sp(master_part, ph_type: Optional[str], idx: int) -> Optional[etree._Element]:
    """Find the <p:sp> in a slideMaster by ph type (preferred) or idx."""
    sp_tree = master_part._element.find(_x("p:cSld"))
    if sp_tree is None:
        return None
    sp_tree = sp_tree.find(_x("p:spTree"))
    if sp_tree is None:
        return None

    # First pass: match by type
    if ph_type is not None:
        for sp in sp_tree.findall(_x("p:sp")):
            if _ph_type(sp) == ph_type:
                return sp

    # Second pass: match by idx
    for sp in sp_tree.findall(_x("p:sp")):
        if _ph_idx(sp) == idx:
            return sp

    return None


def _get_master_tx_styles(master_part) -> Optional[etree._Element]:
    """Return the <p:txStyles> element from a slide master part."""
    return master_part._element.find(_x("p:txStyles"))


def _get_theme_el(master) -> Optional[etree._Element]:
    """Return the <a:theme> element from the theme part associated with a slide master."""
    try:
        part = master.part if hasattr(master, "part") else master
        theme_part = part.part_related_by(
            "http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme"
        )
        if hasattr(theme_part, "_element"):
            return theme_part._element
        return etree.fromstring(theme_part.blob)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Picture helpers (P4)
# ---------------------------------------------------------------------------

def _resolve_blip_asset_ref(blip_fill_el: Optional[etree._Element], part) -> Optional[str]:
    """Resolve a ``<a:blipFill>``'s embedded image to a media basename.

    Reads ``<a:blip r:embed="rIdN"/>`` from *blip_fill_el* and follows the
    relationship on *part* to find the target media partname. Returns the
    basename only (e.g. ``"image1.png"``) so it matches what
    :func:`pictures.extract.extract_pictures` writes to
    ``deck/public/assets/``.

    Returns ``None`` if *blip_fill_el* is missing the ``<a:blip>`` child, the
    ``r:embed`` attribute is absent, the rId is unknown, or the target is
    not an image relationship.
    """
    if blip_fill_el is None:
        return None
    blip = blip_fill_el.find(_x("a:blip"))
    if blip is None:
        return None
    r_embed = blip.get(_x("r:embed"))
    if r_embed is None:
        # `r:link` (linked external image) is out of scope — we only handle embedded.
        return None
    try:
        rel = part.rels[r_embed]
    except KeyError:
        return None
    if "image" not in rel.reltype:
        return None
    try:
        partname = rel.target_part.partname
    except Exception:
        return None
    return Path(str(partname)).name


def _read_prst_geom(
    sp_pr: Optional[etree._Element],
) -> tuple[Optional[str], Optional[dict[str, int]]]:
    """Return (preset_name, adjust_values) for a shape's ``<a:prstGeom>``.

    Returns ``(None, None)`` when *sp_pr* is missing or has no prstGeom child,
    or when the preset is a freeform/custom geometry. Adjust values are read
    from ``<a:avLst><a:gd name="adj" fmla="val N"/></a:avLst>``; only the
    ``val N`` formula form is supported (the only one that maps directly to
    a CSS clip-path parameter — caller may pass the returned dict to
    :func:`pictures.geometry.preset_to_css`).
    """
    if sp_pr is None:
        return None, None
    prst = sp_pr.find(_x("a:prstGeom"))
    if prst is None:
        return None, None
    name = prst.get("prst")
    if not name:
        return None, None
    av_lst = prst.find(_x("a:avLst"))
    if av_lst is None:
        return name, None
    avs: dict[str, int] = {}
    for gd in av_lst.findall(_x("a:gd")):
        gd_name = gd.get("name")
        fmla = gd.get("fmla", "")
        if gd_name and fmla.startswith("val "):
            try:
                avs[gd_name] = int(fmla[4:])
            except ValueError:
                continue
    return name, (avs or None)


def _read_cnv_pr(parent_nv: Optional[etree._Element]) -> tuple[int, str]:
    """Return (shape_id, alt_text) from a ``<p:nvPicPr>`` or ``<p:nvSpPr>``.

    *parent_nv* should be the container that holds ``<p:cNvPr>``. Alt text is
    taken from ``@descr`` first, then ``@title``, then empty. Shape id defaults
    to 0 when not parsable.
    """
    if parent_nv is None:
        return 0, ""
    c_nv_pr = parent_nv.find(_x("p:cNvPr"))
    if c_nv_pr is None:
        return 0, ""
    try:
        shape_id = int(c_nv_pr.get("id", "0"))
    except ValueError:
        shape_id = 0
    alt_text = c_nv_pr.get("descr") or c_nv_pr.get("title") or ""
    return shape_id, alt_text


def _parse_pic(
    pic_el: etree._Element,
    slide_part,
    order_index: int,
) -> Optional[Picture]:
    """Parse a ``<p:pic>`` shape into a :class:`Picture`.

    Returns ``None`` only when the picture lacks both a resolvable image and
    geometry (degenerate case worth skipping silently).
    """
    nv_pic_pr = pic_el.find(_x("p:nvPicPr"))
    shape_id, alt_text = _read_cnv_pr(nv_pic_pr)

    blip_fill = pic_el.find(_x("p:blipFill"))
    asset_ref = _resolve_blip_asset_ref(blip_fill, slide_part)

    sp_pr = pic_el.find(_x("p:spPr"))
    x, y, w, h, _rot = _get_sp_position(pic_el)
    preset_name, preset_av = _read_prst_geom(sp_pr)
    effects = parse_effects(sp_pr, blip_fill)

    # Degenerate skip: no image, no size — nothing to render.
    if asset_ref is None and w == 0 and h == 0:
        return None

    return Picture(
        asset_ref=asset_ref,
        x_px=x,
        y_px=y,
        width_px=w,
        height_px=h,
        preset_geom=preset_name,
        preset_geom_av=preset_av,
        effects=effects,
        alt_text=alt_text,
        shape_id=shape_id,
        is_placeholder=False,
        ph_idx=None,
        order_index=order_index,
    )


def _parse_picture_placeholder(
    sp_el: etree._Element,
    slide_part,
    layout_part,
    layout_sp: Optional[etree._Element],
    idx: int,
    order_index: int,
) -> Picture:
    """Parse a picture-typed ``<p:sp>`` (``<p:ph type="pic">``) into a :class:`Picture`.

    blipFill cascade: slide-level ``<p:blipFill>`` wins; if missing or has no
    embed, fall back to the layout's blipFill on the matching layout shape
    (resolved against the layout part's rels).

    Geometry cascade: slide-level xfrm wins; if zero-sized, fall back to
    layout's xfrm.

    Returns a :class:`Picture` even when no image is bound on either level —
    in that case ``asset_ref`` is ``None`` and emit renders an empty
    positioned box (mirroring PPT's behaviour for un-bound picture
    placeholders).
    """
    nv_sp_pr = sp_el.find(_x("p:nvSpPr"))
    shape_id, alt_text = _read_cnv_pr(nv_sp_pr)

    sp_pr = sp_el.find(_x("p:spPr"))

    # blipFill cascade: slide → layout
    slide_blip_fill = sp_pr.find(_x("a:blipFill")) if sp_pr is not None else None
    asset_ref = _resolve_blip_asset_ref(slide_blip_fill, slide_part)
    effective_blip_fill = slide_blip_fill if asset_ref is not None else None
    if asset_ref is None and layout_sp is not None:
        layout_sp_pr = layout_sp.find(_x("p:spPr"))
        layout_blip_fill = (
            layout_sp_pr.find(_x("a:blipFill")) if layout_sp_pr is not None else None
        )
        layout_asset = _resolve_blip_asset_ref(layout_blip_fill, layout_part)
        if layout_asset is not None:
            asset_ref = layout_asset
            effective_blip_fill = layout_blip_fill

    # Geometry cascade
    x, y, w, h, _rot = _get_sp_position(sp_el)
    if w == 0 and h == 0 and layout_sp is not None:
        x, y, w, h, _rot = _get_sp_position(layout_sp)

    preset_name, preset_av = _read_prst_geom(sp_pr)
    effects = parse_effects(sp_pr, effective_blip_fill)

    return Picture(
        asset_ref=asset_ref,
        x_px=x,
        y_px=y,
        width_px=w,
        height_px=h,
        preset_geom=preset_name,
        preset_geom_av=preset_av,
        effects=effects,
        alt_text=alt_text,
        shape_id=shape_id,
        is_placeholder=True,
        ph_idx=idx,
        order_index=order_index,
    )


def _parse_layout_only_picture_placeholder(
    layout_sp: etree._Element,
    layout_part,
    idx: int,
    order_index: int,
) -> Optional[Picture]:
    """Parse a layout-level ``<p:sp>`` picture placeholder NOT redeclared on the slide.

    OOXML semantics: a layout's picture-typed placeholder renders on every
    slide using that layout unless the slide overrides it by redeclaring the
    same idx. ``parse.py`` only walks the slide's own spTree, so without this
    helper layout-only picture placeholders never reach the resolved model
    (this was the cause of "16 assets extracted but only 5 rendered" against
    the IU template).

    Both blipFill and geometry resolve entirely against the layout part — no
    slide-level cascade since the slide has no matching shape.

    Returns ``None`` if the layout shape itself is degenerate (no image and
    zero geometry).
    """
    nv_sp_pr = layout_sp.find(_x("p:nvSpPr"))
    shape_id, alt_text = _read_cnv_pr(nv_sp_pr)

    sp_pr = layout_sp.find(_x("p:spPr"))
    blip_fill = sp_pr.find(_x("a:blipFill")) if sp_pr is not None else None
    asset_ref = _resolve_blip_asset_ref(blip_fill, layout_part)

    x, y, w, h, _rot = _get_sp_position(layout_sp)
    if asset_ref is None and w == 0 and h == 0:
        return None

    preset_name, preset_av = _read_prst_geom(sp_pr)
    effects = parse_effects(sp_pr, blip_fill if asset_ref is not None else None)

    return Picture(
        asset_ref=asset_ref,
        x_px=x,
        y_px=y,
        width_px=w,
        height_px=h,
        preset_geom=preset_name,
        preset_geom_av=preset_av,
        effects=effects,
        alt_text=alt_text,
        shape_id=shape_id,
        is_placeholder=True,
        ph_idx=idx,
        order_index=order_index,
    )


# ---------------------------------------------------------------------------
# Main parse function
# ---------------------------------------------------------------------------

def parse(pptx_path: Path) -> Presentation:
    """Parse a PPTX file and return a fully-resolved Presentation model.

    Only text-bearing placeholders are extracted (v1 scope).
    """
    prs = pptx.Presentation(str(pptx_path))

    # Canvas dimensions
    sld_sz = prs._element.find(_x("p:sldSz"))
    if sld_sz is not None:
        canvas_w = int(int(sld_sz.get("cx", "9144000")) / _EMU_PER_PX)
        canvas_h = int(int(sld_sz.get("cy", "5143500")) / _EMU_PER_PX)
    else:
        canvas_w, canvas_h = 1920, 1080

    slides: list[Slide] = []
    typefaces: set[str] = set()

    for slide_idx, slide in enumerate(prs.slides, start=1):
        layout = slide.slide_layout
        master = layout.slide_master
        theme_el = _get_theme_el(master)
        master_tx_styles = _get_master_tx_styles(master)
        clr_map = get_clr_map(master._element)

        bg_fill = _resolve_background(slide, prs, theme_el, clr_map)

        placeholders: list[Placeholder] = []
        pictures: list[Picture] = []

        # Iterate shapes via lxml on the slide's XML
        cSld = slide._element.find(_x("p:cSld"))
        sp_tree = cSld.find(_x("p:spTree")) if cSld is not None else None
        if sp_tree is None:
            slides.append(Slide(index=slide_idx, placeholders=[], background_fill=bg_fill))
            continue

        # Record document order so picture/placeholder interleaving is reproducible
        # in emit (P6). Each direct child of <p:spTree> gets a sequential index.
        doc_order: dict[int, int] = {}
        for i, child in enumerate(sp_tree):
            doc_order[id(child)] = i

        # ----- Picture placeholders + free <p:pic> -----
        # These are walked before the text-placeholder loop only because the
        # text-loop's `continue` path skips picture-typed phs; we still rely on
        # the same per-element traversal otherwise. Order is preserved via
        # the `order_index` field on Picture so emit can interleave correctly.
        for pic_el in sp_tree.findall(_x("p:pic")):
            picture = _parse_pic(
                pic_el,
                slide.part,
                doc_order.get(id(pic_el), 0),
            )
            if picture is not None:
                pictures.append(picture)

        for sp_el in sp_tree.findall(_x("p:sp")):
            idx = _ph_idx(sp_el)
            if idx is None:
                continue  # Not a placeholder

            ph_type = _ph_type(sp_el)
            if ph_type == "pic":
                # Picture placeholder: cascades blipFill slide → layout
                layout_sp_for_pic = _find_layout_sp(layout, idx)
                picture = _parse_picture_placeholder(
                    sp_el,
                    slide.part,
                    layout.part,
                    layout_sp_for_pic,
                    idx,
                    doc_order.get(id(sp_el), 0),
                )
                pictures.append(picture)
                continue
            if ph_type not in _TEXT_PH_TYPES:
                continue  # Non-text placeholder (chart, tbl, etc.) — still out of scope

            # Check if there's a txBody (for non-text types, skip gracefully)
            tx_body = sp_el.find(_x("p:txBody"))
            if tx_body is None:
                # Might still be valid as a text placeholder — only skip if type is definitely non-text
                if ph_type in ("pic", "chart", "tbl", "clipArt", "dgm", "media", "waveAudioFile"):
                    continue

            # Locate cascade elements
            layout_sp = _find_layout_sp(layout, idx)
            master_sp = _find_master_sp(master, ph_type, idx)

            # Resolve defaults (cascade level 1–5)
            default_run, default_para = resolve_placeholder(
                slide_sp=sp_el,
                layout_ph=layout_sp,
                master_ph=master_sp,
                master_tx_styles=master_tx_styles,
                theme_el=theme_el,
                ph_type=ph_type,
                level=0,
                clr_map=clr_map,
            )

            # Collect typefaces from defaults
            if default_run.font_family:
                typefaces.add(default_run.font_family)

            # Geometry — prefer slide-level xfrm, fall back to layout, then master
            x_px, y_px, w_px, h_px, rot_deg = _get_sp_position(sp_el)
            if w_px == 0 and h_px == 0:
                if layout_sp is not None:
                    x_px, y_px, w_px, h_px, rot_deg = _get_sp_position(layout_sp)
            if w_px == 0 and h_px == 0:
                if master_sp is not None:
                    x_px, y_px, w_px, h_px, rot_deg = _get_sp_position(master_sp)

            # Fill — cascades slide → layout
            fill = _resolve_fill(sp_el, theme_el, clr_map, layout_sp=layout_sp)

            # Opacity (not commonly set on placeholders, default 1.0)
            opacity = 1.0

            # TextFrame — with prompt-fallback for empty slide-level content
            text_frame = None
            is_prompt_fallback = False
            if tx_body is not None:
                if (
                    _txbody_is_empty(tx_body)
                    and layout_sp is not None
                    and _layout_ph_has_custom_prompt(layout_sp)
                ):
                    # Slide placeholder is empty; use layout's prompt text as the content.
                    # Only the text RUNS come from the layout; styling cascade is already
                    # resolved from slide → layout → master defaults (default_run/default_para).
                    layout_tx_body = layout_sp.find(_x("p:txBody"))
                    if layout_tx_body is not None and not _txbody_is_empty(layout_tx_body):
                        text_frame = _parse_text_frame(
                            layout_tx_body, default_run, default_para, theme_el, clr_map
                        )
                        is_prompt_fallback = True
                if text_frame is None:
                    layout_tx_body = (
                        layout_sp.find(_x("p:txBody")) if layout_sp is not None else None
                    )
                    text_frame = _parse_text_frame(
                        tx_body, default_run, default_para, theme_el, clr_map,
                        layout_tx_body=layout_tx_body,
                    )
                # Collect typefaces from actual runs
                if text_frame is not None:
                    for para in text_frame.paragraphs:
                        for run in para.runs:
                            if run.font_family:
                                typefaces.add(run.font_family)

            placeholders.append(Placeholder(
                idx=idx,
                type=ph_type,
                x_px=x_px,
                y_px=y_px,
                width_px=w_px,
                height_px=h_px,
                rotation_deg=rot_deg,
                fill=fill,
                opacity=opacity,
                text_frame=text_frame,
                default_run_props=default_run,
                default_para_props=default_para,
                is_prompt_fallback=is_prompt_fallback,
            ))

        # Surface layout-only picture placeholders. OOXML: a layout-level
        # <p:sp type="pic"> renders on every slide using that layout unless
        # the slide redeclares the same idx. Without this pass, the IU
        # template's layout-bound decorative images (logos, sidebars, sample
        # photos baked into the layout's blipFill) never reach the model.
        slide_ph_idxes = {p.idx for p in placeholders} | {
            p.ph_idx for p in pictures if p.is_placeholder and p.ph_idx is not None
        }
        layout_sp_tree = (
            layout._element.find(_x("p:cSld") + "/" + _x("p:spTree"))
            if layout._element is not None
            else None
        )
        if layout_sp_tree is None:
            # Fallback: find with explicit walk
            l_csld = layout._element.find(_x("p:cSld"))
            layout_sp_tree = l_csld.find(_x("p:spTree")) if l_csld is not None else None
        if layout_sp_tree is not None:
            # Use a high base order_index so layout-inherited pics naturally land
            # behind slide-level pics in DOM order (they're the background).
            base = 10_000
            for i, lsp in enumerate(layout_sp_tree.findall(_x("p:sp"))):
                lidx = _ph_idx(lsp)
                if lidx is None:
                    continue
                if lidx in slide_ph_idxes:
                    continue  # Slide overrides this layout placeholder.
                if _ph_type(lsp) != "pic":
                    continue
                inherited = _parse_layout_only_picture_placeholder(
                    lsp, layout.part, lidx, base + i,
                )
                if inherited is not None:
                    pictures.append(inherited)

            # Also walk layout-level free <p:pic> shapes (e.g. the IU template's
            # decorative logo lives as a <p:pic> directly on the layout, not
            # inside a placeholder). These render under every slide that uses
            # the layout, so we surface them per-slide.
            for j, lpic in enumerate(layout_sp_tree.findall(_x("p:pic"))):
                inherited_free = _parse_pic(
                    lpic, layout.part, base + 5_000 + j,
                )
                if inherited_free is not None:
                    pictures.append(inherited_free)

        # Master-level inheritance. OOXML: master shapes render under every
        # slide unless the slide or its layout sets showMasterSp="0". The IU
        # template's "black on light background" logo lives on the master and
        # only appears on slides whose layout doesn't override it with the
        # white variant. Dedup by position so a layout's own logo (e.g. the
        # white variant at the same top-right position) suppresses the
        # master's logo for that slide.
        slide_show_master = slide._element.get("showMasterSp")
        layout_show_master = (
            layout._element.get("showMasterSp")
            if layout._element is not None
            else None
        )
        effective_show_master = slide_show_master or layout_show_master or "1"
        if effective_show_master != "0":
            master_sp_tree = None
            m_csld = master._element.find(_x("p:cSld"))
            if m_csld is not None:
                master_sp_tree = m_csld.find(_x("p:spTree"))
            if master_sp_tree is not None:
                # Build a position set from already-collected pictures so
                # master pics overlapping a layout pic at the same xy can be
                # skipped (layout overrides). Rounded-int positions tolerate
                # subpixel EMU conversion noise.
                covered_positions = {
                    (round(p.x_px), round(p.y_px)) for p in pictures
                }
                master_base = 20_000
                for k, mpic in enumerate(master_sp_tree.findall(_x("p:pic"))):
                    inherited_master = _parse_pic(
                        mpic, master.part, master_base + k,
                    )
                    if inherited_master is None:
                        continue
                    pos_key = (
                        round(inherited_master.x_px),
                        round(inherited_master.y_px),
                    )
                    if pos_key in covered_positions:
                        continue  # Layout's own pic at this xy overrides.
                    pictures.append(inherited_master)

        # Stable document order across both <p:pic> shapes and <p:ph type="pic">
        # placeholders (which arrive from four sources: slide-level <p:pic>,
        # slide-level <p:sp type="pic">, layout-inherited shapes, and
        # master-inherited <p:pic> shapes).
        pictures.sort(key=lambda p: p.order_index)

        slides.append(Slide(
            index=slide_idx,
            placeholders=placeholders,
            background_fill=bg_fill,
            pictures=pictures,
        ))

    return Presentation(
        slides=slides,
        canvas_width_px=canvas_w,
        canvas_height_px=canvas_h,
        typefaces_referenced=typefaces,
    )


