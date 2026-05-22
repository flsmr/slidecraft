"""Tests for the manifest orchestrator (Stage 2 Google Fonts mock + Stage 3 + Stage 4).

Covers:
- test_google_fonts_lookup_mocked — mocked HTTP, entry shape, woff2 files written
- test_manifest_entry_shapes — all four source types are correct shape
- Integration: substitute, fallback, and metric-substitute entries in manifest.json
"""
from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from slidecraft.importer.fonts.manifest import resolve_fonts
from slidecraft.importer.fonts.google import (
    _parse_font_face_blocks,
    lookup_google_fonts,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_minimal_pptx() -> bytes:
    """A valid but empty PPTX with no embedded fonts."""
    ns_p = "http://schemas.openxmlformats.org/presentationml/2006/main"
    ns_rel = "http://schemas.openxmlformats.org/package/2006/relationships"
    buf = io.BytesIO()
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
    return buf.getvalue()


_MOCK_GOOGLE_CSS = """\
/* latin */
@font-face {
  font-family: 'Open Sans';
  font-style: normal;
  font-weight: 400;
  src: url(https://fonts.gstatic.com/s/opensans/v40/memSYaGs126MiZpBA-UvWbX2vVnXBbObj2OVZyOOSr4dVJWUgsiH0B4gaVc.woff2) format('woff2');
  unicode-range: U+0000-00FF;
}
/* latin */
@font-face {
  font-family: 'Open Sans';
  font-style: normal;
  font-weight: 700;
  src: url(https://fonts.gstatic.com/s/opensans/v40/memSYaGs126MiZpBA-UvWbX2vVnXBbObj2OVZyOOSr4dVJWUgsiH0B4gaVc-bold.woff2) format('woff2');
  unicode-range: U+0000-00FF;
}
/* latin */
@font-face {
  font-family: 'Open Sans';
  font-style: italic;
  font-weight: 400;
  src: url(https://fonts.gstatic.com/s/opensans/v40/memSYaGs126MiZpBA-UvWbX2vVnXBbObj2OVZyOOSr4dVJWUgsiH0B4gaVc-italic.woff2) format('woff2');
}
"""


def _make_mock_session(css: str = _MOCK_GOOGLE_CSS) -> MagicMock:
    """Return a requests.Session mock that returns *css* for CSS requests
    and 1-byte bodies for font file requests."""
    session = MagicMock()

    def mock_get(url, **kwargs):
        resp = MagicMock()
        if "googleapis.com/css" in url:
            resp.status_code = 200
            resp.text = css
        elif ".woff2" in url:
            resp.status_code = 200
            resp.content = b"\x00" * 4  # minimal fake woff2
        else:
            resp.status_code = 404
            resp.text = ""
            resp.content = b""
        return resp

    session.get.side_effect = mock_get
    return session


# ---------------------------------------------------------------------------
# test_google_fonts_lookup_mocked
# ---------------------------------------------------------------------------

class TestGoogleFontsLookupMocked:
    def test_returns_google_fonts_entry(self, tmp_path: Path):
        session = _make_mock_session()
        entry = lookup_google_fonts("Open Sans", tmp_path, session=session)

        assert entry is not None
        assert entry["source"] == "google-fonts"
        assert entry["fidelity"] == "exact"

    def test_files_list_nonempty(self, tmp_path: Path):
        session = _make_mock_session()
        entry = lookup_google_fonts("Open Sans", tmp_path, session=session)

        assert entry is not None
        assert len(entry["files"]) > 0

    def test_woff2_files_written_to_dest(self, tmp_path: Path):
        session = _make_mock_session()
        entry = lookup_google_fonts("Open Sans", tmp_path, session=session)

        assert entry is not None
        for filename in entry["files"]:
            assert (tmp_path / filename).exists(), f"{filename} missing"

    def test_variants_cover_weights(self, tmp_path: Path):
        session = _make_mock_session()
        entry = lookup_google_fonts("Open Sans", tmp_path, session=session)

        assert entry is not None
        weights = {v["weight"] for v in entry["variants"]}
        assert 400 in weights
        assert 700 in weights

    def test_variants_cover_italic(self, tmp_path: Path):
        session = _make_mock_session()
        entry = lookup_google_fonts("Open Sans", tmp_path, session=session)

        assert entry is not None
        styles = {v["style"] for v in entry["variants"]}
        assert "italic" in styles

    def test_not_found_returns_none(self, tmp_path: Path):
        session = MagicMock()
        resp = MagicMock()
        resp.status_code = 404
        resp.text = ""
        session.get.return_value = resp

        entry = lookup_google_fonts("SomeNonExistentFont", tmp_path, session=session)
        assert entry is None

    def test_network_error_returns_none(self, tmp_path: Path):
        import requests

        session = MagicMock()
        session.get.side_effect = requests.ConnectionError("no network")

        entry = lookup_google_fonts("Open Sans", tmp_path, session=session)
        assert entry is None


class TestParseFontFaceBlocks:
    def test_parses_three_blocks(self):
        blocks = _parse_font_face_blocks(_MOCK_GOOGLE_CSS)
        assert len(blocks) == 3

    def test_weight_parsed_correctly(self):
        blocks = _parse_font_face_blocks(_MOCK_GOOGLE_CSS)
        weights = {b["weight"] for b in blocks}
        assert 400 in weights
        assert 700 in weights

    def test_style_parsed_correctly(self):
        blocks = _parse_font_face_blocks(_MOCK_GOOGLE_CSS)
        styles = {b["style"] for b in blocks}
        assert "normal" in styles
        assert "italic" in styles

    def test_urls_are_woff2(self):
        blocks = _parse_font_face_blocks(_MOCK_GOOGLE_CSS)
        for b in blocks:
            assert b["url"].endswith(".woff2")


# ---------------------------------------------------------------------------
# test_manifest_entry_shapes
# ---------------------------------------------------------------------------

class TestManifestEntryShapes:
    """Verify that resolve_fonts produces the correct entry shapes for each source."""

    def test_substitute_entry_shape(self, tmp_path: Path):
        pptx_file = tmp_path / "deck.pptx"
        pptx_file.write_bytes(_make_minimal_pptx())
        theme_dir = tmp_path / "theme"

        with patch(
            "slidecraft.importer.fonts.manifest.lookup_google_fonts",
            return_value=None,
        ):
            manifest = resolve_fonts(pptx_file, {"Calibri"}, theme_dir)

        entry = manifest["Calibri"]
        assert entry["source"] == "metric-substitute"
        assert entry["substitute"] == "Carlito"
        assert "files" in entry
        assert entry["fidelity"] == "high"

    def test_fallback_entry_shape(self, tmp_path: Path):
        pptx_file = tmp_path / "deck.pptx"
        pptx_file.write_bytes(_make_minimal_pptx())
        theme_dir = tmp_path / "theme"

        with patch(
            "slidecraft.importer.fonts.manifest.lookup_google_fonts",
            return_value=None,
        ):
            manifest = resolve_fonts(pptx_file, {"SomeObscureFont"}, theme_dir)

        entry = manifest["SomeObscureFont"]
        assert entry["source"] == "fallback"
        assert "fallback" in entry
        assert entry["fidelity"] == "low"

    def test_google_fonts_entry_shape(self, tmp_path: Path):
        pptx_file = tmp_path / "deck.pptx"
        pptx_file.write_bytes(_make_minimal_pptx())
        theme_dir = tmp_path / "theme"

        mock_gf_entry = {
            "source": "google-fonts",
            "files": ["OpenSans-w400-abc.woff2"],
            "variants": [{"file": "OpenSans-w400-abc.woff2", "weight": 400, "style": "normal"}],
            "fidelity": "exact",
        }
        with patch(
            "slidecraft.importer.fonts.manifest.lookup_google_fonts",
            return_value=mock_gf_entry,
        ):
            manifest = resolve_fonts(pptx_file, {"Open Sans"}, theme_dir)

        entry = manifest["Open Sans"]
        assert entry["source"] == "google-fonts"
        assert "files" in entry
        assert entry["fidelity"] == "exact"

    def test_manifest_json_written(self, tmp_path: Path):
        pptx_file = tmp_path / "deck.pptx"
        pptx_file.write_bytes(_make_minimal_pptx())
        theme_dir = tmp_path / "theme"

        with patch(
            "slidecraft.importer.fonts.manifest.lookup_google_fonts",
            return_value=None,
        ):
            resolve_fonts(pptx_file, {"Calibri"}, theme_dir)

        manifest_path = theme_dir / "public" / "fonts" / "manifest.json"
        assert manifest_path.exists()
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert "Calibri" in data

    def test_index_css_written(self, tmp_path: Path):
        pptx_file = tmp_path / "deck.pptx"
        pptx_file.write_bytes(_make_minimal_pptx())
        theme_dir = tmp_path / "theme"

        with patch(
            "slidecraft.importer.fonts.manifest.lookup_google_fonts",
            return_value=None,
        ):
            resolve_fonts(pptx_file, {"Calibri"}, theme_dir)

        css_path = theme_dir / "styles" / "index.css"
        assert css_path.exists()
        css = css_path.read_text(encoding="utf-8")
        assert "@font-face" in css
        assert '"Calibri"' in css

    def test_css_uses_verbatim_typeface_name(self, tmp_path: Path):
        """@font-face font-family must use the PPT typeface name, not the substitute."""
        pptx_file = tmp_path / "deck.pptx"
        pptx_file.write_bytes(_make_minimal_pptx())
        theme_dir = tmp_path / "theme"

        with patch(
            "slidecraft.importer.fonts.manifest.lookup_google_fonts",
            return_value=None,
        ):
            resolve_fonts(pptx_file, {"Arial"}, theme_dir)

        css = (theme_dir / "styles" / "index.css").read_text(encoding="utf-8")
        assert '"Arial"' in css
        # Should NOT declare the substitute name as the font-family
        assert '"Arimo"' not in css

    def test_fallback_no_font_face_block(self, tmp_path: Path):
        """Pure fallback typefaces must not get a @font-face block in the CSS."""
        pptx_file = tmp_path / "deck.pptx"
        pptx_file.write_bytes(_make_minimal_pptx())
        theme_dir = tmp_path / "theme"

        with patch(
            "slidecraft.importer.fonts.manifest.lookup_google_fonts",
            return_value=None,
        ):
            resolve_fonts(pptx_file, {"SomeObscureFont"}, theme_dir)

        css_path = theme_dir / "styles" / "index.css"
        if css_path.exists():
            css = css_path.read_text(encoding="utf-8")
            assert '"SomeObscureFont"' not in css

    def test_fontscheme_used_for_fallback_classification(self, tmp_path: Path):
        pptx_file = tmp_path / "deck.pptx"
        pptx_file.write_bytes(_make_minimal_pptx())
        theme_dir = tmp_path / "theme"
        fontscheme = {"mono": ["FixedWidthFont"], "latin": ["LatinFont"]}

        with patch(
            "slidecraft.importer.fonts.manifest.lookup_google_fonts",
            return_value=None,
        ):
            manifest = resolve_fonts(
                pptx_file, {"FixedWidthFont"}, theme_dir,
                theme_fontscheme=fontscheme,
            )

        assert manifest["FixedWidthFont"]["fallback"] == "monospace"

    def test_multiple_typefaces_resolved(self, tmp_path: Path):
        pptx_file = tmp_path / "deck.pptx"
        pptx_file.write_bytes(_make_minimal_pptx())
        theme_dir = tmp_path / "theme"

        with patch(
            "slidecraft.importer.fonts.manifest.lookup_google_fonts",
            return_value=None,
        ):
            manifest = resolve_fonts(
                pptx_file,
                {"Calibri", "Consolas", "UnknownFont"},
                theme_dir,
            )

        assert "Calibri" in manifest
        assert "Consolas" in manifest
        assert "UnknownFont" in manifest

    def test_inconsolata_italic_synthesized_in_manifest(self, tmp_path: Path):
        """Consolas → Inconsolata entry should carry italic: synthesized."""
        pptx_file = tmp_path / "deck.pptx"
        pptx_file.write_bytes(_make_minimal_pptx())
        theme_dir = tmp_path / "theme"

        with patch(
            "slidecraft.importer.fonts.manifest.lookup_google_fonts",
            return_value=None,
        ):
            manifest = resolve_fonts(pptx_file, {"Consolas"}, theme_dir)

        entry = manifest["Consolas"]
        assert entry.get("italic") == "synthesized"

    def test_resolve_returns_manifest_dict(self, tmp_path: Path):
        pptx_file = tmp_path / "deck.pptx"
        pptx_file.write_bytes(_make_minimal_pptx())
        theme_dir = tmp_path / "theme"

        with patch(
            "slidecraft.importer.fonts.manifest.lookup_google_fonts",
            return_value=None,
        ):
            result = resolve_fonts(pptx_file, {"Calibri"}, theme_dir)

        assert isinstance(result, dict)
        assert len(result) == 1
