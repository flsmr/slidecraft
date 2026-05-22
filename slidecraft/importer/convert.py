"""Top-level orchestrator: pptx_path → theme_dir + deck_dir."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .emit import emit_deck, emit_layouts, emit_theme
from .fonts.manifest import resolve_fonts
from .parse import parse


@dataclass
class ConvertResult:
    theme_dir: Path
    deck_dir: Path
    slides_count: int
    typefaces_resolved: int
    typefaces_substituted: int
    typefaces_fallback: int
    warnings: list[str]


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
    emit_theme(presentation, theme_dir, theme_name=theme_name)
    font_manifest = resolve_fonts(
        pptx_path=pptx_path,
        typefaces=presentation.typefaces_referenced,
        theme_dir=theme_dir,
    )
    emit_layouts(presentation, theme_dir)

    try:
        theme_rel = Path("..") / theme_dir.resolve().relative_to(deck_dir.resolve().parent)
    except ValueError:
        theme_rel = theme_dir.resolve()
    emit_deck(presentation, deck_dir, theme_relative_path=str(theme_rel).replace("\\", "/"))

    substituted = sum(1 for e in font_manifest.values() if e.get("source") == "metric-substitute")
    fallback = sum(1 for e in font_manifest.values() if e.get("source") == "fallback")

    return ConvertResult(
        theme_dir=theme_dir,
        deck_dir=deck_dir,
        slides_count=len(presentation.slides),
        typefaces_resolved=len(font_manifest),
        typefaces_substituted=substituted,
        typefaces_fallback=fallback,
        warnings=warnings,
    )
