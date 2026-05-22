"""Emit theme/layouts/slide<N>.vue for each slide in the presentation."""
from __future__ import annotations

from pathlib import Path
from typing import Union

from ..fonts import strip_weight_suffix
from ..model import (
    Fill,
    GradientStop,
    LinearGradientFill,
    NoFill,
    Placeholder,
    Presentation,
    RadialGradientFill,
    RGB,
    Slide,
    SolidFill,
)

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


def _run_props_css(ph: Placeholder) -> list[str]:
    """Return CSS declarations for the placeholder's default run properties."""
    rp = ph.default_run_props
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


def _para_props_css(ph: Placeholder) -> list[str]:
    """Return CSS declarations for the placeholder's default paragraph properties."""
    pp = ph.default_para_props
    parts: list[str] = []
    if pp.align:
        parts.append(f"text-align: {_ALIGN_MAP.get(pp.align, 'left')}")
    if pp.line_spacing_pct is not None:
        parts.append(f"line-height: {pp.line_spacing_pct / 100:.4g}")
    if pp.space_before_pt is not None:
        parts.append(f"--ph-spc-before: {pp.space_before_pt:.4g}pt")
    if pp.space_after_pt is not None:
        parts.append(f"--ph-spc-after: {pp.space_after_pt:.4g}pt")
    return parts


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

    # Vertical anchor via flex
    align_items = _ANCHOR_ALIGN.get(frame_anchor, "flex-start")
    parts.append("display:flex")
    parts.append(f"align-items:{align_items}")

    # TextFrame insets → padding (l, t, r, b → CSS order t r b l)
    tf = ph.text_frame
    if tf is not None:
        l_ins, t_ins, r_ins, b_ins = tf.insets_pt
        # Convert pt → px
        def pt2px(v: float) -> str:
            return f"{v * 96 / 72:.4g}px"
        padding = f"{pt2px(t_ins)} {pt2px(r_ins)} {pt2px(b_ins)} {pt2px(l_ins)}"
        parts.append(f"padding:{padding}")

        if tf.rotation_deg != 0.0:
            # Combine with shape rotation if already present
            rot_total = ph.rotation_deg + tf.rotation_deg
            # Replace the existing transform or add
            parts = [p for p in parts if not p.startswith("transform:")]
            if rot_total != 0.0:
                parts.append(f"transform:rotate({rot_total:.4g}deg)")

    # Run defaults (font, color, weight, etc.)
    parts.extend(_run_props_css(ph))
    # Para defaults (text-align, line-height)
    parts.extend(_para_props_css(ph))

    return "; ".join(parts)


# ---------------------------------------------------------------------------
# Vue template builder
# ---------------------------------------------------------------------------

_INDENT = "  "


def _emit_layout_vue(slide: Slide, canvas_width: int, canvas_height: int) -> str:
    lines: list[str] = []

    lines.append("<template>")
    lines.append(f'{_INDENT}<div class="slidev-layout">')
    lines.append(f'{_INDENT * 2}<div class="slide-root">')

    for ph in slide.placeholders:
        anchor = ph.text_frame.anchor if ph.text_frame else "t"
        style = _placeholder_style(ph, frame_anchor=anchor)
        lines.append(f'{_INDENT * 3}<div class="ph-{ph.idx}" style="{style}">')
        lines.append(f'{_INDENT * 4}<slot name="ph_{ph.idx}" />')
        lines.append(f"{_INDENT * 3}</div>")

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

    # Bullet styling per placeholder
    for ph in slide.placeholders:
        # Collect bullet levels present in this placeholder
        if ph.text_frame is None:
            continue
        levels_with_bullets = set()
        for para in ph.text_frame.paragraphs:
            eff_bullet = para.bullet or ph.default_para_props.bullet
            if eff_bullet in ("char", "auto-num"):
                levels_with_bullets.add(para.level)

        if not levels_with_bullets:
            continue

        # Emit bullet CSS using pure nesting selectors
        # level 0 → ul > li, level 1 → ul ul > li, etc.
        max_level = max(levels_with_bullets)
        for lvl in range(max_level + 1):
            if lvl not in levels_with_bullets:
                continue
            ul_chain = " ".join(["ul"] * (lvl + 1))
            selector = f".slidev-layout .ph-{ph.idx} {ul_chain} li"
            # Default bullet styles – override as needed
            lines.append(f"{selector} {{")
            if lvl == 0:
                lines.append("  list-style-type: disc;")
            elif lvl == 1:
                lines.append("  list-style-type: circle;")
            else:
                lines.append("  list-style-type: square;")
            lines.append("}")

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
