"""image_diff.py — standalone image comparison utility.

Compares two PNG files using SSIM and pixel-level diff, and writes a
side-by-side visualisation (original A | original B | diff overlay).
"""

from __future__ import annotations

import tempfile
import warnings
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image
from skimage.metrics import structural_similarity as _ssim


@dataclass
class DiffResult:
    matched: bool
    ssim: float
    pixel_diff_pct: float       # % of pixels where any channel differs > pixel_tolerance
    diff_png_path: Path | None  # side-by-side a|b|diff visualisation
    width: int
    height: int


def compare(
    png_a: Path,
    png_b: Path,
    *,
    ssim_threshold: float = 0.98,
    pixel_tolerance: int = 5,
    output_dir: Path | None = None,
) -> DiffResult:
    """Compare two PNG images and return a DiffResult.

    Parameters
    ----------
    png_a, png_b:
        Paths to the PNG files to compare.
    ssim_threshold:
        Minimum SSIM score for ``matched`` to be True (default 0.98).
    pixel_tolerance:
        Per-channel absolute difference threshold; pixels where the maximum
        per-channel diff exceeds this value are counted as "different".
    output_dir:
        Directory in which to write the diff PNG visualisation.  If None a
        temporary directory is created automatically.
    """
    img_a = Image.open(png_a).convert("RGB")
    img_b = Image.open(png_b).convert("RGB")

    w_a, h_a = img_a.size
    w_b, h_b = img_b.size

    # Resize smaller image to match larger if dimensions differ
    if (w_a, h_a) != (w_b, h_b):
        target_w = max(w_a, w_b)
        target_h = max(h_a, h_b)

        # Warn when size difference > 5 % in either dimension
        if abs(w_a - w_b) / max(w_a, w_b) > 0.05 or abs(h_a - h_b) / max(h_a, h_b) > 0.05:
            warnings.warn(
                f"Image dimensions differ by more than 5 %: "
                f"{w_a}x{h_a} vs {w_b}x{h_b}. "
                "The smaller image will be upscaled.",
                stacklevel=2,
            )

        if img_a.size != (target_w, target_h):
            img_a = img_a.resize((target_w, target_h), Image.LANCZOS)
        if img_b.size != (target_w, target_h):
            img_b = img_b.resize((target_w, target_h), Image.LANCZOS)

    width, height = img_a.size

    arr_a = np.asarray(img_a, dtype=np.uint8)
    arr_b = np.asarray(img_b, dtype=np.uint8)

    # SSIM — multichannel on the full RGB arrays
    ssim_score: float = float(
        _ssim(arr_a, arr_b, data_range=255, channel_axis=2)
    )

    # Pixel diff
    diff = np.abs(arr_a.astype(np.int16) - arr_b.astype(np.int16))  # shape H×W×3
    max_channel_diff = diff.max(axis=2)                               # shape H×W
    different_pixels = int((max_channel_diff > pixel_tolerance).sum())
    total_pixels = width * height
    pixel_diff_pct = (different_pixels / total_pixels) * 100.0

    # Build diff visualisation
    if output_dir is None:
        output_dir = Path(tempfile.mkdtemp())
    else:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

    diff_png_path = _write_diff_png(arr_a, arr_b, max_channel_diff, pixel_tolerance, output_dir)

    return DiffResult(
        matched=(ssim_score >= ssim_threshold),
        ssim=ssim_score,
        pixel_diff_pct=pixel_diff_pct,
        diff_png_path=diff_png_path,
        width=width,
        height=height,
    )


def _write_diff_png(
    arr_a: np.ndarray,
    arr_b: np.ndarray,
    max_channel_diff: np.ndarray,
    pixel_tolerance: int,
    output_dir: Path,
) -> Path:
    """Write a three-panel PNG: A | B | grayscale-A with red changed-pixel overlay."""
    h, w = arr_a.shape[:2]

    # Panel C: greyscale of A with red overlay for changed pixels
    grey_a = np.stack([arr_a.mean(axis=2)] * 3, axis=2).astype(np.uint8)
    mask = max_channel_diff > pixel_tolerance          # bool H×W
    panel_c = grey_a.copy()
    panel_c[mask] = [255, 0, 0]                        # red overlay

    # Horizontal composite: A | B | C
    composite = np.concatenate([arr_a, arr_b, panel_c], axis=1)
    out_img = Image.fromarray(composite, "RGB")
    out_path = output_dir / "diff.png"
    out_img.save(out_path)
    return out_path
