"""Emit theme scaffolding: package.json (with Slidev-native font config)."""
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
    *,
    sans_families: list[str] | None = None,
    weights: str = "400,600,700",
) -> None:
    """Write theme scaffolding into *theme_dir*.

    Idempotent: safe to call when theme_dir already exists.

    Creates ``package.json`` only. Fonts are configured via Slidev's native
    ``slidev.defaults.fonts`` mechanism so Slidev's Google-Fonts auto-import
    fetches them — no styles/index.css, no bundled @font-face, no Vite
    conditional-styles path issues.
    """
    theme_dir = Path(theme_dir)
    theme_dir.mkdir(parents=True, exist_ok=True)

    aspect_ratio = _simplify_ratio(
        presentation.canvas_width_px, presentation.canvas_height_px
    )

    fonts_cfg: dict[str, str] = {"weights": weights}
    if sans_families:
        # Comma-separated list — Slidev fetches each from Google Fonts.
        fonts_cfg["sans"] = ", ".join(sans_families)

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
                "fonts": fonts_cfg,
            },
        },
    }
    (theme_dir / "package.json").write_text(
        json.dumps(pkg, indent=2), encoding="utf-8"
    )
