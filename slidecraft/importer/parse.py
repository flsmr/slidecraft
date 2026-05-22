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

        # Iterate shapes via lxml on the slide's XML
        cSld = slide._element.find(_x("p:cSld"))
        sp_tree = cSld.find(_x("p:spTree")) if cSld is not None else None
        if sp_tree is None:
            slides.append(Slide(index=slide_idx, placeholders=[], background_fill=bg_fill))
            continue

        for sp_el in sp_tree.findall(_x("p:sp")):
            idx = _ph_idx(sp_el)
            if idx is None:
                continue  # Not a placeholder

            ph_type = _ph_type(sp_el)
            if ph_type not in _TEXT_PH_TYPES:
                continue  # Non-text placeholder (pic, chart, tbl, etc.)

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

        _apply_contrast_inversion(placeholders, bg_fill)
        slides.append(Slide(index=slide_idx, placeholders=placeholders, background_fill=bg_fill))

    return Presentation(
        slides=slides,
        canvas_width_px=canvas_w,
        canvas_height_px=canvas_h,
        typefaces_referenced=typefaces,
    )


def _apply_contrast_inversion(placeholders: list, bg_fill) -> None:
    """When a placeholder's resolved text color matches the slide background,
    flip the text color so it stays visible.

    PowerPoint applies an implicit contrast rule: if both the slide background
    and a placeholder's text color resolve to the same scheme color (typically
    ``tx1`` on dark layouts where the layout sets ``<p:bg>`` to ``tx1``), the
    actual rendered text uses the complementary color (``bg1``). We don't track
    scheme provenance through resolution, so we approximate by comparing the
    final RGB: if equal, flip the text to its luminance complement.

    This only mutates the placeholder's *default* run/para props and any runs
    that inherited (None) — explicit per-run colors are respected as-is.
    """
    if not isinstance(bg_fill, SolidFill):
        return
    bg = bg_fill.color
    inverted = _luminance_complement(bg)
    for ph in placeholders:
        tc = ph.default_run_props.color
        if tc is not None and tc.r == bg.r and tc.g == bg.g and tc.b == bg.b:
            ph.default_run_props.color = inverted
        # Also flip explicit per-run colors that happen to match (rare).
        if ph.text_frame is not None:
            for para in ph.text_frame.paragraphs:
                for run in para.runs:
                    rc = run.color
                    if rc is not None and rc.r == bg.r and rc.g == bg.g and rc.b == bg.b:
                        run.color = inverted


def _luminance_complement(c: RGB) -> RGB:
    """Return white if *c* is dark, black if *c* is light. Preserves alpha."""
    luminance = (0.299 * c.r + 0.587 * c.g + 0.114 * c.b) / 255.0
    if luminance < 0.5:
        return RGB(255, 255, 255, c.alpha)
    return RGB(0, 0, 0, c.alpha)
