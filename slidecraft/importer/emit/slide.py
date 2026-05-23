"""Emit deck/package.json and deck/slides.md."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from ..model import (
    Fill,
    LinearGradientFill,
    NoFill,
    Paragraph,
    Placeholder,
    Presentation,
    RadialGradientFill,
    RGB,
    Run,
    Slide,
    SolidFill,
)
from ..shapes.emit import render_text_shape_slot_content

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _hex(c: RGB) -> str:
    if c.alpha < 1.0:
        return f"rgba({c.r},{c.g},{c.b},{c.alpha:.4g})"
    return f"#{c.r:02X}{c.g:02X}{c.b:02X}"


# ---------------------------------------------------------------------------
# Run emission
# ---------------------------------------------------------------------------

def _run_deviations(run: Run, default: Run) -> dict:
    """Return a dict of field → run_value for fields that differ from default."""
    fields = ("bold", "italic", "underline", "strike", "color", "font_family", "font_size_pt")
    deviations = {}
    for f in fields:
        rv = getattr(run, f)
        dv = getattr(default, f)
        if rv is not None and rv != dv:
            deviations[f] = rv
    return deviations


_MARKDOWN_ONLY = frozenset({"bold", "italic", "strike"})


def _emit_run_markdown(text: str, deviations: dict) -> str:
    """Emit run as markdown text with inline markers/HTML (no block HTML context)."""
    if not deviations:
        return text

    dev_keys = set(deviations.keys())

    # Underline-only → <u>
    if dev_keys == {"underline"} and deviations["underline"]:
        return f"<u>{text}</u>"

    # If there are non-markdown properties, use <span style="…">
    non_md = dev_keys - _MARKDOWN_ONLY - {"underline"}
    if non_md:
        style_parts = []
        if "color" in deviations:
            style_parts.append(f"color:{_hex(deviations['color'])}")
        if "font_size_pt" in deviations:
            px = deviations["font_size_pt"] * 96 / 72
            style_parts.append(f"font-size:{px:.4g}px")
        if "font_family" in deviations:
            style_parts.append(f'font-family:"{deviations["font_family"]}"')
        # bold/italic/underline/strike inside span via additional CSS
        if deviations.get("bold"):
            style_parts.append("font-weight:700")
        elif deviations.get("bold") is False:
            style_parts.append("font-weight:400")
        if deviations.get("italic"):
            style_parts.append("font-style:italic")
        text_dec = []
        if deviations.get("underline"):
            text_dec.append("underline")
        if deviations.get("strike"):
            text_dec.append("line-through")
        if text_dec:
            style_parts.append(f"text-decoration:{' '.join(text_dec)}")
        style = ";".join(style_parts)
        return f'<span style="{style}">{text}</span>'

    # Only markdown-able properties (subset of bold/italic/strike)
    # CommonMark requires non-whitespace adjacent to emphasis markers, so peel
    # leading/trailing whitespace out of the wrapped span.
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


def _emit_run_html(text: str, deviations: dict) -> str:
    """Emit run as HTML (inside a block-level HTML element — no markdown markers)."""
    if not deviations:
        return text

    dev_keys = set(deviations.keys())

    # Underline only → <u>
    if dev_keys == {"underline"} and deviations["underline"]:
        return f"<u>{text}</u>"

    # Non-markdown properties → <span>
    non_md = dev_keys - _MARKDOWN_ONLY - {"underline"}
    if non_md:
        style_parts = []
        if "color" in deviations:
            style_parts.append(f"color:{_hex(deviations['color'])}")
        if "font_size_pt" in deviations:
            px = deviations["font_size_pt"] * 96 / 72
            style_parts.append(f"font-size:{px:.4g}px")
        if "font_family" in deviations:
            style_parts.append(f'font-family:"{deviations["font_family"]}"')
        if deviations.get("bold"):
            style_parts.append("font-weight:700")
        elif deviations.get("bold") is False:
            style_parts.append("font-weight:400")
        if deviations.get("italic"):
            style_parts.append("font-style:italic")
        text_dec = []
        if deviations.get("underline"):
            text_dec.append("underline")
        if deviations.get("strike"):
            text_dec.append("line-through")
        if text_dec:
            style_parts.append(f"text-decoration:{' '.join(text_dec)}")
        style = ";".join(style_parts)
        return f'<span style="{style}">{text}</span>'

    # Only markdown-able properties → HTML equivalents
    if deviations.get("bold") and deviations.get("italic"):
        text = f"<strong><em>{text}</em></strong>"
    elif deviations.get("bold"):
        text = f"<strong>{text}</strong>"
    elif deviations.get("italic"):
        text = f"<em>{text}</em>"
    if deviations.get("strike"):
        text = f"<s>{text}</s>"
    if deviations.get("underline"):
        text = f"<u>{text}</u>"
    return text


# ---------------------------------------------------------------------------
# Paragraph emission
# ---------------------------------------------------------------------------

_ALIGN_MAP = {"l": "left", "ctr": "center", "r": "right", "just": "justify"}


def _para_deviations(para: Paragraph, default: Paragraph) -> dict:
    """Return paragraph-level deviations from the default (non-bullet)."""
    fields = ("align", "line_spacing_pct", "space_before_pt", "space_after_pt",
              "indent_pt", "margin_left_pt")
    deviations = {}
    for f in fields:
        pv = getattr(para, f)
        dv = getattr(default, f)
        if pv is not None and pv != dv:
            deviations[f] = pv
    return deviations


def _para_style(deviations: dict) -> str:
    parts = []
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


def _emit_paragraph(
    para: Paragraph,
    ph: Optional[Placeholder] = None,
    use_html: bool = False,
    *,
    default_run: Optional[Run] = None,
    default_para: Optional[Paragraph] = None,
) -> str:
    """Emit a single paragraph.  use_html forces HTML-inside-block mode.

    Either pass ``ph`` (preferred for placeholder content) and the defaults
    are taken from it, or pass ``default_run`` + ``default_para`` directly
    (used by TextShape emission via shapes.emit).
    """
    if default_run is None:
        default_run = ph.default_run_props if ph is not None else Run(text="")
    if default_para is None:
        default_para = ph.default_para_props if ph is not None else Paragraph(runs=[])

    def emit_runs(html_mode: bool) -> str:
        # Merge adjacent runs with identical deviation sets so we emit one
        # markdown wrapper (or one <span>) per stretch of same-styled text
        # instead of many tiny ones that produce broken markers.
        grouped: list[tuple[str, dict | None, str]] = []
        for run in para.runs:
            if run.text == "\n":
                grouped.append(("br", None, ""))
                continue
            devs = _run_deviations(run, default_run)
            if grouped and grouped[-1][0] == "run" and grouped[-1][1] == devs:
                grouped[-1] = ("run", devs, grouped[-1][2] + run.text)
            else:
                grouped.append(("run", devs, run.text))

        pieces = []
        for kind, devs, text in grouped:
            if kind == "br":
                pieces.append("<br/>")
            elif html_mode:
                pieces.append(_emit_run_html(text, devs or {}))
            else:
                pieces.append(_emit_run_markdown(text, devs or {}))
        return "".join(pieces)

    eff_bullet = para.bullet or default_para.bullet
    para_devs = _para_deviations(para, default_para)

    if use_html:
        # Already inside a block — just emit runs as HTML
        return emit_runs(html_mode=True)

    if eff_bullet in ("char", "auto-num"):
        # Bullet paragraph — prefix with markdown bullet marker
        # Indentation for nested levels: two spaces per level beyond 0
        indent = "  " * para.level
        if eff_bullet == "auto-num":
            prefix = "1. "
        else:
            prefix = "- "
        content = emit_runs(html_mode=False)
        return f"{indent}{prefix}{content}"

    if para_devs:
        # Paragraph has deviating properties → wrap in <p style="…">
        style = _para_style(para_devs)
        if style:
            inner = emit_runs(html_mode=True)
            return f'<p style="{style}">{inner}</p>'

    return emit_runs(html_mode=False)


# ---------------------------------------------------------------------------
# Placeholder slot content
# ---------------------------------------------------------------------------

def emit_slot_body(
    paragraphs: list[Paragraph],
    default_run: Run,
    default_para: Paragraph,
) -> str:
    """Return the markdown/HTML body for a slot, given paragraphs + defaults.

    Public helper — shapes.emit calls this directly to render TextShape slot
    content. Empty paragraphs are filtered. Bullet paragraphs are joined
    without blank lines; non-bullet paragraphs separated by one blank line.
    """
    rendered_paras: list[str] = []
    for para in paragraphs:
        # Skip paragraphs whose runs together have no actual text content.
        # Without this we emit useless `- ` lines and empty `<p style="...">`
        # wrappers for paragraphs that exist only to override formatting on
        # blank lines in the PPT source.
        has_text = any(
            run.text and run.text != "\n" and run.text.strip()
            for run in para.runs
        )
        if not has_text:
            continue
        rendered_paras.append(
            _emit_paragraph(
                para,
                default_run=default_run,
                default_para=default_para,
            )
        )

    # Join consecutive bullet paragraphs directly (one newline),
    # separate non-bullet paragraphs with a blank line.
    lines: list[str] = []
    for i, rp in enumerate(rendered_paras):
        is_bullet = rp.lstrip().startswith("- ") or rp.lstrip().startswith("1. ")
        prev_is_bullet = (
            i > 0
            and (
                rendered_paras[i - 1].lstrip().startswith("- ")
                or rendered_paras[i - 1].lstrip().startswith("1. ")
            )
        )

        if i == 0:
            lines.append(rp)
        elif is_bullet and prev_is_bullet:
            lines.append(rp)
        else:
            lines.append("")
            lines.append(rp)

    return "\n".join(lines)


def _emit_slot_content(ph: Placeholder) -> str:
    """Return the markdown/HTML content for a placeholder slot (thin wrapper)."""
    if ph.text_frame is None or not ph.text_frame.paragraphs:
        return ""
    return emit_slot_body(
        ph.text_frame.paragraphs,
        ph.default_run_props,
        ph.default_para_props,
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def emit_deck(
    presentation: Presentation,
    deck_dir: Path,
    theme_relative_path: str,
    theme_name: str = "slidev-theme-slidecraft-tmp",
) -> None:
    """Write ``deck_dir/package.json`` and ``deck_dir/slides.md``."""
    deck_dir = Path(deck_dir)
    deck_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ #
    # package.json
    # ------------------------------------------------------------------ #
    pkg = {
        "private": True,
        "scripts": {
            "dev": "slidev",
            "build": "slidev build",
            "export": "slidev export",
        },
        "dependencies": {
            "@slidev/cli": "^52.0.0",
            theme_name: f"file:{theme_relative_path}",
        },
    }
    (deck_dir / "package.json").write_text(
        json.dumps(pkg, indent=2), encoding="utf-8"
    )

    # ------------------------------------------------------------------ #
    # slides.md
    # ------------------------------------------------------------------ #
    md_parts: list[str] = []

    if not presentation.slides:
        md_parts.append("---")
        md_parts.append(f"theme: {theme_name}")
        md_parts.append("---")

    for i, slide in enumerate(presentation.slides):
        if i == 0:
            # First slide frontmatter carries the deck-level theme: declaration.
            # Slidev parses this as slide 1, not a separate cover.
            md_parts.append("---")
            md_parts.append(f"theme: {theme_name}")
            md_parts.append(f"layout: slide{slide.index}")
            md_parts.append("---")
        else:
            md_parts.append("")
            md_parts.append("---")
            md_parts.append(f"layout: slide{slide.index}")
            md_parts.append("---")

        for ph in slide.placeholders:
            md_parts.append("")
            md_parts.append(f"::ph_{ph.idx}::")
            content = _emit_slot_content(ph)
            if content:
                md_parts.append(content)

        # Layer 3 — slide-source non-placeholder text shapes surface as
        # ::txt_<id>:: slots. Layout/master-source shapes are baked into
        # the layout .vue and don't appear in slides.md.
        for shape in slide.text_shapes:
            if shape.source != "slide":
                continue
            md_parts.append("")
            md_parts.append(f"::txt_{shape.shape_id}::")
            content = render_text_shape_slot_content(shape)
            if content:
                md_parts.append(content)

    md_parts.append("")

    (deck_dir / "slides.md").write_text(
        "\n".join(md_parts), encoding="utf-8"
    )
