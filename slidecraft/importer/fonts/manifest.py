"""Fonts pipeline orchestrator.

Runs the 4-stage resolution pipeline per typeface, writes
``theme/public/fonts/manifest.json``, and emits ``@font-face`` blocks into
``theme/styles/index.css``.

Pipeline (first match wins per typeface):
  1. Embedded  — extract from .pptx zip, deobfuscate
  2. Google Fonts — CSS endpoint lookup + woff2 download
  3. Metric-substitute — copy from bundled data/substitutes/
  4. Generic fallback — emit manifest entry only, source: "fallback"
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

import requests

from .extract import extract_embedded_fonts
from .google import lookup_google_fonts
from .substitute import copy_substitute

# Generic CSS fallback families keyed by font scheme classification
_GENERIC_FALLBACK: dict[str, str] = {
    "latin": "sans-serif",
    "serif": "serif",
    "mono": "monospace",
    "ea": "sans-serif",       # East Asian
    "cs": "sans-serif",       # Complex Script
}

_DEFAULT_FALLBACK = "sans-serif"


def _classify_typeface(
    typeface: str,
    theme_fontscheme: dict | None,
) -> str:
    """Return a generic CSS family for *typeface* from the font scheme, or sans-serif."""
    if not theme_fontscheme:
        return _DEFAULT_FALLBACK

    # theme_fontscheme is expected to be a dict like:
    # { "latin": ["Calibri", ...], "serif": [...], "mono": [...] }
    for classification, names in theme_fontscheme.items():
        if isinstance(names, list) and typeface in names:
            return _GENERIC_FALLBACK.get(classification, _DEFAULT_FALLBACK)

    return _DEFAULT_FALLBACK


def _build_font_face_block(
    typeface: str,
    filename: str,
    weight: int,
    style: str,
    fmt: str = "woff2",
) -> str:
    """Return a single ``@font-face`` CSS block."""
    ext_to_fmt = {
        ".woff2": "woff2",
        ".woff": "woff",
        ".ttf": "truetype",
        ".otf": "opentype",
        ".ttc": "truetype",
    }
    suffix = Path(filename).suffix.lower()
    css_fmt = ext_to_fmt.get(suffix, fmt)
    return (
        f'@font-face {{\n'
        f'  font-family: "{typeface}";\n'
        f'  font-weight: {weight};\n'
        f'  font-style: {style};\n'
        f'  src: url("/fonts/{filename}") format("{css_fmt}");\n'
        f'}}'
    )


def _write_font_face_css(
    typeface: str,
    variants: list[dict],
    css_path: Path,
) -> None:
    """Append ``@font-face`` blocks for *typeface* to *css_path*."""
    css_path.parent.mkdir(parents=True, exist_ok=True)
    blocks = []
    for v in variants:
        block = _build_font_face_block(
            typeface=typeface,
            filename=v["file"],
            weight=v["weight"],
            style=v["style"],
        )
        blocks.append(block)

    content = "\n".join(blocks) + "\n"

    if css_path.exists():
        existing = css_path.read_text(encoding="utf-8")
        css_path.write_text(existing + "\n" + content, encoding="utf-8")
    else:
        css_path.write_text(content, encoding="utf-8")


def _write_manifest(manifest: dict, manifest_path: Path) -> None:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def resolve_fonts(
    pptx_path: Path,
    typefaces: set[str],
    theme_dir: Path,
    theme_fontscheme: dict | None = None,
) -> dict:
    """Resolve all *typefaces* and populate the theme's font assets.

    Runs the 4-stage pipeline (embedded → Google Fonts → metric-substitute →
    fallback) for each typeface, writes font files to
    ``theme/public/fonts/``, appends ``@font-face`` blocks to
    ``theme/styles/index.css``, and writes ``theme/public/fonts/manifest.json``.

    Args:
        pptx_path:        Path to the source .pptx file.
        typefaces:        Set of typeface names to resolve.
        theme_dir:        Root of the generated Slidev theme directory.
        theme_fontscheme: Optional parsed ``<a:fontScheme>`` dict for fallback
                          classification.  Keys are classifications like
                          ``"latin"``, ``"serif"``, ``"mono"``; values are lists
                          of typeface names in that category.

    Returns:
        The manifest dict that was written to manifest.json.
    """
    fonts_public_dir = theme_dir / "public" / "fonts"
    css_path = theme_dir / "styles" / "index.css"
    manifest_path = fonts_public_dir / "manifest.json"

    fonts_public_dir.mkdir(parents=True, exist_ok=True)
    (theme_dir / "styles").mkdir(parents=True, exist_ok=True)

    # Stage 1: extract all embedded fonts up-front so we can query by typeface
    embedded_by_typeface: dict[str, list[str]] = {}
    if pptx_path.exists():
        try:
            embedded_by_typeface = extract_embedded_fonts(pptx_path, fonts_public_dir)
        except (zipfile.BadZipFile, Exception):
            # Non-fatal: a broken or missing PPTX falls through to later stages
            pass

    # Shared requests session for all Google Fonts lookups
    http_session = requests.Session()

    manifest: dict[str, Any] = {}

    for typeface in sorted(typefaces):
        # ------------------------------------------------------------------ #
        # Stage 1 — Embedded                                                  #
        # ------------------------------------------------------------------ #
        if typeface in embedded_by_typeface:
            files = embedded_by_typeface[typeface]
            variants = _infer_variants_from_filenames(files, family_name=typeface)
            entry: dict[str, Any] = {
                "source": "embedded",
                "files": files,
                "variants": variants,
                "fidelity": "exact",
            }
            manifest[typeface] = entry
            _write_font_face_css(typeface, variants, css_path)
            continue

        # ------------------------------------------------------------------ #
        # Stage 2 — Google Fonts                                              #
        # ------------------------------------------------------------------ #
        gf_entry = lookup_google_fonts(
            typeface,
            dest_dir=fonts_public_dir,
            session=http_session,
        )
        if gf_entry is not None:
            manifest[typeface] = {k: v for k, v in gf_entry.items() if k != "variants"}
            _write_font_face_css(typeface, gf_entry["variants"], css_path)
            continue

        # ------------------------------------------------------------------ #
        # Stage 3 — Metric-substitute                                        #
        # ------------------------------------------------------------------ #
        sub_entry = copy_substitute(typeface, dest_dir=fonts_public_dir)
        if sub_entry is not None:
            manifest[typeface] = {k: v for k, v in sub_entry.items() if k != "variants"}
            _write_font_face_css(typeface, sub_entry["variants"], css_path)
            continue

        # ------------------------------------------------------------------ #
        # Stage 4 — Generic fallback                                          #
        # ------------------------------------------------------------------ #
        fallback_family = _classify_typeface(typeface, theme_fontscheme)
        manifest[typeface] = {
            "source": "fallback",
            "fallback": fallback_family,
            "fidelity": "low",
        }
        # No @font-face block for pure fallbacks — the CSS class references
        # the generic family directly via the fallback chain.

    _write_manifest(manifest, manifest_path)
    return manifest


# Weight modifier names recognized at the end of a family name.
_SUBFAMILY_WEIGHT_NAMES: dict[str, int] = {
    "thin": 100, "hairline": 100,
    "extralight": 200, "ultralight": 200,
    "light": 300,
    "medium": 500,
    "semibold": 600, "demibold": 600,
    "bold": 700,
    "extrabold": 800, "ultrabold": 800, "heavy": 800,
    "black": 900,
}


def _natural_weight_for_family(family_name: str) -> int:
    """Return the natural CSS weight encoded by a family name's trailing modifier.

    "Source Sans Pro Bold" → 700, "Helvetica Neue Light" → 300, otherwise 400.
    """
    norm = family_name.strip()
    for name, weight in sorted(_SUBFAMILY_WEIGHT_NAMES.items(), key=lambda x: -len(x[0])):
        for sep in (" ", "-"):
            suffix = f"{sep}{name}"
            if len(norm) > len(suffix) and norm.lower().endswith(suffix.lower()):
                return weight
    return 400


def _infer_variants_from_filenames(files: list[str], family_name: str = "") -> list[dict]:
    """Infer weight/style metadata from font filenames.

    Handles common naming patterns: *-Regular.ttf, *-Bold.ttf, *-Italic.ttf,
    *-BoldItalic.ttf, and the w400/w700 pattern used by Google downloads.

    When ``family_name`` ends in a weight modifier ("Source Sans Pro Bold",
    "Helvetica Neue Light", etc.), the variant suffix is interpreted relative
    to that natural weight: a "Bold" file inside a Bold subfamily is the
    family's natural rendering (CSS weight = the modifier), not extra-bold.
    Only "BoldItalic" within a non-400 subfamily is mapped one step bolder.
    """
    natural = _natural_weight_for_family(family_name) if family_name else 400
    is_modified = natural != 400
    extra_bold = min(natural + 200, 900) if is_modified else 700

    variants = []
    for filename in files:
        stem = Path(filename).stem
        # Variant info comes from the trailing "-<suffix>" only, never the
        # family prefix — otherwise "SourceSansProBold-Italic" would match
        # both "bold" and "italic" patterns due to the family name.
        suffix = stem.rsplit("-", 1)[-1].lower() if "-" in stem else stem.lower()
        weight = natural
        style = "normal"

        if "bolditalic" in suffix or ("bold" in suffix and "italic" in suffix):
            weight = extra_bold if is_modified else 700
            style = "italic"
        elif "bold" in suffix:
            # In a Bold/Light/etc. subfamily the "Bold" file IS the natural
            # rendering (the family name already implies the weight).
            weight = natural if is_modified else 700
            style = "normal"
        elif "italic" in suffix:
            weight = natural
            style = "italic"
        elif "w700i" in suffix:
            weight = 700
            style = "italic"
        elif "w700" in suffix:
            weight = 700
            style = "normal"
        elif "w400i" in suffix:
            weight = 400
            style = "italic"

        variants.append({"file": filename, "weight": weight, "style": style})
    return variants
