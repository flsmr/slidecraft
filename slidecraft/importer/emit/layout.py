"""Emit theme/layouts/slide<N>.vue for each slide in the presentation."""
from __future__ import annotations

from pathlib import Path
from typing import Optional, Union

from ..fonts import strip_weight_suffix
from ..model import (
    Fill,
    GradientStop,
    LinearGradientFill,
    NoFill,
    Picture,
    Placeholder,
    Presentation,
    RadialGradientFill,
    RGB,
    Slide,
    SolidFill,
)
from ..pictures.derivatives import derivative_filename
from ..pictures.geometry import preset_to_css
from ..shapes.emit import render_text_shape_host
from ..tables.emit import render_table

# ---------------------------------------------------------------------------
# Fill → CSS helpers
# ---------------------------------------------------------------------------

def _rgb_css(c: RGB) -> str:
    if c.alpha < 1.0:
        return f"rgba({c.r},{c.g},{c.b},{c.alpha:.4g})"
    return f"rgb({c.r},{c.g},{c.b})"


def _hex_css(c: RGB) -> str:
    """Return #RRGGBB (or rgba) — used for style attributes."""
    if c.alpha < 1.0:
        return f"rgba({c.r},{c.g},{c.b},{c.alpha:.4g})"
    return f"#{c.r:02X}{c.g:02X}{c.b:02X}"


def _stop_css(stop: GradientStop) -> str:
    return f"{_rgb_css(stop.color)} {stop.position * 100:.4g}%"


def _fill_css(fill: Fill) -> str:
    if isinstance(fill, NoFill):
        return "transparent"
    if isinstance(fill, SolidFill):
        return _hex_css(fill.color)
    if isinstance(fill, LinearGradientFill):
        stops = ", ".join(_stop_css(s) for s in fill.stops)
        return f"linear-gradient({fill.angle_deg:.4g}deg, {stops})"
    if isinstance(fill, RadialGradientFill):
        stops = ", ".join(_stop_css(s) for s in fill.stops)
        return f"radial-gradient(ellipse at center, {stops})"
    return "transparent"


# ---------------------------------------------------------------------------
# Anchor → flex CSS
# ---------------------------------------------------------------------------

_ANCHOR_ALIGN = {"t": "flex-start", "ctr": "center", "b": "flex-end"}


# ---------------------------------------------------------------------------
# Paragraph defaults → CSS helpers
# ---------------------------------------------------------------------------

_ALIGN_MAP = {"l": "left", "ctr": "center", "r": "right", "just": "justify"}


# OOXML <a:buAutoNum @type> → CSS list-style-type.
# Periods ("arabicPeriod" → "1.") map cleanly; right-paren / paren-both
# styles need counter()-based ::marker content which is added on top of
# the base list-style-type rule. The mapping intentionally only covers
# the variants where CSS has a direct equivalent — exotic styles fall
# back to "decimal" / "lower-alpha" / etc. and the marker still renders
# with a period.
_AUTONUM_TO_LIST_STYLE: dict[str, str] = {
    "arabicPeriod":    "decimal",
    "arabicParenR":    "decimal",     # 1) — period instead
    "arabicParenBoth": "decimal",
    "arabicPlain":     "decimal",
    "arabicMinus":     "decimal",
    "arabicDbPeriod":  "decimal-leading-zero",
    "alphaUcPeriod":   "upper-alpha",
    "alphaLcPeriod":   "lower-alpha",
    "alphaUcParenR":   "upper-alpha",
    "alphaLcParenR":   "lower-alpha",
    "alphaUcParenBoth": "upper-alpha",
    "alphaLcParenBoth": "lower-alpha",
    "romanUcPeriod":   "upper-roman",
    "romanLcPeriod":   "lower-roman",
    "romanUcParenR":   "upper-roman",
    "romanLcParenR":   "lower-roman",
    "romanUcParenBoth": "upper-roman",
    "romanLcParenBoth": "lower-roman",
}


def _autonum_type_to_css(autonum_type: Optional[str]) -> Optional[str]:
    """Map an OOXML buAutoNum @type to a CSS list-style-type value.

    Returns ``None`` when ``autonum_type`` is ``None`` (caller should fall
    back to the browser default).
    """
    if autonum_type is None:
        return None
    return _AUTONUM_TO_LIST_STYLE.get(autonum_type, "decimal")


def _run_to_css(rp) -> list[str]:
    """Return CSS declarations for a :class:`Run`'s explicit properties.

    Pure function of the Run — no Placeholder context. Used by both
    placeholder host rendering and TextShape host rendering.
    """
    parts: list[str] = []

    # Strip weight suffix from font-family so we reference the base family
    # name (which Google Fonts can fetch) and encode the weight separately.
    # e.g. PPT "Source Sans Pro Bold" → font-family: 'Source Sans Pro'; font-weight: 700
    weight_from_family: int | None = None
    if rp.font_family:
        base_family, natural = strip_weight_suffix(rp.font_family)
        parts.append(f"font-family: '{base_family}', sans-serif")
        if natural != 400 and base_family != rp.font_family:
            weight_from_family = natural

    if rp.font_size_pt is not None:
        # pt → px (96dpi, 1pt = 4/3 px)
        px = rp.font_size_pt * 96 / 72
        parts.append(f"font-size: {px:.4g}px")
    # Weight resolution order:
    #  - explicit b="1" → always 700 (force bold)
    #  - family name implies weight ("Source Sans Pro Bold") → that natural weight,
    #    EVEN when b="0" is set. PPT convention: b="0" with a Bold-named subfamily
    #    means "no additional bold styling" — the family itself already provides bold.
    #  - explicit b="0" → 400 (only when the family doesn't already encode a weight)
    #  - otherwise → inherit (no font-weight emitted)
    if rp.bold:
        parts.append("font-weight: 700")
    elif weight_from_family is not None:
        parts.append(f"font-weight: {weight_from_family}")
    elif rp.bold is False:
        parts.append("font-weight: 400")
    if rp.italic:
        parts.append("font-style: italic")
    if rp.color:
        parts.append(f"color: {_hex_css(rp.color)}")
    if rp.cap == "all":
        parts.append("text-transform: uppercase")
    elif rp.cap == "small":
        parts.append("text-transform: lowercase")
    if rp.strike:
        parts.append("text-decoration: line-through")
    if rp.underline:
        # combine with strike when both present
        existing = next((p for p in parts if p.startswith("text-decoration:")), None)
        if existing:
            parts = [p for p in parts if not p.startswith("text-decoration:")]
            parts.append("text-decoration: underline line-through")
        else:
            parts.append("text-decoration: underline")
    return parts


def _para_to_css(pp, *, spc_var_prefix: str = "ph") -> list[str]:
    """Return CSS declarations for a :class:`Paragraph`'s explicit properties.

    Pure function of the Paragraph. The ``spc_var_prefix`` controls the
    CSS-variable namespace used for space-before / space-after (default
    ``--ph-spc-*`` for placeholder hosts; pass ``"txt"`` for TextShape hosts
    to keep selectors distinct).
    """
    parts: list[str] = []
    if pp.align:
        parts.append(f"text-align: {_ALIGN_MAP.get(pp.align, 'left')}")
    if pp.line_spacing_pct is not None:
        parts.append(f"line-height: {pp.line_spacing_pct / 100:.4g}")
    if pp.space_before_pt is not None:
        parts.append(f"--{spc_var_prefix}-spc-before: {pp.space_before_pt:.4g}pt")
    if pp.space_after_pt is not None:
        parts.append(f"--{spc_var_prefix}-spc-after: {pp.space_after_pt:.4g}pt")
    return parts


def _run_props_css(ph: Placeholder) -> list[str]:
    """Thin wrapper: CSS declarations for a placeholder's default run."""
    return _run_to_css(ph.default_run_props)


def _para_props_css(ph: Placeholder) -> list[str]:
    """Thin wrapper: CSS declarations for a placeholder's default paragraph."""
    return _para_to_css(ph.default_para_props)


# ---------------------------------------------------------------------------
# Per-placeholder inline style
# ---------------------------------------------------------------------------

def _placeholder_style(ph: Placeholder, frame_anchor: str = "t") -> str:
    """Build the full inline style string for a placeholder wrapper div."""
    parts: list[str] = [
        "position:absolute",
        f"left:{ph.x_px:.4g}px",
        f"top:{ph.y_px:.4g}px",
        f"width:{ph.width_px:.4g}px",
        f"height:{ph.height_px:.4g}px",
    ]

    if ph.rotation_deg != 0.0:
        parts.append(f"transform:rotate({ph.rotation_deg:.4g}deg)")

    parts.append(f"background:{_fill_css(ph.fill)}")

    if ph.opacity != 1.0:
        parts.append(f"opacity:{ph.opacity:.4g}")

    # Vertical anchor via flex.  flex-direction:column is mandatory — without
    # it, multi-paragraph content (e.g. the thank-you slide's contact slot:
    # "name<br/>phone" / "email") lays out HORIZONTALLY as flex items rather
    # than stacking vertically.  With column direction, align-items still
    # controls cross-axis (horizontal) alignment which we want as
    # flex-start (left); justify-content takes over the vertical anchor.
    align_items = _ANCHOR_ALIGN.get(frame_anchor, "flex-start")
    parts.append("display:flex")
    parts.append("flex-direction:column")
    parts.append(f"justify-content:{align_items}")

    # TextFrame insets → padding (l, t, r, b → CSS order t r b l)
    tf = ph.text_frame
    if tf is not None:
        l_ins_pt, t_ins_pt, r_ins_pt, b_ins_pt = tf.insets_pt
        # pt → px
        pt_to_px = 96.0 / 72.0
        t_px = t_ins_pt * pt_to_px
        b_px = b_ins_pt * pt_to_px
        l_px = l_ins_pt * pt_to_px
        r_px = r_ins_pt * pt_to_px

        # PPT-fidelity inset clamping. When tIns + bIns exceeds the element
        # height (the chip on IU's title page sets tIns=52.91px on a 43.74px
        # box, with anchor="b"), PPT keeps the anchored side's inset and
        # discards the opposite. CSS without clamping gives the inner box
        # negative height and pushes text outside the element. Match PPT:
        if t_px + b_px > ph.height_px:
            if frame_anchor == "b":
                # bottom-anchored: respect bIns, zero out tIns.
                t_px = max(0.0, ph.height_px - b_px)
            elif frame_anchor == "ctr":
                # center-anchored: split available height equally.
                each = max(0.0, ph.height_px / 2)
                t_px = min(t_px, each)
                b_px = min(b_px, each)
            else:
                # top-anchored (default): respect tIns, zero out bIns.
                b_px = max(0.0, ph.height_px - t_px)
        # Same logic for horizontal insets (rare in practice but harmless).
        if l_px + r_px > ph.width_px:
            each = max(0.0, ph.width_px / 2)
            l_px = min(l_px, each)
            r_px = min(r_px, each)

        def fmt(v: float) -> str:
            return f"{v:.4g}px"
        padding = f"{fmt(t_px)} {fmt(r_px)} {fmt(b_px)} {fmt(l_px)}"
        parts.append(f"padding:{padding}")

        if tf.rotation_deg != 0.0:
            # Combine with shape rotation if already present
            rot_total = ph.rotation_deg + tf.rotation_deg
            # Replace the existing transform or add
            parts = [p for p in parts if not p.startswith("transform:")]
            if rot_total != 0.0:
                parts.append(f"transform:rotate({rot_total:.4g}deg)")

    # Clip-path from prstGeom / custGeom cascade (e.g. drawer-shape chip on
    # IU title page). When set, the wrapper's background and text content are
    # both clipped to the path; padding inside the wrapper keeps text from
    # hitting the curved edges.
    if ph.clip_path:
        parts.append(f"clip-path:{ph.clip_path}")

    # Run defaults (font, color, weight, etc.)
    parts.extend(_run_props_css(ph))
    # Para defaults (text-align, line-height)
    parts.extend(_para_props_css(ph))

    return "; ".join(parts)


# ---------------------------------------------------------------------------
# Picture helpers (P6)
# ---------------------------------------------------------------------------

def _resolve_asset_url(asset_ref: str, effects: dict) -> str:
    """Compute the final ``/assets/...`` URL after the derivative chain.

    PPT effects that require pre-baked image work (crop / duotone / soft_edge)
    produce ``derivatives_needed`` entries on the effects dict. Their
    filenames are deterministic via
    :func:`pictures.derivatives.derivative_filename`, so emit can predict the
    final URL without running Pillow — the actual file write happens later in
    the build pipeline (convert.py orchestrates the work-order list).
    """
    name = asset_ref
    for d in effects.get("derivatives_needed", []) or []:
        try:
            name = derivative_filename(name, d["op"], d["params"])
        except (KeyError, ValueError):
            # Skip a malformed work order rather than break emit; warnings
            # for unsupported ops live in effects.warnings already.
            continue
    return f"/assets/{name}"


def _picture_wrapper_style(pic: Picture) -> str:
    """Inline style for a Picture wrapper div.

    Carries position/size, prstGeom mask (clip-path or border-radius),
    rotation+flip transforms, css filter chain, alphaModFix opacity, inner
    shadow mask hint, and -webkit-box-reflect — i.e. everything from the
    effects dict that lives on the wrapper rather than the inner ``<img>``.
    ``overflow: hidden`` ensures the prstGeom clip + child overflow play
    well together.
    """
    parts: list[str] = [
        "position:absolute",
        f"left:{pic.x_px:.4g}px",
        f"top:{pic.y_px:.4g}px",
        f"width:{pic.width_px:.4g}px",
        f"height:{pic.height_px:.4g}px",
        "overflow:hidden",
    ]

    eff = pic.effects or {}

    transforms = eff.get("transforms") or []
    if transforms:
        parts.append(f"transform:{' '.join(transforms)}")

    css_filter = eff.get("css_filter") or ""
    if css_filter:
        parts.append(f"filter:{css_filter}")

    opacity = eff.get("opacity")
    if opacity is not None and opacity != 1.0:
        parts.append(f"opacity:{opacity:.4g}")

    box_reflect = eff.get("box_reflect")
    if box_reflect:
        parts.append(f"-webkit-box-reflect:{box_reflect}")

    # prstGeom mask
    if pic.preset_geom:
        geom = preset_to_css(
            pic.preset_geom,
            int(pic.width_px) if pic.width_px else 0,
            int(pic.height_px) if pic.height_px else 0,
            pic.preset_geom_av,
        )
        if geom is not None:
            if geom.get("clip_path"):
                parts.append(f"clip-path:{geom['clip_path']}")
            if geom.get("border_radius"):
                parts.append(f"border-radius:{geom['border_radius']}")

    return ";".join(parts)


def _picture_img_tag(pic: Picture) -> str:
    """Emit the inner ``<img>`` element for a Picture, or empty string if no asset.

    The ``<img>`` always fills the wrapper (object-fit: fill mirrors PPT's
    default stretch behaviour). Alt text is HTML-escaped on quotes only —
    other characters are safe inside an attribute value.
    """
    if not pic.asset_ref:
        return ""
    alt = (pic.alt_text or "").replace('"', "&quot;")
    url = _resolve_asset_url(pic.asset_ref, pic.effects or {})
    return (
        f'<img src="{url}" alt="{alt}" '
        f'style="width:100%;height:100%;object-fit:fill;display:block;"/>'
    )


# ---------------------------------------------------------------------------
# Vue template builder
# ---------------------------------------------------------------------------

_INDENT = "  "


def _emit_layout_vue(slide: Slide, canvas_width: int, canvas_height: int) -> str:
    lines: list[str] = []

    lines.append("<template>")
    lines.append(f'{_INDENT}<div class="slidev-layout">')
    lines.append(f'{_INDENT * 2}<div class="slide-root">')

    # Layout 3 background decoration: layout/master non-placeholder shapes
    # render BEHIND placeholders and pictures. Slide-source text shapes are
    # foreground content and emit after placeholders/pictures (see below).
    # This mirrors PPT z-order: layout/master spTree below slide spTree.
    for shape in slide.text_shapes:
        if shape.source in ("layout", "master"):
            lines.append(f"{_INDENT * 3}{render_text_shape_host(shape)}")

    for ph in slide.placeholders:
        anchor = ph.text_frame.anchor if ph.text_frame else "t"
        style = _placeholder_style(ph, frame_anchor=anchor)
        lines.append(f'{_INDENT * 3}<div class="ph-{ph.idx}" style="{style}">')
        lines.append(f'{_INDENT * 4}<slot name="ph_{ph.idx}" />')
        lines.append(f"{_INDENT * 3}</div>")

    # Pictures (P6): free <p:pic> shapes baked fully into the layout; picture
    # placeholders emit a wrapped <slot> with the layout's default <img> as the
    # slot's default content, so slides can override per-placeholder by
    # supplying their own ::ph_<idx>:: block.
    for pic in slide.pictures:
        style = _picture_wrapper_style(pic)
        img_tag = _picture_img_tag(pic)
        if pic.is_placeholder and pic.ph_idx is not None:
            lines.append(
                f'{_INDENT * 3}<div class="ph-{pic.ph_idx}" style="{style}">'
            )
            if img_tag:
                lines.append(f'{_INDENT * 4}<slot name="ph_{pic.ph_idx}">{img_tag}</slot>')
            else:
                # Un-bound picture placeholder — empty box; slide may still
                # override via ::ph_<idx>:: to supply its own image.
                lines.append(f'{_INDENT * 4}<slot name="ph_{pic.ph_idx}" />')
            lines.append(f"{_INDENT * 3}</div>")
        else:
            # Free <p:pic> — baked completely; no slot, no override.
            lines.append(
                f'{_INDENT * 3}<div class="pic-{pic.shape_id}" style="{style}">'
            )
            if img_tag:
                lines.append(f"{_INDENT * 4}{img_tag}")
            lines.append(f"{_INDENT * 3}</div>")

    # Layer 4 — tables (<p:graphicFrame>/<a:tbl>) live on the slide only;
    # emit between pictures and slide-source text shapes. render_table()
    # returns a multi-line block; indent each line.
    for table in slide.tables:
        block = render_table(table)
        for line in block.split("\n"):
            lines.append(f"{_INDENT * 3}{line}")

    # Slide-source text shapes are foreground — emit after placeholders and
    # pictures so they sit on top (matches the IU template's slide 6/7/8
    # "Source" footers). Layout/master-source shapes were already emitted
    # above as background decoration.
    for shape in slide.text_shapes:
        if shape.source == "slide":
            lines.append(f"{_INDENT * 3}{render_text_shape_host(shape)}")

    lines.append(f"{_INDENT * 2}</div>")
    lines.append(f"{_INDENT}</div>")
    lines.append("</template>")
    lines.append("")

    # ---- <style scoped> -----------------------------------------------
    lines.append("<style scoped>")
    bg = _fill_css(slide.background_fill)
    lines.append(f".slidev-layout .slide-root {{")
    lines.append(f"  position: relative;")
    lines.append(f"  width: {canvas_width}px;")
    lines.append(f"  height: {canvas_height}px;")
    lines.append(f"  background: {bg};")
    lines.append(f"  overflow: hidden;")
    lines.append(f"}}")

    # Bullet styling per placeholder — ::marker CSS faithful to PPT.
    #
    # PPT stores bullets in three forms:
    #   1. <a:buChar char="-"/>   → character bullet ("-", "•", etc.)
    #   2. <a:buAutoNum type="…"/> → numbered list (1., a., i., etc.)
    #   3. <a:buNone/>            → no bullet
    #
    # Plus three independent style fields (any combination):
    #   <a:buClr>     → bullet color (often a schemeClr → theme accent)
    #   <a:buFont>    → bullet font (often "Symbol" or "Wingdings")
    #   <a:buSzPct>   → bullet size as percentage of surrounding text
    #
    # The cascade resolves these from master <p:bodyStyle>/<p:titleStyle>/
    # <p:otherStyle> down through layout lstStyle to per-paragraph pPr.
    # We emit one ::marker rule per (placeholder, level, bullet kind) so
    # the output uses pixel-accurate PPT bullets instead of browser defaults.
    # Reset paragraph margins inside placeholder slots. Slidev / UnoCSS
    # don't reset <p> margin, so the browser-default ~1em (16 px) margin
    # stacks ON TOP of any per-paragraph PPT `space_before_pt` we emit
    # inline (e.g. `<p style="margin-top:6pt">` from <a:spcBef>). That made
    # tmp2 slide 7 (Feynman method) render with visibly wider gaps between
    # paragraphs than the PPT shows. Resetting all <p> margins to 0 inside
    # the placeholder + text-shape scope means the inline `margin-top:6pt`
    # we emit IS the total gap, matching PPT exactly.
    for ph in slide.placeholders:
        if ph.text_frame is None:
            continue
        lines.append(
            f".slidev-layout .ph-{ph.idx} :deep(p) {{ margin: 0; }}"
        )
    for shape in slide.text_shapes:
        if shape.text_frame is None:
            continue
        lines.append(
            f".slidev-layout .txt-{shape.shape_id} :deep(p) {{ margin: 0; }}"
        )

    def _emit_bullet_css(
        css_class: str,
        paragraphs,
        def_p,
    ) -> None:
        """Emit per-(level, kind) bullet CSS for one slot (placeholder or
        text shape).  Pushes lines into the enclosing `lines` list."""
        # Group present paragraphs by (level, kind) → source_para so we
        # know which CSS to emit. Key on BOTH level AND kind because a
        # placeholder can mix char and auto-num bullets at the same level
        # (Vorlage slide 7 ph_14 has auto-num lvl=0 paragraphs AND char
        # lvl=0 URLs in the same slot — keying by level alone made the
        # second kind silently inherit no marker CSS).
        levels_seen: dict[tuple[int, str], "object"] = {}
        for para in paragraphs:
            eff_bullet = para.bullet or def_p.bullet
            if eff_bullet in ("char", "auto-num"):
                key = (para.level, eff_bullet)
                if key not in levels_seen:
                    levels_seen[key] = para

        if not levels_seen:
            return

        for (lvl, kind), para in sorted(levels_seen.items()):
            # Effective bullet props — per-paragraph override wins, else default.
            char       = para.bullet_char        if para.bullet_char        is not None else def_p.bullet_char
            color      = para.bullet_color       if para.bullet_color       is not None else def_p.bullet_color
            font       = para.bullet_font        if para.bullet_font        is not None else def_p.bullet_font
            size_pct   = para.bullet_size_pct    if para.bullet_size_pct    is not None else def_p.bullet_size_pct
            autonum    = para.bullet_autonum_type if para.bullet_autonum_type is not None else def_p.bullet_autonum_type
            # marL / indent for marker positioning (PPT hanging-indent idiom).
            # Slidev's UnoCSS bundle injects a CSS reset that effectively
            # sets ``ul, ol { margin: 0; padding: 0; list-style: none }``
            # globally. Without undoing this inside our scoped layout, the
            # ul/ol containers have NO padding for markers to live in —
            # they hang outside the placeholder edge (the symptom the user
            # showed: bullets to the left of the placeholder's "black bar").
            #
            # So we restore: a sensible padding-left (40 px ≈ browser
            # default), ``list-style: revert`` so the user-agent's native
            # marker rendering kicks back in for our markers, and a
            # neutralised margin so the ul/ol doesn't push down beyond
            # PPT's text-frame top.
            chain_tag = "ul" if kind == "char" else "ol"
            chain = " ".join([chain_tag] * (lvl + 1))
            base_sel = f".slidev-layout {css_class} :deep({chain} > li)"
            container_sel = f".slidev-layout {css_class} :deep({chain})"
            lines.append(f"{container_sel} {{")
            lines.append("  padding-left: 40px;")
            lines.append("  margin: 0;")
            lines.append("  list-style: revert;")
            lines.append("}")

            if kind == "char":
                marker_props: list[str] = []
                if char:
                    esc = char.replace("\\", "\\\\").replace('"', '\\"')
                    marker_props.append(f'  content: "{esc}\\00a0";')
                if color is not None:
                    marker_props.append(f"  color: {_hex_css(color)};")
                if font:
                    marker_props.append(f"  font-family: '{font}', sans-serif;")
                if marker_props:
                    lines.append(f"{base_sel}::marker {{")
                    lines.extend(marker_props)
                    lines.append("}")
            else:  # auto-num
                list_style = _autonum_type_to_css(autonum)
                if list_style:
                    lines.append(f"{base_sel} {{")
                    lines.append(f"  list-style-type: {list_style};")
                    lines.append("}")
                # Auto-num markers: only emit color (when distinct from
                # text). Skip font-family because PPT's buFont reference
                # often resolves to "<Family> Bold" — a synthetic name
                # with no @font-face declaration, so the marker would
                # render in fallback sans-serif at a different size than
                # the surrounding text. Auto-num numbers look fine in
                # the inherited text font.
                if color is not None:
                    lines.append(f"{base_sel}::marker {{")
                    lines.append(f"  color: {_hex_css(color)};")
                    lines.append("}")

    # Invoke the helper for placeholders…
    for ph in slide.placeholders:
        if ph.text_frame is None:
            continue
        _emit_bullet_css(
            f".ph-{ph.idx}",
            ph.text_frame.paragraphs,
            ph.default_para_props,
        )
    # …and for text shapes. Layout-source lists like Vorlage layout 6's
    # "Wer bist Du?" Textfeld 1 had their <ul><li> emitted but no marker
    # CSS to undo Slidev's `list-style: none` reset, so markers were
    # invisible (user complaint: "slide 13 missed to identify the list").
    for shape in slide.text_shapes:
        if shape.text_frame is None:
            continue
        _emit_bullet_css(
            f".txt-{shape.shape_id}",
            shape.text_frame.paragraphs,
            shape.default_para,
        )

    lines.append("</style>")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def emit_layouts(presentation: Presentation, theme_dir: Path) -> None:
    """Write ``theme_dir/layouts/slide<N>.vue`` for each slide."""
    layouts_dir = Path(theme_dir) / "layouts"
    layouts_dir.mkdir(parents=True, exist_ok=True)

    for slide in presentation.slides:
        vue_content = _emit_layout_vue(
            slide, presentation.canvas_width_px, presentation.canvas_height_px
        )
        out_path = layouts_dir / f"slide{slide.index}.vue"
        out_path.write_text(vue_content, encoding="utf-8")
