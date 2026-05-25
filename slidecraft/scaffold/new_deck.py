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
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

_SLIDES_MD_WITH_THEME = """\
---
theme: {theme_name}
title: {deck_name}
---

# {deck_name}

Replace this with your opening slide.

---

# Slide 2

- Bullet one
- Bullet two

---

# Slot overrides

When a layout exposes named slots (e.g. ``slide14`` from an imported theme),
override them with ``::slot-name::`` blocks. Example:

```
---
layout: slide14
---

::title::
My custom title

::body-19::
My custom body

::picture-22::
![](/my-image.png)
```

Drop assets into ``public/`` and reference them as ``/filename.ext`` from any
slide.
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

_GITIGNORE = """\
node_modules/
dist/
.slidev/
*.log
.DS_Store
Thumbs.db
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
    return name, str(pkg_path)


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
    pkg: dict = {
        "name": deck_name.lower(),
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
    if theme_dir is not None:
        theme_dir = Path(theme_dir)
        theme_name, _ = _load_theme_metadata(theme_dir)
        theme_rel = _portable_relpath(theme_dir, deck_dir)

    # Create directories.
    deck_dir.mkdir(parents=True, exist_ok=overwrite)
    (deck_dir / "public").mkdir(exist_ok=True)

    # Render templates.
    if theme_dir is not None:
        slides_md = _SLIDES_MD_WITH_THEME.format(
            theme_name=theme_name, deck_name=deck_name,
        )
    else:
        slides_md = _SLIDES_MD_DEFAULT_THEME.format(deck_name=deck_name)

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
    print(f"installed:   {result.installed}")
    print(f"preview:     {result.preview_hint()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
