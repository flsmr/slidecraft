"""Read/write deck/public/assets/manifest.json for the pictures pipeline.

The manifest records, per image file, the source format, fidelity, any
derivative files, and warnings raised during classification.

Schema example::

    {
      "image1.png": {
        "source_format": "png",
        "fidelity": "exact",
        "derivatives": {},
        "warnings": []
      },
      "image2.emf": {
        "source_format": "emf",
        "fidelity": "low",
        "derivatives": {},
        "warnings": ["unsupported_format:emf"]
      }
    }
"""
from __future__ import annotations

import json
from pathlib import Path


def write_manifest(manifest: dict, manifest_path: Path) -> None:
    """Write *manifest* to *manifest_path* as pretty-printed JSON.

    Parent directories are created if they do not exist.  The file always ends
    with a trailing newline.

    Args:
        manifest:      Dict mapping image filenames to their manifest entries.
        manifest_path: Destination path for ``manifest.json``.
    """
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def load_manifest(manifest_path: Path) -> dict:
    """Load a manifest JSON file, returning an empty dict if it does not exist.

    Args:
        manifest_path: Path to ``manifest.json``.

    Returns:
        Parsed manifest dict, or ``{}`` if the file is absent or unreadable.
    """
    if not manifest_path.exists():
        return {}
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
