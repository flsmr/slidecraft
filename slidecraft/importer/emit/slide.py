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
from ..fonts import strip_weight_suffix
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
        # Strip weight suffix from font-family so we reference the base
        # @font-face name (matches the _run_to_css logic in emit/layout.py).
        # "Source Sans Pro Bold" splits to family="Source Sans Pro" +
        # implied weight 700; without this split, browsers fall back to
        # the default sans-serif because no @font-face named "Source Sans
        # Pro Bold" is registered.
        weight_from_family: int | None = None
        if "font_family" in deviations:
            base_family, natural = strip_weight_suffix(deviations["font_family"])
            style_parts.append(f"font-family:'{base_family}'")
            if natural != 400 and base_family != deviations["font_family"]:
                weight_from_family = natural
        if "color" in deviations:
            style_parts.append(f"color:{_hex(deviations['color'])}")
        if "font_size_pt" in deviations:
            px = deviations["font_size_pt"] * 96 / 72
            style_parts.append(f"font-size:{px:.4g}px")
        # bold/italic/underline/strike inside span via additional CSS
        if deviations.get("bold"):
            style_parts.append("font-weight:700")
        elif weight_from_family is not None:
            style_parts.append(f"font-weight:{weight_from_family}")
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
        # Strip weight suffix from font-family — same logic as
        # _emit_run_markdown and _run_to_css. See those for the rationale.
        weight_from_family: int | None = None
        if "font_family" in deviations:
            base_family, natural = strip_weight_suffix(deviations["font_family"])
            style_parts.append(f"font-family:'{base_family}'")
            if natural != 400 and base_family != deviations["font_family"]:
                weight_from_family = natural
        if "color" in deviations:
            style_parts.append(f"color:{_hex(deviations['color'])}")
        if "font_size_pt" in deviations:
            px = deviations["font_size_pt"] * 96 / 72
            style_parts.append(f"font-size:{px:.4g}px")
        if deviations.get("bold"):
            style_parts.append("font-weight:700")
        elif weight_from_family is not None:
            style_parts.append(f"font-weight:{weight_from_family}")
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

    # Plain text path.  PPT sometimes stores intentional leading whitespace
    # in <a:t> (e.g. tmp2 slide 12 ph_24 has "    Dozierender..." with four
    # literal leading spaces). Markdown interprets ≥ 4 leading spaces as
    # an indented code block — the text renders in monospace and HTML
    # inside is escaped. To preserve PPT's visual intent without
    # triggering code-block mode, wrap such paragraphs in a `<p>` (which
    # markdown leaves alone) so leading whitespace stays as literal
    # spaces in the paragraph.
    rendered = emit_runs(html_mode=False)
    if rendered.startswith("    ") or rendered.startswith("\t"):
        inner = emit_runs(html_mode=True)
        return f'<p>{inner}</p>'
    return rendered


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
    content.  Bullet paragraphs are joined without blank lines; non-bullet
    paragraphs are separated by one blank line.

    Empty paragraphs (``<a:p>`` carrying only ``<a:endParaRPr>``, no runs)
    are treated as **intentional vertical spacers** — kept in the output
    as blank markdown lines so paragraph breaks become visible — EXCEPT:
      - leading and trailing empties are stripped (PPT's habit of
        terminating a txBody with an endParaRPr-only paragraph);
      - runs of two or more consecutive empties collapse to one.
    This restores the missing blank lines in tmp2 slide 31 (bibliography)
    and recovers the swallowed plain paragraph between two lists on
    tmp2 slide 7's right column.
    """
    def _has_text(para: Paragraph) -> bool:
        return any(
            run.text and run.text != "\n" and run.text.strip()
            for run in para.runs
        )

    _NON_MD_FIELDS = frozenset({"color", "font_size_pt", "font_family"})

    def _has_non_markdownable_runs(para: Paragraph) -> bool:
        """True if any run in *para* carries a deviation markdown can't express.

        Per-run color / font-size / font-family ARE expressible inline as
        ``<span style="...">``, but only outside an indented code block.
        When such a run lives at a list-indent depth that markdown-it
        interprets as a code block (≥4 spaces), the ``<span>`` becomes
        literal text. Treat such lists as candidates for HTML emission.
        """
        for run in para.runs:
            if run.text == "\n":
                continue
            devs = _run_deviations(run, default_run)
            if any(k in devs for k in _NON_MD_FIELDS):
                return True
        return False

    # Classify each paragraph.
    classified: list[tuple[str, Paragraph]] = []
    for p in paragraphs:
        if not _has_text(p):
            classified.append(("blank", p))
        else:
            eff_bullet = p.bullet or default_para.bullet
            kind = "bullet" if eff_bullet in ("char", "auto-num") else "plain"
            classified.append((kind, p))

    # Trim leading + trailing blanks; collapse consecutive blanks to one.
    while classified and classified[0][0] == "blank":
        classified.pop(0)
    while classified and classified[-1][0] == "blank":
        classified.pop()
    collapsed: list[tuple[str, Paragraph]] = []
    for kind, p in classified:
        if kind == "blank" and collapsed and collapsed[-1][0] == "blank":
            continue
        collapsed.append((kind, p))

    # Walk collapsed, grouping consecutive bullets into "list blocks".
    # Each block emits as either flat markdown (`- foo`) or nested HTML
    # `<ul><li>...</li>...</ul>`. Decision rule:
    #
    #   - any para.level >= 1, OR
    #   - any run carries a non-markdownable deviation
    #     → HTML emission (sidesteps markdown's ≥4-space-indent =
    #       code-block trap which turns inline <span> into literal)
    #   - else → markdown (tmp1's case — flat level-0 char bullets)
    out_lines: list[str] = []
    i = 0
    while i < len(collapsed):
        kind, para = collapsed[i]
        if kind == "bullet":
            block_paras: list[Paragraph] = []
            while i < len(collapsed) and collapsed[i][0] == "bullet":
                block_paras.append(collapsed[i][1])
                i += 1
            needs_html = any(
                p.level >= 1 or _has_non_markdownable_runs(p) for p in block_paras
            )
            if out_lines:
                out_lines.append("")  # blank line before block
            if needs_html:
                out_lines.append(_emit_html_list(block_paras, default_run, default_para))
            else:
                for p in block_paras:
                    out_lines.append(
                        _emit_paragraph(
                            p,
                            default_run=default_run,
                            default_para=default_para,
                        )
                    )
        elif kind == "plain":
            if out_lines:
                out_lines.append("")
            out_lines.append(
                _emit_paragraph(
                    para,
                    default_run=default_run,
                    default_para=default_para,
                )
            )
            i += 1
        else:  # blank
            if out_lines:
                out_lines.append("")
            i += 1

    return "\n".join(out_lines)


def _emit_html_list(
    paragraphs: list[Paragraph],
    default_run: Run,
    default_para: Paragraph,
) -> str:
    """Render a contiguous list block as nested ``<ul>`` / ``<ol>`` HTML.

    Used when a block contains paragraphs at level ≥ 1 or any
    non-markdownable per-run style.  The DOM structure mirrors what
    markdown-it produces for a properly-nested markdown list, so the
    existing ``::marker`` CSS in the generated layout (which targets
    ``ul > li::marker`` for level 0, ``ul ul > li::marker`` for level 1,
    etc.) lights up automatically without any per-class selector changes.

    Mixed bullet kinds within one block are not common; the first
    paragraph's bullet kind determines the outer tag for the whole block.
    """
    eff_bullet = paragraphs[0].bullet or default_para.bullet
    tag = "ol" if eff_bullet == "auto-num" else "ul"

    pieces: list[str] = []
    current_level = -1
    for para in paragraphs:
        target = para.level
        # Descend: open inner <ul>/<ol> blocks until we reach target.
        while current_level < target:
            current_level += 1
            pieces.append(f"<{tag}>")
        # Ascend: close inner blocks until current matches target.
        while current_level > target:
            pieces.append(f"</{tag}>")
            current_level -= 1
        # Render runs as inline HTML (mirrors _emit_paragraph's run-merge
        # logic but always in html mode).
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

        # Hoist common font-size to the <li> so ::marker inherits it.
        # Without this, the auto-num/char marker uses the <li>'s
        # font-size (inherited from the placeholder wrapper = level-0
        # default), while the text inside is wrapped in <span style=
        # "font-size:Npx"> at the per-run / per-level deviation —
        # marker LARGER than text. Visible on tmp2 slide 1 where the
        # "1." "2." numbers were noticeably bigger than the list text.
        run_fontsizes: set = set()
        for kind, devs, _text in grouped:
            if kind != "run" or not devs:
                continue
            run_fontsizes.add(devs.get("font_size_pt"))
        li_style = ""
        hoist_fs: float | None = None
        # All non-br runs share a single font-size deviation → hoist.
        if (
            run_fontsizes
            and len(run_fontsizes) == 1
            and None not in run_fontsizes
        ):
            hoist_fs = next(iter(run_fontsizes))
            li_style = f' style="font-size:{hoist_fs:.4g}pt"'

        run_pieces: list[str] = []
        for k, devs, text in grouped:
            if k == "br":
                run_pieces.append("<br/>")
            else:
                # If we hoisted font-size to the <li>, drop it from per-run
                # spans (otherwise we double-emit identical font-size).
                # The span's other deviations (color, weight, family, etc.)
                # still flow through.
                if hoist_fs is not None and devs and "font_size_pt" in devs:
                    devs = {k: v for k, v in devs.items() if k != "font_size_pt"}
                run_pieces.append(_emit_run_html(text, devs or {}))
        inner = "".join(run_pieces)
        pieces.append(f"<li{li_style}>{inner}</li>")
    # Close any remaining open levels.
    while current_level >= 0:
        pieces.append(f"</{tag}>")
        current_level -= 1
    return "".join(pieces)


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
