"""Tests for slidecraft.importer.pictures.verify_helper."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from slidecraft.importer.pictures.verify_helper import (
    collect_asset_refs_from_layout,
    threshold_for_layout,
    threshold_for_slide,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_vue(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "layout1.vue"
    p.write_text(content, encoding="utf-8")
    return p


def _write_manifest(tmp_path: Path, data: dict) -> Path:
    p = tmp_path / "manifest.json"
    p.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# collect_asset_refs_from_layout
# ---------------------------------------------------------------------------

class TestCollectAssetRefs:
    def test_finds_src_attr_and_css_url(self, tmp_path):
        """Both img src and CSS url() forms are returned as sorted basenames."""
        vue = _write_vue(
            tmp_path,
            '<img src="/assets/foo.png">\n'
            "<style>.bg { background-image: url(/assets/bar.jpg); }</style>\n",
        )
        refs = collect_asset_refs_from_layout(vue)
        assert refs == ["bar.jpg", "foo.png"]

    def test_query_string_stripped(self, tmp_path):
        """Query strings after '?' are ignored; only the bare filename is kept."""
        vue = _write_vue(tmp_path, '<img src="/assets/foo.png?v=1">\n')
        refs = collect_asset_refs_from_layout(vue)
        assert refs == ["foo.png"]

    def test_fragment_stripped(self, tmp_path):
        """Fragments after '#' are ignored."""
        vue = _write_vue(tmp_path, '<img src="/assets/foo.png#section">\n')
        refs = collect_asset_refs_from_layout(vue)
        assert refs == ["foo.png"]

    def test_deduplicates(self, tmp_path):
        """The same asset referenced multiple times appears only once."""
        vue = _write_vue(
            tmp_path,
            '<img src="/assets/foo.png">\n'
            '<img src="/assets/foo.png">\n',
        )
        refs = collect_asset_refs_from_layout(vue)
        assert refs == ["foo.png"]

    def test_missing_file_returns_empty(self, tmp_path):
        """A path that does not exist returns []."""
        refs = collect_asset_refs_from_layout(tmp_path / "nonexistent.vue")
        assert refs == []

    def test_empty_file_returns_empty(self, tmp_path):
        """A file with no asset references returns []."""
        vue = _write_vue(tmp_path, "<template><div>no images here</div></template>\n")
        refs = collect_asset_refs_from_layout(vue)
        assert refs == []

    def test_single_quoted_src(self, tmp_path):
        """Single-quoted src attribute is also recognised."""
        vue = _write_vue(tmp_path, "<img src='/assets/baz.webp'>\n")
        refs = collect_asset_refs_from_layout(vue)
        assert refs == ["baz.webp"]

    def test_css_url_with_quotes(self, tmp_path):
        """CSS url() with quoted path is recognised."""
        vue = _write_vue(
            tmp_path,
            '<style>div { background-image: url("/assets/hero.jpg"); }</style>\n',
        )
        refs = collect_asset_refs_from_layout(vue)
        assert refs == ["hero.jpg"]

    def test_returns_sorted(self, tmp_path):
        """Result is alphabetically sorted regardless of appearance order."""
        vue = _write_vue(
            tmp_path,
            '<img src="/assets/z.png">\n'
            '<img src="/assets/a.png">\n',
        )
        refs = collect_asset_refs_from_layout(vue)
        assert refs == ["a.png", "z.png"]


# ---------------------------------------------------------------------------
# threshold_for_slide
# ---------------------------------------------------------------------------

class TestThresholdForSlide:
    def test_all_exact_returns_strict(self, tmp_path):
        """All assets with fidelity='exact' → strict threshold."""
        manifest = _write_manifest(
            tmp_path,
            {
                "image1.png": {
                    "source_format": "png",
                    "fidelity": "exact",
                    "derivatives": {},
                    "warnings": [],
                },
                "image2.jpeg": {
                    "source_format": "jpeg",
                    "fidelity": "exact",
                    "derivatives": {},
                    "warnings": [],
                },
            },
        )
        result = threshold_for_slide(["image1.png", "image2.jpeg"], manifest)
        assert result == pytest.approx(0.98)

    def test_one_low_returns_relaxed(self, tmp_path):
        """One low-fidelity asset in the list → relaxed threshold."""
        manifest = _write_manifest(
            tmp_path,
            {
                "good.png": {
                    "source_format": "png",
                    "fidelity": "exact",
                    "derivatives": {},
                    "warnings": [],
                },
                "bad.emf": {
                    "source_format": "emf",
                    "fidelity": "low",
                    "derivatives": {},
                    "warnings": ["unsupported_format:emf"],
                },
            },
        )
        result = threshold_for_slide(["good.png", "bad.emf"], manifest)
        assert result == pytest.approx(0.90)

    def test_derivative_of_low_fidelity_returns_relaxed(self, tmp_path):
        """A derivative name that maps to a low-fidelity original → relaxed."""
        manifest = _write_manifest(
            tmp_path,
            {
                "image1.png": {
                    "source_format": "png",
                    "fidelity": "low",
                    "derivatives": {
                        "image1__crop_l10000_t0_r0_b0.png": {
                            "op": "crop",
                            "params": {"l": 10000, "t": 0, "r": 0, "b": 0},
                        }
                    },
                    "warnings": [],
                },
            },
        )
        result = threshold_for_slide(
            ["image1__crop_l10000_t0_r0_b0.png"], manifest
        )
        assert result == pytest.approx(0.90)

    def test_derivative_of_exact_fidelity_returns_strict(self, tmp_path):
        """A derivative that maps to an exact-fidelity original → strict."""
        manifest = _write_manifest(
            tmp_path,
            {
                "image1.png": {
                    "source_format": "png",
                    "fidelity": "exact",
                    "derivatives": {
                        "image1__crop_l500_t0_r0_b0.png": {
                            "op": "crop",
                            "params": {},
                        }
                    },
                    "warnings": [],
                },
            },
        )
        result = threshold_for_slide(
            ["image1__crop_l500_t0_r0_b0.png"], manifest
        )
        assert result == pytest.approx(0.98)

    def test_unknown_asset_returns_relaxed(self, tmp_path):
        """An asset not in the manifest is treated defensively as low → relaxed."""
        manifest = _write_manifest(tmp_path, {})
        result = threshold_for_slide(["totally_unknown.bmp"], manifest)
        assert result == pytest.approx(0.90)

    def test_empty_asset_list_returns_strict(self, tmp_path):
        """No assets at all → no reason to relax → strict."""
        manifest = _write_manifest(tmp_path, {})
        result = threshold_for_slide([], manifest)
        assert result == pytest.approx(0.98)

    def test_missing_manifest_treats_assets_as_unknown(self, tmp_path):
        """A missing manifest file → every asset is unknown → relaxed."""
        result = threshold_for_slide(
            ["image.png"], tmp_path / "nonexistent_manifest.json"
        )
        assert result == pytest.approx(0.90)

    def test_high_fidelity_uses_strict(self, tmp_path):
        """fidelity='high' (metric-substitute level) is not relaxed."""
        manifest = _write_manifest(
            tmp_path,
            {
                "image1.png": {
                    "source_format": "png",
                    "fidelity": "high",
                    "derivatives": {},
                    "warnings": [],
                },
            },
        )
        result = threshold_for_slide(["image1.png"], manifest)
        assert result == pytest.approx(0.98)

    def test_custom_thresholds_honoured(self, tmp_path):
        """Custom strict/relaxed values are passed through correctly."""
        manifest = _write_manifest(
            tmp_path,
            {
                "img.emf": {
                    "source_format": "emf",
                    "fidelity": "low",
                    "derivatives": {},
                    "warnings": [],
                },
            },
        )
        result = threshold_for_slide(
            ["img.emf"], manifest, strict=0.99, relaxed=0.85
        )
        assert result == pytest.approx(0.85)


# ---------------------------------------------------------------------------
# threshold_for_layout (end-to-end)
# ---------------------------------------------------------------------------

class TestThresholdForLayout:
    def test_end_to_end_exact(self, tmp_path):
        """Layout referencing an exact-fidelity asset → strict."""
        vue = _write_vue(tmp_path, '<img src="/assets/photo.png">\n')
        manifest = _write_manifest(
            tmp_path,
            {
                "photo.png": {
                    "source_format": "png",
                    "fidelity": "exact",
                    "derivatives": {},
                    "warnings": [],
                }
            },
        )
        result = threshold_for_layout(vue, manifest)
        assert result == pytest.approx(0.98)

    def test_end_to_end_low(self, tmp_path):
        """Layout referencing a low-fidelity asset → relaxed."""
        vue = _write_vue(
            tmp_path,
            "<style>.bg { background-image: url(/assets/chart.emf.png); }</style>\n",
        )
        manifest = _write_manifest(
            tmp_path,
            {
                "chart.emf.png": {
                    "source_format": "emf",
                    "fidelity": "low",
                    "derivatives": {},
                    "warnings": [],
                }
            },
        )
        result = threshold_for_layout(vue, manifest)
        assert result == pytest.approx(0.90)

    def test_end_to_end_derivative(self, tmp_path):
        """Layout referencing a derivative of a low-fidelity original → relaxed."""
        vue = _write_vue(
            tmp_path,
            '<img src="/assets/image1__crop_l10000_t0_r0_b0.png">\n',
        )
        manifest = _write_manifest(
            tmp_path,
            {
                "image1.png": {
                    "source_format": "png",
                    "fidelity": "low",
                    "derivatives": {
                        "image1__crop_l10000_t0_r0_b0.png": {
                            "op": "crop",
                            "params": {"l": 10000, "t": 0, "r": 0, "b": 0},
                        }
                    },
                    "warnings": [],
                }
            },
        )
        result = threshold_for_layout(vue, manifest)
        assert result == pytest.approx(0.90)

    def test_end_to_end_missing_layout(self, tmp_path):
        """A missing layout .vue file produces no asset refs → strict."""
        manifest = _write_manifest(tmp_path, {})
        result = threshold_for_layout(tmp_path / "missing.vue", manifest)
        assert result == pytest.approx(0.98)
