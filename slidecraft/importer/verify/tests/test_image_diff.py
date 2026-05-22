"""Tests for slidecraft.importer.verify.image_diff.

All fixtures are generated in-memory via Pillow — no binary files committed.
"""
import tempfile
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from slidecraft.importer.verify.image_diff import compare, DiffResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _solid(size: tuple[int, int], color: tuple[int, int, int], path: Path) -> Path:
    """Save a solid-colour PNG and return its path."""
    img = Image.new("RGB", size, color)
    img.save(path)
    return path


def _draw_block(
    size: tuple[int, int],
    base_color: tuple[int, int, int],
    block_rect: tuple[int, int, int, int],
    block_color: tuple[int, int, int],
    path: Path,
) -> Path:
    """Save a PNG with a base colour and a filled rectangle block."""
    img = Image.new("RGB", size, base_color)
    draw = ImageDraw.Draw(img)
    draw.rectangle(block_rect, fill=block_color)
    img.save(path)
    return path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_identical_images_match(tmp_path: Path) -> None:
    """Two identical PNGs must yield matched=True, ssim≈1.0, pixel_diff_pct≈0."""
    a = _solid((200, 200), (100, 150, 200), tmp_path / "a.png")
    b = _solid((200, 200), (100, 150, 200), tmp_path / "b.png")

    result = compare(a, b, output_dir=tmp_path)

    assert isinstance(result, DiffResult)
    assert result.matched is True
    assert result.ssim == pytest.approx(1.0, abs=1e-4)
    assert result.pixel_diff_pct == pytest.approx(0.0, abs=0.01)
    assert result.width == 200
    assert result.height == 200


def test_pixel_block_difference(tmp_path: Path) -> None:
    """A 100x100 block changed in B → ssim < 1.0 and pixel_diff_pct > 0."""
    size = (300, 300)
    base = (200, 200, 200)
    block_rect = (100, 100, 199, 199)   # 100×100 px block

    a = _solid(size, base, tmp_path / "a.png")
    b = _draw_block(size, base, block_rect, (255, 0, 0), tmp_path / "b.png")

    result = compare(a, b, output_dir=tmp_path)

    assert isinstance(result, DiffResult)
    assert result.ssim < 1.0
    assert result.pixel_diff_pct > 0.0
    # The changed block is 100×100 = 10 000 px out of 90 000 → ~11 %
    assert result.pixel_diff_pct == pytest.approx(100 * 100 / (300 * 300) * 100, rel=0.05)


def test_size_mismatch_handled(tmp_path: Path) -> None:
    """Different-sized images must return a valid DiffResult without raising."""
    a = _solid((200, 200), (255, 255, 255), tmp_path / "a.png")
    b = _solid((100, 100), (255, 255, 255), tmp_path / "b.png")

    import warnings
    with warnings.catch_warnings(record=True):
        warnings.simplefilter("always")
        result = compare(a, b, output_dir=tmp_path)

    assert isinstance(result, DiffResult)
    # Result dimensions should match the larger image
    assert result.width == 200
    assert result.height == 200


def test_diff_png_written(tmp_path: Path) -> None:
    """diff_png_path must exist and be a valid PNG after comparison."""
    a = _solid((150, 150), (0, 128, 0), tmp_path / "a.png")
    b = _solid((150, 150), (0, 64, 0), tmp_path / "b.png")

    result = compare(a, b, output_dir=tmp_path)

    assert result.diff_png_path is not None
    assert result.diff_png_path.exists()
    assert result.diff_png_path.suffix == ".png"

    # Verify it can be re-opened as a valid image
    img = Image.open(result.diff_png_path)
    assert img.size == (150 * 3, 150)   # three panels side-by-side
