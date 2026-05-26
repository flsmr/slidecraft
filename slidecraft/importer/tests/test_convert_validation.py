"""Convert-time input validation — fail fast before any file I/O.

Goal: an invalid theme name must surface as a Python ValueError from
``convert()`` BEFORE we parse the PPTX, write theme files, or extract
assets. Otherwise the user sees a cryptic error from `npx slidev` only
at deck startup, hours after the bad input was accepted.

We pass a non-existent pptx path on purpose — if validation runs first,
the bad-name ValueError fires before parse() ever opens the file. If
that ordering ever regresses, this test catches it (the FileNotFound
that parse() would raise is a different error class).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from slidecraft.importer.convert import convert


class TestConvertRejectsBadThemeName:
    def test_uppercase_theme_name(self, tmp_path):
        with pytest.raises(ValueError, match="uppercase"):
            convert(
                pptx_path=Path("/nonexistent.pptx"),
                theme_dir=tmp_path / "theme",
                deck_dir=tmp_path / "deck",
                theme_name="slidev-theme-ILSE",
            )

    def test_invalid_chars_theme_name(self, tmp_path):
        with pytest.raises(ValueError, match="theme name"):
            convert(
                pptx_path=Path("/nonexistent.pptx"),
                theme_dir=tmp_path / "theme",
                deck_dir=tmp_path / "deck",
                theme_name="slidev theme spaces",
            )

    def test_validation_runs_before_parse(self, tmp_path):
        """If the validator runs first, the ValueError should fire even
        though pptx_path doesn't exist — proving no file work happened."""
        with pytest.raises(ValueError):
            convert(
                pptx_path=Path("/definitely-does-not-exist.pptx"),
                theme_dir=tmp_path / "theme",
                deck_dir=tmp_path / "deck",
                theme_name="BAD",
            )
        # Nothing should have been written.
        assert not (tmp_path / "theme").exists()
        assert not (tmp_path / "deck").exists()
