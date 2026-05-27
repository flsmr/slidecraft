"""Render a Slidecraft CIF (``.slidecraft/cif.json``) into a Slidev ``slides.md``.

The authoring skill writes a Canonical Intermediate Format (CIF) file as the
sole source of truth for a deck. Slidev itself, however, consumes a flat
markdown file. This script is the one-way bridge — CIF in, ``slides.md`` out.

Two flavours of theme are supported:

* **Flavour A** — the theme ships a ``semantic-layouts.json`` next to its
  ``package.json``. The CIF references layouts by semantic role
  (``cover``, ``default``, ``section`` …) and that file maps each role to
  (a) one of the theme's numbered ``slideN.vue`` layouts and (b) which
  named slot inside that layout holds the title / body / image / etc.
  Output uses Slidev's ``::slot-name::`` block syntax.

* **Flavour B** — no ``semantic-layouts.json``. Either the theme already
  uses semantic layout names (a `default.vue`, `cover.vue` …) and a
  default slot, or the CIF's layout is a Slidev built-in. Output is plain
  markdown (no named-slot blocks).

The script is idempotent — running it twice on the same CIF produces a
byte-identical ``slides.md`` and the second run reports ``unchanged``.
Writes are atomic via a tempfile + rename so a failure mid-render never
truncates an existing output.

Standard library only. Importable as :func:`render_cif`; runnable as
``python -m slidecraft.scripts.render_cif``.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Slidev's built-in layouts — accepted as a literal layout name when neither
#: a theme alias nor a ``<theme>/layouts/<name>.vue`` file exists. Keep this
#: list narrow: anything outside it must be a theme-provided layout, so an
#: unknown name is a real error worth surfacing rather than passing through.
SLIDEV_BUILTIN_LAYOUTS = frozenset({
    "default", "cover", "center", "intro", "image-right", "image-left",
    "two-cols", "section", "statement", "fact", "quote", "end",
})

#: Keys that the renderer projects from a CIF slide's flat fields into the
#: theme alias's ``slots`` mapping (Flavour A). ``title`` and ``body`` get
#: special-cased because they correspond to the CIF's top-level ``title`` and
#: ``content`` fields rather than to entries inside ``cif_slide.slots``.
TOP_LEVEL_FIELD_TO_SEMANTIC = {
    "title": "title",
    "content": "body",
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class RenderResult:
    """Outcome of one ``render_cif`` invocation.

    Attributes are stable — callers (tests, the authoring skill) read them
    directly. ``status`` is one of ``"written" | "unchanged"``; ``mode``
    is ``"A" | "B" | "mixed"`` reflecting which theme flavour(s) the deck
    ended up using.
    """

    slides_count: int
    theme: str | None
    mode: str
    status: str
    output_path: Path
    resolutions: list["LayoutResolution"] = field(default_factory=list)


@dataclass
class LayoutResolution:
    """How one CIF slide's ``layout`` was resolved to a physical layout."""

    slide_id: str
    cif_layout: str
    physical_layout: str
    flavour: str   # "A" | "B-file" | "B-builtin"
    slots: dict[str, str] = field(default_factory=dict)   # semantic → physical
    defaults: dict[str, str] = field(default_factory=dict)  # semantic → default content


# ---------------------------------------------------------------------------
# CIF + theme loading
# ---------------------------------------------------------------------------


def _load_json(path: Path) -> dict:
    """Read *path* as UTF-8 JSON. Raises with a path-prefixed message on failure."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path}: invalid JSON: {exc}") from exc


def _resolve_theme_path(cif_path: Path, cif: dict) -> tuple[Path | None, str | None]:
    """Locate the theme directory for *cif*.

    Resolution order:

    1. ``<deck>/.slidecraft.json``'s ``theme.path`` (relative to deck root),
       where the deck root is ``dirname(dirname(cif_path))`` — the CIF
       conventionally lives at ``<deck>/.slidecraft/cif.json``.
    2. CIF's own ``meta.themePath`` (relative to the deck root).

    The theme NAME comes from ``.slidecraft.json``'s ``theme.name`` if
    present, else from CIF's ``meta.theme``. Either may be missing — in
    which case ``None`` is returned for that slot and the renderer falls
    through to Flavour B / built-in resolution.

    Returns ``(theme_dir_or_none, theme_name_or_none)``. The directory is
    returned even when it doesn't exist on disk — the caller decides
    whether to fail or fall through.
    """
    deck_dir = cif_path.parent.parent
    meta = cif.get("meta", {}) or {}

    theme_path: Path | None = None
    theme_name: str | None = meta.get("theme") or None

    slidecraft_json = deck_dir / ".slidecraft.json"
    if slidecraft_json.is_file():
        try:
            sj = _load_json(slidecraft_json)
            theme = sj.get("theme", {}) or {}
            if isinstance(theme, dict):
                if theme.get("path"):
                    theme_path = (deck_dir / theme["path"]).resolve()
                if theme.get("name"):
                    theme_name = theme["name"]
        except (ValueError, OSError):
            # Malformed ``.slidecraft.json`` — fall back to CIF meta rather
            # than aborting; the CIF is the source of truth.
            pass

    if theme_path is None and meta.get("themePath"):
        theme_path = (deck_dir / meta["themePath"]).resolve()

    return theme_path, theme_name


def _load_semantic_layouts(theme_dir: Path | None) -> dict | None:
    """Load ``<theme-dir>/semantic-layouts.json`` if present, else None."""
    if theme_dir is None:
        return None
    sl = theme_dir / "semantic-layouts.json"
    if not sl.is_file():
        return None
    try:
        return _load_json(sl)
    except ValueError:
        # Corrupt mapping file is a hard error — Flavour-A intent has been
        # declared by the theme author, silently falling through to Flavour
        # B would render the wrong slot content.
        raise


# ---------------------------------------------------------------------------
# Layout resolution
# ---------------------------------------------------------------------------


def _resolve_layout(
    slide_id: str,
    cif_layout: str,
    theme_dir: Path | None,
    theme_name: str | None,
    semantic_layouts: dict | None,
) -> LayoutResolution:
    """Decide which physical layout + flavour to render this slide as.

    Algorithm (from the renderer spec):

    1. If a ``semantic-layouts.json`` is present AND its ``aliases`` has an
       entry for *cif_layout*: use that alias (Flavour A).
    2. Else if ``<theme-dir>/layouts/<cif_layout>.vue`` exists: emit the
       layout name literally, content goes to the default slot (Flavour B
       with a file-backed layout).
    3. Else if *cif_layout* is one of Slidev's built-ins: emit literally
       and let Slidev resolve (Flavour B with a built-in layout).
    4. Else: raise ValueError — the caller turns this into an exit-1 error.
    """
    if semantic_layouts:
        aliases = semantic_layouts.get("aliases", {}) or {}
        alias = aliases.get(cif_layout)
        if isinstance(alias, dict) and alias.get("layout"):
            return LayoutResolution(
                slide_id=slide_id,
                cif_layout=cif_layout,
                physical_layout=str(alias["layout"]),
                flavour="A",
                slots=dict(alias.get("slots", {}) or {}),
                defaults=dict(alias.get("defaults", {}) or {}),
            )

    if theme_dir is not None:
        layout_file = theme_dir / "layouts" / f"{cif_layout}.vue"
        if layout_file.is_file():
            return LayoutResolution(
                slide_id=slide_id,
                cif_layout=cif_layout,
                physical_layout=cif_layout,
                flavour="B-file",
            )

    if cif_layout in SLIDEV_BUILTIN_LAYOUTS:
        return LayoutResolution(
            slide_id=slide_id,
            cif_layout=cif_layout,
            physical_layout=cif_layout,
            flavour="B-builtin",
        )

    theme_label = theme_name or (theme_dir.name if theme_dir else "<no theme>")
    raise ValueError(
        f"slide {slide_id}: layout '{cif_layout}' has no semantic alias in "
        f"{theme_label}'s semantic-layouts.json AND no "
        f"{theme_label}/layouts/{cif_layout}.vue file"
    )


# ---------------------------------------------------------------------------
# Frontmatter helpers
# ---------------------------------------------------------------------------


def _yaml_escape(value: str) -> str:
    """Minimal YAML scalar serialiser for frontmatter values.

    We only need to handle plain strings and dates — the CIF fields that
    end up here are ``title``, ``subtitle``, ``author``, ``date``, and
    arbitrary per-slide ``meta`` values. If a value contains a YAML-special
    character (``:``, ``#``, ``-`` at start, quotes, etc.) we wrap it in
    double quotes and backslash-escape inner double quotes and backslashes.
    Otherwise we emit it bare for human readability.
    """
    if not isinstance(value, str):
        # Numbers and bools render via their JSON form, which is also valid
        # YAML for these scalar types.
        return json.dumps(value, ensure_ascii=False)
    needs_quote = (
        value == ""
        or value[0] in "-?:,[]{}#&*!|>'\"%@`"
        or ": " in value
        or " #" in value
        or value.strip() != value
        or any(c in value for c in "\n\t")
    )
    if not needs_quote:
        return value
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _format_frontmatter(fields: list[tuple[str, object]]) -> str:
    """Render an ordered list of ``(key, value)`` pairs as a frontmatter block.

    *fields* is a list (not a dict) because order matters for deterministic
    output. Entries with ``None`` or empty-string values are dropped so
    they don't clutter the block. Returns the block including the opening
    ``---`` and trailing ``---`` lines; no surrounding newlines.
    """
    lines: list[str] = ["---"]
    for key, value in fields:
        if value is None or value == "":
            continue
        lines.append(f"{key}: {_yaml_escape(value) if isinstance(value, str) else json.dumps(value, ensure_ascii=False)}")
    lines.append("---")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Body rendering — Flavour A (named slots) and Flavour B (default slot)
# ---------------------------------------------------------------------------


def _collect_slot_blocks(
    cif_slide: dict,
    alias_slots: dict[str, str],
    alias_defaults: dict[str, str],
    *,
    warn,
) -> list[tuple[str, str]]:
    """Build the ``[(physical_slot_name, content), ...]`` list for Flavour A.

    Sources, in priority order:

    1. The CIF's top-level ``title`` and ``content`` fields project to the
       alias's ``title`` and ``body`` semantic slots respectively (when those
       exist in the alias).
    2. Every key in the CIF slide's ``slots`` object projects to the alias's
       same-named semantic slot. Explicit slot content overrides field
       projection. If the alias doesn't declare that semantic name, the
       slot passes through under its CIF name and *warn* is called.
    3. Anything still empty after 1 + 2 falls back to ``alias_defaults`` —
       the theme's default content for that semantic slot, declared in
       ``semantic-layouts.json``. This is how closing slides get
       "Thank you" without the author having to populate the field.

    Empty-string values are dropped — no ``::slot::`` block for content
    the author left blank AND that has no default. Order is stable:
    alias-declared slots first in the order they appear in the alias's
    mapping, then passthrough slots in CIF insertion order.
    """
    cif_slots = cif_slide.get("slots", {}) or {}
    if not isinstance(cif_slots, dict):
        cif_slots = {}

    # Semantic -> markdown content, in alias declaration order. Using dict
    # preserves insertion order (Py 3.7+), which is what we want for
    # deterministic output.
    semantic_content: dict[str, str] = {}

    # 1. Project top-level CIF fields (title/content) onto the alias's
    #    title/body semantic slots when those exist.
    for cif_field, semantic_name in TOP_LEVEL_FIELD_TO_SEMANTIC.items():
        if semantic_name not in alias_slots:
            continue
        value = cif_slide.get(cif_field)
        if isinstance(value, str) and value.strip():
            semantic_content[semantic_name] = value

    # 2. Layer in cif_slide.slots — these override the top-level field
    #    projections if they collide (explicit slot wins over implicit
    #    field-mapping) and add any non-title/body slots the alias knows
    #    about.
    passthrough: list[tuple[str, str]] = []
    for semantic_name, content in cif_slots.items():
        if not isinstance(content, str) or not content.strip():
            continue
        if semantic_name in alias_slots:
            semantic_content[semantic_name] = content
        else:
            # No alias mapping for this semantic name — passthrough using
            # the CIF's key as the physical slot name. Warn so verbose
            # runs can surface drift between CIF authoring and the theme.
            warn(f"slot '{semantic_name}' has no mapping in alias; "
                 f"emitting as ::{semantic_name}:: directly")
            passthrough.append((semantic_name, content))

    # 3. Fall back to alias defaults for any semantic slot still empty.
    #    Themes use this for closing-slide "Thank you" etc. so authors
    #    don't have to populate every slot of every layout role.
    for semantic_name, default_content in alias_defaults.items():
        if not isinstance(default_content, str) or not default_content.strip():
            continue
        if semantic_name not in alias_slots:
            # Default declared for a slot the alias doesn't actually map.
            # Skip silently — theme misconfiguration but not the renderer's
            # job to validate themes.
            continue
        semantic_content.setdefault(semantic_name, default_content)

    blocks: list[tuple[str, str]] = []
    # Emit in alias-declaration order for stable diffs.
    for semantic_name in alias_slots:
        if semantic_name in semantic_content:
            physical = alias_slots[semantic_name]
            blocks.append((physical, semantic_content[semantic_name]))
    blocks.extend(passthrough)
    return blocks


def _render_flavour_a_body(blocks: list[tuple[str, str]], *, warn) -> str:
    """Render named-slot blocks. Each block starts on its own line.

    Multi-paragraph content (i.e. content containing a blank line) inside a
    named slot is a Slidev/MDC parser hazard: the blank line closes the
    ``::slot-name::`` block early and any subsequent paragraph leaks into
    the slide root with no slot, which silently breaks the layout. We
    detect this case, warn, and wrap the offending content in an explicit
    ``<div>...</div>`` so MDC sees one unambiguous block.
    """
    parts: list[str] = []
    for slot_name, content in blocks:
        stripped = content.rstrip()
        if "\n\n" in stripped:
            warn(f"slot '{slot_name}' contains a blank line — MDC would "
                 f"close the slot block early; wrapping in <div>")
            stripped = f"<div>\n\n{stripped}\n\n</div>"
        # Content gets one trailing newline-less form; the join below adds
        # the blank-line separator between slots.
        parts.append(f"::{slot_name}::\n{stripped}")
    return "\n\n".join(parts)


def _render_flavour_b_body(cif_slide: dict) -> str:
    """Render default-slot content.

    The CIF's ``title`` becomes an ``# H1`` heading, then ``content``
    follows verbatim. If ``content`` already starts with a heading
    (``#``-prefixed line) we don't add another ``#`` — common pattern in
    user-edited markdown.
    """
    title = cif_slide.get("title") or ""
    content = cif_slide.get("content") or ""

    parts: list[str] = []
    if title and isinstance(title, str) and title.strip():
        parts.append(f"# {title.strip()}")
    if content and isinstance(content, str) and content.strip():
        stripped = content.lstrip()
        if parts and stripped.startswith("#"):
            # Title already implied by the content's leading heading.
            parts = [content.rstrip()]
        else:
            parts.append(content.rstrip())
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Slide assembly
# ---------------------------------------------------------------------------


def _render_slide(
    cif_slide: dict,
    resolution: LayoutResolution,
    *,
    is_first: bool,
    deck_frontmatter_extra: list[tuple[str, object]],
    warn,
) -> str:
    """Render one slide — frontmatter + body + speaker-notes comment.

    The first slide carries deck-level frontmatter (theme/title/author/date)
    in addition to its own per-slide fields; subsequent slides only carry
    per-slide fields. *deck_frontmatter_extra* is the deck-level list and
    is empty for non-first slides.
    """
    fm_fields: list[tuple[str, object]] = []
    if is_first:
        fm_fields.extend(deck_frontmatter_extra)
    fm_fields.append(("layout", resolution.physical_layout))

    slide_meta = cif_slide.get("meta", {}) or {}
    if isinstance(slide_meta, dict):
        for key, value in slide_meta.items():
            if key == "layout":
                # Slide-level meta.layout would conflict with the resolved
                # physical layout; the resolved one wins, silently.
                continue
            fm_fields.append((key, value))

    frontmatter = _format_frontmatter(fm_fields)

    if resolution.flavour == "A":
        blocks = _collect_slot_blocks(
            cif_slide, resolution.slots, resolution.defaults, warn=warn)
        body = _render_flavour_a_body(blocks, warn=warn)
    else:
        body = _render_flavour_b_body(cif_slide)

    notes = cif_slide.get("notes") or ""
    notes_block = ""
    if isinstance(notes, str) and notes.strip():
        notes_block = f"<!--\n{notes.strip()}\n-->"

    parts = [frontmatter]
    if body:
        parts.append(body)
    if notes_block:
        parts.append(notes_block)
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Top-level render
# ---------------------------------------------------------------------------


def render_cif(
    cif_path: Path,
    output_path: Path,
    *,
    verbose: bool = False,
    force: bool = False,
    log=print,
) -> RenderResult:
    """Render the CIF at *cif_path* into *output_path*.

    Args:
        cif_path:     Path to ``cif.json``. The deck root is assumed to be
                      ``cif_path.parent.parent`` (i.e. the CIF conventionally
                      lives at ``<deck>/.slidecraft/cif.json``).
        output_path:  Where to write ``slides.md``. Written atomically: the
                      content is staged in a temp file in the same directory
                      and renamed over the target on success.
        verbose:      Log each layout resolution and unmapped-slot warning.
        force:        Accepted for CLI parity with sibling scripts; this
                      renderer has no caching layer so the flag is a no-op.
        log:          Logging hook (defaults to ``print``); tests inject a
                      buffer.

    Returns:
        A :class:`RenderResult`.

    Raises:
        FileNotFoundError: when *cif_path* does not exist.
        ValueError:        when the CIF or a theme file is malformed, or
                           when a slide's layout cannot be resolved.
    """
    del force  # accepted for parity; no caching → no-op.

    cif = _load_json(cif_path)
    if not isinstance(cif, dict):
        raise ValueError(f"{cif_path}: top-level JSON must be an object")
    slides = cif.get("slides")
    if not isinstance(slides, list) or not slides:
        raise ValueError(f"{cif_path}: 'slides' must be a non-empty array")
    meta = cif.get("meta", {}) or {}

    theme_dir, theme_name = _resolve_theme_path(cif_path, cif)
    semantic_layouts = _load_semantic_layouts(theme_dir)

    def _warn(msg: str) -> None:
        if verbose:
            log(f"warning: {msg}")

    # Resolve every slide's layout up-front. If ANY resolution fails we
    # abort before writing — the spec forbids half-writes.
    resolutions: list[LayoutResolution] = []
    for idx, slide in enumerate(slides, start=1):
        if not isinstance(slide, dict):
            raise ValueError(
                f"{cif_path}: slides[{idx - 1}] must be an object")
        slide_id = str(slide.get("id") or f"slide-{idx:02d}")
        cif_layout = slide.get("layout")
        if not isinstance(cif_layout, str) or not cif_layout:
            raise ValueError(
                f"slide {slide_id}: missing required 'layout' field")
        res = _resolve_layout(
            slide_id, cif_layout, theme_dir, theme_name, semantic_layouts,
        )
        resolutions.append(res)
        if verbose:
            log(f"slide {slide_id}: '{cif_layout}' -> "
                f"{res.physical_layout} (flavour {res.flavour})")

    # Build deck-level frontmatter (rendered only on the first slide).
    deck_extra: list[tuple[str, object]] = []
    if theme_name:
        deck_extra.append(("theme", theme_name))
    for key in ("title", "subtitle", "author", "date"):
        if meta.get(key):
            deck_extra.append((key, meta[key]))

    # Assemble all slides.
    rendered_slides: list[str] = []
    for slide, resolution in zip(slides, resolutions):
        rendered_slides.append(_render_slide(
            slide, resolution,
            is_first=(len(rendered_slides) == 0),
            deck_frontmatter_extra=deck_extra,
            warn=_warn,
        ))

    # Slides are separated by a blank line only. Each rendered slide already
    # opens with its own frontmatter '---' fence, which Slidev simultaneously
    # parses as the inter-slide separator AND the opening of that slide's
    # YAML block. Emitting an additional '---' between slides creates a
    # phantom empty slide between every real one (Slidev parses three '---'
    # in a row as: end-prev, empty-content-slide, start-next-frontmatter).
    content = "\n\n".join(rendered_slides) + "\n"

    # Decide on flavour-mode label for the summary line.
    flavour_set = {r.flavour for r in resolutions}
    has_a = "A" in flavour_set
    has_b = bool({"B-file", "B-builtin"} & flavour_set)
    if has_a and has_b:
        mode = "mixed"
    elif has_a:
        mode = "A"
    else:
        mode = "B"

    # Idempotency check — compare existing content byte-for-byte. We
    # encode here once so the write path and the check use identical bytes.
    new_bytes = content.encode("utf-8")
    status = "written"
    if output_path.is_file():
        try:
            existing = output_path.read_bytes()
        except OSError:
            existing = None
        if existing == new_bytes:
            status = "unchanged"

    if status == "written":
        # Atomic write: stage to a temp file in the same directory (so the
        # rename is on the same filesystem) and then replace. ``os.replace``
        # is atomic on POSIX and works cross-platform on Windows for an
        # existing target.
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            prefix=".slides.md.", dir=str(output_path.parent))
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(new_bytes)
            os.replace(tmp_path, output_path)
        except Exception:
            # Clean up the temp file on any failure so a re-run doesn't
            # leave a litter of orphaned ``.slides.md.*`` files.
            try:
                tmp_path.unlink()
            except OSError:
                pass
            raise

    return RenderResult(
        slides_count=len(slides),
        theme=theme_name,
        mode=mode,
        status=status,
        output_path=output_path,
        resolutions=resolutions,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m slidecraft.scripts.render_cif",
        description=("Render a Slidecraft CIF (cif.json) into a Slidev-"
                     "consumable slides.md. Stdlib-only; idempotent."),
    )
    p.add_argument("--input", required=True, type=Path,
                   help="Path to the CIF JSON file.")
    p.add_argument("--output", required=True, type=Path,
                   help="Path to write the rendered slides.md.")
    p.add_argument("--verbose", action="store_true",
                   help="Log layout resolutions and unmapped-slot warnings.")
    p.add_argument("--force", action="store_true",
                   help="Accepted for parity with sibling scripts. This "
                        "renderer has no caching layer; the flag is a no-op.")
    return p


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point — returns the process exit code."""
    args = _build_arg_parser().parse_args(argv)

    cif_path: Path = args.input
    output_path: Path = args.output

    if not cif_path.is_file():
        print(f"error: CIF not found: {cif_path}", file=sys.stderr)
        return 1

    try:
        result = render_cif(
            cif_path, output_path,
            verbose=args.verbose, force=args.force,
        )
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    theme_label = result.theme or "<none>"
    print(
        f"rendered {result.slides_count} slides, "
        f"theme={theme_label}, mode={result.mode}, status={result.status}"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
