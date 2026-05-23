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

import re
import zipfile
from pathlib import Path

from .formats import classify
from .manifest import write_manifest


_MEDIA_PREFIX = "ppt/media/"


# ---------------------------------------------------------------------------
# SVG post-processing — fix Microsoft icon-library tiny-stroke paths
# ---------------------------------------------------------------------------

# Microsoft's icon-library SVGs (the ones referenced via <asvg:svgBlip> on
# pictures inserted from PPT's Insert > Icons) frequently draw a "dot" — like
# the period of a question mark — as a path whose bounding box is much smaller
# than its stroke width, with fill="none". PowerPoint's renderer ends up
# painting it as a solid blob (the stroke overlaps itself); browser SVG
# renderers paint a faint ring or nothing visible. Patch each such path so
# its fill matches its stroke colour, which produces a filled dot in browsers
# without changing any path that was meant to be an outline.

# Regex extracting numeric pairs from path data — `M`, `L`, `C`, etc. plus
# their numeric arguments. Handles negative numbers, decimals, scientific
# notation. Captures one number at a time; we group into x/y pairs in code.
_PATH_NUMBER_RE = re.compile(r"-?\d+\.?\d*(?:[eE][-+]?\d+)?")


def _path_bbox(d_attr: str) -> tuple[float, float, float, float] | None:
    """Return ``(min_x, min_y, max_x, max_y)`` for an SVG ``d=""`` string.

    Bezier-curve control points are included in the bbox — this overestimates
    the visual extent slightly, which is fine for the "is this path small?"
    decision we're making here. Returns ``None`` when no numbers parse.
    """
    nums = [float(m) for m in _PATH_NUMBER_RE.findall(d_attr)]
    if len(nums) < 2:
        return None
    # Pair numbers as (x, y).  Path data alternates coordinates; this is
    # technically inaccurate for commands like ``A`` (arc) where some
    # parameters are flags or radii, but Microsoft icon-library paths use
    # only M/L/C/Z so the alternation is safe.
    xs = nums[0::2]
    ys = nums[1::2]
    if not xs or not ys:
        return None
    return (min(xs), min(ys), max(xs), max(ys))


def _patch_tiny_stroked_paths(svg_bytes: bytes) -> bytes:
    """Set ``fill=stroke`` on ``<path>`` elements whose bbox < stroke width.

    Returns the modified SVG bytes. If no patches are needed (or the file
    isn't well-formed SVG), returns the input unchanged.
    """
    try:
        from lxml import etree
    except ImportError:
        # lxml is a hard dep of the importer; this should never happen.
        return svg_bytes

    try:
        # ``recover=True`` lets us tolerate the occasional sloppy SVG.
        parser = etree.XMLParser(recover=True, remove_blank_text=False)
        root = etree.fromstring(svg_bytes, parser=parser)
    except etree.XMLSyntaxError:
        return svg_bytes
    if root is None:
        return svg_bytes

    # SVG namespace — most SVGs put paths inside the default SVG namespace.
    svg_ns = "http://www.w3.org/2000/svg"
    patched = False
    for path_el in root.iter(f"{{{svg_ns}}}path"):
        fill = path_el.get("fill")
        if fill is None or fill.strip().lower() != "none":
            continue
        stroke = path_el.get("stroke")
        if not stroke or stroke.strip().lower() == "none":
            continue
        try:
            stroke_width = float(path_el.get("stroke-width", "1"))
        except ValueError:
            continue
        d = path_el.get("d", "")
        bbox = _path_bbox(d)
        if bbox is None:
            continue
        min_x, min_y, max_x, max_y = bbox
        width = max_x - min_x
        height = max_y - min_y
        # If the path's drawn extent is smaller than its stroke width on
        # BOTH axes, the stroke covers the entire interior — the user-facing
        # intent is a filled dot.
        if width < stroke_width and height < stroke_width:
            path_el.set("fill", stroke)
            patched = True

    if not patched:
        return svg_bytes
    return etree.tostring(root, xml_declaration=False)


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

            # Patch Microsoft icon-library SVGs whose "dot" paths use a
            # tiny bbox with fill="none" and rely on the stroke overlapping
            # itself to look filled. Browsers render that as an outline,
            # not the filled blob PowerPoint draws — so we set fill=stroke
            # on those paths so the visual matches.
            if filename.lower().endswith(".svg"):
                data = _patch_tiny_stroked_paths(data)

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
