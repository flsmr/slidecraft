"""Layer 3 emit — render a ``TextShape`` into HTML/Vue fragments.

This module turns a :class:`slidecraft.importer.shapes.model.TextShape` into
the snippet that gets dropped into a generated ``theme/layouts/slide<N>.vue``
template (plus, for slide-level shapes, the corresponding ``::txt_<id>::``
body that lives in ``deck/slides.md``).

Three public functions are exposed:

* :func:`render_text_shape_host` — wrapper ``<div class="txt-<id>" ...>``
  with chrome (position, fill, border, rotation, padding, font defaults).
  For ``source == "slide"`` shapes the inner content is a Vue ``<slot/>``;
  for layout/master shapes the inner content is the baked-out HTML
  rendering of the shape's paragraphs.
* :func:`render_text_shape_baked_content` — the inner HTML used by
  layout/master shapes.
* :func:`render_text_shape_slot_content` — the markdown/HTML body that
  goes underneath ``::txt_<id>::`` for slide-level shapes.

The CSS / markdown emission policy mirrors Layer 1.  Run/paragraph defaults
flow through the shared ``_run_to_css`` / ``_para_to_css`` helpers in
``emit/layout.py``; slot-body emission flows through ``emit_slot_body`` in
``emit/slide.py``.  Local helpers here cover only the chrome (fill / border /
position / anchor / insets) and the wrapper-class assembly.
"""
from __future__ import annotations

from typing import Optional

# NOTE: imports from slidecraft.importer.emit.{layout,slide} are LAZY (done
# inside functions below) — emit.layout imports render_text_shape_host from
# this module, so a top-level import here would deadlock the package load.
from slidecraft.importer.model import (
    Fill,
    GradientStop,
    LinearGradientFill,
    NoFill,
    Paragraph,
    RadialGradientFill,
    RGB,
    Run,
    SolidFill,
)
from slidecraft.importer.shapes.model import BorderProps, ShapeGeometry, TextShape


# ---------------------------------------------------------------------------
# Small utilities
# ---------------------------------------------------------------------------

# pt → px at 96 dpi (1pt = 4/3 px). Matches the constant used implicitly by
# emit/layout.py (``v * 96 / 72``).
_PT_TO_PX = 96.0 / 72.0

_ANCHOR_ALIGN = {"t": "flex-start", "ctr": "center", "b": "flex-end"}
_ALIGN_MAP = {"l": "left", "ctr": "center", "r": "right", "just": "justify"}


def _fmt(n: float) -> str:
    """Format a number for CSS — strip trailing zeros, max two decimals."""
    s = f"{n:.2f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s if s else "0"


def _escape_html(text: str) -> str:
    """HTML-escape user text for safe interpolation inside a Vue template body.

    We don't escape attribute-only chars (``"``) here because user text only
    lands inside element bodies via this helper. Style attributes built by
    the wrapper builder use double-quotes around the whole declaration list
    and never embed user text.
    """
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


# ---------------------------------------------------------------------------
# Color / fill helpers (duplicated from emit/layout.py — see module docstring)
# ---------------------------------------------------------------------------

def _hex_css(c: RGB) -> str:
    """Render an :class:`RGB` as ``#RRGGBB`` (or ``rgba(...)`` if alpha < 1)."""
    if c.alpha < 1.0:
        return f"rgba({c.r},{c.g},{c.b},{c.alpha:.4g})"
    return f"#{c.r:02X}{c.g:02X}{c.b:02X}"


def _rgb_css(c: RGB) -> str:
    """Render an :class:`RGB` as ``rgb(...)`` / ``rgba(...)`` (used inside gradient stops)."""
    if c.alpha < 1.0:
        return f"rgba({c.r},{c.g},{c.b},{c.alpha:.4g})"
    return f"rgb({c.r},{c.g},{c.b})"


def _stop_css(stop: GradientStop) -> str:
    return f"{_rgb_css(stop.color)} {stop.position * 100:.4g}%"


def _fill_css(fill: Fill) -> str:
    """Render a :class:`Fill` union member as a CSS ``background`` value."""
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


def _border_css(border: BorderProps) -> str:
    """Render a :class:`BorderProps` as a CSS ``border`` shorthand."""
    width_px = border.width_pt * _PT_TO_PX
    style = border.style if border.style in {"solid", "dashed", "dotted"} else "solid"
    return f"{_fmt(width_px)}px {style} {_hex_css(border.color)}"


# ---------------------------------------------------------------------------
# Wrapper style builder
# ---------------------------------------------------------------------------

def _geometry_to_svg_path(
    geometry: ShapeGeometry,
    width_px: float,
    height_px: float,
) -> Optional[str]:
    """Resolve a :class:`ShapeGeometry` to bare SVG ``d=""`` path data.

    Returns the pre-resolved ``svg_path`` if present (custGeom case), or
    expands the ``preset`` against :func:`pictures.geometry.preset_to_svg_path`.
    Returns ``None`` for unsupported presets — caller should fall back.
    """
    if geometry.svg_path:
        return geometry.svg_path
    if geometry.preset:
        from slidecraft.importer.pictures.geometry import preset_to_svg_path
        return preset_to_svg_path(
            geometry.preset,
            width_px,
            height_px,
            geometry.preset_adjusts,
        )
    return None


def _fill_to_svg_attrs(fill: Fill) -> tuple[str, Optional[str]]:
    """Return ``(fill_value, opacity)`` for an SVG ``fill=""`` attribute.

    Gradient fills surface as a sentinel ``"url(#GRAD)"`` string for now —
    inline gradient `<defs>` are not yet generated; falls back to the first
    stop color.  Solid / no-fill render verbatim.
    """
    if isinstance(fill, NoFill) or fill is None:
        return "none", None
    if isinstance(fill, SolidFill):
        alpha = fill.color.alpha
        opacity = f"{alpha:.3g}" if alpha is not None and alpha < 1.0 else None
        return _hex_css(fill.color), opacity
    # Gradients: pick the first stop's color for now — full gradient
    # rendering on a path needs inline <defs> which we don't generate yet.
    if isinstance(fill, (LinearGradientFill, RadialGradientFill)):
        if fill.stops:
            return _hex_css(fill.stops[0].color), None
    return "none", None


def _build_geometry_svg(
    shape: TextShape,
    d: str,
) -> str:
    """Build an inline ``<svg>`` rendering the shape's path with fill + stroke.

    The SVG is sized 100%×100% of its wrapper and uses a ``viewBox`` matching
    the shape's pixel bbox so the path coordinates (already in pixel space)
    line up. ``preserveAspectRatio="none"`` is used so the SVG fills the
    wrapper exactly — the wrapper is the size of the bbox and rotation lives
    on the wrapper, not the SVG.
    """
    fill_value, fill_opacity = _fill_to_svg_attrs(shape.fill)
    fill_attrs = f' fill="{fill_value}"'
    if fill_opacity is not None:
        fill_attrs += f' fill-opacity="{fill_opacity}"'

    stroke_attrs = ""
    if shape.border is not None:
        stroke_color = _hex_css(shape.border.color)
        stroke_width_px = shape.border.width_pt * _PT_TO_PX
        stroke_attrs = (
            f' stroke="{stroke_color}" stroke-width="{_fmt(stroke_width_px)}"'
        )
        if shape.border.style == "dashed":
            stroke_attrs += ' stroke-dasharray="8 4"'
        elif shape.border.style == "dotted":
            stroke_attrs += ' stroke-dasharray="2 4"'

    width = _fmt(shape.width_px)
    height = _fmt(shape.height_px)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="100%" height="100%" '
        f'viewBox="0 0 {width} {height}" '
        f'preserveAspectRatio="none" '
        f'style="position:absolute;inset:0;overflow:visible">'
        f'<path d="{d}"{fill_attrs}{stroke_attrs}/>'
        f'</svg>'
    )


def _build_wrapper_style(shape: TextShape, *, use_svg_chrome: bool = False) -> str:
    """Assemble the inline ``style="..."`` declaration list for the wrapper div.

    When ``use_svg_chrome`` is ``True`` the wrapper omits its CSS
    ``background`` / ``border`` declarations because an inline ``<svg>``
    child draws them on the path instead.  Position, rotation, opacity,
    flex layout for text, padding, and default text styling still emit
    so any text overlay sits correctly on top of the SVG.
    """
    parts: list[str] = [
        "position:absolute",
        f"left:{_fmt(shape.x_px)}px",
        f"top:{_fmt(shape.y_px)}px",
        f"width:{_fmt(shape.width_px)}px",
        f"height:{_fmt(shape.height_px)}px",
    ]

    if shape.rotation_deg != 0.0:
        parts.append(f"transform:rotate({_fmt(shape.rotation_deg)}deg)")

    if not use_svg_chrome:
        parts.append(f"background:{_fill_css(shape.fill)}")
        if shape.border is not None:
            parts.append(f"border:{_border_css(shape.border)}")

    if shape.opacity != 1.0:
        parts.append(f"opacity:{_fmt(shape.opacity)}")

    # Vertical anchor via flex.  flex-direction:column is required so that
    # multi-paragraph text shapes stack VERTICALLY (each <p> as its own
    # row) rather than laying out horizontally as flex items. Without it,
    # slides 26 / 32 of tmp2 rendered their multi-paragraph disclaimer
    # text shapes as side-by-side columns. The placeholder host
    # (emit/layout.py) and table cells (tables/emit.py) already use this
    # pattern; this brings text shapes in line.
    #
    # With flex-direction:column, the anchor maps to `justify-content`
    # (main axis = vertical), not `align-items` (cross axis = horizontal,
    # which stays at the default `stretch` so paragraphs fill cell width
    # and their per-para text-align centers within that width).
    anchor = shape.text_frame.anchor if shape.text_frame else "t"
    parts.append("display:flex")
    parts.append("flex-direction:column")
    parts.append(f"justify-content:{_ANCHOR_ALIGN.get(anchor, 'flex-start')}")

    # bodyPr insets → padding (insets are stored l, t, r, b; CSS order is t r b l)
    if shape.text_frame is not None:
        l_ins_pt, t_ins_pt, r_ins_pt, b_ins_pt = shape.text_frame.insets_pt
        t_px = t_ins_pt * _PT_TO_PX
        b_px = b_ins_pt * _PT_TO_PX
        l_px = l_ins_pt * _PT_TO_PX
        r_px = r_ins_pt * _PT_TO_PX

        # Clamp insets when they exceed the box dimensions — PPT keeps the
        # anchored side's inset and discards the opposite when they conflict.
        # See emit/layout.py::_placeholder_style for the same logic on
        # placeholders (the IU template's chip on the title page exposes this).
        anchor = shape.text_frame.anchor
        if t_px + b_px > shape.height_px:
            if anchor == "b":
                t_px = max(0.0, shape.height_px - b_px)
            elif anchor == "ctr":
                each = max(0.0, shape.height_px / 2)
                t_px = min(t_px, each)
                b_px = min(b_px, each)
            else:
                b_px = max(0.0, shape.height_px - t_px)
        if l_px + r_px > shape.width_px:
            each = max(0.0, shape.width_px / 2)
            l_px = min(l_px, each)
            r_px = min(r_px, each)

        padding = (
            f"{_fmt(t_px)}px "
            f"{_fmt(r_px)}px "
            f"{_fmt(b_px)}px "
            f"{_fmt(l_px)}px"
        )
        parts.append(f"padding:{padding}")

    # Default paragraph + run defaults via the shared Layer 1 helpers
    # (text-align, line-height, font-family, font-size, color, etc.).
    # spc_var_prefix="txt" keeps the CSS-variable namespace disjoint from
    # placeholder hosts' --ph-spc-* variables.  Lazy import to break the
    # shapes ↔ emit cycle.
    from slidecraft.importer.emit.layout import _para_to_css, _run_to_css
    parts.extend(_para_to_css(shape.default_para, spc_var_prefix="txt"))
    parts.extend(_run_to_css(shape.default_run))

    # PPT clips text that overflows the shape box — but when the shape is
    # drawn via SVG, the stroke is centered on the geometric edge and the
    # half outside the bbox must be visible. Switch to overflow:visible in
    # the SVG-chrome path. (Text overflow for SVG+text shapes is rare; if
    # it bites, a nested clip element can be added later.)
    parts.append("overflow:visible" if use_svg_chrome else "overflow:hidden")

    return "; ".join(parts)


# ---------------------------------------------------------------------------
# Run / paragraph deviation diff (mirrors emit/slide.py)
# ---------------------------------------------------------------------------

_RUN_FIELDS = ("bold", "italic", "underline", "strike", "color", "font_family", "font_size_pt")
_PARA_FIELDS = ("align", "line_spacing_pct", "space_before_pt", "space_after_pt",
                "indent_pt", "margin_left_pt")
_MARKDOWN_ONLY = frozenset({"bold", "italic", "strike"})


def _run_deviations(run: Run, default: Run) -> dict:
    """Return ``{field: run_value}`` for run fields that differ from default."""
    deviations: dict = {}
    for f in _RUN_FIELDS:
        rv = getattr(run, f)
        dv = getattr(default, f)
        if rv is not None and rv != dv:
            deviations[f] = rv
    return deviations


def _para_deviations(para: Paragraph, default: Paragraph) -> dict:
    """Return ``{field: para_value}`` for paragraph fields that differ from default."""
    deviations: dict = {}
    for f in _PARA_FIELDS:
        pv = getattr(para, f)
        dv = getattr(default, f)
        if pv is not None and pv != dv:
            deviations[f] = pv
    return deviations


def _run_span_style(deviations: dict) -> str:
    """Build a ``style="..."`` value string from a run's deviation dict."""
    parts: list[str] = []
    if "color" in deviations:
        parts.append(f"color:{_hex_css(deviations['color'])}")
    if "font_size_pt" in deviations:
        px = deviations["font_size_pt"] * _PT_TO_PX
        parts.append(f"font-size:{_fmt(px)}px")
    if "font_family" in deviations:
        # SINGLE quotes inside the double-quoted style="..." attribute
        # (same fix already applied to emit/slide.py _emit_run_html /
        # _emit_run_markdown). The Vue compiler errors out with
        # "Attribute name cannot contain U+0022" when nested double
        # quotes break the outer attribute parsing.
        # Also strip the PPT weight suffix so the family name matches
        # what Slidev's Google Fonts auto-import registers (mirrors the
        # behaviour in emit/layout.py::_run_to_css).
        from ..fonts import strip_weight_suffix
        base_family, _ = strip_weight_suffix(deviations["font_family"])
        parts.append(f"font-family:'{base_family}'")
    if deviations.get("bold"):
        parts.append("font-weight:700")
    elif deviations.get("bold") is False:
        parts.append("font-weight:400")
    if deviations.get("italic"):
        parts.append("font-style:italic")
    text_dec: list[str] = []
    if deviations.get("underline"):
        text_dec.append("underline")
    if deviations.get("strike"):
        text_dec.append("line-through")
    if text_dec:
        parts.append(f"text-decoration:{' '.join(text_dec)}")
    return ";".join(parts)


def _para_block_style(deviations: dict) -> str:
    """Build a ``style="..."`` value string from a paragraph's deviation dict."""
    parts: list[str] = []
    if "align" in deviations:
        parts.append(f"text-align:{_ALIGN_MAP.get(deviations['align'], 'left')}")
    if "line_spacing_pct" in deviations:
        parts.append(f"line-height:{deviations['line_spacing_pct'] / 100:.4g}")
    if "space_before_pt" in deviations:
        parts.append(f"margin-top:{deviations['space_before_pt']:.4g}pt")
    if "space_after_pt" in deviations:
        parts.append(f"margin-bottom:{deviations['space_after_pt']:.4g}pt")
    if "indent_pt" in deviations:
        parts.append(f"text-indent:{deviations['indent_pt']:.4g}pt")
    if "margin_left_pt" in deviations:
        parts.append(f"padding-left:{deviations['margin_left_pt']:.4g}pt")
    return ";".join(parts)


# ---------------------------------------------------------------------------
# Run emission (HTML and markdown variants)
# ---------------------------------------------------------------------------

def _emit_run_html(text: str, deviations: dict) -> str:
    """Emit a run as HTML — used inside block-level HTML (``<p>``) contexts
    and for baked layout/master content.

    Escapes the user text and applies styling via ``<span>``, ``<strong>``,
    ``<em>``, ``<u>``, ``<s>``.
    """
    escaped = _escape_html(text)
    if not deviations:
        return escaped

    dev_keys = set(deviations.keys())

    # Underline-only → <u>
    if dev_keys == {"underline"} and deviations["underline"]:
        return f"<u>{escaped}</u>"

    non_md = dev_keys - _MARKDOWN_ONLY - {"underline"}
    if non_md:
        style = _run_span_style(deviations)
        return f'<span style="{style}">{escaped}</span>'

    # Markdown-able properties → HTML equivalents
    out = escaped
    if deviations.get("bold") and deviations.get("italic"):
        out = f"<strong><em>{out}</em></strong>"
    elif deviations.get("bold"):
        out = f"<strong>{out}</strong>"
    elif deviations.get("italic"):
        out = f"<em>{out}</em>"
    if deviations.get("strike"):
        out = f"<s>{out}</s>"
    if deviations.get("underline"):
        out = f"<u>{out}</u>"
    return out


def _emit_run_markdown(text: str, deviations: dict) -> str:
    """Emit a run as markdown — used inside markdown paragraph contexts in slot bodies.

    The text is NOT HTML-escaped here because raw text inside a markdown
    paragraph is processed as text; ``<``/``>``/``&`` would only need
    escaping if they form HTML, which the shape model does not produce.
    """
    if not deviations:
        return text

    dev_keys = set(deviations.keys())

    if dev_keys == {"underline"} and deviations["underline"]:
        return f"<u>{text}</u>"

    non_md = dev_keys - _MARKDOWN_ONLY - {"underline"}
    if non_md:
        style = _run_span_style(deviations)
        return f'<span style="{style}">{text}</span>'

    # CommonMark: emphasis markers need non-whitespace adjacency.
    stripped = text.strip()
    if not stripped:
        return text
    lead = text[: len(text) - len(text.lstrip())]
    trail = text[len(text.rstrip()):]
    inner = stripped
    if deviations.get("bold") and deviations.get("italic"):
        inner = f"***{inner}***"
    elif deviations.get("bold"):
        inner = f"**{inner}**"
    elif deviations.get("italic"):
        inner = f"*{inner}*"
    if deviations.get("strike"):
        inner = f"~~{inner}~~"
    if deviations.get("underline"):
        inner = f"<u>{inner}</u>"
    return f"{lead}{inner}{trail}"


# ---------------------------------------------------------------------------
# Paragraph emission helpers (group adjacent identically-styled runs)
# ---------------------------------------------------------------------------

def _group_runs(paragraph: Paragraph, default_run: Run) -> list[tuple[str, dict, str]]:
    """Group adjacent runs that share the same deviation set.

    Returns a list of ``(kind, deviations, text)`` triples where ``kind`` is
    either ``"run"`` (text content) or ``"br"`` (a soft line break). This
    matches the pattern from ``emit/slide.py::_emit_paragraph``.
    """
    grouped: list[tuple[str, dict, str]] = []
    for run in paragraph.runs:
        if run.text == "\n":
            grouped.append(("br", {}, ""))
            continue
        devs = _run_deviations(run, default_run)
        if grouped and grouped[-1][0] == "run" and grouped[-1][1] == devs:
            kind, prev_devs, prev_text = grouped[-1]
            grouped[-1] = (kind, prev_devs, prev_text + run.text)
        else:
            grouped.append(("run", devs, run.text))
    return grouped


def _emit_runs_html(paragraph: Paragraph, default_run: Run) -> str:
    """Render the runs of a paragraph as concatenated HTML."""
    pieces: list[str] = []
    for kind, devs, text in _group_runs(paragraph, default_run):
        if kind == "br":
            pieces.append("<br/>")
        else:
            pieces.append(_emit_run_html(text, devs))
    return "".join(pieces)


def _emit_runs_markdown(paragraph: Paragraph, default_run: Run) -> str:
    """Render the runs of a paragraph as markdown (with inline HTML where needed)."""
    pieces: list[str] = []
    for kind, devs, text in _group_runs(paragraph, default_run):
        if kind == "br":
            pieces.append("<br/>")
        else:
            pieces.append(_emit_run_markdown(text, devs))
    return "".join(pieces)


def _paragraph_has_text(paragraph: Paragraph) -> bool:
    """True iff at least one run carries non-whitespace, non-``\\n`` text."""
    return any(
        run.text and run.text != "\n" and run.text.strip()
        for run in paragraph.runs
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def render_text_shape_host(shape: TextShape) -> str:
    """Render the wrapping ``<div class="txt-<id>" style="...">...</div>``.

    The inner content depends on ``shape.source``:

    * ``"slide"``: a Vue ``<slot name="txt_<shape_id>"/>`` placeholder. The
      actual text body lives in ``deck/slides.md`` under
      ``::txt_<shape_id>::`` and is produced by
      :func:`render_text_shape_slot_content`.
    * ``"layout"`` / ``"master"``: baked-out HTML produced by
      :func:`render_text_shape_baked_content` — these shapes are template
      decoration, not slide-editable user content.

    The returned string is intended for direct interpolation into a
    ``.vue`` ``<template>`` body. No leading or trailing newline is added;
    the caller controls indentation.

    Non-rect geometry (``shape.geometry`` set) emits an inline ``<svg>``
    for the chrome and overlays text on top when present.  Plain
    rectangles use the existing CSS-div path.
    """
    cls = f"txt-{shape.shape_id}"

    # Resolve geometry to bare SVG path data — if available, the wrapper
    # carries no CSS chrome and an inline <svg> renders the shape.
    svg_d: Optional[str] = None
    if shape.geometry is not None:
        svg_d = _geometry_to_svg_path(
            shape.geometry, shape.width_px, shape.height_px
        )

    use_svg_chrome = svg_d is not None
    style = _build_wrapper_style(shape, use_svg_chrome=use_svg_chrome)

    # Build the inner content.  Order matters: SVG goes first so text
    # overlays on top.  Text overlays / slot markers come last.
    pieces: list[str] = []
    if use_svg_chrome:
        pieces.append(_build_geometry_svg(shape, svg_d))

    if shape.source == "slide":
        # Slide-level shapes always get a slot, even when geometry covers
        # the chrome — the slot lets users add overlay text via slides.md.
        pieces.append(f'<slot name="txt_{shape.shape_id}"/>')
    else:
        # Layout/master shapes bake their text content directly.
        baked = render_text_shape_baked_content(shape)
        if baked:
            pieces.append(baked)

    inner = "".join(pieces)
    return f'<div class="{cls}" style="{style}">{inner}</div>'


def render_text_shape_baked_content(shape: TextShape) -> str:
    """Render a layout/master shape's paragraphs as inline HTML.

    Each non-empty paragraph becomes a ``<p>`` element. Paragraph-level
    deviations from ``shape.default_para`` produce a ``style="..."``
    attribute on the ``<p>``. Per-run deviations from ``shape.default_run``
    produce ``<span style="...">`` / ``<strong>`` / ``<em>`` / ``<u>`` /
    ``<s>`` wrappers around the affected text.

    Bulleted paragraphs are rendered as ``<ul><li>...</li></ul>``;
    consecutive bullets at the same nesting level are grouped under one
    ``<ul>``. Numbered bullets use ``<ol>`` instead. Markdown markers are
    NOT used here — this is baked HTML living inside a Vue template, not
    slide markdown.

    If the shape has no text frame or no paragraphs with content, returns
    an empty string.
    """
    if shape.text_frame is None or not shape.text_frame.paragraphs:
        return ""

    default_run = shape.default_run
    default_para = shape.default_para

    out: list[str] = []
    # Track the currently-open list (tag and level) so we can group
    # consecutive bullets cleanly.
    open_list_tag: Optional[str] = None
    open_list_level: int = -1

    def close_list() -> None:
        nonlocal open_list_tag, open_list_level
        if open_list_tag is not None:
            out.append(f"</{open_list_tag}>")
            open_list_tag = None
            open_list_level = -1

    for para in shape.text_frame.paragraphs:
        if not _paragraph_has_text(para):
            continue

        eff_bullet = para.bullet or default_para.bullet
        if eff_bullet in ("char", "auto-num"):
            list_tag = "ol" if eff_bullet == "auto-num" else "ul"
            if open_list_tag != list_tag or open_list_level != para.level:
                close_list()
                out.append(f"<{list_tag}>")
                open_list_tag = list_tag
                open_list_level = para.level
            inner = _emit_runs_html(para, default_run)
            out.append(f"<li>{inner}</li>")
            continue

        close_list()

        inner = _emit_runs_html(para, default_run)
        para_devs = _para_deviations(para, default_para)
        if para_devs:
            style = _para_block_style(para_devs)
            if style:
                out.append(f'<p style="{style}">{inner}</p>')
                continue
        out.append(f"<p>{inner}</p>")

    close_list()
    return "".join(out)


def render_text_shape_slot_content(shape: TextShape) -> str:
    """Render the markdown body of a ``::txt_<id>::`` slot in ``slides.md``.

    Only meaningful for ``shape.source == "slide"``; passing a
    layout/master shape returns an empty string (those are baked into the
    layout ``.vue`` instead — use :func:`render_text_shape_baked_content`).

    Emission policy mirrors Layer 1's placeholder slot content:

    * Plain paragraphs render as plain text separated by blank lines.
    * Per-run deviations use markdown markers (``**bold**``, ``*italic*``,
      ``~~strike~~``) when only bold/italic/strike differ; ``<u>`` for
      underline-only; ``<span style="...">`` for any property that
      markdown cannot express (color, font-size, font-family).
    * Bulleted paragraphs render as ``- text`` / ``1. text`` with two
      spaces of indent per nesting level.
    * Paragraph-level deviations (alignment, line-spacing, spacing,
      indent) wrap the entire paragraph in ``<p style="...">``, and the
      runs inside switch to HTML form (markdown markers don't process
      inside block HTML, per CommonMark).
    """
    if shape.source != "slide":
        return ""
    if shape.text_frame is None or not shape.text_frame.paragraphs:
        return ""

    # Delegate to the shared emit_slot_body helper in emit/slide.py — the
    # same policy used for placeholder slot content, applied to TextShape
    # defaults. Eliminates the ~50-line duplicate that used to live here.
    # Lazy import to break the shapes ↔ emit cycle.
    from slidecraft.importer.emit.slide import emit_slot_body
    return emit_slot_body(
        shape.text_frame.paragraphs,
        shape.default_run,
        shape.default_para,
    )
