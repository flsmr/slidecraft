"""Stage 1 — Embedded font extraction from .pptx zip.

PowerPoint obfuscates the first 32 bytes of embedded TTF/OTF files by XOR-ing
them with a GUID derived from the font relationship ID.  The GUID is encoded in
the part URI as a sequence of hex pairs; this module reverses that obfuscation
and returns raw font bytes ready to write to disk.

Reference:
  ECMA-376 Part 1 §14.2.7 (Embedded Fonts)
  https://docs.microsoft.com/en-us/openspecs/office_file_formats/ms-oe376/…
  The deobfuscation algorithm: XOR the first 32 bytes of the font data with
  the 16-byte GUID in little-endian byte order, repeated twice.
"""
from __future__ import annotations

import re
import zipfile
from pathlib import Path, PurePosixPath
from typing import Iterator
from xml.etree import ElementTree as ET

# XML namespace map used across PPTX internals
_NS = {
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
}

# Relationship type for embedded fonts
_EMBEDDED_FONT_REL = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/font"
)

# Pattern for the GUID portion in a font part URI, e.g.:
#   /ppt/fonts/font1.fntdata  → no GUID here, it's in the rel target
#   The obfuscation key is extracted from the font data's relationship rid
_GUID_RE = re.compile(
    r"\{([0-9A-Fa-f]{8})-([0-9A-Fa-f]{4})-([0-9A-Fa-f]{4})"
    r"-([0-9A-Fa-f]{4})-([0-9A-Fa-f]{12})\}"
)


def _guid_to_key(guid_str: str) -> bytes:
    """Convert a GUID string to the 16-byte deobfuscation key.

    PowerPoint stores the GUID in standard string form
    ``{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}`` and uses it to XOR the first
    32 bytes of the embedded font (the key is used twice).

    The byte order follows the COM/Windows GUID binary layout:
      - First  4 bytes → little-endian DWORD
      - Next   2 bytes → little-endian WORD
      - Next   2 bytes → little-endian WORD
      - Last   8 bytes → big-endian (as-is)
    """
    m = _GUID_RE.match(guid_str.strip())
    if not m:
        raise ValueError(f"Cannot parse GUID: {guid_str!r}")

    p1 = int(m.group(1), 16)   # 4-byte LE
    p2 = int(m.group(2), 16)   # 2-byte LE
    p3 = int(m.group(3), 16)   # 2-byte LE
    p4 = bytes.fromhex(m.group(4))  # 2 bytes, big-endian
    p5 = bytes.fromhex(m.group(5))  # 6 bytes, big-endian

    key = (
        p1.to_bytes(4, "little")
        + p2.to_bytes(2, "little")
        + p3.to_bytes(2, "little")
        + p4
        + p5
    )
    assert len(key) == 16, f"Key length mismatch: {len(key)}"
    return key


def _deobfuscate(data: bytes, key: bytes) -> bytes:
    """XOR the first 32 bytes of *data* with *key* (repeated twice)."""
    if len(data) < 32:
        # Too short to XOR fully; XOR what we have
        xor_key = (key * 2)[: len(data)]
        return bytes(b ^ k for b, k in zip(data, xor_key))
    obfuscated = data[:32]
    xor_key = key * 2  # 32 bytes
    clear = bytes(b ^ k for b, k in zip(obfuscated, xor_key))
    return clear + data[32:]


def _parse_presentation_rels(zf: zipfile.ZipFile) -> dict[str, str]:
    """Return {rId: target_path} for ppt/presentation.xml.rels."""
    rels_path = "ppt/_rels/presentation.xml.rels"
    try:
        xml = zf.read(rels_path)
    except KeyError:
        return {}
    root = ET.fromstring(xml)
    result: dict[str, str] = {}
    for rel in root:
        rid = rel.get("Id", "")
        target = rel.get("Target", "")
        result[rid] = target
    return result


def _read_presentation_xml(zf: zipfile.ZipFile) -> ET.Element | None:
    """Parse ppt/presentation.xml and return its root element."""
    try:
        xml = zf.read("ppt/presentation.xml")
        return ET.fromstring(xml)
    except KeyError:
        return None


def _iter_embedded_font_parts(
    zf: zipfile.ZipFile,
) -> Iterator[tuple[str, str, bytes]]:
    """Yield (typeface_name, suggested_filename, raw_deobfuscated_bytes).

    Walks ``<p:embeddedFontLst>`` in ``ppt/presentation.xml``, resolves each
    font's relationship target, reads the obfuscated bytes, and deobfuscates.
    The GUID for deobfuscation is derived from the ``<p:font>`` element's
    ``typeface`` attribute per the MS-OE376 spec.  In practice many real-world
    files encode the GUID in the font part URI; we handle both.
    """
    prs_root = _read_presentation_xml(zf)
    if prs_root is None:
        return

    prs_rels = _parse_presentation_rels(zf)

    # <p:embeddedFontLst> may appear directly under <p:presentation>
    ns_p = "http://schemas.openxmlformats.org/presentationml/2006/main"
    ns_a = "http://schemas.openxmlformats.org/drawingml/2006/main"
    ns_r = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

    font_lst = prs_root.find(f"{{{ns_p}}}embeddedFontLst")
    if font_lst is None:
        return

    for embedded in font_lst.findall(f"{{{ns_p}}}embeddedFont"):
        font_el = embedded.find(f"{{{ns_p}}}font")
        if font_el is None:
            continue
        typeface = font_el.get("typeface", "").strip()
        if not typeface:
            continue

        # Each variant (regular, bold, italic, boldItalic) is a child element
        variants = {
            "regular":    (400, "normal"),
            "bold":       (700, "normal"),
            "italic":     (400, "italic"),
            "boldItalic": (700, "italic"),
        }
        for variant_tag, (weight, style) in variants.items():
            variant_el = embedded.find(f"{{{ns_p}}}{variant_tag}")
            if variant_el is None:
                continue
            rid = variant_el.get(f"{{{ns_r}}}id", "")
            if not rid:
                continue

            target = prs_rels.get(rid, "")
            if not target:
                continue

            # Normalise the part path (targets are relative to ppt/)
            if target.startswith("/"):
                part_path = target.lstrip("/")
            else:
                part_path = f"ppt/{target}"

            try:
                raw_data = zf.read(part_path)
            except KeyError:
                continue

            # Extract the GUID from the part URI if present; fall back to rid
            guid_str = _extract_guid_from_path(part_path) or _extract_guid_from_rid(rid)
            if guid_str:
                try:
                    key = _guid_to_key(guid_str)
                    font_bytes = _deobfuscate(raw_data, key)
                except (ValueError, AssertionError):
                    font_bytes = raw_data  # use as-is if GUID parsing fails
            else:
                font_bytes = raw_data

            # Determine the file extension from the first bytes (magic numbers)
            ext = _sniff_extension(font_bytes)
            safe_name = typeface.replace(" ", "")
            variant_suffix = {
                "regular": "Regular",
                "bold": "Bold",
                "italic": "Italic",
                "boldItalic": "BoldItalic",
            }[variant_tag]
            filename = f"{safe_name}-{variant_suffix}{ext}"

            yield typeface, filename, font_bytes


def _extract_guid_from_path(path: str) -> str | None:
    """Try to extract a GUID from the font part path."""
    m = _GUID_RE.search(path)
    return m.group(0) if m else None


def _extract_guid_from_rid(rid: str) -> str | None:
    """Try to extract a GUID from the relationship ID (rare)."""
    m = _GUID_RE.search(rid)
    return m.group(0) if m else None


def _sniff_extension(data: bytes) -> str:
    """Return .ttf or .otf based on font magic bytes; default .ttf."""
    if data[:4] == b"OTTO":
        return ".otf"
    if data[:4] in (b"\x00\x01\x00\x00", b"true", b"typ1"):
        return ".ttf"
    # TrueType collections
    if data[:4] == b"ttcf":
        return ".ttc"
    return ".ttf"  # safe default


def extract_embedded_fonts(
    pptx_path: Path,
    dest_dir: Path,
) -> dict[str, list[str]]:
    """Extract all embedded fonts from *pptx_path* to *dest_dir*.

    Returns a dict mapping typeface name → list of filenames written.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    result: dict[str, list[str]] = {}

    with zipfile.ZipFile(pptx_path, "r") as zf:
        for typeface, filename, font_bytes in _iter_embedded_font_parts(zf):
            dest = dest_dir / filename
            dest.write_bytes(font_bytes)
            result.setdefault(typeface, []).append(filename)

    return result
