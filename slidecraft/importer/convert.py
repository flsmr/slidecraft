"""Top-level orchestrator: pptx_path → theme_dir + deck_dir."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from .emit import emit_deck, emit_layouts, emit_theme
from .fonts import strip_weight_suffix
from .fonts.substitute import SUBSTITUTE_TABLE
from .parse import parse

# Substitute names that need a space inserted for the Google Fonts URL.
# e.g. our local file uses "DejaVuSans" but Google Fonts lists "DejaVu Sans".
_GOOGLE_FONTS_DISPLAY_NAME: dict[str, str] = {
    "DejaVuSans": "DejaVu Sans",
}


@dataclass
class ConvertResult:
    theme_dir: Path
    deck_dir: Path
    slides_count: int
    typefaces_total: int
    typefaces_substituted: int
    sans_families: list[str] = field(default_factory=list)
    alias_font_faces: dict[str, tuple[str, int]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def _resolve_typeface_for_google_fonts(typeface: str) -> tuple[str, bool]:
    """Return (resolved_name, was_substituted) suitable for Google Fonts.

    - MS-proprietary names (Calibri, Cambria, …) are remapped via SUBSTITUTE_TABLE
      to a metric-compatible open-source family that Google Fonts hosts
      (Calibri → Carlito, Cambria → Caladea, …).
    - DejaVuSans → "DejaVu Sans" (Google Fonts API uses the spaced form).
    - Otherwise passes through unchanged.
    """
    substitute = SUBSTITUTE_TABLE.get(typeface)
    if substitute is not None:
        return _GOOGLE_FONTS_DISPLAY_NAME.get(substitute, substitute), True
    return _GOOGLE_FONTS_DISPLAY_NAME.get(typeface, typeface), False


def convert(
    pptx_path: Path,
    theme_dir: Path,
    deck_dir: Path,
    *,
    theme_name: str = "slidev-theme-slidecraft-tmp",
) -> ConvertResult:
    pptx_path = Path(pptx_path)
    theme_dir = Path(theme_dir)
    deck_dir = Path(deck_dir)
    warnings: list[str] = []

    presentation = parse(pptx_path)

    # Build the Google-Fonts-resolvable sans list (substitute MS fonts, strip
    # weight suffixes so Google Fonts receives the base family name).
    # Also collect aliases: weight-suffix typeface names → (base, weight) so
    # emit_theme can write @font-face alias blocks in styles/index.css.
    sans_families: list[str] = []
    alias_font_faces: dict[str, tuple[str, int]] = {}
    seen: set[str] = set()
    substituted_count = 0

    for tf in sorted(presentation.typefaces_referenced):
        # First apply MS-proprietary substitution (Calibri → Carlito etc.)
        resolved_ms, was_sub = _resolve_typeface_for_google_fonts(tf)
        if was_sub:
            substituted_count += 1

        # Then strip any trailing weight/style modifier from the name so Google
        # Fonts receives "Source Sans Pro" instead of "Source Sans Pro Bold".
        base_family, natural_weight = strip_weight_suffix(resolved_ms)
        is_weight_alias = base_family != resolved_ms

        if is_weight_alias:
            # Record alias so emit_theme can write @font-face blocks.
            # Key is the verbatim PPT name (what layouts reference),
            # value is (base_family, natural_weight) for the @font-face src.
            alias_font_faces[tf] = (base_family, natural_weight)

        if base_family not in seen:
            seen.add(base_family)
            sans_families.append(base_family)

    emit_theme(
        presentation,
        theme_dir,
        theme_name=theme_name,
        sans_families=sans_families,
        alias_font_faces=alias_font_faces or None,
    )
    emit_layouts(presentation, theme_dir)

    theme_rel = os.path.relpath(theme_dir.resolve(), deck_dir.resolve()).replace("\\", "/")
    emit_deck(presentation, deck_dir, theme_relative_path=theme_rel)

    return ConvertResult(
        theme_dir=theme_dir,
        deck_dir=deck_dir,
        slides_count=len(presentation.slides),
        typefaces_total=len(presentation.typefaces_referenced),
        typefaces_substituted=substituted_count,
        sans_families=sans_families,
        alias_font_faces=alias_font_faces,
        warnings=warnings,
    )
