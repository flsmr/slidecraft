"""Scaffold a new Slidev deck that consumes an existing theme.

Pure mechanics — no LLM needed. Used by /slidecraft:new-deck (via the
command file's `python -m slidecraft.scaffold.new_deck …` invocation)
and importable directly as a Python API.

Inputs are explicit: the caller decides the deck location and which
theme to point at. Theme discovery (presenting sibling candidates,
asking the user to choose) is the LLM's responsibility — by the time
we get here, ``theme_dir`` is either an absolute Path to a directory
containing a valid Slidev theme ``package.json``, or ``None`` for
Slidev's built-in default theme.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..npm_name import validate_npm_package_name


# ---------------------------------------------------------------------------
# Templates — minimal mode (no theme, or --minimal)
# ---------------------------------------------------------------------------

_SLIDES_MD_MINIMAL_WITH_THEME = """\
---
theme: {theme_name}
title: {deck_name}
layout: {first_layout}
---

# {deck_name}

Replace this with your opening slide.

---
layout: {first_layout}
---

# Slide 2

- Bullet one
- Bullet two
"""

_SLIDES_MD_DEFAULT_THEME = """\
---
title: {deck_name}
---

# {deck_name}

Replace this with your opening slide.

---

# Slide 2

- Bullet one
- Bullet two
"""

# ---------------------------------------------------------------------------
# Gallery mode (default when a theme is given): one slide per layout
# ---------------------------------------------------------------------------

# Gallery-mode header: the explanatory HTML comment lives at the top of
# slides.md, sandwiched between the global frontmatter close and the
# first layout's slot overrides. Slidev renders nothing for an HTML
# comment, so it sits invisibly above slide 1's actual content.
_GALLERY_INTRO_COMMENT = """\
<!--
This deck was scaffolded in **gallery mode** — one starter slide per layout
the theme exposes, every text slot populated with a placeholder so you can
see the layout's intended shape at first ``npx slidev``.

Workflow:
  1. Browse the slides to see what each layout looks like populated.
  2. Delete the slides you don't need.
  3. Replace placeholder text in the ``::slot-name::`` blocks with your
     real content.
  4. Drop runtime assets into ``public/`` and reference them as ``/file.ext``.
     Source material (papers, outlines, meeting notes) lives in ``resources/``.

Re-scaffold with ``--minimal`` to skip gallery mode and get a 2-slide starter.
-->"""

_GITIGNORE = """\
node_modules/
dist/
.slidev/
*.log
.DS_Store
Thumbs.db
"""

_RESOURCES_README = """\
# Source material

Drop the raw material your presentation is based on here:

- Papers (PDFs), articles, references
- Source images, screenshots, diagrams in their original resolution
- Outlines, meeting notes, draft talking points
- Spreadsheets, CSVs, datasets

**This folder is NOT served by Slidev** — it's just your source-of-truth
for things that feed *into* the slides. Use it as scratchpad / archive.

For files the slides actually reference at runtime (images shown on a
slide via `![](/foo.png)`, embedded videos, etc.), put them in `public/`
instead — Slidev serves that folder at `/`.

Both folders are committed to git by default; if any single file in
`resources/` gets large (multi-MB PDFs), consider adding a `.gitignore`
entry or using Git LFS.
"""


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class ScaffoldResult:
    deck_dir: Path
    deck_name: str
    theme_name: str           # npm package name, or "@slidev/theme-default"
    theme_dir: Optional[Path] # None ⇒ using Slidev's built-in default
    theme_rel: Optional[str]  # forward-slash relpath used in package.json file: dep
    installed: bool           # whether npm install ran successfully
    mode: str                 # "gallery", "minimal", or "default-theme"
    slide_count: int          # how many slides the generated slides.md contains

    def preview_hint(self) -> str:
        return f'cd "{self.deck_dir}" && npx slidev'


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------

def _load_theme_metadata(theme_dir: Path) -> tuple[str, str]:
    """Return ``(theme_npm_name, theme_rel_path_unused_here)``.

    Validates the theme directory has a ``package.json`` with a ``"slidev"``
    key (the Slidev convention for marking a package as a theme) and a
    non-empty ``"name"`` field.
    """
    pkg_path = theme_dir / "package.json"
    if not pkg_path.is_file():
        raise FileNotFoundError(
            f"theme has no package.json: {pkg_path}"
        )
    try:
        pkg = json.loads(pkg_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(f"theme package.json is invalid JSON: {pkg_path} — {e}")
    if "slidev" not in pkg:
        raise ValueError(
            f"theme package.json missing required 'slidev' key (not a Slidev theme?): {pkg_path}"
        )
    name = pkg.get("name")
    if not name:
        raise ValueError(
            f"theme package.json missing 'name' field: {pkg_path}"
        )
    # Surface Slidev/npm naming rules as a Python error before we generate
    # any files referencing the bad name — otherwise the deck only fails
    # at `npx slidev` with a cryptic message buried in node_modules.
    validate_npm_package_name(name, role="theme")
    return name, str(pkg_path)


# ---------------------------------------------------------------------------
# Layout enumeration — for gallery mode
# ---------------------------------------------------------------------------

_LAYOUT_NUMBER_RE = re.compile(r"(\d+)")
_SLOT_NAME_RE = re.compile(r'<slot\s+name="([^"]+)"')


def _natural_sort_key(name: str) -> tuple:
    """Sort key that orders `slide2` before `slide10` (natural numeric order).

    Splits the name into alternating text/digit runs and converts the digit
    runs to ints so they compare numerically. Falls back to lexical for
    purely textual names.
    """
    parts = _LAYOUT_NUMBER_RE.split(name)
    return tuple(int(p) if p.isdigit() else p for p in parts)


def _enumerate_layouts(theme_dir: Path) -> list[str]:
    """Return layout names (without .vue suffix) for every .vue file in the
    theme's ``layouts/`` directory, sorted naturally so slide2 < slide10.

    Returns an empty list if the theme has no ``layouts/`` directory — that's
    the path for hand-scaffolded themes that ship only global styles. Callers
    fall back to the minimal starter when this returns [].
    """
    layouts_dir = theme_dir / "layouts"
    if not layouts_dir.is_dir():
        return []
    names = [p.stem for p in layouts_dir.glob("*.vue")]
    names.sort(key=_natural_sort_key)
    return names


def _extract_slot_names(layout_vue: Path) -> list[str]:
    """Return the ordered list of slot names declared in a layout .vue file.

    Reads ``<slot name="…" …/>`` declarations from the template. Order
    preserved by document order so the gallery comment lists slots in the
    same sequence the layout designer placed them — usually top-to-bottom,
    left-to-right.
    """
    try:
        text = layout_vue.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    return _SLOT_NAME_RE.findall(text)


# ---------------------------------------------------------------------------
# Demo-deck discovery and content copy
# ---------------------------------------------------------------------------
#
# When ``import-template`` generates a theme, it also writes a *demo deck*
# alongside it — one slide per layout, every slot populated with the
# original PPT's example content (title text, body copy, picture
# placeholder defaults). The demo deck looks "right" because each piece
# of text was authored for the layout's fixed-width box.
#
# Inventing our own placeholder text ("body-21 content", "Layout: slide1")
# overflows those boxes — the IU template's title slot is 475 × 116px at
# 101pt font; anything longer than ~10 chars wraps and breaks the design.
#
# So gallery mode now COPIES the demo deck's slides.md verbatim (just
# patching the global frontmatter to reference the user-chosen theme
# name + add a deck title). Falls back to a "structure-only" gallery
# (frontmatter + slot-name comment, no text overrides) when no demo
# deck is found — that's structurally clear and avoids the overflow
# problem at the cost of empty boxes.

# Where ``import-template`` puts the demo deck, relative to the theme:
#   <theme_dir>/../deck/slides.md
# Some users may also put it as a sibling literal "deck" folder of the
# theme dir's parent; we check both.
_DEMO_DECK_REL_CANDIDATES: tuple[Path, ...] = (
    Path("..") / "deck" / "slides.md",
    Path("..") / "demo" / "slides.md",
)


def _find_demo_deck(theme_dir: Path) -> Optional[Path]:
    """Return the path to a sibling demo-deck ``slides.md`` if one exists.

    The demo deck is what ``import-template`` writes as ``<base>/deck/``
    when it converts a PPTX. We check a couple of conventional locations
    relative to the theme directory; returning the first that resolves
    to a real file. ``None`` means "no demo deck available — fall back".
    """
    for rel in _DEMO_DECK_REL_CANDIDATES:
        candidate = (theme_dir / rel).resolve()
        if candidate.is_file():
            return candidate
    return None


# Match the FIRST frontmatter block at the top of a slides.md (between two
# `---` lines on their own). Multiline+dotall so the body can span lines.
_FIRST_FRONTMATTER_RE = re.compile(
    r"\A---\s*\n(.*?)\n---\s*\n",
    re.DOTALL,
)


def _patch_demo_deck_frontmatter(text: str, theme_name: str) -> str:
    """Take the demo deck's slides.md content, replace/insert ``theme:``
    in slide 1's frontmatter so it points at ``theme_name``.

    Idempotent — if the theme is already correct, no changes.

    Why patch instead of regenerate: we want to preserve every other
    field the demo deck happened to set (custom canvas size, fonts
    declared in frontmatter, etc.). Less brittle than rebuilding the
    YAML from scratch.
    """
    m = _FIRST_FRONTMATTER_RE.match(text)
    if m is None:
        # No frontmatter — that's unusual for a Slidev deck but possible.
        # Prepend a minimal one.
        return f"---\ntheme: {theme_name}\n---\n\n{text}"
    block = m.group(1)
    lines = block.split("\n")
    new_lines: list[str] = []
    theme_seen = False
    for line in lines:
        if line.startswith("theme:"):
            new_lines.append(f"theme: {theme_name}")
            theme_seen = True
        else:
            new_lines.append(line)
    if not theme_seen:
        new_lines.insert(0, f"theme: {theme_name}")
    new_block = "\n".join(new_lines)
    return f"---\n{new_block}\n---\n" + text[m.end():]


# ---------------------------------------------------------------------------
# Structure-only gallery (fallback when no demo deck available)
# ---------------------------------------------------------------------------

# Slots that are unique within a layout (≤1 each). Mirrors the singleton
# set in slidecraft.importer.emit.naming — keeping a small duplicate is
# easier than introducing a cross-package coupling on a 5-name list.
_SINGLETON_TEXT_SLOTS: frozenset[str] = frozenset({
    "title", "subtitle", "footer", "date", "slide-number",
})


def _render_slot_hint_comment(slots: list[str]) -> str:
    """Render an HTML comment listing the slots available for a layout.

    Used in structure-only mode (no demo deck). The user sees the layout
    rendered empty + a comment telling them which slot names they can
    override. No text overrides are emitted because we don't know what
    will fit the layout's fixed-width boxes; inventing text causes
    overflow (the bug that motivated this rewrite).
    """
    if not slots:
        return ""
    text_slots = [s for s in slots if not s.startswith("picture-")]
    pic_slots = [s for s in slots if s.startswith("picture-")]
    lines = ["<!-- Slots available in this layout:"]
    if text_slots:
        lines.append(f"  Text:    {', '.join(text_slots)}")
        lines.append(
            "    Override by adding a block like ``::<slot>::\\n<your text>``"
        )
    if pic_slots:
        lines.append(f"  Picture: {', '.join(pic_slots)}")
        lines.append(
            "    Default image is baked in; override with "
            "``::<slot>::\\n![](/your-image.png)``"
        )
    lines.append("-->")
    return "\n".join(lines)


def _render_structure_only_slides_md(
    deck_name: str,
    theme_name: str,
    theme_dir: Path,
    layouts: list[str],
) -> str:
    """Fallback gallery used when no sibling demo deck is found.

    Emits one slide per layout with NO text-slot overrides — just the
    ``layout:`` frontmatter and an HTML comment listing the slot names
    so the user knows what they can override. Layouts render with their
    text-slot boxes empty (the wrapper divs and backgrounds still show);
    picture slots render the default images the converter baked in.

    This is structurally informative but visually sparse. Use the
    demo-deck path (``_copy_demo_deck_as_gallery``) when one exists —
    that's the one that shows each layout's intended look with the
    template's original example content fitted to each box.
    """
    if not layouts:
        raise ValueError("gallery mode requires at least one layout")

    first_layout = layouts[0]
    first_slots = _extract_slot_names(theme_dir / "layouts" / f"{first_layout}.vue")

    parts: list[str] = ["---", f"theme: {theme_name}", f"layout: {first_layout}", "---", ""]
    parts.append(_GALLERY_INTRO_COMMENT)
    parts.append("")
    hint = _render_slot_hint_comment(first_slots)
    if hint:
        parts.append(hint)

    for layout in layouts[1:]:
        slots = _extract_slot_names(theme_dir / "layouts" / f"{layout}.vue")
        parts.append("")
        parts.append("---")
        parts.append(f"layout: {layout}")
        parts.append("---")
        parts.append("")
        hint = _render_slot_hint_comment(slots)
        if hint:
            parts.append(hint)

    return "\n".join(parts) + "\n"


def _copy_demo_deck_as_gallery(
    demo_deck_path: Path,
    theme_name: str,
) -> str:
    """Read the sibling demo deck and patch its frontmatter to use
    ``theme_name``. Returns the patched slides.md content.

    The demo deck was generated by ``import-template`` with one slide
    per layout, every slot already populated with the original PPT's
    example content. Because that content was authored for each layout's
    fixed-width box, it fits without overflow — unlike anything we'd
    invent at scaffold time.
    """
    text = demo_deck_path.read_text(encoding="utf-8")
    return _patch_demo_deck_frontmatter(text, theme_name)


def _render_gallery_slides_md(
    deck_name: str,
    theme_name: str,
    theme_dir: Path,
    layouts: list[str],
) -> str:
    """Render the full gallery slides.md.

    Two paths:
      1. **Demo-deck path (preferred)** — when a sibling demo deck exists
         (typically ``<theme_dir>/../deck/slides.md``, the one
         ``import-template`` generated), copy it verbatim with the
         frontmatter patched to reference ``theme_name``. The user gets
         a deck identical to the demo: every layout populated with the
         template's example content, fitted to each layout's geometry.

      2. **Structure-only path (fallback)** — when no demo deck is
         found, emit one slide per layout with NO text-slot overrides
         and a slot-name hint comment. Layouts render empty but
         structurally visible; picture defaults still show.

    Critical Slidev rule both paths respect: a single ``---`` line is
    both a slide separator AND a frontmatter delimiter. Inserting an
    extra ``---`` between slides whose frontmatter already opens with
    ``---`` creates an empty intermediate slide (regression we hit at
    99 slides for the 49-layout ILSE theme).
    """
    if not layouts:
        raise ValueError("gallery mode requires at least one layout")

    demo = _find_demo_deck(theme_dir)
    if demo is not None:
        return _copy_demo_deck_as_gallery(demo, theme_name)
    return _render_structure_only_slides_md(
        deck_name=deck_name,
        theme_name=theme_name,
        theme_dir=theme_dir,
        layouts=layouts,
    )


def _portable_relpath(target: Path, start: Path) -> str:
    """Return ``target`` relative to ``start`` using forward slashes.

    Npm's ``file:`` protocol accepts both slash styles on Windows, but
    forward slashes are universally portable and what every Slidev
    example uses. Resolve both ends first so we don't get confused by
    symlinks or relative pieces.
    """
    rel = os.path.relpath(target.resolve(), start.resolve())
    return rel.replace("\\", "/")


def _render_package_json(
    deck_name: str,
    theme_name: str,
    theme_rel: Optional[str],
) -> str:
    """Render package.json with stable key ordering."""
    # The deck's own npm package name is the lowercased deck_name. Validate
    # so a deck_name like "my deck" or "my!deck" fails fast instead of
    # generating an unrunnable package.json.
    npm_deck_name = deck_name.lower()
    validate_npm_package_name(npm_deck_name, role="deck")
    pkg: dict = {
        "name": npm_deck_name,
        "private": True,
        "scripts": {
            "dev": "slidev",
            "build": "slidev build",
            "export": "slidev export",
        },
        "dependencies": {
            "@slidev/cli": "^52.0.0",
        },
    }
    if theme_rel is not None:
        pkg["dependencies"][theme_name] = f"file:{theme_rel}"
    return json.dumps(pkg, indent=2) + "\n"


def _npm_install(deck_dir: Path) -> bool:
    """Run ``npm install`` in ``deck_dir``. Returns True on success.

    Captures output to avoid spamming the caller's stdout; on failure,
    prints stderr so the user can diagnose. Doesn't raise — the deck is
    still usable if the user wants to run npm install themselves later.
    """
    cmd = ["npm", "install"]
    # On Windows, `npm` is a `npm.cmd` shim that needs shell=True for
    # subprocess to find it via PATH. On POSIX it's a binary — shell=False
    # is fine. Use shell=True universally; the args are not user-controlled.
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(deck_dir),
            shell=True,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        sys.stderr.write(
            "npm not found on PATH — skipping install. "
            f"Run `cd {deck_dir} && npm install` manually.\n"
        )
        return False
    if proc.returncode != 0:
        sys.stderr.write(
            f"npm install failed (exit {proc.returncode}):\n{proc.stderr}\n"
        )
        return False
    return True


def scaffold_deck(
    deck_dir: Path,
    theme_dir: Optional[Path],
    deck_name: str,
    *,
    overwrite: bool = False,
    install: bool = True,
    minimal: bool = False,
) -> ScaffoldResult:
    """Create a new Slidev deck at ``deck_dir`` consuming ``theme_dir``.

    Parameters
    ----------
    deck_dir
        Absolute path where the deck folder will be created. Must not
        already exist unless ``overwrite=True``.
    theme_dir
        Absolute path to a Slidev theme directory (must contain a
        ``package.json`` with a ``"slidev"`` key). Pass ``None`` to use
        Slidev's built-in default theme — no ``file:`` dependency is
        added in that case.
    deck_name
        Human-readable name for the deck. Used as the title in
        ``slides.md`` frontmatter and (lowercased) as the npm package
        name in ``package.json``.
    overwrite
        If True and ``deck_dir`` already exists, files inside it will be
        overwritten. Default False (raises ``FileExistsError``).
    install
        If True (default), run ``npm install`` in the deck dir after
        scaffolding. Set False for tests or when the caller wants to
        defer install.
    minimal
        If True, skip gallery mode and emit a 2-slide starter even when
        the theme exposes many layouts. Default False — gallery mode
        (one slide per layout) is the standard, because slides without
        an explicit ``layout:`` frontmatter use Slidev's built-in
        default layout (NOT the theme's styling), so the gallery is
        what makes "the theme actually loads" obviously true on first
        ``npx slidev``.
    """
    deck_dir = Path(deck_dir)
    if deck_dir.exists() and not overwrite:
        raise FileExistsError(
            f"deck directory already exists: {deck_dir} "
            f"(pass overwrite=True to proceed)"
        )

    # Validate and resolve the theme (or set defaults for the no-theme path).
    theme_name = "@slidev/theme-default"
    theme_rel: Optional[str] = None
    layouts: list[str] = []
    if theme_dir is not None:
        theme_dir = Path(theme_dir)
        theme_name, _ = _load_theme_metadata(theme_dir)
        theme_rel = _portable_relpath(theme_dir, deck_dir)
        layouts = _enumerate_layouts(theme_dir)

    # Create directories.
    #   public/    — Slidev convention; runtime-served at /, slides reference
    #                as `![](/foo.png)`. For artifacts that ship with the deck.
    #   resources/ — source material the deck is based on (papers, raw
    #                images, outlines, meeting notes). NOT served by Slidev.
    #                Separate folder so the user can keep a clean line
    #                between "input material" and "runtime assets".
    deck_dir.mkdir(parents=True, exist_ok=overwrite)
    (deck_dir / "public").mkdir(exist_ok=True)
    (deck_dir / "resources").mkdir(exist_ok=True)
    (deck_dir / "resources" / "README.md").write_text(
        _RESOURCES_README, encoding="utf-8",
    )

    # Choose the slides.md template:
    #   • No theme            → 2-slide default-theme starter
    #   • Theme + minimal     → 2-slide minimal starter pinned to layouts[0]
    #   • Theme + has layouts → gallery (one slide per layout)
    #   • Theme + no layouts  → minimal pinned to "default"
    if theme_dir is None:
        slides_md = _SLIDES_MD_DEFAULT_THEME.format(deck_name=deck_name)
        mode = "default-theme"
        slide_count = 2
    elif minimal or not layouts:
        # Pin to the first available layout if any, else fall back to
        # "default" (Slidev's built-in) so the slide at least renders.
        first_layout = layouts[0] if layouts else "default"
        slides_md = _SLIDES_MD_MINIMAL_WITH_THEME.format(
            theme_name=theme_name,
            deck_name=deck_name,
            first_layout=first_layout,
        )
        mode = "minimal"
        slide_count = 2
    else:
        slides_md = _render_gallery_slides_md(
            deck_name=deck_name,
            theme_name=theme_name,
            theme_dir=theme_dir,
            layouts=layouts,
        )
        mode = "gallery"
        slide_count = len(layouts)

    (deck_dir / "slides.md").write_text(slides_md, encoding="utf-8")
    (deck_dir / "package.json").write_text(
        _render_package_json(deck_name, theme_name, theme_rel),
        encoding="utf-8",
    )
    (deck_dir / ".gitignore").write_text(_GITIGNORE, encoding="utf-8")

    installed = _npm_install(deck_dir) if install else False

    return ScaffoldResult(
        deck_dir=deck_dir,
        deck_name=deck_name,
        theme_name=theme_name,
        theme_dir=theme_dir,
        theme_rel=theme_rel,
        installed=installed,
        mode=mode,
        slide_count=slide_count,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="python -m slidecraft.scaffold.new_deck",
        description="Scaffold a new Slidev deck that consumes an existing theme.",
    )
    p.add_argument("--name", required=True, help="Deck name (folder + npm package name)")
    p.add_argument(
        "--location", required=True,
        help="Parent directory where the deck folder will be created "
             "(the deck folder itself is <location>/<name>).",
    )
    p.add_argument(
        "--theme", default=None,
        help="Absolute path to a Slidev theme directory. Omit to use "
             "Slidev's built-in default theme.",
    )
    p.add_argument(
        "--no-install", action="store_true",
        help="Skip the `npm install` step. The deck is still usable; "
             "the caller is responsible for installing later.",
    )
    p.add_argument(
        "--overwrite", action="store_true",
        help="Allow writing into an existing deck directory.",
    )
    p.add_argument(
        "--minimal", action="store_true",
        help="Emit a 2-slide starter instead of the default gallery mode "
             "(one slide per theme layout). Use when you want to start "
             "from a blank slate and already know which layouts you'll "
             "use.",
    )
    return p.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = _parse_args(argv)
    deck_dir = Path(args.location) / args.name
    theme_dir = Path(args.theme) if args.theme else None
    try:
        result = scaffold_deck(
            deck_dir=deck_dir,
            theme_dir=theme_dir,
            deck_name=args.name,
            overwrite=args.overwrite,
            install=not args.no_install,
            minimal=args.minimal,
        )
    except (FileExistsError, FileNotFoundError, ValueError) as e:
        sys.stderr.write(f"error: {e}\n")
        return 1

    # Human-readable summary on stdout — same fields a downstream LLM
    # would surface to the user.
    print(f"deck_dir:    {result.deck_dir}")
    print(f"deck_name:   {result.deck_name}")
    print(f"theme_name:  {result.theme_name}")
    print(f"theme_dir:   {result.theme_dir if result.theme_dir else '(Slidev built-in default)'}")
    print(f"theme_rel:   {result.theme_rel if result.theme_rel else '(none)'}")
    print(f"mode:        {result.mode}")
    print(f"slide_count: {result.slide_count}")
    print(f"installed:   {result.installed}")
    print(f"preview:     {result.preview_hint()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
