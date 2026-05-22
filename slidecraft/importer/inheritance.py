"""Placeholder property cascade resolver.

Cascade order (highest → lowest priority):
  1. Slide <p:sp> (slide-level shape XML)
  2. SlideLayout <p:ph idx> (matched by idx)
  3. SlideMaster <p:ph type> or <p:ph idx> (matched by type, then idx)
  4. Master <p:txStyles> (titleStyle / bodyStyle / otherStyle) for the placeholder type at each lvl
  5. Theme <a:fontScheme> / <a:clrScheme> defaults

resolve_placeholder() returns the fully-resolved (Run, Paragraph) defaults for level 0
of the placeholder, representing what emit/layout.py bakes into the Vue layout.
"""
from __future__ import annotations

from typing import Optional
from lxml import etree

from slidecraft.importer.model import (
    RGB,
    Run,
    Paragraph,
)

# ---------------------------------------------------------------------------
# XML namespace map used throughout (OOXML namespaces)
# ---------------------------------------------------------------------------
_NSMAP = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}


def _x(tag: str) -> str:
    """Expand a prefixed tag name using the standard OOXML nsmap."""
    prefix, local = tag.split(":")
    return f"{{{_NSMAP[prefix]}}}{local}"


# ---------------------------------------------------------------------------
# Low-level XML helpers
# ---------------------------------------------------------------------------

def _find(el: Optional[etree._Element], *path: str) -> Optional[etree._Element]:
    """Walk a chain of child tags; return None if any step fails."""
    if el is None:
        return None
    for tag in path:
        el = el.find(_x(tag))
        if el is None:
            return None
    return el


def _get(el: Optional[etree._Element], attr: str, default=None):
    """Safely get an attribute value."""
    if el is None:
        return default
    return el.get(attr, default)


def _emu_to_pt(emu: Optional[int]) -> Optional[float]:
    """Convert EMU to points (1 pt = 12700 EMU)."""
    if emu is None:
        return None
    return emu / 12700.0


def _sz_to_pt(hundredths_pt: Optional[int]) -> Optional[float]:
    """Convert PPT font size (hundredths of a point) to points."""
    if hundredths_pt is None:
        return None
    return hundredths_pt / 100.0


def get_clr_map(master_el: Optional[etree._Element]) -> Optional[dict[str, str]]:
    """Read the <p:clrMap> from a slideMaster, returning a name → name remap dict.

    Example: clrMap bg1="lt1" tx1="dk1" → {"bg1": "lt1", "tx1": "dk1", ...}
    Used to translate logical schemeClr names into theme clrScheme names.
    """
    if master_el is None:
        return None
    clr_map_el = master_el.find(_x("p:clrMap"))
    if clr_map_el is None:
        return None
    return dict(clr_map_el.attrib)


_SYS_COLOR_FALLBACK: dict[str, str] = {
    "windowText": "000000", "window": "FFFFFF",
    "btnText": "000000", "btnFace": "F0F0F0",
}


def _hex_to_rgb(val: str, alpha: float = 1.0) -> Optional[RGB]:
    if len(val) != 6:
        return None
    return RGB(int(val[0:2], 16), int(val[2:4], 16), int(val[4:6], 16), alpha)


def _resolve_scheme_color(
    scheme_name: str,
    theme_el: Optional[etree._Element],
    clr_map: Optional[dict[str, str]],
) -> Optional[RGB]:
    """Resolve a schemeClr name → RGB via clrMap remap then clrScheme lookup."""
    if theme_el is None:
        return None
    name = clr_map.get(scheme_name, scheme_name) if clr_map else scheme_name
    clr_scheme = _find(theme_el, "a:themeElements", "a:clrScheme")
    if clr_scheme is None:
        return None
    color_el = clr_scheme.find(_x(f"a:{name}"))
    if color_el is None:
        return None
    srgb = color_el.find(_x("a:srgbClr"))
    if srgb is not None:
        return _hex_to_rgb(srgb.get("val", ""))
    sysclr = color_el.find(_x("a:sysClr"))
    if sysclr is not None:
        last = sysclr.get("lastClr") or _SYS_COLOR_FALLBACK.get(sysclr.get("val", ""), "")
        return _hex_to_rgb(last)
    return None


def _resolve_font_ref(ref: str, theme_el: Optional[etree._Element]) -> Optional[str]:
    """Resolve a theme font ref like '+mj-lt' / '+mn-lt' → actual typeface name."""
    if theme_el is None or not ref.startswith("+"):
        return None
    # +mj-lt = major Latin; +mn-lt = minor Latin; -ea = East Asian; -cs = Complex Script
    family_key = "a:majorFont" if ref.startswith("+mj-") else "a:minorFont"
    script_suffix = ref[4:] if len(ref) >= 5 else "lt"
    script_tag = {"lt": "a:latin", "ea": "a:ea", "cs": "a:cs"}.get(script_suffix, "a:latin")
    font_el = _find(theme_el, "a:themeElements", "a:fontScheme", family_key, script_tag)
    if font_el is not None:
        return font_el.get("typeface") or None
    return None


def _parse_color(
    solid_fill_el: Optional[etree._Element],
    theme_el: Optional[etree._Element] = None,
    clr_map: Optional[dict[str, str]] = None,
) -> Optional[RGB]:
    """Parse <a:solidFill> → RGB. Supports srgbClr, schemeClr (via theme+clrMap), and sysClr."""
    if solid_fill_el is None:
        return None
    srgb = solid_fill_el.find(_x("a:srgbClr"))
    if srgb is not None:
        alpha_el = srgb.find(_x("a:alpha"))
        alpha = int(alpha_el.get("val", "100000")) / 100000.0 if alpha_el is not None else 1.0
        return _hex_to_rgb(srgb.get("val", ""), alpha)
    scheme = solid_fill_el.find(_x("a:schemeClr"))
    if scheme is not None:
        rgb = _resolve_scheme_color(scheme.get("val", ""), theme_el, clr_map)
        if rgb is not None:
            alpha_el = scheme.find(_x("a:alpha"))
            if alpha_el is not None:
                alpha = int(alpha_el.get("val", "100000")) / 100000.0
                rgb = RGB(rgb.r, rgb.g, rgb.b, alpha)
            return rgb
    sysclr = solid_fill_el.find(_x("a:sysClr"))
    if sysclr is not None:
        last = sysclr.get("lastClr") or _SYS_COLOR_FALLBACK.get(sysclr.get("val", ""), "")
        return _hex_to_rgb(last)
    return None


# ---------------------------------------------------------------------------
# Per-element rPr / pPr extractors
# ---------------------------------------------------------------------------

def _extract_rpr(
    rpr_el: Optional[etree._Element],
    theme_el: Optional[etree._Element] = None,
    clr_map: Optional[dict[str, str]] = None,
) -> Run:
    """Extract explicit run properties from an <a:rPr> element into a Run(text='')."""
    run = Run(text="")
    if rpr_el is None:
        return run

    b = rpr_el.get("b")
    if b is not None:
        run.bold = b == "1"

    i = rpr_el.get("i")
    if i is not None:
        run.italic = i == "1"

    u = rpr_el.get("u")
    if u is not None:
        run.underline = u != "none"

    strike = rpr_el.get("strike")
    if strike is not None:
        run.strike = strike != "noStrike"

    cap = rpr_el.get("cap")
    if cap is not None:
        # "all" → uppercase, "small" → lowercase, "none" → no transform
        run.cap = cap

    sz = rpr_el.get("sz")
    if sz is not None:
        run.font_size_pt = _sz_to_pt(int(sz))

    latin = rpr_el.find(_x("a:latin"))
    if latin is not None:
        tf = latin.get("typeface")
        if tf:
            if tf.startswith("+"):
                resolved = _resolve_font_ref(tf, theme_el)
                if resolved:
                    run.font_family = resolved
            else:
                run.font_family = tf

    solid = rpr_el.find(_x("a:solidFill"))
    if solid is not None:
        run.color = _parse_color(solid, theme_el, clr_map)

    return run


def _extract_ppr(ppr_el: Optional[etree._Element]) -> Paragraph:
    """Extract explicit paragraph properties from an <a:pPr> element into a Paragraph."""
    para = Paragraph(runs=[])
    if ppr_el is None:
        return para

    algn = ppr_el.get("algn")
    if algn is not None:
        para.align = algn  # type: ignore[assignment]

    # marL → margin_left_pt (EMU)
    mar_l = ppr_el.get("marL")
    if mar_l is not None:
        para.margin_left_pt = _emu_to_pt(int(mar_l))

    # indent → indent_pt (EMU, can be negative for hanging indent)
    indent = ppr_el.get("indent")
    if indent is not None:
        para.indent_pt = _emu_to_pt(int(indent))

    # Line spacing
    lnspc = ppr_el.find(_x("a:lnSpc"))
    if lnspc is not None:
        spc_pct = lnspc.find(_x("a:spcPct"))
        if spc_pct is not None:
            pct_str = spc_pct.get("val", "")
            if pct_str.endswith("%"):
                para.line_spacing_pct = float(pct_str[:-1])
            else:
                # val is in 1000ths of a percent in OOXML (e.g. 100000 = 100%)
                try:
                    para.line_spacing_pct = int(pct_str) / 1000.0
                except ValueError:
                    pass

    # Space before
    spc_bef = ppr_el.find(_x("a:spcBef"))
    if spc_bef is not None:
        spc_pts = spc_bef.find(_x("a:spcPts"))
        if spc_pts is not None:
            # val is in hundredths of a point
            para.space_before_pt = int(spc_pts.get("val", "0")) / 100.0

    # Space after
    spc_aft = ppr_el.find(_x("a:spcAft"))
    if spc_aft is not None:
        spc_pts = spc_aft.find(_x("a:spcPts"))
        if spc_pts is not None:
            para.space_after_pt = int(spc_pts.get("val", "0")) / 100.0

    # Bullet
    bu_none = ppr_el.find(_x("a:buNone"))
    bu_char = ppr_el.find(_x("a:buChar"))
    bu_auto = ppr_el.find(_x("a:buAutoNum"))
    if bu_none is not None:
        para.bullet = "none"
    elif bu_char is not None:
        para.bullet = "char"
        para.bullet_char = bu_char.get("char")
    elif bu_auto is not None:
        para.bullet = "auto-num"

    return para


# ---------------------------------------------------------------------------
# Cascade merge helpers
# ---------------------------------------------------------------------------

def _merge_run(base: Run, override: Run) -> Run:
    """Return a new Run where override's non-None fields win over base."""
    return Run(
        text="",
        bold=override.bold if override.bold is not None else base.bold,
        italic=override.italic if override.italic is not None else base.italic,
        underline=override.underline if override.underline is not None else base.underline,
        strike=override.strike if override.strike is not None else base.strike,
        color=override.color if override.color is not None else base.color,
        font_family=override.font_family if override.font_family is not None else base.font_family,
        font_size_pt=override.font_size_pt if override.font_size_pt is not None else base.font_size_pt,
        cap=override.cap if override.cap is not None else base.cap,
    )


def _merge_para(base: Paragraph, override: Paragraph) -> Paragraph:
    """Return a new Paragraph where override's non-None fields win over base."""
    return Paragraph(
        runs=[],
        align=override.align if override.align is not None else base.align,
        line_spacing_pct=override.line_spacing_pct if override.line_spacing_pct is not None else base.line_spacing_pct,
        space_before_pt=override.space_before_pt if override.space_before_pt is not None else base.space_before_pt,
        space_after_pt=override.space_after_pt if override.space_after_pt is not None else base.space_after_pt,
        indent_pt=override.indent_pt if override.indent_pt is not None else base.indent_pt,
        margin_left_pt=override.margin_left_pt if override.margin_left_pt is not None else base.margin_left_pt,
        bullet=override.bullet if override.bullet is not None else base.bullet,
        bullet_char=override.bullet_char if override.bullet_char is not None else base.bullet_char,
        level=base.level,
    )


# ---------------------------------------------------------------------------
# txStyles reader
# ---------------------------------------------------------------------------

def _txstyles_defaults(
    tx_styles_el: Optional[etree._Element],
    ph_type: Optional[str],
    level: int = 0,
    theme_el: Optional[etree._Element] = None,
    clr_map: Optional[dict[str, str]] = None,
) -> tuple[Run, Paragraph]:
    """Extract level-N default rPr/pPr from master's <p:txStyles> for the given ph type.

    ph_type → XML element name:
      title / ctrTitle → <p:titleStyle>
      body / subTitle  → <p:bodyStyle>
      everything else  → <p:otherStyle>
    """
    if tx_styles_el is None:
        return Run(text=""), Paragraph(runs=[])

    if ph_type in ("title", "ctrTitle"):
        style_tag = "p:titleStyle"
    elif ph_type in ("body", "subTitle"):
        style_tag = "p:bodyStyle"
    else:
        style_tag = "p:otherStyle"

    style_el = tx_styles_el.find(_x(style_tag))
    if style_el is None:
        return Run(text=""), Paragraph(runs=[])

    # lstStyle contains <a:lvl{N+1}pPr> elements (lvl1pPr = level 0, lvl2pPr = level 1, …)
    lvl_tag = _x(f"a:lvl{level + 1}pPr")
    lvl_el = style_el.find(lvl_tag)
    if lvl_el is None:
        # Fall back to lvl1pPr
        lvl_el = style_el.find(_x("a:lvl1pPr"))
    if lvl_el is None:
        return Run(text=""), Paragraph(runs=[])

    ppr = _extract_ppr(lvl_el)

    # Default rPr inside the lvlXpPr
    def_rpr = lvl_el.find(_x("a:defRPr"))
    rpr = _extract_rpr(def_rpr, theme_el, clr_map)

    return rpr, ppr


# ---------------------------------------------------------------------------
# Theme defaults reader
# ---------------------------------------------------------------------------

def _theme_run_defaults(theme_el: Optional[etree._Element], ph_type: Optional[str]) -> Run:
    """Extract run-level defaults from <a:theme><a:themeElements><a:fontScheme>.

    Returns a Run with font_family populated if a major/minor font is found.
    For title placeholders the major font (+mj-lt Latin) is used; for body the minor (+mn-lt).
    """
    run = Run(text="")
    if theme_el is None:
        return run

    font_scheme = _find(theme_el, "a:themeElements", "a:fontScheme")
    if font_scheme is None:
        return run

    # title → major font, body → minor font
    if ph_type in ("title", "ctrTitle"):
        font_el = _find(font_scheme, "a:majorFont", "a:latin")
    else:
        font_el = _find(font_scheme, "a:minorFont", "a:latin")

    if font_el is not None:
        tf = font_el.get("typeface")
        if tf:
            run.font_family = tf

    return run


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def resolve_placeholder(
    slide_sp: Optional[etree._Element],
    layout_ph: Optional[etree._Element],
    master_ph: Optional[etree._Element],
    master_tx_styles: Optional[etree._Element],
    theme_el: Optional[etree._Element],
    ph_type: Optional[str] = None,
    level: int = 0,
    clr_map: Optional[dict[str, str]] = None,
) -> tuple[Run, Paragraph]:
    """Resolve the default Run and Paragraph props for a placeholder by walking the cascade.

    Parameters
    ----------
    slide_sp:
        The <p:sp> element from the slide (or None if the placeholder has no slide-level shape).
    layout_ph:
        The matching <p:sp> element from the slideLayout (matched by idx).
    master_ph:
        The matching <p:sp> element from the slideMaster (matched by type, then idx).
    master_tx_styles:
        The <p:txStyles> element from the slideMaster.
    theme_el:
        The <a:theme> root element from the theme part.
    ph_type:
        Placeholder type string (e.g. "title", "body", "ctrTitle") — used to pick the
        correct txStyles entry and theme font.
    level:
        List level for which defaults are resolved (0 = top-level paragraph).

    Returns
    -------
    (default_run_props, default_para_props): the fully-resolved cascade values.
    """
    # Level 5: theme defaults (lowest priority)
    theme_run = _theme_run_defaults(theme_el, ph_type)
    base_run = theme_run
    base_para = Paragraph(runs=[])

    # Level 4: master txStyles
    tx_run, tx_para = _txstyles_defaults(master_tx_styles, ph_type, level, theme_el, clr_map)
    base_run = _merge_run(base_run, tx_run)
    base_para = _merge_para(base_para, tx_para)

    # Level 3: master placeholder shape's txBody lstStyle / defRPr
    if master_ph is not None:
        base_run, base_para = _apply_sp_defaults(master_ph, base_run, base_para, level, theme_el, clr_map)

    # Level 2: layout placeholder shape's txBody
    if layout_ph is not None:
        base_run, base_para = _apply_sp_defaults(layout_ph, base_run, base_para, level, theme_el, clr_map)

    # Level 1: slide-level shape's txBody
    if slide_sp is not None:
        base_run, base_para = _apply_sp_defaults(slide_sp, base_run, base_para, level, theme_el, clr_map)

    return base_run, base_para


def _apply_sp_defaults(
    sp_el: etree._Element,
    base_run: Run,
    base_para: Paragraph,
    level: int,
    theme_el: Optional[etree._Element] = None,
    clr_map: Optional[dict[str, str]] = None,
) -> tuple[Run, Paragraph]:
    """Apply the txBody-level lstStyle / bodyPr defaults from a <p:sp> element."""
    tx_body = sp_el.find(_x("p:txBody"))
    if tx_body is None:
        return base_run, base_para

    lst_style = tx_body.find(_x("a:lstStyle"))
    if lst_style is not None:
        lvl_tag = _x(f"a:lvl{level + 1}pPr")
        lvl_el = lst_style.find(lvl_tag)
        if lvl_el is None and level != 0:
            lvl_el = lst_style.find(_x("a:lvl1pPr"))
        if lvl_el is not None:
            ppr_override = _extract_ppr(lvl_el)
            base_para = _merge_para(base_para, ppr_override)
            def_rpr = lvl_el.find(_x("a:defRPr"))
            if def_rpr is not None:
                rpr_override = _extract_rpr(def_rpr, theme_el, clr_map)
                base_run = _merge_run(base_run, rpr_override)

    first_p = tx_body.find(_x("a:p"))
    if first_p is not None:
        ppr_el = first_p.find(_x("a:pPr"))
        if ppr_el is not None:
            ppr_override = _extract_ppr(ppr_el)
            base_para = _merge_para(base_para, ppr_override)

        first_r = first_p.find(_x("a:r"))
        if first_r is not None:
            rpr_el = first_r.find(_x("a:rPr"))
            if rpr_el is not None:
                rpr_override = _extract_rpr(rpr_el, theme_el, clr_map)
                base_run = _merge_run(base_run, rpr_override)

        def_rpr_p = first_p.find(_x("a:endParaRPr"))
        if def_rpr_p is None:
            def_rpr_p = first_p.find(_x("a:defRPr"))
        if def_rpr_p is not None:
            rpr_override = _extract_rpr(def_rpr_p, theme_el, clr_map)
            base_run = _merge_run(base_run, rpr_override)

    return base_run, base_para


def diff_run(run: Run, default: Run) -> Run:
    """Return a Run containing only fields that differ from the default (None = same as default)."""
    return Run(
        text=run.text,
        bold=run.bold if run.bold != default.bold else None,
        italic=run.italic if run.italic != default.italic else None,
        underline=run.underline if run.underline != default.underline else None,
        strike=run.strike if run.strike != default.strike else None,
        color=run.color if run.color != default.color else None,
        font_family=run.font_family if run.font_family != default.font_family else None,
        font_size_pt=run.font_size_pt if run.font_size_pt != default.font_size_pt else None,
        cap=run.cap if run.cap != default.cap else None,
    )


def diff_para(para: Paragraph, default: Paragraph) -> Paragraph:
    """Return a Paragraph with only fields that differ from the default (None = same as default)."""
    return Paragraph(
        runs=para.runs,
        align=para.align if para.align != default.align else None,
        line_spacing_pct=para.line_spacing_pct if para.line_spacing_pct != default.line_spacing_pct else None,
        space_before_pt=para.space_before_pt if para.space_before_pt != default.space_before_pt else None,
        space_after_pt=para.space_after_pt if para.space_after_pt != default.space_after_pt else None,
        indent_pt=para.indent_pt if para.indent_pt != default.indent_pt else None,
        margin_left_pt=para.margin_left_pt if para.margin_left_pt != default.margin_left_pt else None,
        bullet=para.bullet if para.bullet != default.bullet else None,
        bullet_char=para.bullet_char if para.bullet_char != default.bullet_char else None,
        level=para.level,
    )
