"""Extract media assets from a PPTX zip into the Slidev deck's public/assets/.

Copies every file found under ``ppt/media/`` in the PPTX zip byte-for-byte into
``output_dir/public/assets/``, then classifies each image and writes a manifest.

The caller passes the *deck* directory: Slidev's Vite dev server only exposes
the deck's ``public/`` at site root. A theme's ``public/`` directory is NOT
served by Vite — putting assets there causes ``/assets/<name>`` requests to
fall through to the SPA index.html (returning text/html instead of the image
bytes). Assets therefore live with the deck.

The operation is idempotent: re-running with the same PPTX and the same
output_dir is a no-op on bytes (files with identical content are not
overwritten) and the manifest is always rewritten.
"""
from __future__ import annotations

import zipfile
from pathlib import Path

from .formats import classify
from .manifest import write_manifest


_MEDIA_PREFIX = "ppt/media/"


def extract_pictures(pptx_path: Path, output_dir: Path) -> dict[str, dict]:
    """Copy ``ppt/media/*`` from *pptx_path* to *output_dir/public/assets/*.

    Reads every entry whose zip path starts with ``ppt/media/`` from the PPTX
    (which is a zip archive), copies its bytes verbatim to
    ``output_dir/public/assets/<filename>``, classifies the image, and builds
    a manifest dict.  The manifest is written to
    ``output_dir/public/assets/manifest.json`` before returning.

    Idempotency: an existing asset file is only overwritten when its content
    differs from the zip entry bytes.

    Args:
        pptx_path:  Path to the source ``.pptx`` file.
        output_dir: Root of the directory whose ``public/assets/`` subtree
                    receives the bytes. For a Slidev import this MUST be the
                    deck directory (not the theme) — see module docstring.

    Returns:
        The manifest dict (also written to disk).  Keys are the original
        filenames (e.g. ``"image1.png"``); values follow the pictures manifest
        schema::

            {
                "source_format": "png",
                "fidelity": "exact",
                "derivatives": {},
                "warnings": []
            }
    """
    assets_dir = output_dir / "public" / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    manifest: dict[str, dict] = {}

    with zipfile.ZipFile(pptx_path, "r") as zf:
        for entry in zf.infolist():
            if not entry.filename.startswith(_MEDIA_PREFIX):
                continue

            # Strip the ppt/media/ prefix to get a bare filename
            filename = entry.filename[len(_MEDIA_PREFIX):]
            if not filename:
                # Skip the directory entry itself if present
                continue

            data = zf.read(entry.filename)
            dest = assets_dir / filename

            # Idempotency: skip write when bytes are identical
            if dest.exists() and dest.read_bytes() == data:
                pass
            else:
                dest.write_bytes(data)

            source_format, fidelity, warnings = classify(filename, data)
            manifest[filename] = {
                "source_format": source_format,
                "fidelity": fidelity,
                "derivatives": {},
                "warnings": warnings,
            }

    manifest_path = assets_dir / "manifest.json"
    write_manifest(manifest, manifest_path)

    return manifest
