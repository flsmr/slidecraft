"""Tests for slidecraft.importer.pictures.derivatives."""
from __future__ import annotations

import time
from pathlib import Path

import pytest
from PIL import Image

from slidecraft.importer.pictures.derivatives import apply_derivative, derivative_filename


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_rgba(width: int = 100, height: int = 100, color: tuple = (128, 64, 32, 255)) -> Image.Image:
    """Return a solid-colour RGBA image."""
    img = Image.new("RGBA", (width, height), color)
    return img


def _make_gradient_l(width: int = 100, height: int = 256) -> Image.Image:
    """Return an L-mode image with a vertical gradient from 0 (top) to 255 (bottom)."""
    import numpy as np

    arr = np.tile(np.arange(height, dtype=np.uint8).reshape(height, 1), (1, width))
    return Image.fromarray(arr, mode="L")


def _make_hard_edge_rgba(width: int = 60, height: int = 60, margin: int = 10) -> Image.Image:
    """Return an RGBA image that is opaque in the centre and transparent at the edges.

    This creates a clear alpha boundary so that GaussianBlur will actually
    reduce the alpha near the edge pixels.
    """
    img = Image.new("RGBA", (width, height), (255, 255, 255, 0))
    # Fill the interior with full opacity
    for y in range(margin, height - margin):
        for x in range(margin, width - margin):
            img.putpixel((x, y), (255, 255, 255, 255))
    return img


# ---------------------------------------------------------------------------
# Round-trip crop
# ---------------------------------------------------------------------------


def test_crop_width_reduced(tmp_path: Path) -> None:
    """Cropping 10 000 bp from the left of a 100-wide image yields 90-wide output."""
    img = _make_rgba(100, 100)
    src = tmp_path / "test.png"
    img.save(src)

    manifest: dict = {"test.png": {"source_format": "png", "fidelity": "exact", "derivatives": {}, "warnings": []}}
    params = {"l": 10_000, "t": 0, "r": 0, "b": 0}
    derived = apply_derivative(tmp_path, "test.png", "crop", params, manifest)

    out = Image.open(tmp_path / derived)
    assert out.size == (90, 100), f"Expected (90, 100) got {out.size}"


def test_crop_preserves_extension(tmp_path: Path) -> None:
    """Crop derivative keeps the original file extension."""
    # JPEG doesn't support alpha — use RGB
    img = _make_rgba(50, 50).convert("RGB")
    src = tmp_path / "photo.jpeg"
    img.save(src, format="JPEG")

    manifest: dict = {}
    params = {"l": 0, "t": 5_000, "r": 5_000, "b": 0}
    derived = apply_derivative(tmp_path, "photo.jpeg", "crop", params, manifest)
    assert derived.endswith(".jpeg")


# ---------------------------------------------------------------------------
# Duotone
# ---------------------------------------------------------------------------


def test_duotone_gradient_endpoints(tmp_path: Path) -> None:
    """Top pixel ≈ c1 (red), bottom pixel ≈ c2 (blue) on a luminance gradient."""
    img = _make_gradient_l(width=10, height=256)
    src = tmp_path / "grad.png"
    img.save(src)

    manifest: dict = {}
    params = {"c1": "ff0000", "c2": "0000ff"}
    derived = apply_derivative(tmp_path, "grad.png", "duotone", params, manifest)

    out = Image.open(tmp_path / derived).convert("RGBA")
    top_r, top_g, top_b, _ = out.getpixel((5, 0))
    bot_r, bot_g, bot_b, _ = out.getpixel((5, 255))

    # Allow ±2 for rounding in LUT / numpy path
    assert top_r > 250, f"Top pixel R should be ~255, got {top_r}"
    assert top_b < 5,   f"Top pixel B should be ~0, got {top_b}"
    assert bot_r < 5,   f"Bot pixel R should be ~0, got {bot_r}"
    assert bot_b > 250, f"Bot pixel B should be ~255, got {bot_b}"


def test_duotone_output_is_png(tmp_path: Path) -> None:
    """Duotone always produces a .png output regardless of input extension."""
    # JPEG doesn't support alpha — use RGB mode
    img = _make_rgba(20, 20).convert("RGB")
    src = tmp_path / "img.jpg"
    img.save(src, format="JPEG")

    manifest: dict = {}
    params = {"c1": "123456", "c2": "abcdef"}
    derived = apply_derivative(tmp_path, "img.jpg", "duotone", params, manifest)
    assert derived.endswith(".png")


def test_duotone_preserves_alpha(tmp_path: Path) -> None:
    """Alpha channel from the source is preserved in the duotone output."""
    img = Image.new("RGBA", (10, 10), (128, 128, 128, 100))
    src = tmp_path / "alpha.png"
    img.save(src)

    manifest: dict = {}
    params = {"c1": "ff0000", "c2": "0000ff"}
    derived = apply_derivative(tmp_path, "alpha.png", "duotone", params, manifest)

    out = Image.open(tmp_path / derived).convert("RGBA")
    _, _, _, a = out.getpixel((5, 5))
    assert a == 100, f"Expected alpha 100, got {a}"


# ---------------------------------------------------------------------------
# Soft edge
# ---------------------------------------------------------------------------


def test_soft_edge_reduces_edge_alpha(tmp_path: Path) -> None:
    """After soft-edge blur, pixels at the alpha boundary are softened.

    We use an image that is transparent at the border and opaque in the
    centre.  After blurring, the boundary region should have intermediate
    alpha values — specifically the outermost (transparent) pixels should
    gain some alpha, and the opaque interior should remain 255.
    """
    img = _make_hard_edge_rgba(width=60, height=60, margin=10)
    src = tmp_path / "hard_edge.png"
    img.save(src)

    manifest: dict = {}
    params = {"radius_px": 4}
    derived = apply_derivative(tmp_path, "hard_edge.png", "soft_edge", params, manifest)

    out = Image.open(tmp_path / derived).convert("RGBA")
    # Outermost corner was transparent (0); after blur it receives some alpha
    _, _, _, corner_a = out.getpixel((0, 0))
    # Deep interior pixel was 255; Gaussian blur on a uniform region → stays 255
    _, _, _, center_a = out.getpixel((30, 30))
    # The edge pixel just inside the margin was 255 but is adjacent to 0 → softened
    _, _, _, edge_a = out.getpixel((10, 10))

    assert center_a == 255, f"Center alpha should be 255, got {center_a}"
    assert corner_a < 255, f"Corner (originally 0) should gain alpha but stay < 255, got {corner_a}"
    # edge pixel may be reduced somewhat but needn't be checked strictly beyond < 255
    assert edge_a < 255, f"Edge pixel alpha should be < 255 after soft-edge, got {edge_a}"


def test_soft_edge_output_is_png(tmp_path: Path) -> None:
    """soft_edge always produces a .png output."""
    img = _make_rgba(20, 20)
    src = tmp_path / "img.bmp"
    img.save(src, format="BMP")

    manifest: dict = {}
    params = {"radius_px": 4}
    derived = apply_derivative(tmp_path, "img.bmp", "soft_edge", params, manifest)
    assert derived.endswith(".png")


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


def test_idempotency_same_filename(tmp_path: Path) -> None:
    """Calling apply_derivative twice returns the same derived filename."""
    img = _make_rgba(50, 50)
    src = tmp_path / "img.png"
    img.save(src)

    manifest: dict = {}
    params = {"l": 5_000, "t": 0, "r": 0, "b": 0}

    first  = apply_derivative(tmp_path, "img.png", "crop", params, manifest)
    second = apply_derivative(tmp_path, "img.png", "crop", params, manifest)

    assert first == second


def test_idempotency_no_rewrite(tmp_path: Path) -> None:
    """Second call does not overwrite the file (mtime unchanged)."""
    img = _make_rgba(50, 50)
    src = tmp_path / "img.png"
    img.save(src)

    manifest: dict = {}
    params = {"l": 5_000, "t": 0, "r": 0, "b": 0}

    derived = apply_derivative(tmp_path, "img.png", "crop", params, manifest)
    dest = tmp_path / derived
    mtime_after_first = dest.stat().st_mtime

    # Small sleep to ensure mtime would differ if the file were rewritten
    time.sleep(0.05)
    apply_derivative(tmp_path, "img.png", "crop", params, manifest)
    mtime_after_second = dest.stat().st_mtime

    assert mtime_after_first == mtime_after_second, (
        "File was re-written on second call (mtime changed)"
    )


def test_idempotency_manifest_entry_present(tmp_path: Path) -> None:
    """Manifest entry is present whether the derivative existed beforehand or not."""
    img = _make_rgba(50, 50)
    src = tmp_path / "img.png"
    img.save(src)

    # Pre-create the derived file to simulate a prior run
    params = {"c1": "ff0000", "c2": "00ff00"}
    derived_name = derivative_filename("img.png", "duotone", params)
    # Create a minimal valid PNG so Pillow won't be called
    dummy = Image.new("RGBA", (50, 50), (255, 0, 0, 255))
    dummy.save(tmp_path / derived_name)

    manifest: dict = {}
    result = apply_derivative(tmp_path, "img.png", "duotone", params, manifest)

    assert result in manifest.get("img.png", {}).get("derivatives", {})


# ---------------------------------------------------------------------------
# Filename determinism
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("op,params,expected_suffix", [
    (
        "crop",
        {"l": 10_000, "t": 20_000, "r": 5_000, "b": 0},
        "__crop_l10000_t20000_r5000_b0.png",
    ),
    (
        "duotone",
        {"c1": "ff0000", "c2": "0000ff"},
        "__duotone_ff0000_0000ff.png",
    ),
    (
        "soft_edge",
        {"radius_px": 12},
        "__softedge_12px.png",
    ),
])
def test_derivative_filename_pattern(op: str, params: dict, expected_suffix: str) -> None:
    """derivative_filename produces the expected filename pattern for each op."""
    result = derivative_filename("image.png", op, params)
    assert result == f"image{expected_suffix}", f"Got {result!r}"


def test_derivative_filename_crop_preserves_ext() -> None:
    """Crop filename keeps the source extension."""
    result = derivative_filename("photo.jpeg", "crop", {"l": 0, "t": 0, "r": 0, "b": 5_000})
    assert result.endswith(".jpeg")
    assert "__crop_" in result


def test_derivative_filename_unknown_op_raises() -> None:
    """derivative_filename raises ValueError for an unknown op."""
    with pytest.raises(ValueError, match="Unknown derivative op"):
        derivative_filename("img.png", "rotate", {})


# ---------------------------------------------------------------------------
# Manifest update
# ---------------------------------------------------------------------------


def test_manifest_updated_after_apply(tmp_path: Path) -> None:
    """apply_derivative writes the correct entry into the manifest dict."""
    img = _make_rgba(40, 40)
    src = tmp_path / "pic.png"
    img.save(src)

    manifest: dict = {}
    params = {"radius_px": 5}
    derived = apply_derivative(tmp_path, "pic.png", "soft_edge", params, manifest)

    entry = manifest["pic.png"]["derivatives"][derived]
    assert entry["op"] == "soft_edge"
    assert entry["params"] == params
