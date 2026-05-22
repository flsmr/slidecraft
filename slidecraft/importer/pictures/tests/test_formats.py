"""Tests for slidecraft.importer.pictures.formats.classify."""
from __future__ import annotations

import pytest

from slidecraft.importer.pictures.formats import classify


# ---------------------------------------------------------------------------
# PNG
# ---------------------------------------------------------------------------

class TestPNG:
    _MAGIC = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100

    def test_exact_fidelity(self):
        fmt, fidelity, warnings = classify("image.png", self._MAGIC)
        assert fidelity == "exact"

    def test_format_name(self):
        fmt, _, _ = classify("image.png", self._MAGIC)
        assert fmt == "png"

    def test_no_warnings(self):
        _, _, warnings = classify("image.png", self._MAGIC)
        assert warnings == []

    def test_magic_overrides_wrong_extension(self):
        """PNG magic bytes recognised even with a .jpg extension."""
        fmt, fidelity, _ = classify("photo.jpg", self._MAGIC)
        assert fmt == "png"
        assert fidelity == "exact"


# ---------------------------------------------------------------------------
# JPEG
# ---------------------------------------------------------------------------

class TestJPEG:
    _MAGIC = b"\xff\xd8\xff\xe0" + b"\x00" * 100

    def test_exact_fidelity(self):
        _, fidelity, _ = classify("photo.jpg", self._MAGIC)
        assert fidelity == "exact"

    def test_format_name(self):
        fmt, _, _ = classify("photo.jpg", self._MAGIC)
        assert fmt == "jpeg"

    def test_no_warnings(self):
        _, _, warnings = classify("photo.jpeg", self._MAGIC)
        assert warnings == []

    def test_jpg_extension_alias(self):
        fmt, fidelity, _ = classify("photo.jpg", self._MAGIC)
        assert fmt == "jpeg"
        assert fidelity == "exact"


# ---------------------------------------------------------------------------
# GIF
# ---------------------------------------------------------------------------

class TestGIF:
    _MAGIC_87 = b"GIF87a" + b"\x00" * 100
    _MAGIC_89 = b"GIF89a" + b"\x00" * 100

    def test_gif87a_exact(self):
        fmt, fidelity, warnings = classify("anim.gif", self._MAGIC_87)
        assert fmt == "gif"
        assert fidelity == "exact"
        assert warnings == []

    def test_gif89a_exact(self):
        fmt, fidelity, warnings = classify("anim.gif", self._MAGIC_89)
        assert fmt == "gif"
        assert fidelity == "exact"
        assert warnings == []


# ---------------------------------------------------------------------------
# SVG
# ---------------------------------------------------------------------------

class TestSVG:
    _SVG_DATA = b'<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg"></svg>'
    _SVG_BARE = b'<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"></svg>'

    def test_xml_prefix_exact(self):
        fmt, fidelity, warnings = classify("icon.svg", self._SVG_DATA)
        assert fmt == "svg"
        assert fidelity == "exact"
        assert warnings == []

    def test_bare_svg_tag_exact(self):
        fmt, fidelity, _ = classify("icon.svg", self._SVG_BARE)
        assert fmt == "svg"
        assert fidelity == "exact"

    def test_svg_extension_extension_fallback(self):
        """When data is empty-ish, extension should kick in."""
        # Very short data that won't trigger magic — use just whitespace
        fmt, fidelity, _ = classify("icon.svg", b"   ")
        assert fmt == "svg"
        assert fidelity == "exact"


# ---------------------------------------------------------------------------
# EMF
# ---------------------------------------------------------------------------

class TestEMF:
    # Canonical EMF magic: first 4 bytes = 0x01 0x00 0x00 0x00
    _MAGIC = b"\x01\x00\x00\x00" + b"\x58\x00\x00\x00" + b"\x00" * 100

    def test_low_fidelity(self):
        _, fidelity, _ = classify("chart.emf", self._MAGIC)
        assert fidelity == "low"

    def test_format_name(self):
        fmt, _, _ = classify("chart.emf", self._MAGIC)
        assert fmt == "emf"

    def test_warning_present(self):
        _, _, warnings = classify("chart.emf", self._MAGIC)
        assert "unsupported_format:emf" in warnings


# ---------------------------------------------------------------------------
# WMF
# ---------------------------------------------------------------------------

class TestWMF:
    # Placeable WMF: starts with 0x9AC6CDD7 (little-endian)
    _MAGIC = b"\xd7\xcd\xc6\x9a" + b"\x00" * 100

    def test_low_fidelity(self):
        _, fidelity, _ = classify("logo.wmf", self._MAGIC)
        assert fidelity == "low"

    def test_format_name(self):
        fmt, _, _ = classify("logo.wmf", self._MAGIC)
        assert fmt == "wmf"

    def test_warning_present(self):
        _, _, warnings = classify("logo.wmf", self._MAGIC)
        assert "unsupported_format:wmf" in warnings


# ---------------------------------------------------------------------------
# TIFF
# ---------------------------------------------------------------------------

class TestTIFF:
    _MAGIC_LE = b"II\x2a\x00" + b"\x00" * 100  # little-endian
    _MAGIC_BE = b"MM\x00\x2a" + b"\x00" * 100  # big-endian

    def test_little_endian_low(self):
        fmt, fidelity, warnings = classify("scan.tiff", self._MAGIC_LE)
        assert fmt == "tiff"
        assert fidelity == "low"
        assert "unsupported_format:tiff" in warnings

    def test_big_endian_low(self):
        fmt, fidelity, _ = classify("scan.tif", self._MAGIC_BE)
        assert fmt == "tiff"
        assert fidelity == "low"


# ---------------------------------------------------------------------------
# BMP
# ---------------------------------------------------------------------------

class TestBMP:
    _MAGIC = b"BM" + b"\x00" * 100

    def test_low_fidelity(self):
        _, fidelity, _ = classify("icon.bmp", self._MAGIC)
        assert fidelity == "low"

    def test_format_name(self):
        fmt, _, _ = classify("icon.bmp", self._MAGIC)
        assert fmt == "bmp"

    def test_warning_present(self):
        _, _, warnings = classify("icon.bmp", self._MAGIC)
        assert "unsupported_format:bmp" in warnings


# ---------------------------------------------------------------------------
# Unknown / fallback
# ---------------------------------------------------------------------------

class TestUnknown:
    def test_unknown_extension_returns_low(self):
        _, fidelity, warnings = classify("file.xyz", b"\x00\x01\x02\x03" * 10)
        assert fidelity == "low"
        assert len(warnings) == 1
        assert warnings[0].startswith("unsupported_format:")

    def test_completely_empty_data_extension_fallback(self):
        # Empty data + known extension → extension wins
        fmt, fidelity, warnings = classify("image.png", b"")
        assert fmt == "png"
        assert fidelity == "exact"
