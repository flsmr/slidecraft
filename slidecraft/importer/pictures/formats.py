"""Image format classification for the pictures pipeline.

Classifies image data by source format and fidelity using both magic-byte
detection and filename extension, preferring magic bytes when they disagree.
"""
from __future__ import annotations

from pathlib import Path


# ---------------------------------------------------------------------------
# Magic-byte signatures
# ---------------------------------------------------------------------------

# Each entry: (format_name, magic_bytes, byte_offset)
_MAGIC: list[tuple[str, bytes, int]] = [
    ("png",  b"\x89PNG\r\n\x1a\n",  0),
    ("gif",  b"GIF87a",              0),
    ("gif",  b"GIF89a",              0),
    ("jpeg", b"\xff\xd8\xff",        0),
    ("bmp",  b"BM",                  0),
    # EMF: ENHMETARECORD type=1, size at offset 4 (typically 0x58 or larger)
    # The canonical EMF magic is the first 4 bytes = 0x01 0x00 0x00 0x00
    ("emf",  b"\x01\x00\x00\x00",   0),
    # WMF: placeable WMF header starts with 0x9AC6CDD7
    ("wmf",  b"\xd7\xcd\xc6\x9a",   0),
    # TIFF: little-endian II or big-endian MM + magic 42
    ("tiff", b"II\x2a\x00",          0),
    ("tiff", b"MM\x00\x2a",          0),
]

# SVG is XML text; detect by sniffing the first 512 bytes for SVG markers
_SVG_MARKERS = (b"<svg", b"<?xml")

# Formats that render with full fidelity in a browser
_EXACT_FORMATS = frozenset({"png", "jpeg", "gif", "svg", "webp"})

# Extension → format name (lower-cased, dot-stripped)
_EXT_TO_FMT: dict[str, str] = {
    "png":  "png",
    "jpg":  "jpeg",
    "jpeg": "jpeg",
    "gif":  "gif",
    "svg":  "svg",
    "webp": "webp",
    "emf":  "emf",
    "wmf":  "wmf",
    "tiff": "tiff",
    "tif":  "tiff",
    "bmp":  "bmp",
}


def _detect_magic(data: bytes) -> str | None:
    """Return format name from magic bytes, or *None* if unrecognised."""
    # SVG check first — it's text-based so no magic header
    head = data[:512].lower()
    for marker in _SVG_MARKERS:
        if marker in head:
            return "svg"

    for fmt, magic, offset in _MAGIC:
        end = offset + len(magic)
        if len(data) >= end and data[offset:end] == magic:
            return fmt

    return None


def _fmt_from_extension(filename: str) -> str | None:
    """Return format name derived from *filename*'s extension, or *None*."""
    ext = Path(filename).suffix.lstrip(".").lower()
    return _EXT_TO_FMT.get(ext)


def classify(filename: str, data: bytes) -> tuple[str, str, list[str]]:
    """Classify image *data* by format, fidelity, and any warnings.

    Uses magic-byte detection as the primary signal and falls back to the
    filename extension.  When magic bytes and extension disagree, magic bytes
    win.

    Args:
        filename: Original filename (used for extension fallback only).
        data:     Raw image bytes.

    Returns:
        A three-tuple ``(source_format, fidelity, warnings)`` where:

        * ``source_format`` is a lower-cased format string such as ``"png"``,
          ``"jpeg"``, ``"gif"``, ``"svg"``, ``"emf"``, ``"wmf"``, ``"tiff"``,
          or ``"bmp"``.
        * ``fidelity`` is ``"exact"`` for browser-native formats (PNG, JPEG,
          GIF, SVG) or ``"low"`` for formats that cannot be rendered faithfully
          in a web browser (EMF, WMF, TIFF, BMP).
        * ``warnings`` is an empty list for exact formats, or a list containing
          ``"unsupported_format:<ext>"`` for low-fidelity formats.
    """
    # Magic-byte detection takes precedence
    fmt = _detect_magic(data)

    # Fall back to extension when magic detection is inconclusive
    if fmt is None:
        fmt = _fmt_from_extension(filename)

    # Last resort: mark as unknown
    if fmt is None:
        ext = Path(filename).suffix.lstrip(".").lower() or "unknown"
        return ext, "low", [f"unsupported_format:{ext}"]

    if fmt in _EXACT_FORMATS:
        return fmt, "exact", []

    return fmt, "low", [f"unsupported_format:{fmt}"]
