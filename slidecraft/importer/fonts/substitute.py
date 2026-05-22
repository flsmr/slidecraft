"""Stage 3 — Metric-compatible font substitution.

Maps Microsoft proprietary typeface names to open-source metric-compatible
alternatives bundled in ``data/substitutes/``.  Copies the selected variant
files to the theme's public fonts directory and returns manifest metadata.

Inconsolata special case:
  Only Regular and Bold variants exist in the bundle (no italic or bold-italic).
  The manifest records ``italic: "synthesized"`` so the verifier and CSS layer
  know that italic rendering relies on browser synthesis rather than a real
  italic font file.
"""
from __future__ import annotations

import shutil
from pathlib import Path

# Location of bundled substitute font files (relative to this module)
_DATA_DIR = Path(__file__).parent / "data" / "substitutes"

# Maps PPT typeface name → substitute family name (as used in file names)
SUBSTITUTE_TABLE: dict[str, str] = {
    "Calibri":          "Carlito",
    "Cambria":          "Caladea",
    "Times New Roman":  "Tinos",
    "Arial":            "Arimo",
    "Courier New":      "Cousine",
    "Consolas":         "Inconsolata",
    "Verdana":          "DejaVuSans",
}

# Variants available for most families
_STANDARD_VARIANTS: list[tuple[str, int, str]] = [
    ("Regular",    400, "normal"),
    ("Bold",       700, "normal"),
    ("Italic",     400, "italic"),
    ("BoldItalic", 700, "italic"),
]

# Families that only have a subset of variants
_VARIANT_OVERRIDES: dict[str, list[tuple[str, int, str]]] = {
    "Inconsolata": [
        ("Regular", 400, "normal"),
        ("Bold",    700, "normal"),
        # No Italic or BoldItalic — handled via CSS font-synthesis
    ],
}


def copy_substitute(
    typeface: str,
    dest_dir: Path,
) -> dict | None:
    """Copy substitute font files for *typeface* into *dest_dir*.

    Returns a manifest entry dict if the typeface is in the substitute table,
    or None if it is not.

    Args:
        typeface:  The PPT typeface name (verbatim).
        dest_dir:  Destination directory (``theme/public/fonts/``).
    """
    substitute_family = SUBSTITUTE_TABLE.get(typeface)
    if substitute_family is None:
        return None

    dest_dir.mkdir(parents=True, exist_ok=True)

    variants = _VARIANT_OVERRIDES.get(substitute_family, _STANDARD_VARIANTS)
    copied_files: list[str] = []
    font_face_meta: list[dict] = []

    for variant_name, weight, style in variants:
        filename = f"{substitute_family}-{variant_name}.ttf"
        src_file = _DATA_DIR / filename
        if not src_file.exists():
            continue  # skip missing variants gracefully

        dest_file = dest_dir / filename
        if not dest_file.exists():
            shutil.copy2(src_file, dest_file)

        copied_files.append(filename)
        font_face_meta.append({
            "file": filename,
            "weight": weight,
            "style": style,
        })

    if not copied_files:
        return None

    entry: dict = {
        "source": "metric-substitute",
        "substitute": substitute_family,
        "files": copied_files,
        "variants": font_face_meta,
        "fidelity": "high",
    }

    # Special annotation for Inconsolata: no real italic files
    if substitute_family == "Inconsolata":
        entry["italic"] = "synthesized"

    return entry
