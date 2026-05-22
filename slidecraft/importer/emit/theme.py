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


def _build_alias_css(alias_font_faces: dict[str, tuple[str, int]]) -> str:
    """Build ``@font-face`` CSS blocks that alias weight-suffix names.

    *alias_font_faces* maps ``alias_name → (base_family, weight)`` so that
    ``font-family: 'Source Sans Pro Bold'`` in layout ``.vue`` files resolves
    to the Bold weight of ``'Source Sans Pro'`` (which Slidev fetches from
    Google Fonts by its correct base name).

    For each alias we emit two blocks — ``font-weight: 400`` and
    ``font-weight: 700`` — so the alias resolves regardless of whether the
    layout CSS specifies a weight or not.

    Example output::

        @font-face {
          font-family: 'Source Sans Pro Bold';
          src: local('Source Sans Pro Bold'), local('SourceSansPro-Bold');
          font-weight: 400;
          font-style: normal;
        }
        @font-face {
          font-family: 'Source Sans Pro Bold';
          src: local('Source Sans Pro Bold'), local('SourceSansPro-Bold');
          font-weight: 700;
          font-style: normal;
        }

    The ``local()`` hint is intentionally a lie — it makes the browser
    immediately resolve to the Google-Fonts-downloaded glyphs of the base
    family at the correct weight without requiring us to bundle font files.
    Slidev has already loaded the base family at all weights via its Google
    Fonts mechanism, so the rendered weight matches.

    We use ``font-weight: <natural>`` as the override target inside a
    ``@supports`` wrapper so that browsers that don't need the alias still
    get the correct weight.  For simplicity we emit the alias blocks
    unconditionally — they are harmless when the base family is present.
    """
    lines: list[str] = []
    for alias, (base_family, natural_weight) in sorted(alias_font_faces.items()):
        # Two blocks per alias: one covering weight 400 (no explicit weight in
        # layout), one covering weight 700 (layout sets font-weight:700).
        # Both point to the natural weight of the base family so the browser
        # uses the correct glyph set regardless of what the layout requests.
        for style in ("normal", "italic"):
            for declared_weight in sorted({400, natural_weight}):
                no_space = base_family.replace(" ", "")
                weight_name = {700: "Bold", 600: "SemiBold", 300: "Light",
                               800: "ExtraBold", 200: "ExtraLight", 900: "Black",
                               500: "Medium", 100: "Thin"}.get(natural_weight, "Regular")
                style_suffix = "Italic" if style == "italic" else ""
                local1 = f"{base_family} {weight_name}{style_suffix}".strip()
                local2 = f"{no_space}-{weight_name}{style_suffix}"
                lines.append("@font-face {")
                lines.append(f"  font-family: '{alias}';")
                lines.append(f"  src: local('{local1}'), local('{local2}');")
                lines.append(f"  font-weight: {declared_weight};")
                lines.append(f"  font-style: {style};")
                lines.append("  font-display: swap;")
                lines.append("}")
    return "\n".join(lines) + "\n" if lines else ""


def emit_theme(
    presentation: Presentation,
    theme_dir: Path,
    theme_name: str = "slidev-theme-slidecraft-tmp",
    *,
    sans_families: list[str] | None = None,
    weights: str = "400,600,700",
    alias_font_faces: dict[str, tuple[str, int]] | None = None,
) -> None:
    """Write theme scaffolding into *theme_dir*.

    Idempotent: safe to call when theme_dir already exists.

    Creates ``package.json``.  Fonts are configured via Slidev's native
    ``slidev.defaults.fonts`` mechanism so Slidev's Google-Fonts auto-import
    fetches them by their correct base family names.

    When *alias_font_faces* is provided it maps weight-suffix typeface names
    (verbatim PPT names like ``'Source Sans Pro Bold'``) to their base family
    and natural CSS weight.  A ``styles/index.css`` is written with
    ``@font-face`` alias blocks so that layout ``.vue`` files referencing the
    weight-suffix name still resolve to the correct glyphs and weight.
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

    # We no longer write styles/index.css with @font-face alias blocks.
    # Slidev's @slidev/conditional-styles Vite plugin chokes on it when the
    # theme lives at an absolute Windows path. Instead, emit/layout.py strips
    # the weight suffix from font-family declarations at emit time (so the
    # CSS already references the correct base family + font-weight pair) and
    # Slidev's native Google-Fonts auto-import handles the rest.
    # The alias_font_faces parameter is retained for backwards compatibility
    # but is no longer written to disk.
