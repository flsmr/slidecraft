"""Tests for metric-substitute font resolution (Stage 3)."""
from __future__ import annotations

from pathlib import Path

import pytest

from slidecraft.importer.fonts.substitute import (
    SUBSTITUTE_TABLE,
    _DATA_DIR,
    copy_substitute,
)


class TestSubstituteTableHit:
    """test_substitute_table_hit — basic table lookup and file copy."""

    def test_calibri_maps_to_carlito(self, tmp_path: Path):
        entry = copy_substitute("Calibri", tmp_path)

        assert entry is not None
        assert entry["source"] == "metric-substitute"
        assert entry["substitute"] == "Carlito"
        assert entry["fidelity"] == "high"

    def test_calibri_files_copied(self, tmp_path: Path):
        entry = copy_substitute("Calibri", tmp_path)

        assert entry is not None
        for filename in entry["files"]:
            assert (tmp_path / filename).exists(), f"{filename} not copied"

    def test_calibri_has_four_variants(self, tmp_path: Path):
        entry = copy_substitute("Calibri", tmp_path)

        assert entry is not None
        assert len(entry["files"]) == 4

    def test_cambria_maps_to_caladea(self, tmp_path: Path):
        entry = copy_substitute("Cambria", tmp_path)
        assert entry is not None
        assert entry["substitute"] == "Caladea"

    def test_arial_maps_to_arimo(self, tmp_path: Path):
        entry = copy_substitute("Arial", tmp_path)
        assert entry is not None
        assert entry["substitute"] == "Arimo"

    def test_times_new_roman_maps_to_tinos(self, tmp_path: Path):
        entry = copy_substitute("Times New Roman", tmp_path)
        assert entry is not None
        assert entry["substitute"] == "Tinos"

    def test_courier_new_maps_to_cousine(self, tmp_path: Path):
        entry = copy_substitute("Courier New", tmp_path)
        assert entry is not None
        assert entry["substitute"] == "Cousine"

    def test_verdana_maps_to_dejavusans(self, tmp_path: Path):
        entry = copy_substitute("Verdana", tmp_path)
        assert entry is not None
        assert entry["substitute"] == "DejaVuSans"

    def test_unknown_typeface_returns_none(self, tmp_path: Path):
        entry = copy_substitute("SomeObscureFont", tmp_path)
        assert entry is None

    def test_variants_have_correct_shape(self, tmp_path: Path):
        entry = copy_substitute("Arial", tmp_path)

        assert entry is not None
        assert "variants" in entry
        for v in entry["variants"]:
            assert "file" in v
            assert "weight" in v
            assert "style" in v
            assert v["weight"] in (400, 700)
            assert v["style"] in ("normal", "italic")

    def test_idempotent_copy(self, tmp_path: Path):
        """Calling copy_substitute twice should not raise or corrupt files."""
        entry1 = copy_substitute("Calibri", tmp_path)
        entry2 = copy_substitute("Calibri", tmp_path)
        assert entry1 == entry2


class TestSubstituteInconsolataNoItalic:
    """test_substitute_inconsolata_no_italic — only Regular + Bold, italic: "synthesized"."""

    def test_consolas_maps_to_inconsolata(self, tmp_path: Path):
        entry = copy_substitute("Consolas", tmp_path)
        assert entry is not None
        assert entry["substitute"] == "Inconsolata"

    def test_inconsolata_only_two_variants(self, tmp_path: Path):
        entry = copy_substitute("Consolas", tmp_path)

        assert entry is not None
        assert len(entry["files"]) == 2

    def test_inconsolata_regular_present(self, tmp_path: Path):
        entry = copy_substitute("Consolas", tmp_path)

        assert entry is not None
        files = entry["files"]
        assert any("Regular" in f for f in files)

    def test_inconsolata_bold_present(self, tmp_path: Path):
        entry = copy_substitute("Consolas", tmp_path)

        assert entry is not None
        files = entry["files"]
        assert any("Bold" in f for f in files)

    def test_inconsolata_no_italic_file(self, tmp_path: Path):
        entry = copy_substitute("Consolas", tmp_path)

        assert entry is not None
        files = entry["files"]
        assert not any("Italic" in f for f in files)
        assert not any("BoldItalic" in f for f in files)

    def test_inconsolata_italic_synthesized_flag(self, tmp_path: Path):
        """Manifest must record italic: "synthesized" for Inconsolata."""
        entry = copy_substitute("Consolas", tmp_path)

        assert entry is not None
        assert entry.get("italic") == "synthesized"

    def test_inconsolata_fidelity_high(self, tmp_path: Path):
        entry = copy_substitute("Consolas", tmp_path)

        assert entry is not None
        assert entry["fidelity"] == "high"

    def test_inconsolata_files_copied_to_dest(self, tmp_path: Path):
        entry = copy_substitute("Consolas", tmp_path)

        assert entry is not None
        for filename in entry["files"]:
            assert (tmp_path / filename).exists()

    def test_inconsolata_variants_no_italic_style(self, tmp_path: Path):
        """None of the variant dicts should have style: italic."""
        entry = copy_substitute("Consolas", tmp_path)

        assert entry is not None
        for v in entry["variants"]:
            assert v["style"] == "normal", (
                f"Unexpected italic variant in Inconsolata: {v}"
            )
