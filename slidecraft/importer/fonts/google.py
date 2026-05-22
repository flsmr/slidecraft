"""Stage 2 — Google Fonts CSS-endpoint lookup and download.

Hits the public Google Fonts CSS2 endpoint with a real browser User-Agent
(required; Google returns a 400/empty response to non-browser UAs).
Parses the returned CSS for ``src: url(...)`` woff2 lines and downloads each
font file variant.

No API key required; this uses the same unauthenticated endpoint that browsers
hit when a page loads a Google Fonts stylesheet.
"""
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse, urlencode

import requests

# Mimic a real Windows browser so Google Fonts returns woff2 format
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

_GOOGLE_FONTS_CSS_URL = "https://fonts.googleapis.com/css2"

# Match: src: url(https://fonts.gstatic.com/…/somefile.woff2) format('woff2')
# Also handles lines that just have url(...) without explicit format
_URL_RE = re.compile(r"url\((https://[^\)]+\.woff2)\)", re.IGNORECASE)

# Match font-weight inside a @font-face block
_WEIGHT_RE = re.compile(r"font-weight:\s*(\d+)", re.IGNORECASE)
_STYLE_RE = re.compile(r"font-style:\s*(normal|italic|oblique)", re.IGNORECASE)

_TIMEOUT = 15  # seconds for HTTP requests


def _build_css_url(family: str, extra_variants: str = "") -> str:
    """Build a Google Fonts CSS2 URL for the given family name."""
    params = {
        "family": family,
        "display": "swap",
    }
    return f"{_GOOGLE_FONTS_CSS_URL}?{urlencode(params)}"


def _parse_font_face_blocks(css: str) -> list[dict]:
    """Parse @font-face blocks from CSS text.

    Returns a list of dicts with keys: url, weight, style.
    """
    results = []
    # Split on @font-face to process each block separately
    blocks = re.split(r"@font-face\s*\{", css)
    for block in blocks[1:]:  # first element is text before the first @font-face
        # Find the closing brace
        end = block.find("}")
        if end == -1:
            continue
        block_content = block[:end]

        url_m = _URL_RE.search(block_content)
        if not url_m:
            continue

        weight_m = _WEIGHT_RE.search(block_content)
        style_m = _STYLE_RE.search(block_content)

        results.append({
            "url": url_m.group(1),
            "weight": int(weight_m.group(1)) if weight_m else 400,
            "style": style_m.group(1) if style_m else "normal",
        })
    return results


def _filename_from_url(url: str, family: str, weight: int, style: str) -> str:
    """Generate a clean local filename from the variant metadata."""
    safe_family = family.replace(" ", "")
    variant = f"w{weight}"
    if style == "italic":
        variant += "i"
    # Extract original filename for uniqueness
    url_path = urlparse(url).path
    original = url_path.rsplit("/", 1)[-1]  # e.g. "Xxxxxhash.woff2"
    return f"{safe_family}-{variant}-{original}"


def lookup_google_fonts(
    family: str,
    dest_dir: Path,
    *,
    session: requests.Session | None = None,
) -> dict | None:
    """Look up *family* on Google Fonts and download all available woff2 variants.

    Returns a dict suitable for a manifest entry, or None if the font is not
    found on Google Fonts.

    Args:
        family:   The exact typeface name as it appears in the PPTX.
        dest_dir: Directory to write downloaded .woff2 files.
        session:  Optional requests.Session (allows mocking in tests).
    """
    dest_dir.mkdir(parents=True, exist_ok=True)

    sess = session or requests.Session()
    css_url = _build_css_url(family)

    try:
        resp = sess.get(
            css_url,
            headers={"User-Agent": _USER_AGENT},
            timeout=_TIMEOUT,
        )
    except requests.RequestException:
        return None

    if resp.status_code != 200 or not resp.text.strip():
        return None

    css = resp.text
    blocks = _parse_font_face_blocks(css)
    if not blocks:
        return None

    downloaded_files: list[str] = []
    font_face_meta: list[dict] = []

    for block in blocks:
        url = block["url"]
        weight = block["weight"]
        style = block["style"]
        filename = _filename_from_url(url, family, weight, style)
        dest_file = dest_dir / filename

        if not dest_file.exists():
            try:
                font_resp = sess.get(
                    url,
                    headers={"User-Agent": _USER_AGENT},
                    timeout=_TIMEOUT,
                )
                if font_resp.status_code == 200:
                    dest_file.write_bytes(font_resp.content)
                else:
                    continue
            except requests.RequestException:
                continue

        downloaded_files.append(filename)
        font_face_meta.append({
            "file": filename,
            "weight": weight,
            "style": style,
        })

    if not downloaded_files:
        return None

    return {
        "source": "google-fonts",
        "files": downloaded_files,
        "variants": font_face_meta,
        "fidelity": "exact",
    }
