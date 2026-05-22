"""Pillow-based image derivative operations for the pictures pipeline.

Supports three ops:
  crop       — basis-point crop from each edge
  duotone    — two-colour gradient mapped from luminance
  soft_edge  — Gaussian-blur on the alpha channel

Each op is deterministically named so callers (emit layer, effects.py) can
predict the derived filename without running Pillow, via
:func:`derivative_filename`.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageFilter

# ---------------------------------------------------------------------------
# Filename helpers
# ---------------------------------------------------------------------------


def derivative_filename(original_name: str, op: str, params: dict) -> str:
    """Return the deterministic derived filename for (*op*, *params*) on *original_name*.

    The returned name can be used by callers that need to know the eventual
    path (e.g. the emit layer constructing asset URLs) **without** performing
    any Pillow work.

    Args:
        original_name: Basename of the source image (e.g. ``"photo.png"``).
        op:            One of ``"crop"``, ``"duotone"``, ``"soft_edge"``.
        params:        Op-specific parameter dict (same shape as passed to
                       :func:`apply_derivative`).

    Returns:
        Derived basename string (extension may differ from *original_name*).

    Raises:
        ValueError: If *op* is not recognised.
    """
    stem = Path(original_name).stem
    ext = Path(original_name).suffix  # e.g. ".png"

    if op == "crop":
        l = int(params["l"])
        t = int(params["t"])
        r = int(params["r"])
        b = int(params["b"])
        return f"{stem}__crop_l{l}_t{t}_r{r}_b{b}{ext}"

    if op == "duotone":
        c1 = params["c1"]
        c2 = params["c2"]
        return f"{stem}__duotone_{c1}_{c2}.png"

    if op == "soft_edge":
        radius_px = int(params["radius_px"])
        return f"{stem}__softedge_{radius_px}px.png"

    raise ValueError(f"Unknown derivative op: {op!r}")


# ---------------------------------------------------------------------------
# Internal op implementations
# ---------------------------------------------------------------------------


def _apply_crop(img: Image.Image, params: dict) -> Image.Image:
    """Crop *img* using basis-point offsets from each edge.

    Args:
        img:    Source PIL image (any mode).
        params: Dict with keys ``l``, ``t``, ``r``, ``b`` each an int
                0..100000 (fraction × 100 000 of the respective dimension).

    Returns:
        Cropped PIL image in the original mode.
    """
    W, H = img.size
    l = int(params["l"])
    t = int(params["t"])
    r = int(params["r"])
    b = int(params["b"])

    left   = round((l / 100_000) * W)
    top    = round((t / 100_000) * H)
    right  = W - round((r / 100_000) * W)
    bottom = H - round((b / 100_000) * H)

    # Guard against degenerate crop boxes
    left   = max(0, min(left, W))
    top    = max(0, min(top, H))
    right  = max(left + 1, min(right, W))
    bottom = max(top + 1, min(bottom, H))

    return img.crop((left, top, right, bottom))


def _apply_duotone(img: Image.Image, params: dict) -> Image.Image:
    """Map image luminance to a two-colour gradient.

    ITU-R 601-2 weights (Pillow's default for "L" conversion) are used.
    Alpha is preserved if present.

    Fast path: uses numpy when available.  Slow path: per-channel PIL
    ``Image.point()`` with a 256-entry LUT.

    Args:
        img:    Source PIL image (any mode).
        params: Dict with keys ``c1`` and ``c2``, each a 6-hex-digit colour
                string WITHOUT ``#`` (e.g. ``"ff0000"``).

    Returns:
        RGBA PIL image with the duotone applied.
    """
    c1_hex = params["c1"]
    c2_hex = params["c2"]

    c1_r = int(c1_hex[0:2], 16)
    c1_g = int(c1_hex[2:4], 16)
    c1_b = int(c1_hex[4:6], 16)

    c2_r = int(c2_hex[0:2], 16)
    c2_g = int(c2_hex[2:4], 16)
    c2_b = int(c2_hex[4:6], 16)

    # Separate alpha before converting to gray
    alpha: Image.Image | None = None
    if img.mode in ("RGBA", "LA"):
        alpha = img.getchannel("A")
    elif img.mode == "PA":
        img = img.convert("RGBA")
        alpha = img.getchannel("A")

    gray = img.convert("L")  # ITU-R 601-2 weights

    try:
        import numpy as np

        arr = np.asarray(gray, dtype=np.float32) / 255.0  # shape (H, W), 0..1
        r_arr = np.round(c1_r + arr * (c2_r - c1_r)).astype(np.uint8)
        g_arr = np.round(c1_g + arr * (c2_g - c1_g)).astype(np.uint8)
        b_arr = np.round(c1_b + arr * (c2_b - c1_b)).astype(np.uint8)

        rgb = np.stack([r_arr, g_arr, b_arr], axis=-1)  # (H, W, 3)
        result = Image.fromarray(rgb, mode="RGB")
    except ImportError:
        # Slow-path: precomputed 256-entry LUT per channel
        lut_r = bytes(round(c1_r + (i / 255) * (c2_r - c1_r)) for i in range(256))
        lut_g = bytes(round(c1_g + (i / 255) * (c2_g - c1_g)) for i in range(256))
        lut_b = bytes(round(c1_b + (i / 255) * (c2_b - c1_b)) for i in range(256))

        # point() on an RGB image expects a flat 768-entry table
        lut_rgb = lut_r + lut_g + lut_b
        result = gray.convert("RGB").point(lut_rgb)

    if alpha is not None:
        result = result.convert("RGBA")
        result.putalpha(alpha)
    else:
        result = result.convert("RGBA")
        result.putalpha(255)

    return result


def _apply_soft_edge(img: Image.Image, params: dict) -> Image.Image:
    """Apply Gaussian blur to the alpha channel to soften edges.

    If the source image has no alpha channel, an opaque (255) alpha is
    synthesised first.  Only the alpha channel is blurred; RGB data is
    unchanged.

    Args:
        img:    Source PIL image (any mode).
        params: Dict with key ``radius_px`` (int) — Gaussian blur sigma in px.

    Returns:
        RGBA PIL image with blurred alpha.
    """
    radius_px = int(params["radius_px"])

    rgba = img.convert("RGBA")
    r, g, b, a = rgba.split()

    blurred_a = a.filter(ImageFilter.GaussianBlur(radius=radius_px))

    result = Image.merge("RGBA", (r, g, b, blurred_a))
    return result


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

_OP_MAP = {
    "crop":       _apply_crop,
    "duotone":    _apply_duotone,
    "soft_edge":  _apply_soft_edge,
}


def apply_derivative(
    asset_dir: Path,
    original_name: str,
    op: str,
    params: dict,
    manifest: dict,
) -> str:
    """Apply *op* to ``asset_dir/original_name`` and write the derived file.

    The derived filename is deterministic (see :func:`derivative_filename`).
    If the file already exists the Pillow work is skipped, but the manifest
    entry is still ensured (idempotent).

    Args:
        asset_dir:     Directory that contains *original_name* and where the
                       derived file will be written.
        original_name: Basename of the source image (must exist in *asset_dir*).
        op:            One of ``"crop"``, ``"duotone"``, ``"soft_edge"``.
        params:        Op-specific parameters (see module docstring for shapes).
        manifest:      Live manifest dict keyed by image basename.  Updated in
                       place; caller is responsible for persisting to disk.

    Returns:
        Basename of the derived file (relative to *asset_dir*).

    Raises:
        ValueError: If *op* is unknown.
        FileNotFoundError: If *asset_dir/original_name* does not exist.
    """
    if op not in _OP_MAP:
        raise ValueError(f"Unknown derivative op: {op!r}.  Valid ops: {list(_OP_MAP)}")

    derived_name = derivative_filename(original_name, op, params)
    dest_path = asset_dir / derived_name

    if not dest_path.exists():
        src_path = asset_dir / original_name
        if not src_path.exists():
            raise FileNotFoundError(f"Source image not found: {src_path}")

        with Image.open(src_path) as img:
            img.load()  # ensure full decode before close
            derived_img = _OP_MAP[op](img, params)

        derived_img.save(dest_path)

    # Ensure manifest entry regardless of whether we wrote the file
    manifest.setdefault(original_name, {}).setdefault("derivatives", {})[derived_name] = {
        "op": op,
        "params": params,
    }

    return derived_name
