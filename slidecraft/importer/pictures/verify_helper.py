"""Verify-helper for the pictures pipeline.

Provides utilities to determine the SSIM threshold to use when comparing a
rendered Slidev layout against the original PPTX slide.  The threshold is
relaxed when any picture referenced by the layout has a ``fidelity`` of
``"low"`` in ``theme/public/assets/manifest.json`` (e.g. an EMF or WMF that
was converted to PNG with lossy re-encoding), and strict when all pictures are
``"exact"`` or ``"high"``.

Derivative lookup:  a layout often references a *derivative* filename (a
cropped or transformed variant, e.g.
``image1__crop_l10000_t0_r0_b0.png``) rather than the original.  Derivatives
are stored under each manifest entry's ``"derivatives"`` dict.  A derivative
inherits the fidelity of the original entry it belongs to.

Unknown assets (present in the layout but absent from the manifest) are
treated as ``"low"``-fidelity defensively — worst-case assumption.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

# ---------------------------------------------------------------------------
# Regex patterns for /assets/<name> URL references in .vue files
# ---------------------------------------------------------------------------

# Matches: src="/assets/foo.png" or src='/assets/foo.png'
# Captures the path segment (without query string / fragment).
_RE_SRC_ATTR = re.compile(
    r"""src\s*=\s*['"](?P<path>/assets/[^'"?#\s]+)[^'"]*['"]""",
    re.IGNORECASE,
)

# Matches: url(/assets/foo.png) or url('/assets/foo.png') or url("/assets/foo.png")
# Captures the path segment (without query string / fragment).
_RE_CSS_URL = re.compile(
    r"""url\(\s*['"]?(?P<path>/assets/[^'")?#\s]+)[^'")]*['"]?\s*\)""",
    re.IGNORECASE,
)


def collect_asset_refs_from_layout(layout_vue_path: Path) -> list[str]:
    """Scan a layoutN.vue file for ``/assets/<name>`` URL references.

    Returns a sorted, unique list of bare basenames (no leading path, no query
    string, no fragment).  Both HTML attribute form
    (``src="/assets/foo.png"``) and CSS form
    (``url(/assets/bar.jpg)``) are recognised.

    Args:
        layout_vue_path: Absolute path to the ``layoutN.vue`` file to scan.

    Returns:
        Sorted list of unique asset basenames, e.g. ``['bar.jpg', 'foo.png']``.
        Returns ``[]`` if the file does not exist or is unreadable.
    """
    if not layout_vue_path.exists():
        return []

    try:
        text = layout_vue_path.read_text(encoding="utf-8")
    except OSError:
        return []

    basenames: set[str] = set()

    for match in _RE_SRC_ATTR.finditer(text):
        path = match.group("path")
        basenames.add(Path(path).name)

    for match in _RE_CSS_URL.finditer(text):
        path = match.group("path")
        basenames.add(Path(path).name)

    return sorted(basenames)


def threshold_for_slide(
    asset_names: list[str],
    manifest_path: Path,
    strict: float = 0.98,
    relaxed: float = 0.90,
) -> float:
    """Return the SSIM threshold appropriate for a slide that references *asset_names*.

    The threshold is ``relaxed`` if **any** asset in *asset_names* is found to
    have ``fidelity="low"`` in the manifest, or is absent from the manifest
    entirely (defensive worst-case).  Otherwise ``strict`` is returned.

    Derivative lookup:  if an asset name is not found as a top-level key it is
    looked up inside each entry's ``"derivatives"`` dict and the fidelity of
    the owning entry is used.

    Args:
        asset_names:   List of asset basenames to check (as returned by
                       :func:`collect_asset_refs_from_layout`).
        manifest_path: Path to ``theme/public/assets/manifest.json``.
        strict:        Threshold used when all assets have high/exact fidelity.
        relaxed:       Threshold used when at least one asset has low fidelity
                       or is unknown.

    Returns:
        Either *strict* or *relaxed*.
    """
    if not asset_names:
        return strict

    manifest = _load_manifest(manifest_path)

    # Build a flat mapping: derivative_basename → fidelity from parent entry,
    # to make derivative lookups O(1).
    derivative_fidelity: dict[str, str] = {}
    for entry in manifest.values():
        entry_fidelity = entry.get("fidelity", "low")
        for deriv_name in entry.get("derivatives", {}):
            derivative_fidelity[deriv_name] = entry_fidelity

    for name in asset_names:
        fidelity = _resolve_fidelity(name, manifest, derivative_fidelity)
        if fidelity == "low":
            return relaxed

    return strict


def threshold_for_layout(
    layout_vue_path: Path,
    manifest_path: Path,
    strict: float = 0.98,
    relaxed: float = 0.90,
) -> float:
    """Return the SSIM threshold for the slide rendered by *layout_vue_path*.

    Convenience composite: scans the layout for asset references via
    :func:`collect_asset_refs_from_layout`, then delegates to
    :func:`threshold_for_slide`.

    Args:
        layout_vue_path: Absolute path to the ``layoutN.vue`` file.
        manifest_path:   Path to ``theme/public/assets/manifest.json``.
        strict:          Strict SSIM threshold (default 0.98).
        relaxed:         Relaxed SSIM threshold (default 0.90).

    Returns:
        Either *strict* or *relaxed*.
    """
    asset_names = collect_asset_refs_from_layout(layout_vue_path)
    return threshold_for_slide(
        asset_names=asset_names,
        manifest_path=manifest_path,
        strict=strict,
        relaxed=relaxed,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _load_manifest(manifest_path: Path) -> dict:
    """Load the assets manifest, returning ``{}`` on any error."""
    if not manifest_path.exists():
        return {}
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _resolve_fidelity(
    name: str,
    manifest: dict,
    derivative_fidelity: dict[str, str],
) -> str:
    """Return the fidelity string for *name*, or ``"low"`` if not found.

    Lookup order:
    1. Top-level manifest key.
    2. Derivative name inside any entry's ``"derivatives"`` dict
       (pre-built into *derivative_fidelity*).
    3. Unknown → ``"low"`` (defensive).
    """
    if name in manifest:
        return manifest[name].get("fidelity", "low")

    if name in derivative_fidelity:
        return derivative_fidelity[name]

    # Unknown asset — treat as low fidelity defensively.
    return "low"
