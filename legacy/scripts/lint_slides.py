"""Pre-flight lint for Slidecraft slide files.

Runs before the slide-critic agent. The critic handles judgment-call review
(is this title doing its job? is the body restating the title?); this lint
handles the *mechanical* errors that have repeatedly broken Slidev renders —
semantic-vs-physical name confusion, image-in-named-slot Vite import errors,
formula-in-title, multi-paragraph slot blocks, and so on. The findings here
are things that would either make Slidev render a blank slide silently or
crash with an obscure error — never matters of taste.

The lint walks ``<deck-dir>/slides/*.md``, validates each, prints findings,
and exits with a code the caller can branch on:

* ``0`` — no errors (and, if ``--strict``, no warnings either)
* ``1`` — at least one error
* ``2`` — only with ``--strict``: at least one warning was promoted to error

Each finding is printed as::

    <severity>  <slide>:<line>  <rule>  <message>
                                          suggested fix: <fix>

Pure stdlib. No YAML dependency — frontmatter is parsed line-by-line for
the keys we actually care about (``layout``, ``sources``, ``title``). That
keeps the lint zero-install and fast.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence


# ---------------------------------------------------------------------------
# Severity + finding model
# ---------------------------------------------------------------------------


ERROR = "ERROR"
WARNING = "WARNING"


@dataclass
class Finding:
    """One lint result.

    ``rule`` is a short stable id (e.g. ``L1``, ``L6``) so callers can grep
    for specific findings. ``line`` is 1-indexed within the slide file (or
    1 for whole-file issues). ``fix`` may be empty if no actionable hint.
    """

    severity: str
    file: Path
    line: int
    rule: str
    message: str
    fix: str = ""

    def format(self, deck_dir: Path) -> str:
        try:
            rel = self.file.resolve().relative_to(deck_dir.resolve()).as_posix()
        except ValueError:
            rel = self.file.as_posix()
        header = f"{self.severity:7s} {rel}:{self.line}  {self.rule}  {self.message}"
        if self.fix:
            # Indent the fix under the message so a long run of findings is
            # visually scannable — the severity column lines up.
            pad = " " * (7 + 1 + len(rel) + 1 + len(str(self.line)) + 2
                         + len(self.rule) + 2)
            return f"{header}\n{pad}suggested fix: {self.fix}"
        return header


# ---------------------------------------------------------------------------
# Slide model — what we extract from each file
# ---------------------------------------------------------------------------


@dataclass
class SlotBlock:
    """One ``::slot-name::`` block: its name, body lines, and line range."""

    name: str
    name_line: int          # 1-indexed line where ``::name::`` appears
    body_lines: list[str] = field(default_factory=list)
    body_start: int = 0     # 1-indexed line of the first body line
    body_end: int = 0       # 1-indexed line of the last body line (inclusive)


@dataclass
class SlideFile:
    """Parsed view of a slide markdown file used by the lint rules."""

    path: Path
    raw: str
    frontmatter_text: str = ""              # everything between the --- fences
    frontmatter_end_line: int = 0           # 1-indexed line of the closing ---
    has_frontmatter: bool = False
    yaml_error: str = ""                    # populated if frontmatter unparseable
    layout: str | None = None
    layout_line: int = 0
    title_field: str | None = None          # from ``title:`` frontmatter
    sources_keys: list[tuple[str, int]] = field(default_factory=list)  # (key, line)
    slots: list[SlotBlock] = field(default_factory=list)
    last_html_comment: str = ""             # used for the speaker-notes heuristic


# ---------------------------------------------------------------------------
# Frontmatter + slide parsing
# ---------------------------------------------------------------------------


_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*(?:\n|$)", re.DOTALL)
_SLOT_RE = re.compile(r"^::([A-Za-z0-9_\-]+)::\s*$")
_IMG_MD_RE = re.compile(r"!\[[^\]]*\]\([^)]+\)")
_IMG_HTML_RE = re.compile(r"<img\s+[^>]*src=", re.IGNORECASE)
_HTML_COMMENT_RE = re.compile(r"<!--(.*?)-->", re.DOTALL)


def parse_slide(path: Path) -> SlideFile:
    """Read *path* and extract everything the lint rules need.

    Robust to slightly malformed input — a slide with bad YAML still gets
    parsed for its slot blocks so the lint can flag the YAML error alongside
    any structural issues. We never raise from here; downstream rules check
    the populated fields and emit findings.
    """
    raw = path.read_text(encoding="utf-8")
    slide = SlideFile(path=path, raw=raw)

    # ----- frontmatter -------------------------------------------------------
    m = _FRONTMATTER_RE.match(raw)
    if m:
        slide.has_frontmatter = True
        slide.frontmatter_text = m.group(1)
        # The closing --- is on the line right after the YAML body. Count
        # newlines in m.group(0) to locate it.
        slide.frontmatter_end_line = m.group(0).count("\n")
        body_offset = m.end()
        body_lines_offset = raw[:body_offset].count("\n")
        _parse_frontmatter_fields(slide)
    else:
        body_offset = 0
        body_lines_offset = 0

    # ----- slot blocks -------------------------------------------------------
    lines = raw.splitlines()
    current: SlotBlock | None = None
    for idx, line in enumerate(lines, start=1):
        # Anything in the frontmatter region is not a slot block.
        if idx <= body_lines_offset:
            continue
        match = _SLOT_RE.match(line)
        if match:
            # Close out the previous block at the line before this one.
            if current is not None:
                current.body_end = idx - 1
                _trim_slot_body(current)
                slide.slots.append(current)
            current = SlotBlock(name=match.group(1), name_line=idx,
                                body_start=idx + 1)
            continue
        # Stop accumulating into a slot block as soon as we hit a top-level
        # HTML comment — context blocks and speaker notes are NOT part of any
        # slot. Use the start of the comment marker as the terminator.
        if current is not None and line.lstrip().startswith("<!--"):
            current.body_end = idx - 1
            _trim_slot_body(current)
            slide.slots.append(current)
            current = None
            continue
        if current is not None:
            current.body_lines.append(line)

    if current is not None:
        current.body_end = len(lines)
        _trim_slot_body(current)
        slide.slots.append(current)

    # ----- last HTML comment (Slidev's speaker-notes convention) -------------
    comments = _HTML_COMMENT_RE.findall(raw)
    if comments:
        slide.last_html_comment = comments[-1].strip()

    return slide


def _trim_slot_body(block: SlotBlock) -> None:
    """Drop leading/trailing all-whitespace lines from a slot body.

    Keeps the body_start/body_end accurate to the first/last *real* content
    line so the multi-paragraph (blank-line-inside) check is meaningful —
    we don't want a trailing blank line before the next ``::slot::`` to
    register as "blank inside the body".
    """
    while block.body_lines and not block.body_lines[0].strip():
        block.body_lines.pop(0)
        block.body_start += 1
    while block.body_lines and not block.body_lines[-1].strip():
        block.body_lines.pop()
        block.body_end -= 1


def _parse_frontmatter_fields(slide: SlideFile) -> None:
    """Extract the handful of fields the lint cares about, line-by-line.

    We deliberately avoid a real YAML parser: stdlib has none, and the
    fields we need (``layout``, ``title``, ``sources[].key``) are a regular
    enough subset that regex parsing is unambiguous. If the frontmatter has
    syntax that *would* fail a real YAML parser (unclosed quote, tabs in
    indentation), we attempt a best-effort detection here and populate
    ``yaml_error`` so the L5 rule fires.
    """
    text = slide.frontmatter_text
    # Best-effort YAML sanity check — catches the common breakage modes
    # without pulling in PyYAML. We flag unbalanced quotes on a value line
    # and tabs (YAML forbids tabs for indentation).
    for offset, raw_line in enumerate(text.splitlines(), start=2):
        # offset starts at 2 because the opening --- is line 1.
        if "\t" in raw_line and raw_line.lstrip(" ") != raw_line.lstrip():
            slide.yaml_error = (f"tab character in indentation at line {offset} "
                                f"(YAML forbids tabs)")
            return
        # Quote balance check — only on key:value lines, only when a quote
        # is the leading character of the value. Multi-line YAML strings
        # (block scalar |, > ) are out of scope for our subset.
        kv = re.match(r"^\s*[A-Za-z_][\w\-]*\s*:\s*(.+?)\s*$", raw_line)
        if kv:
            value = kv.group(1)
            if value.startswith('"') and (value.count('"') % 2) != 0:
                slide.yaml_error = (f"unbalanced double-quote in value at "
                                    f"line {offset}")
                return
            if value.startswith("'") and (value.count("'") % 2) != 0:
                slide.yaml_error = (f"unbalanced single-quote in value at "
                                    f"line {offset}")
                return

    # ----- layout ------------------------------------------------------------
    for offset, raw_line in enumerate(text.splitlines(), start=2):
        m = re.match(r"^layout:\s*(\S+)\s*$", raw_line)
        if m:
            slide.layout = m.group(1).strip().strip('"').strip("'")
            slide.layout_line = offset
            break

    # ----- title (frontmatter form) ------------------------------------------
    for raw_line in text.splitlines():
        m = re.match(r"^title:\s*(.+?)\s*$", raw_line)
        if m:
            slide.title_field = m.group(1).strip().strip('"').strip("'")
            break

    # ----- sources[].key -----------------------------------------------------
    in_sources = False
    for offset, raw_line in enumerate(text.splitlines(), start=2):
        if re.match(r"^sources\s*:\s*(\[\s*\])?\s*$", raw_line):
            in_sources = True
            continue
        if in_sources:
            # A top-level key (no leading indent followed by ``:``) closes
            # the sources list.
            if re.match(r"^[A-Za-z_][\w\-]*\s*:", raw_line):
                in_sources = False
                continue
            m = re.match(r"^\s*-\s*key\s*:\s*(\S+)\s*$", raw_line)
            if m:
                key = m.group(1).strip().strip('"').strip("'")
                slide.sources_keys.append((key, offset))


# ---------------------------------------------------------------------------
# Theme resolution
# ---------------------------------------------------------------------------


@dataclass
class ThemeInfo:
    """What we need from the theme to validate layout + slot names.

    ``aliases`` mirrors the JSON shape: ``{semantic_name: {"layout": str,
    "slots": {semantic: physical}, ...}}``. ``physical_layouts`` is the set
    of all ``layout`` values across aliases — used to test whether a slide's
    ``layout:`` value is "physical" in the sense of "actually corresponds
    to a slideN.vue exposed by the theme".
    """

    path: Path
    aliases: dict[str, dict]
    physical_layouts: set[str]


def resolve_theme(deck_dir: Path) -> tuple[ThemeInfo | None, str]:
    """Resolve the theme directory and load ``semantic-layouts.json``.

    Returns ``(info, diagnostic)``. ``info`` is None when the theme can't
    be found or its JSON can't be parsed; *diagnostic* is a one-line human
    string the caller surfaces as a warning. The caller then skips the
    theme-dependent rules (L1, L2) for that run.

    Resolution order:
      1. ``<deck>/.slidecraft.json``'s ``theme.path`` (relative to deck).
      2. Scan ``<deck>/slides.md`` frontmatter for a ``theme:`` line; walk
         the deck's parent chain looking for a sibling ``slidecraft-themes``
         directory; within it, find a subdir whose ``slidev-theme-*`` child
         matches the theme name (or where any subdir matches the theme
         name directly).
    """
    # ----- (1) explicit config -----------------------------------------------
    config_path = deck_dir / ".slidecraft.json"
    if config_path.is_file():
        try:
            cfg = json.loads(config_path.read_text(encoding="utf-8"))
            theme_path = cfg.get("theme", {}).get("path")
            if theme_path:
                tp = (deck_dir / theme_path).resolve()
                info = _load_theme(tp)
                if info is not None:
                    return info, ""
                return None, f"theme at {tp} has no semantic-layouts.json"
        except (OSError, json.JSONDecodeError) as exc:
            return None, f".slidecraft.json unreadable: {exc}"

    # ----- (2) scan slides.md ------------------------------------------------
    slides_md = deck_dir / "slides.md"
    theme_name: str | None = None
    if slides_md.is_file():
        text = slides_md.read_text(encoding="utf-8")
        m = _FRONTMATTER_RE.match(text)
        if m:
            for raw_line in m.group(1).splitlines():
                tm = re.match(r"^theme:\s*(\S+)\s*$", raw_line)
                if tm:
                    theme_name = tm.group(1).strip().strip('"').strip("'")
                    break
    if not theme_name:
        return None, "no theme: in slides.md frontmatter and no .slidecraft.json"

    # Walk up looking for a sibling slidecraft-themes directory. The shared
    # OneDrive layout puts decks and themes as siblings of an outer folder.
    for ancestor in [deck_dir, *deck_dir.parents]:
        themes_root = ancestor.parent / "slidecraft-themes" if ancestor.parent else None
        candidates: list[Path] = []
        if themes_root and themes_root.is_dir():
            candidates.append(themes_root)
        also = ancestor / "slidecraft-themes"
        if also.is_dir():
            candidates.append(also)
        for themes_dir in candidates:
            # Each immediate subdir of slidecraft-themes is a "theme bundle".
            # Inside that, look for a child whose folder name matches the
            # theme name (typical layout: ``ILSE-theme/slidev-theme-ilse/``).
            for bundle in themes_dir.iterdir():
                if not bundle.is_dir():
                    continue
                direct = bundle / theme_name
                if direct.is_dir():
                    info = _load_theme(direct)
                    if info is not None:
                        return info, ""
                # Fallback — the bundle itself may be the theme dir.
                if bundle.name == theme_name:
                    info = _load_theme(bundle)
                    if info is not None:
                        return info, ""
    return None, (f"could not locate theme '{theme_name}' under any "
                  f"slidecraft-themes/ sibling directory")


def _load_theme(theme_dir: Path) -> ThemeInfo | None:
    """Load ``semantic-layouts.json`` from *theme_dir* if present."""
    jpath = theme_dir / "semantic-layouts.json"
    if not jpath.is_file():
        return None
    try:
        data = json.loads(jpath.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    aliases = data.get("aliases") or {}
    physical = set()
    for alias_data in aliases.values():
        layout = alias_data.get("layout")
        if layout:
            physical.add(layout)
    return ThemeInfo(path=theme_dir, aliases=aliases,
                     physical_layouts=physical)


# ---------------------------------------------------------------------------
# references.bib helpers
# ---------------------------------------------------------------------------


_BIB_KEY_RE = re.compile(r"@\w+\s*\{\s*([^,\s]+)\s*,")


def load_bib_keys(deck_dir: Path) -> set[str] | None:
    """Return cite keys present in ``<deck>/references.bib``, or None if absent."""
    bib_path = deck_dir / "references.bib"
    if not bib_path.is_file():
        return None
    try:
        text = bib_path.read_text(encoding="utf-8")
    except OSError:
        return set()
    return set(_BIB_KEY_RE.findall(text))


# ---------------------------------------------------------------------------
# The rules
# ---------------------------------------------------------------------------


# Markers used by the "formula or single uppercase letter in title" rule.
# Each catches a different presentation crime: LaTeX dollars/macros, a bare
# uppercase letter dropped into prose (matrix names), or a math operator
# that should live in the body or notes.
_FORMULA_DOLLAR_RE = re.compile(r"\$\$|\$[^$]+\$")
_FORMULA_MACRO_RE = re.compile(r"\\[a-zA-Z]+")
_BARE_UPPER_RE = re.compile(r"(?:^|\s)([A-Z])(?:\s|$|[.,;:])")
_MATH_OP_CHARS = set("=≠·×÷±∝∈⊆⊂≤≥<>")


_TITLE_SLOT_NAMES = {"title", "Title"}


def _slot_for(theme: ThemeInfo | None,
              layout_value: str | None,
              ) -> dict | None:
    """Return the alias dict whose ``layout`` matches *layout_value*."""
    if theme is None or not layout_value:
        return None
    for alias in theme.aliases.values():
        if alias.get("layout") == layout_value:
            return alias
    return None


def _alias_for_semantic(theme: ThemeInfo, name: str) -> dict | None:
    """Return the alias dict keyed by *name* (semantic-name lookup)."""
    return theme.aliases.get(name)


# Each rule is a function returning a list of Findings. They take the slide
# (always), the resolved theme (when needed), and shared state from the
# deck-level walk (bib keys, prior layouts) where applicable.


def rule_l1_layout_is_physical(slide: SlideFile,
                               theme: ThemeInfo | None,
                               ) -> list[Finding]:
    """L1 — slide's ``layout:`` must be the physical name, not the semantic.

    Slidev resolves ``layout:`` against actual ``.vue`` files under
    ``layouts/``. Writing ``layout: content-image`` when the theme exposes
    ``slide5.vue`` produces a silent fallback to Slidev's built-in layout —
    the user sees a blank slide. We detect by: if the layout value happens
    to also be an alias key AND that alias's ``layout`` value differs, it's
    almost certainly the semantic name authored by mistake.
    """
    if theme is None or not slide.layout:
        return []
    layout = slide.layout
    # Deck-local layouts (<deck>/layouts/*.vue) are merged by Slidev with
    # the theme's and are first-class: the ILSE decks define slidefigure,
    # gallery, agenda, and a slide1 override there. Anything with a local
    # .vue file is valid by construction.
    deck_dir = slide.path.parent.parent
    if (deck_dir / "layouts" / f"{layout}.vue").is_file():
        return []
    # The intended-physical case: matches a ``slideN`` file directly.
    if re.fullmatch(r"slide\d+", layout):
        if layout not in theme.physical_layouts:
            # Physical-looking but not declared by the theme — flag, but
            # softly; some themes have unmapped layouts that still exist
            # on disk. We treat this as ERROR since we can't see disk.
            return [Finding(
                severity=ERROR, file=slide.path, line=slide.layout_line,
                rule="L1",
                message=(f"layout '{layout}' is not declared in any alias "
                         f"of semantic-layouts.json"),
                fix=(f"use one of: "
                     f"{', '.join(sorted(theme.physical_layouts)) or '(none)'}"),
            )]
        return []
    # Not slideN — is it a semantic alias key?
    alias = theme.aliases.get(layout)
    if alias is not None:
        physical = alias.get("layout")
        if physical and physical != layout:
            return [Finding(
                severity=ERROR, file=slide.path, line=slide.layout_line,
                rule="L1",
                message=(f"'{layout}' is the semantic alias name; Slidev "
                         f"needs the physical layout file name"),
                fix=f"rename to '{physical}'",
            )]
    # Unknown layout value entirely.
    return [Finding(
        severity=ERROR, file=slide.path, line=slide.layout_line, rule="L1",
        message=(f"layout '{layout}' is neither a physical 'slideN' file "
                 f"nor a known semantic alias"),
        fix=(f"use a physical layout name "
             f"({', '.join(sorted(theme.physical_layouts)) or 'see theme'})"),
    )]


def rule_l2_slot_names_physical(slide: SlideFile,
                                theme: ThemeInfo | None,
                                ) -> list[Finding]:
    """L2 — slot blocks must use the alias's physical slot names (values)."""
    if theme is None or not slide.layout:
        return []
    alias = _slot_for(theme, slide.layout)
    if alias is None:
        # No alias matches this physical layout — we can't validate slot
        # names. Don't error: the slide might be using an unmapped layout
        # legitimately. L1 will have flagged the layout itself if needed.
        return []
    physical_slots = set(alias.get("slots", {}).values())
    # Keys are semantic; values are physical. If a slide author writes
    # ``::body::`` when the slots map is ``{body: body-16}``, the slot is
    # silently invisible — Slidev only fills slots whose <slot name=X />
    # declarations match.
    semantic_to_physical: dict[str, str] = {
        k: v for k, v in alias.get("slots", {}).items() if k != v
    }
    findings: list[Finding] = []
    for block in slide.slots:
        if block.name in physical_slots:
            continue
        # Semantic name used by mistake — point at the corrected physical.
        if block.name in semantic_to_physical:
            findings.append(Finding(
                severity=ERROR, file=slide.path, line=block.name_line,
                rule="L2",
                message=(f"'::{block.name}::' is the semantic slot name; "
                         f"this layout's alias maps "
                         f"{block.name} → {semantic_to_physical[block.name]}"),
                fix=f"rename to '::{semantic_to_physical[block.name]}::'",
            ))
            continue
        # Some themes expose slots that aren't declared in semantic-layouts
        # (e.g. shared scaffolding slots). Be conservative — emit only if
        # the slot's name is clearly not a physical-looking one either.
        # We don't have the full layout SFC, so we can't confirm; restrict
        # the error to the common semantic synonyms.
        if block.name in {"title", "body", "image", "citations", "subtitle"}:
            # ``title`` happens to be both semantic AND physical in the
            # ILSE theme for many aliases — only flag when the alias's
            # ``slots[block.name]`` exists and differs from block.name.
            mapped = alias.get("slots", {}).get(block.name)
            if mapped and mapped != block.name:
                findings.append(Finding(
                    severity=ERROR, file=slide.path, line=block.name_line,
                    rule="L2",
                    message=(f"'::{block.name}::' is the semantic name; "
                             f"this layout maps it to '{mapped}'"),
                    fix=f"rename to '::{mapped}::'",
                ))
    return findings


def rule_l3_no_image_in_slot(slide: SlideFile) -> list[Finding]:
    """L3 — image references inside a named-slot block break Vite on Windows.

    Slidev's ``slide-import-guard`` rewrites both ``![alt](/figures/x.png)``
    and ``<img src="/figures/x.png">`` inside ``::slot::`` blocks into JS
    ``import`` statements. On Windows, ``/figures/x.png`` resolves to
    ``C:\\figures\\x.png`` which fails Vite's ``fs.allow`` check — the
    whole slide breaks with a cryptic "An error occurred".
    """
    findings: list[Finding] = []
    for block in slide.slots:
        for i, raw_line in enumerate(block.body_lines):
            line_no = block.body_start + i
            md_match = _IMG_MD_RE.search(raw_line)
            # RELATIVE srcs are the failure mode (./public/... resolved
            # against the slide file's location breaks the moment slides
            # move into slides/ — SPRINT_2's migration proved it with 55
            # build errors). Absolute /figures/... paths served from
            # public/ are the working convention across three decks.
            html_rel = re.search(
                r'<img\s+[^>]*src="(?!https?://)(?!/)', raw_line,
                re.IGNORECASE)
            md_rel = md_match and not re.search(
                r"!\[[^\]]*\]\((?:https?://|/)", raw_line)
            if html_rel or md_rel:
                findings.append(Finding(
                    severity=ERROR, file=slide.path, line=line_no, rule="L3",
                    message=(f"RELATIVE image path inside slot "
                             f"'::{block.name}::' breaks once slides live "
                             f"in slides/ (Vite resolves it against the "
                             f"slide file)"),
                    fix=("reference public assets absolutely: "
                         "src=\"/figures/<name>\" (served from public/)"),
                ))
    return findings


def rule_l4_no_blank_line_in_slot(slide: SlideFile) -> list[Finding]:
    """L4 — blank lines inside a slot block close it early in MDC.

    The MDC parser closes ``::slot::`` blocks at the first blank line.
    Content after the blank line silently leaks into the slide root, where
    it renders as un-slotted prose (or doesn't render at all, depending on
    the layout). Detected here by looking for empty (or whitespace-only)
    lines between two non-empty content lines within a single block.
    """
    findings: list[Finding] = []
    #: Continuation patterns that provably render after a blank line in
    #: Slidev page-level named slots (the ILSE house style: one intro
    #: sentence, blank line, then a list / HTML block). Three shipping
    #: decks use exactly this shape.
    safe_next = re.compile(r"^\s*(?:[-*]|\d+\.|<div|<table|<img|<tr|<p\b)")
    for block in slide.slots:
        body = block.body_lines
        # Find blank lines that have non-blank content both before AND after.
        for i in range(1, len(body) - 1):
            if not body[i].strip() and body[i - 1].strip() and any(
                l.strip() for l in body[i + 1:]
            ):
                nxt = next((l for l in body[i + 1:] if l.strip()), "")
                if safe_next.match(nxt):
                    continue  # house-style intro-blank-list pattern: fine
                line_no = block.body_start + i
                findings.append(Finding(
                    severity=WARNING, file=slide.path, line=line_no,
                    rule="L4",
                    message=(f"blank line inside slot '::{block.name}::' "
                             f"before prose may close the block on "
                             f"MDC-container themes"),
                    fix=("if the theme uses MDC containers, remove the "
                         "blank line or use <br><br>; Slidev page-level "
                         "slots (ILSE) tolerate it"),
                ))
                break  # one finding per block is enough
    return findings


def rule_l5_frontmatter_parseable(slide: SlideFile) -> list[Finding]:
    """L5 — frontmatter must parse cleanly."""
    if not slide.yaml_error:
        return []
    return [Finding(
        severity=ERROR, file=slide.path, line=1, rule="L5",
        message=f"frontmatter unparseable: {slide.yaml_error}",
        fix="repair the YAML; common causes are tabs and unbalanced quotes",
    )]


def _extract_title_text(slide: SlideFile) -> tuple[str, int] | None:
    """Return (title-text, source-line) or None if no title is present.

    Prefers the ``::title::`` slot's body over the ``title:`` frontmatter
    field, because the slot is what actually renders — frontmatter title is
    a metadata fallback some themes ignore for content slides.
    """
    for block in slide.slots:
        if block.name in _TITLE_SLOT_NAMES and block.body_lines:
            text = " ".join(b.strip() for b in block.body_lines if b.strip())
            return text, block.body_start
    if slide.title_field:
        return slide.title_field, 1
    return None


def rule_l6_no_formula_in_title(slide: SlideFile) -> list[Finding]:
    """L6 — titles should not carry LaTeX or bare uppercase letters.

    A title is a verbal claim; symbols and matrix names belong in the body.
    "P = K[R|t]" is a worked example, not a headline. WARNING by default,
    promoted to ERROR under ``--strict``.
    """
    extracted = _extract_title_text(slide)
    if extracted is None:
        return []
    text, line = extracted
    reasons: list[str] = []
    if _FORMULA_DOLLAR_RE.search(text):
        reasons.append("LaTeX math ($…$)")
    # Match \\macro but exclude common Markdown escapes that aren't math
    # (e.g. \\* for a literal asterisk would be \*); restrict to known
    # math-y macro names.
    if re.search(r"\\(frac|underbrace|begin|end|sum|int|alpha|beta|gamma|"
                 r"theta|lambda|mu|sigma|cdot|times|leq|geq|neq|infty|"
                 r"mathbf|mathrm)", text):
        reasons.append("LaTeX macro")
    if any(ch in _MATH_OP_CHARS for ch in text):
        # ``=`` is the high-signal flag (a title with ``=`` is almost
        # always wrong). The other operators are rarer but equally bad.
        offending = sorted({ch for ch in text if ch in _MATH_OP_CHARS})
        reasons.append(f"math operator(s) {'/'.join(offending)}")
    if _BARE_UPPER_RE.search(text):
        # Filter out the common all-caps acronyms (≥ 2 letters) by checking
        # whether the match is genuinely a *single* upper letter surrounded
        # by spaces — not part of "GPS" or "PDF".
        matches = _BARE_UPPER_RE.findall(text)
        if matches:
            reasons.append(f"bare uppercase letter(s) {'/'.join(matches)}")
    if not reasons:
        return []
    return [Finding(
        severity=WARNING, file=slide.path, line=line, rule="L6",
        message=("title contains formula-like content: "
                 + "; ".join(reasons)),
        fix=("rewrite the title as a verbal assertion; move the "
             "formula into the body or speaker notes"),
    )]


def rule_l7_has_frontmatter(slide: SlideFile) -> list[Finding]:
    """L7 — every slide following the schema needs frontmatter."""
    if slide.has_frontmatter:
        return []
    return [Finding(
        severity=WARNING, file=slide.path, line=1, rule="L7",
        message="slide has no YAML frontmatter",
        fix=("add at minimum: ``id:`` (== filename without .md) and "
             "``layout:`` (a physical slideN name from the theme)"),
    )]


def rule_l8_citations_slot_needs_bib(slide: SlideFile,
                                     theme: ThemeInfo | None,
                                     deck_dir: Path,
                                     ) -> list[Finding]:
    """L8 — using a citations slot without a references.bib in the deck."""
    if not (deck_dir / "references.bib").exists():
        # Detect whether ANY slot looks like a citations slot. We check both
        # the literal slot name "citations" AND the theme's alias slot
        # mapping (e.g. ILSE maps ``citations → body-13``).
        cite_slot_names: set[str] = {"citations"}
        if theme is not None:
            for alias in theme.aliases.values():
                physical = alias.get("slots", {}).get("citations")
                if physical:
                    cite_slot_names.add(physical)
        for block in slide.slots:
            if block.name in cite_slot_names and block.body_lines:
                return [Finding(
                    severity=WARNING, file=slide.path, line=block.name_line,
                    rule="L8",
                    message=(f"slide uses a citations slot but "
                             f"<deck>/references.bib does not exist"),
                    fix="create references.bib with the cited entries",
                )]
    return []


def rule_l9_cite_keys_in_bib(slide: SlideFile,
                             bib_keys: set[str] | None,
                             ) -> list[Finding]:
    """L9 — every ``sources[].key`` in frontmatter must appear in the bib."""
    if bib_keys is None:
        return []
    findings: list[Finding] = []
    for key, line in slide.sources_keys:
        if key not in bib_keys:
            findings.append(Finding(
                severity=WARNING, file=slide.path, line=line, rule="L9",
                message=f"cite key '{key}' not found in references.bib",
                fix=f"add the bib entry, or correct the key spelling",
            ))
    return findings


def rule_l10_speaker_notes_present(slide: SlideFile) -> list[Finding]:
    """L10 — last HTML comment should be substantial speaker notes."""
    note = slide.last_html_comment
    # Trim out the context-block marker text — if the LAST comment IS the
    # context block, that's the bug L10 wants to surface.
    if "==== SLIDE CONTEXT" in note or "==== END CONTEXT" in note:
        return [Finding(
            severity=WARNING, file=slide.path, line=1, rule="L10",
            message=("last HTML comment is the SLIDE CONTEXT block; Slidev "
                     "will parse this as speaker notes instead of your notes"),
            fix=("place the speaker-notes comment AFTER the context block "
                 "(notes must be the last comment in the file)"),
        )]
    if len(note) < 50:
        return [Finding(
            severity=WARNING, file=slide.path, line=1, rule="L10",
            message=(f"speaker notes are short ({len(note)} chars); the "
                     f"last HTML comment is Slidev's notes block"),
            fix="add substantive speaker notes — they are the script, "
                "not the slide",
        )]
    return []


def rule_l11_body_word_count(slide: SlideFile,
                             theme: ThemeInfo | None,
                             ) -> list[Finding]:
    """L11 — body slot content over 49 words breaks the 7×7 rule."""
    # Identify body slots: the alias's ``body`` mapping, plus the common
    # physical names ``body-16``, ``ph-1``, etc. We pick body slots only,
    # not titles/citations/subtitles.
    body_slot_names: set[str] = set()
    if theme is not None:
        for alias in theme.aliases.values():
            mapped = alias.get("slots", {}).get("body")
            if mapped:
                body_slot_names.add(mapped)
    # Theme-agnostic fallback so the rule still fires when L1/L2 are skipped.
    body_slot_names.update({"body", "body-16", "body-21", "body-25", "ph-1"})

    findings: list[Finding] = []
    for block in slide.slots:
        if block.name not in body_slot_names:
            continue
        body_text = " ".join(block.body_lines)
        # Strip markdown markers so a bullet list isn't punished for its
        # leading ``-`` characters.
        cleaned = re.sub(r"[*_`#>\-]", " ", body_text)
        word_count = len([w for w in cleaned.split() if w.strip()])
        if word_count > 49:
            findings.append(Finding(
                severity=WARNING, file=slide.path, line=block.body_start,
                rule="L11",
                message=(f"slot '::{block.name}::' has {word_count} words "
                         f"(> 49 = 7×7 rule hard cap)"),
                fix="compress or split — audiences read instead of listen "
                    "above ~50 words",
            ))
    return findings


def rule_l12_consecutive_same_layout(slides_in_order: list[SlideFile],
                                     ) -> list[Finding]:
    """L12 — more than 4 consecutive slides with the same layout."""
    findings: list[Finding] = []
    run: list[SlideFile] = []
    last_layout: str | None = None
    for slide in slides_in_order:
        if slide.layout and slide.layout == last_layout:
            run.append(slide)
        else:
            if len(run) > 4:
                first = run[0]
                findings.append(Finding(
                    severity=WARNING, file=first.path, line=1, rule="L12",
                    message=(f"{len(run)} consecutive slides share layout "
                             f"'{last_layout}': "
                             f"{', '.join(s.path.stem for s in run)}"),
                    fix="break the monotony with a section, "
                        "content-image, or hero-statement layout",
                ))
            run = [slide] if slide.layout else []
            last_layout = slide.layout
    # Don't forget the trailing run.
    if len(run) > 4:
        first = run[0]
        findings.append(Finding(
            severity=WARNING, file=first.path, line=1, rule="L12",
            message=(f"{len(run)} consecutive slides share layout "
                     f"'{last_layout}': "
                     f"{', '.join(s.path.stem for s in run)}"),
            fix="break the monotony with a section, content-image, "
                "or hero-statement layout",
        ))
    return findings


# ---------------------------------------------------------------------------
# L13 — house-style characters (centre dot, em-dash)
# ---------------------------------------------------------------------------


def rule_l13_house_style_chars(slide: SlideFile) -> list[Finding]:
    """No centre dot ``·`` and no em-dash ``—`` anywhere in a slide file.

    The ILSE house style bans both (colon or comma instead; en-dash for
    numeric ranges is fine). Agents keep producing em-dashes in alt texts
    and notes despite instructions — SPRINT_2 shipped four of them before
    a manual grep caught it. Deterministic check, ERROR severity: these
    are always a find/replace away from fixed.
    """
    findings = []
    for i, line in enumerate(slide.raw.split("\n"), start=1):
        for ch, name in (("·", "centre dot"), ("—", "em-dash")):
            if ch in line:
                findings.append(Finding(
                    severity=ERROR, file=slide.path, line=i, rule="L13",
                    message=f"{name} '{ch}' violates the house style",
                    fix="replace with a colon, comma, or parentheses "
                        "(en-dash only for numeric ranges)",
                ))
    return findings


# ---------------------------------------------------------------------------
# L14 — malformed HTML attribute quoting
# ---------------------------------------------------------------------------

_TAG_RE = re.compile(r"<(img|a|div|span|figure)\b[^>]*>", re.IGNORECASE)


def rule_l14_attribute_quoting(slide: SlideFile) -> list[Finding]:
    """Detect HTML tags whose attribute quoting is broken.

    An agent once produced ``alt="... the root "Forming" branches ..."`` —
    a nested double quote that silently truncates the attribute and leaks
    the rest as markup. Heuristic: inside a tag, the number of ``"`` must
    be even AND every ``="``-opened value must close before the next
    ``=``. We check the simpler invariant (even quote count per tag) plus
    ``=" ... " ... "`` runs of three quotes between attribute names.
    """
    findings = []
    for i, line in enumerate(slide.raw.split("\n"), start=1):
        for m in _TAG_RE.finditer(line):
            tag = m.group(0)
            if tag.count('"') % 2 == 1:
                findings.append(Finding(
                    severity=ERROR, file=slide.path, line=i, rule="L14",
                    message="odd number of double quotes in HTML tag "
                            "(broken attribute)",
                    fix="remove quotes inside attribute values",
                ))
                continue
            # values themselves must not contain further quotes: after
            # splitting on `="`, each chunk holds "value" + what follows.
            # After the value's closing quote only whitespace+attrname (for
            # middle chunks) or the tag end (last chunk) may appear —
            # anything else means a stray quote truncated the value (e.g.
            # alt="the root "Forming" branches").
            chunks = tag.split('="')[1:]
            ok_middle = re.compile(r'^[^"]*"\s+[\w-]+$')
            ok_last = re.compile(r'^[^"]*"\s*/?\s*>$')
            bad = False
            for j, chunk in enumerate(chunks):
                pattern = ok_last if j == len(chunks) - 1 else ok_middle
                if not pattern.match(chunk):
                    bad = True
                    break
            if bad:
                findings.append(Finding(
                    severity=ERROR, file=slide.path, line=i, rule="L14",
                    message="attribute value contains a stray quote "
                            "or is unterminated",
                    fix="attribute values must be quote-free plain text",
                ))
    return findings


# ---------------------------------------------------------------------------
# L15 — portrait image full-width (renders unreadably small)
# ---------------------------------------------------------------------------

_IMG_SRC_RE = re.compile(r'<img[^>]*src="(/[^"]+)"', re.IGNORECASE)

#: Layouts whose picture slot spans the full slide width. A portrait image
#: there letterboxes to less than half the slide and becomes unreadable —
#: the exact complaint that forced three re-renders in SPRINT_2.
_FULL_WIDTH_LAYOUTS = {"slidefigure"}


def rule_l15_portrait_on_full_width(slide: SlideFile,
                                    deck_dir: Path) -> list[Finding]:
    if slide.layout not in _FULL_WIDTH_LAYOUTS:
        return []
    try:
        from PIL import Image  # optional dependency; skip check if absent
    except ImportError:  # pragma: no cover
        return []
    findings = []
    for i, line in enumerate(slide.raw.split("\n"), start=1):
        for m in _IMG_SRC_RE.finditer(line):
            img_path = deck_dir / "public" / m.group(1).lstrip("/")
            if not img_path.is_file():
                continue
            try:
                with Image.open(img_path) as im:
                    w, h = im.size
            except Exception:
                continue
            if h > w:
                findings.append(Finding(
                    severity=WARNING, file=slide.path, line=i, rule="L15",
                    message=(f"portrait image ({w}x{h}) on full-width "
                             f"layout '{slide.layout}' renders too small"),
                    fix="rotate the image, redraw it landscape "
                        "left-to-right, or switch to a split layout",
                ))
    return findings


# ---------------------------------------------------------------------------
# Deck walk
# ---------------------------------------------------------------------------


def _slide_order_from_deck_md(deck_dir: Path,
                              slide_files: list[Path],
                              ) -> list[Path]:
    """Return *slide_files* sorted by their appearance in ``slides.md``.

    Falls back to alphabetical order when ``slides.md`` doesn't exist or
    can't be parsed. The L12 consecutive-layout check needs presentation
    order; on-disk filename order is meaningless here.
    """
    slides_md = deck_dir / "slides.md"
    if not slides_md.is_file():
        return sorted(slide_files)
    text = slides_md.read_text(encoding="utf-8")
    src_re = re.compile(r"src:\s*\.?/?slides/([\w\-]+)\.md")
    ordered_stems = src_re.findall(text)
    by_stem = {p.stem: p for p in slide_files}
    ordered: list[Path] = []
    for stem in ordered_stems:
        if stem in by_stem:
            ordered.append(by_stem.pop(stem))
    # Anything not referenced from slides.md goes at the end, alphabetical.
    ordered.extend(sorted(by_stem.values()))
    return ordered


def lint_deck(deck_dir: Path,
              *,
              strict: bool = False,
              verbose: bool = False,
              log=print,
              ) -> tuple[list[Finding], int, int]:
    """Lint every slide under ``<deck>/slides/*.md``.

    Returns ``(findings, error_count, warning_count)``. Caller decides the
    exit code from those counts.
    """
    slides_dir = deck_dir / "slides"
    if not slides_dir.is_dir():
        raise FileNotFoundError(f"no slides/ directory at {deck_dir}")

    theme, theme_diag = resolve_theme(deck_dir)
    findings: list[Finding] = []
    if theme is None and theme_diag:
        # Surface as a WARNING so the user knows L1/L2 were skipped.
        findings.append(Finding(
            severity=WARNING, file=deck_dir, line=1, rule="L0",
            message=f"theme not resolved — L1/L2 skipped ({theme_diag})",
            fix="add .slidecraft.json with theme.path, or ensure "
                "slides.md frontmatter has theme: <name>",
        ))

    bib_keys = load_bib_keys(deck_dir)

    slide_paths = sorted(slides_dir.glob("*.md"))
    parsed: list[SlideFile] = []
    for path in slide_paths:
        if verbose:
            log(f"linting: {path.name}")
        slide = parse_slide(path)
        parsed.append(slide)
        findings.extend(rule_l5_frontmatter_parseable(slide))
        findings.extend(rule_l7_has_frontmatter(slide))
        findings.extend(rule_l1_layout_is_physical(slide, theme))
        findings.extend(rule_l2_slot_names_physical(slide, theme))
        findings.extend(rule_l3_no_image_in_slot(slide))
        findings.extend(rule_l4_no_blank_line_in_slot(slide))
        findings.extend(rule_l6_no_formula_in_title(slide))
        findings.extend(rule_l8_citations_slot_needs_bib(slide, theme,
                                                          deck_dir))
        findings.extend(rule_l9_cite_keys_in_bib(slide, bib_keys))
        findings.extend(rule_l10_speaker_notes_present(slide))
        findings.extend(rule_l11_body_word_count(slide, theme))
        findings.extend(rule_l13_house_style_chars(slide))
        findings.extend(rule_l14_attribute_quoting(slide))
        findings.extend(rule_l15_portrait_on_full_width(slide, deck_dir))

    # Deck-level (cross-slide) rules.
    ordered = _slide_order_from_deck_md(deck_dir, slide_paths)
    by_path = {s.path: s for s in parsed}
    ordered_slides = [by_path[p] for p in ordered if p in by_path]
    findings.extend(rule_l12_consecutive_same_layout(ordered_slides))

    # If --strict, warnings count as errors for the purpose of the exit
    # code (the caller decides). We still keep severities truthful in
    # the printed output so the user can see which are *warnings* that
    # got promoted.
    errors = sum(1 for f in findings if f.severity == ERROR)
    warnings = sum(1 for f in findings if f.severity == WARNING)
    return findings, errors, warnings


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m slidecraft.scripts.lint_slides",
        description=("Pre-flight lint for Slidecraft slide files. Catches "
                     "mechanical errors (semantic-vs-physical name "
                     "confusion, image-in-slot, formula-in-title, etc.) "
                     "before the slide-critic agent runs."),
    )
    p.add_argument("--deck", required=True, type=Path,
                   help="Path to the deck directory (must contain slides/).")
    p.add_argument("--strict", action="store_true",
                   help="Treat warnings as errors (exit 2 if any warning).")
    p.add_argument("--verbose", action="store_true",
                   help="Print each slide filename as it's checked.")
    return p


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point — returns the process exit code."""
    args = _build_arg_parser().parse_args(argv)

    deck_dir: Path = args.deck
    if not deck_dir.is_dir():
        print(f"error: deck directory not found: {deck_dir}", file=sys.stderr)
        return 1

    try:
        findings, errors, warnings = lint_deck(
            deck_dir, strict=args.strict, verbose=args.verbose,
        )
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    # Print findings in (file, line, rule) order — stable, scannable.
    findings.sort(key=lambda f: (str(f.file), f.line, f.rule))
    for f in findings:
        print(f.format(deck_dir))

    # Summary.
    slide_count = sum(
        1 for _ in (deck_dir / "slides").glob("*.md")
    )
    print(f"\nlinted {slide_count} files: "
          f"{errors} errors, {warnings} warnings")

    if errors:
        return 1
    if args.strict and warnings:
        return 2
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
