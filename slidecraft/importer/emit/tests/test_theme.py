"""Tests for emit/theme.py."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from slidecraft.importer.model import Presentation, Slide
from slidecraft.importer.emit.theme import emit_theme, _simplify_ratio


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _make_presentation(w: int = 1920, h: int = 1080) -> Presentation:
    return Presentation(
        slides=[],
        canvas_width_px=w,
        canvas_height_px=h,
        typefaces_referenced=set(),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSimplifyRatio:
    def test_16_9(self):
        assert _simplify_ratio(1920, 1080) == "16/9"

    def test_4_3(self):
        assert _simplify_ratio(1024, 768) == "4/3"

    def test_already_simplified(self):
        assert _simplify_ratio(800, 600) == "4/3"

    def test_prime_dimensions(self):
        # 1366×768 — GCD is 2, giving 683/384
        assert _simplify_ratio(1366, 768) == "683/384"


class TestThemePackageJsonShape:
    def test_theme_package_json_shape(self, tmp_path):
        pres = _make_presentation(1920, 1080)
        emit_theme(pres, tmp_path / "theme", theme_name="slidev-theme-test")

        pkg_path = tmp_path / "theme" / "package.json"
        assert pkg_path.exists()
        pkg = json.loads(pkg_path.read_text())

        assert pkg["name"] == "slidev-theme-test"
        assert pkg["version"] == "0.0.1"
        assert "slidev-theme" in pkg["keywords"]
        assert "slidev" in pkg["keywords"]
        assert pkg["engines"]["slidev"] == ">=0.48.0"

        slidev_block = pkg["slidev"]
        assert slidev_block["colorSchema"] == "light"
        defaults = slidev_block["defaults"]
        assert defaults["canvasWidth"] == 1920
        assert defaults["aspectRatio"] == "16/9"
        assert defaults["fonts"]["provider"] == "none"

    def test_theme_aspect_ratio_simplified(self, tmp_path):
        """4:3 canvas should produce '4/3', not '1024/768'."""
        pres = _make_presentation(1024, 768)
        emit_theme(pres, tmp_path / "theme")

        pkg = json.loads((tmp_path / "theme" / "package.json").read_text())
        assert pkg["slidev"]["defaults"]["aspectRatio"] == "4/3"

    def test_canvas_width_reflects_presentation(self, tmp_path):
        pres = _make_presentation(2560, 1440)
        emit_theme(pres, tmp_path / "theme")
        pkg = json.loads((tmp_path / "theme" / "package.json").read_text())
        assert pkg["slidev"]["defaults"]["canvasWidth"] == 2560

    def test_creates_styles_index_css(self, tmp_path):
        pres = _make_presentation()
        emit_theme(pres, tmp_path / "theme")
        assert (tmp_path / "theme" / "styles" / "index.css").exists()

    def test_creates_public_fonts_dir(self, tmp_path):
        pres = _make_presentation()
        emit_theme(pres, tmp_path / "theme")
        assert (tmp_path / "theme" / "public" / "fonts").is_dir()

    def test_idempotent(self, tmp_path):
        """Calling emit_theme twice must not raise or corrupt output."""
        pres = _make_presentation()
        theme_dir = tmp_path / "theme"
        emit_theme(pres, theme_dir)
        # Write something into index.css to verify it isn't cleared on re-run
        (theme_dir / "styles" / "index.css").write_text("/* fonts */", encoding="utf-8")
        emit_theme(pres, theme_dir)
        # index.css should NOT be overwritten (idempotent: only create if absent)
        content = (theme_dir / "styles" / "index.css").read_text()
        assert "/* fonts */" in content
