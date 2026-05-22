"""Tests for embedded font extraction (Stage 1).

Uses in-memory PPTX fixtures built with python-pptx so no binary files need
to be committed.  The deobfuscation helpers are tested directly with known
vectors.
"""
from __future__ import annotations

import io
import struct
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from slidecraft.importer.fonts.extract import (
    _deobfuscate,
    _guid_to_key,
    _sniff_extension,
    extract_embedded_fonts,
)


# ---------------------------------------------------------------------------
# Unit tests for deobfuscation helpers
# ---------------------------------------------------------------------------

class TestGuidToKey:
    def test_canonical_guid(self):
        guid = "{12345678-1234-1234-1234-123456789ABC}"
        key = _guid_to_key(guid)
        assert len(key) == 16

    def test_first_4_bytes_little_endian(self):
        # GUID "{01000000-0000-0000-0000-000000000000}"
        # First 4 bytes = 0x00000001 in LE = bytes [01, 00, 00, 00]
        guid = "{01000000-0000-0000-0000-000000000000}"
        key = _guid_to_key(guid)
        assert key[:4] == bytes([0x00, 0x00, 0x00, 0x01])

    def test_word2_little_endian(self):
        # GUID "{00000000-0102-0000-0000-000000000000}"
        # bytes 4-5 = 0x0102 LE = [02, 01]
        guid = "{00000000-0102-0000-0000-000000000000}"
        key = _guid_to_key(guid)
        assert key[4:6] == bytes([0x02, 0x01])

    def test_invalid_guid_raises(self):
        with pytest.raises(ValueError):
            _guid_to_key("not-a-guid")


class TestDeobfuscate:
    def test_identity_when_key_zeros(self):
        key = bytes(16)
        data = bytes(range(64))
        result = _deobfuscate(data, key)
        assert result == data

    def test_xor_first_32_bytes(self):
        key = bytes([0xFF] * 16)
        data = bytes([0x00] * 64)
        result = _deobfuscate(data, key)
        # First 32 bytes XOR'd with 0xFF = 0xFF; remainder unchanged
        assert result[:32] == bytes([0xFF] * 32)
        assert result[32:] == bytes([0x00] * 32)

    def test_bytes_beyond_32_untouched(self):
        key = bytes([0xAB] * 16)
        tail = bytes([0x42] * 100)
        data = bytes(32) + tail
        result = _deobfuscate(data, key)
        assert result[32:] == tail

    def test_short_data_handled(self):
        key = bytes([0xFF] * 16)
        data = bytes([0x00] * 10)
        result = _deobfuscate(data, key)
        assert len(result) == 10
        assert all(b == 0xFF for b in result)

    def test_roundtrip(self):
        """XOR is its own inverse: deobfuscate(deobfuscate(x)) == x."""
        key = bytes(range(16))
        data = bytes(range(64))
        once = _deobfuscate(data, key)
        twice = _deobfuscate(once, key)
        assert twice == data


class TestSniffExtension:
    def test_ttf_magic(self):
        assert _sniff_extension(b"\x00\x01\x00\x00" + bytes(60)) == ".ttf"

    def test_otf_magic(self):
        assert _sniff_extension(b"OTTO" + bytes(60)) == ".otf"

    def test_true_magic(self):
        assert _sniff_extension(b"true" + bytes(60)) == ".ttf"

    def test_unknown_defaults_to_ttf(self):
        assert _sniff_extension(bytes(64)) == ".ttf"


# ---------------------------------------------------------------------------
# Integration-style test: PPTX with no embedded fonts
# ---------------------------------------------------------------------------

def _make_minimal_pptx_no_embedded_fonts() -> bytes:
    """Build a minimal valid PPTX zip with no <p:embeddedFontLst>."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # Minimal presentation.xml without embeddedFontLst
        prs_xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
            "</p:presentation>"
        )
        zf.writestr("ppt/presentation.xml", prs_xml)
        # Empty rels
        rels_xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            "</Relationships>"
        )
        zf.writestr("ppt/_rels/presentation.xml.rels", rels_xml)
    return buf.getvalue()


class TestExtractNoEmbeddedFonts:
    def test_returns_empty_dict(self, tmp_path: Path):
        pptx_bytes = _make_minimal_pptx_no_embedded_fonts()
        pptx_file = tmp_path / "no_fonts.pptx"
        pptx_file.write_bytes(pptx_bytes)
        dest = tmp_path / "out"

        result = extract_embedded_fonts(pptx_file, dest)

        assert result == {}

    def test_dest_dir_created(self, tmp_path: Path):
        pptx_bytes = _make_minimal_pptx_no_embedded_fonts()
        pptx_file = tmp_path / "no_fonts.pptx"
        pptx_file.write_bytes(pptx_bytes)
        dest = tmp_path / "fonts_out"

        extract_embedded_fonts(pptx_file, dest)

        assert dest.exists()


# ---------------------------------------------------------------------------
# Integration-style test: PPTX with a mock embedded font
# ---------------------------------------------------------------------------

_NS_P = "http://schemas.openxmlformats.org/presentationml/2006/main"
_NS_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_NS_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
_FONT_REL_TYPE = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/font"
)


def _make_pptx_with_embedded_font(typeface: str, font_data: bytes) -> bytes:
    """Build a minimal PPTX with one embedded font (regular variant only).

    The GUID is embedded in the font part filename (as real PPT does) so that
    extract.py can locate it for deobfuscation.
    """
    # The GUID used for obfuscation; embedded in the part filename
    guid = "{AABBCCDD-1122-3344-5566-778899AABBCC}"
    guid_bare = "AABBCCDD112233445566778899AABBCC"  # no braces/hyphens (unused here)

    # Obfuscate the first 32 bytes of the font data (simulating PPT export)
    from slidecraft.importer.fonts.extract import _guid_to_key, _deobfuscate
    key = _guid_to_key(guid)
    obfuscated = _deobfuscate(font_data, key)  # XOR is symmetric

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # Embed the GUID in the font part path so the extractor can find it
        font_filename = f"font{guid}.fntdata"
        font_part = f"ppt/fonts/{font_filename}"
        zf.writestr(font_part, obfuscated)

        # Write presentation.xml with embeddedFontLst
        prs_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<p:presentation xmlns:p="{_NS_P}" xmlns:r="{_NS_R}">
  <p:embeddedFontLst>
    <p:embeddedFont>
      <p:font typeface="{typeface}"/>
      <p:regular r:id="rId1"/>
    </p:embeddedFont>
  </p:embeddedFontLst>
</p:presentation>"""
        zf.writestr("ppt/presentation.xml", prs_xml)

        # Write rels — target is relative to ppt/
        rels_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="{_NS_REL}">
  <Relationship Id="rId1" Type="{_FONT_REL_TYPE}" Target="fonts/{font_filename}"/>
</Relationships>"""
        zf.writestr("ppt/_rels/presentation.xml.rels", rels_xml)

    return buf.getvalue()


class TestExtractWithEmbeddedFont:
    def test_embedded_font_extracted(self, tmp_path: Path):
        # Build fake TTF data (starts with TTF magic)
        font_data = b"\x00\x01\x00\x00" + bytes(60)
        pptx_bytes = _make_pptx_with_embedded_font("MyFont", font_data)
        pptx_file = tmp_path / "with_font.pptx"
        pptx_file.write_bytes(pptx_bytes)
        dest = tmp_path / "fonts"

        result = extract_embedded_fonts(pptx_file, dest)

        assert "MyFont" in result
        assert len(result["MyFont"]) == 1
        written = dest / result["MyFont"][0]
        assert written.exists()

    def test_deobfuscation_applied(self, tmp_path: Path):
        """The written bytes should equal the original (pre-obfuscation) data."""
        original_data = b"\x00\x01\x00\x00" + bytes(range(60))
        pptx_bytes = _make_pptx_with_embedded_font("RoundTrip", original_data)
        pptx_file = tmp_path / "rt.pptx"
        pptx_file.write_bytes(pptx_bytes)
        dest = tmp_path / "fonts"

        result = extract_embedded_fonts(pptx_file, dest)

        assert "RoundTrip" in result
        written_path = dest / result["RoundTrip"][0]
        written = written_path.read_bytes()
        assert written == original_data
