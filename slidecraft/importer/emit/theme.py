"""Emit theme scaffolding: package.json, styles/index.css, public/fonts/."""
from __future__ import annotations

import json
import math
from pathlib import Path

from ..model import Presentation


def _simplify_ratio(w: int, h: int) -> str:
    """Return w/h simplified by GCD (e.g. 1920/1080 → '16/9')."""
    g = math.gcd(w, h)
    return f"{w // g}/{h // g}"


def emit_theme(
    presentation: Presentation,
    theme_dir: Path,
    theme_name: str = "slidev-theme-slidecraft-tmp",
) -> None:
    """Write theme scaffolding into *theme_dir*.

    Idempotent: safe to call when theme_dir already exists.

    Creates:
    - ``package.json``
    - ``styles/index.css``  (empty; fonts pipeline appends @font-face blocks)
    - ``public/fonts/``     (empty dir; fonts pipeline writes binaries there)
    """
    theme_dir = Path(theme_dir)
    theme_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ #
    # package.json
    # ------------------------------------------------------------------ #
    aspect_ratio = _simplify_ratio(
        presentation.canvas_width_px, presentation.canvas_height_px
    )
    pkg = {
        "name": theme_name,
        "version": "0.0.1",
        "keywords": ["slidev-theme", "slidev"],
        "engines": {"slidev": ">=0.48.0"},
        "slidev": {
            "colorSchema": "light",
            "defaults": {
                "canvasWidth": presentation.canvas_width_px,
                "aspectRatio": aspect_ratio,
                "fonts": {"provider": "none"},
            },
        },
    }
    (theme_dir / "package.json").write_text(
        json.dumps(pkg, indent=2), encoding="utf-8"
    )

    # ------------------------------------------------------------------ #
    # styles/index.css  (empty placeholder; fonts pipeline appends here)
    # ------------------------------------------------------------------ #
    styles_dir = theme_dir / "styles"
    styles_dir.mkdir(exist_ok=True)
    index_css = styles_dir / "index.css"
    if not index_css.exists():
        index_css.write_text("", encoding="utf-8")

    # ------------------------------------------------------------------ #
    # public/fonts/  (empty directory; fonts pipeline writes binaries here)
    # ------------------------------------------------------------------ #
    fonts_dir = theme_dir / "public" / "fonts"
    fonts_dir.mkdir(parents=True, exist_ok=True)
