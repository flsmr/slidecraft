"""Tests for slidecraft.importer.pictures.extract and manifest."""
from __future__ import annotations

import io
import json
import os
import zipfile
from pathlib import Path

import pytest

from slidecraft.importer.pictures.extract import extract_pictures
from slidecraft.importer.pictures.manifest import load_manifest, write_manifest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
_JPEG_MAGIC = b"\xff\xd8\xff\xe0" + b"\x00" * 100
_EMF_MAGIC = b"\x01\x00\x00\x00" + b"\x58\x00\x00\x00" + b"\x00" * 100


def _make_pptx(media: dict[str, bytes]) -> bytes:
    """Build an in-memory PPTX zip with *media* files under ppt/media/."""
    buf = io.BytesIO()
    ns_p = "http://schemas.openxmlformats.org/presentationml/2006/main"
    ns_rel = "http://schemas.openxmlformats.org/package/2006/relationships"
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        prs_xml = (
            f'<?xml version="1.0" encoding="UTF-8"?>'
            f'<p:presentation xmlns:p="{ns_p}"></p:presentation>'
        )
        zf.writestr("ppt/presentation.xml", prs_xml)
        rels_xml = (
            f'<?xml version="1.0" encoding="UTF-8"?>'
            f'<Relationships xmlns="{ns_rel}"></Relationships>'
        )
        zf.writestr("ppt/_rels/presentation.xml.rels", rels_xml)
        for name, data in media.items():
            zf.writestr(f"ppt/media/{name}", data)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# extract_pictures — basic asset copy
# ---------------------------------------------------------------------------

class TestExtractPictures:
    def test_png_file_lands_in_assets(self, tmp_path: Path):
        pptx_bytes = _make_pptx({"image1.png": _PNG_MAGIC})
        pptx_path = tmp_path / "deck.pptx"
        pptx_path.write_bytes(pptx_bytes)

        extract_pictures(pptx_path, tmp_path / "theme")

        assert (tmp_path / "theme" / "public" / "assets" / "image1.png").exists()

    def test_jpeg_file_lands_in_assets(self, tmp_path: Path):
        pptx_bytes = _make_pptx({"photo.jpg": _JPEG_MAGIC})
        pptx_path = tmp_path / "deck.pptx"
        pptx_path.write_bytes(pptx_bytes)

        extract_pictures(pptx_path, tmp_path / "theme")

        assert (tmp_path / "theme" / "public" / "assets" / "photo.jpg").exists()

    def test_bytes_are_identical(self, tmp_path: Path):
        pptx_bytes = _make_pptx({"image1.png": _PNG_MAGIC})
        pptx_path = tmp_path / "deck.pptx"
        pptx_path.write_bytes(pptx_bytes)

        extract_pictures(pptx_path, tmp_path / "theme")

        written = (tmp_path / "theme" / "public" / "assets" / "image1.png").read_bytes()
        assert written == _PNG_MAGIC

    def test_multiple_files(self, tmp_path: Path):
        media = {
            "image1.png": _PNG_MAGIC,
            "photo.jpg": _JPEG_MAGIC,
            "chart.emf": _EMF_MAGIC,
        }
        pptx_bytes = _make_pptx(media)
        pptx_path = tmp_path / "deck.pptx"
        pptx_path.write_bytes(pptx_bytes)

        extract_pictures(pptx_path, tmp_path / "theme")

        assets = tmp_path / "theme" / "public" / "assets"
        assert (assets / "image1.png").exists()
        assert (assets / "photo.jpg").exists()
        assert (assets / "chart.emf").exists()

    def test_no_media_returns_empty_manifest(self, tmp_path: Path):
        pptx_bytes = _make_pptx({})
        pptx_path = tmp_path / "deck.pptx"
        pptx_path.write_bytes(pptx_bytes)

        manifest = extract_pictures(pptx_path, tmp_path / "theme")

        assert manifest == {}

    def test_returns_manifest_dict(self, tmp_path: Path):
        pptx_bytes = _make_pptx({"image1.png": _PNG_MAGIC})
        pptx_path = tmp_path / "deck.pptx"
        pptx_path.write_bytes(pptx_bytes)

        manifest = extract_pictures(pptx_path, tmp_path / "theme")

        assert isinstance(manifest, dict)
        assert "image1.png" in manifest


# ---------------------------------------------------------------------------
# extract_pictures — manifest content
# ---------------------------------------------------------------------------

class TestExtractManifestContent:
    def test_png_entry_exact_fidelity(self, tmp_path: Path):
        pptx_bytes = _make_pptx({"image1.png": _PNG_MAGIC})
        pptx_path = tmp_path / "deck.pptx"
        pptx_path.write_bytes(pptx_bytes)

        manifest = extract_pictures(pptx_path, tmp_path / "theme")

        entry = manifest["image1.png"]
        assert entry["source_format"] == "png"
        assert entry["fidelity"] == "exact"
        assert entry["warnings"] == []
        assert entry["derivatives"] == {}

    def test_emf_entry_low_fidelity(self, tmp_path: Path):
        pptx_bytes = _make_pptx({"chart.emf": _EMF_MAGIC})
        pptx_path = tmp_path / "deck.pptx"
        pptx_path.write_bytes(pptx_bytes)

        manifest = extract_pictures(pptx_path, tmp_path / "theme")

        entry = manifest["chart.emf"]
        assert entry["source_format"] == "emf"
        assert entry["fidelity"] == "low"
        assert "unsupported_format:emf" in entry["warnings"]

    def test_manifest_json_written_to_disk(self, tmp_path: Path):
        pptx_bytes = _make_pptx({"image1.png": _PNG_MAGIC})
        pptx_path = tmp_path / "deck.pptx"
        pptx_path.write_bytes(pptx_bytes)

        extract_pictures(pptx_path, tmp_path / "theme")

        manifest_path = tmp_path / "theme" / "public" / "assets" / "manifest.json"
        assert manifest_path.exists()

    def test_manifest_json_is_valid(self, tmp_path: Path):
        pptx_bytes = _make_pptx({"image1.png": _PNG_MAGIC})
        pptx_path = tmp_path / "deck.pptx"
        pptx_path.write_bytes(pptx_bytes)

        extract_pictures(pptx_path, tmp_path / "theme")

        manifest_path = tmp_path / "theme" / "public" / "assets" / "manifest.json"
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert "image1.png" in data

    def test_manifest_json_trailing_newline(self, tmp_path: Path):
        pptx_bytes = _make_pptx({"image1.png": _PNG_MAGIC})
        pptx_path = tmp_path / "deck.pptx"
        pptx_path.write_bytes(pptx_bytes)

        extract_pictures(pptx_path, tmp_path / "theme")

        manifest_path = tmp_path / "theme" / "public" / "assets" / "manifest.json"
        raw = manifest_path.read_text(encoding="utf-8")
        assert raw.endswith("\n")


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------

class TestIdempotency:
    def test_rerun_same_pptx_is_noop_on_bytes(self, tmp_path: Path):
        pptx_bytes = _make_pptx({"image1.png": _PNG_MAGIC})
        pptx_path = tmp_path / "deck.pptx"
        pptx_path.write_bytes(pptx_bytes)
        theme_dir = tmp_path / "theme"

        extract_pictures(pptx_path, theme_dir)
        asset = theme_dir / "public" / "assets" / "image1.png"
        mtime_first = asset.stat().st_mtime

        # Second run: file should NOT be overwritten (same bytes)
        extract_pictures(pptx_path, theme_dir)
        mtime_second = asset.stat().st_mtime

        assert mtime_first == mtime_second

    def test_rerun_different_bytes_overwrites(self, tmp_path: Path):
        pptx_bytes = _make_pptx({"image1.png": _PNG_MAGIC})
        pptx_path = tmp_path / "deck.pptx"
        pptx_path.write_bytes(pptx_bytes)
        theme_dir = tmp_path / "theme"

        extract_pictures(pptx_path, theme_dir)

        # Rebuild pptx with different bytes for same filename
        new_png = _PNG_MAGIC + b"\xff" * 50
        pptx_bytes2 = _make_pptx({"image1.png": new_png})
        pptx_path.write_bytes(pptx_bytes2)

        extract_pictures(pptx_path, theme_dir)

        written = (theme_dir / "public" / "assets" / "image1.png").read_bytes()
        assert written == new_png

    def test_manifest_rewritten_on_rerun(self, tmp_path: Path):
        pptx_bytes = _make_pptx({"image1.png": _PNG_MAGIC})
        pptx_path = tmp_path / "deck.pptx"
        pptx_path.write_bytes(pptx_bytes)
        theme_dir = tmp_path / "theme"

        extract_pictures(pptx_path, theme_dir)

        # Second pptx with an extra file
        pptx_bytes2 = _make_pptx({"image1.png": _PNG_MAGIC, "photo.jpg": _JPEG_MAGIC})
        pptx_path.write_bytes(pptx_bytes2)
        extract_pictures(pptx_path, theme_dir)

        manifest_path = theme_dir / "public" / "assets" / "manifest.json"
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert "photo.jpg" in data


# ---------------------------------------------------------------------------
# manifest read/write helpers
# ---------------------------------------------------------------------------

class TestManifestHelpers:
    def test_write_then_load_roundtrip(self, tmp_path: Path):
        manifest = {
            "image1.png": {
                "source_format": "png",
                "fidelity": "exact",
                "derivatives": {},
                "warnings": [],
            }
        }
        path = tmp_path / "manifest.json"
        write_manifest(manifest, path)
        loaded = load_manifest(path)
        assert loaded == manifest

    def test_load_missing_returns_empty(self, tmp_path: Path):
        result = load_manifest(tmp_path / "nonexistent.json")
        assert result == {}

    def test_write_creates_parent_dirs(self, tmp_path: Path):
        path = tmp_path / "a" / "b" / "manifest.json"
        write_manifest({}, path)
        assert path.exists()

    def test_write_trailing_newline(self, tmp_path: Path):
        path = tmp_path / "manifest.json"
        write_manifest({"x": {}}, path)
        raw = path.read_text(encoding="utf-8")
        assert raw.endswith("\n")

    def test_write_pretty_indented(self, tmp_path: Path):
        path = tmp_path / "manifest.json"
        write_manifest({"x": {"a": 1}}, path)
        raw = path.read_text(encoding="utf-8")
        # Pretty-printed JSON has newlines inside
        assert "\n" in raw
        # And indentation
        assert "  " in raw

    def test_load_invalid_json_returns_empty(self, tmp_path: Path):
        path = tmp_path / "manifest.json"
        path.write_text("NOT JSON", encoding="utf-8")
        assert load_manifest(path) == {}


# ---------------------------------------------------------------------------
# Integration test against a real PPTX (opt-in via SLIDECRAFT_TEST_PPTX)
# ---------------------------------------------------------------------------

_TEST_PPTX_ENV = os.environ.get("SLIDECRAFT_TEST_PPTX")
_TEST_PPTX = Path(_TEST_PPTX_ENV) if _TEST_PPTX_ENV else None


@pytest.mark.skipif(
    _TEST_PPTX is None or not _TEST_PPTX.exists(),
    reason="Set SLIDECRAFT_TEST_PPTX to a sample .pptx to enable",
)
class TestIntegrationRealPptx:
    def test_extracts_without_error(self, tmp_path: Path):
        manifest = extract_pictures(_TEST_PPTX, tmp_path / "theme")
        assert isinstance(manifest, dict)

    def test_assets_dir_created(self, tmp_path: Path):
        extract_pictures(_TEST_PPTX, tmp_path / "theme")
        assets = tmp_path / "theme" / "public" / "assets"
        assert assets.is_dir()

    def test_manifest_json_written(self, tmp_path: Path):
        extract_pictures(_TEST_PPTX, tmp_path / "theme")
        manifest_path = tmp_path / "theme" / "public" / "assets" / "manifest.json"
        assert manifest_path.exists()

    def test_all_entries_have_required_keys(self, tmp_path: Path):
        manifest = extract_pictures(_TEST_PPTX, tmp_path / "theme")
        required = {"source_format", "fidelity", "derivatives", "warnings"}
        for name, entry in manifest.items():
            missing = required - entry.keys()
            assert not missing, f"{name} is missing keys: {missing}"

    def test_fidelity_values_are_valid(self, tmp_path: Path):
        manifest = extract_pictures(_TEST_PPTX, tmp_path / "theme")
        for name, entry in manifest.items():
            assert entry["fidelity"] in ("exact", "low"), (
                f"{name} has unexpected fidelity: {entry['fidelity']!r}"
            )

    def test_at_least_one_image_extracted(self, tmp_path: Path):
        manifest = extract_pictures(_TEST_PPTX, tmp_path / "theme")
        assert len(manifest) >= 1, "Expected at least one image in the sample PPTX"
