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
    # Apply markdown markers
    if deviations.get("bold") and deviations.get("italic"):
        text = f"***{text}***"
    elif deviations.get("bold"):
        text = f"**{text}**"
    elif deviations.get("italic"):
        text = f"*{text}*"
    if deviations.get("strike"):
        text = f"~~{text}~~"
    if deviations.get("underline"):
        text = f"<u>{text}</u>"
    return text


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


def _emit_paragraph(para: Paragraph, ph: Placeholder, use_html: bool = False) -> str:
    """Emit a single paragraph.  use_html forces HTML-inside-block mode."""
    default_run = ph.default_run_props

    def emit_runs(html_mode: bool) -> str:
        pieces = []
        for run in para.runs:
            if run.text == "\n":
                pieces.append("<br/>")
                continue
            devs = _run_deviations(run, default_run)
            if html_mode:
                pieces.append(_emit_run_html(run.text, devs))
            else:
                pieces.append(_emit_run_markdown(run.text, devs))
        return "".join(pieces)

    default_para = ph.default_para_props
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

def _emit_slot_content(ph: Placeholder) -> str:
    """Return the markdown/HTML content for a single named slot."""
    if ph.text_frame is None or not ph.text_frame.paragraphs:
        return ""

    rendered_paras: list[str] = []
    for para in ph.text_frame.paragraphs:
        rendered_paras.append(_emit_paragraph(para, ph))

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

    # Global frontmatter
    md_parts.append("---")
    md_parts.append(f"theme: {theme_name}")
    md_parts.append("---")

    for slide in presentation.slides:
        # Slide separator + layout frontmatter
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

    md_parts.append("")

    (deck_dir / "slides.md").write_text(
        "\n".join(md_parts), encoding="utf-8"
    )
