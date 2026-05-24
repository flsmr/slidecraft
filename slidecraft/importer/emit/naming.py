"""Slot-name derivation for placeholders and picture placeholders.

A single emitted placeholder lives in three places that MUST agree:

1. ``<slot name="…">`` in the layout .vue template
2. ``::…::`` markdown override block in the deck's slides.md
3. ``.…`` CSS class on the placeholder wrapper div (used by per-placeholder
   bullet / margin / picture-stretch rules)

Centralising the name in one helper means there's one place to change the
scheme and zero opportunity for the three sites to drift apart.

Naming scheme
-------------
The slot name is derived from the OOXML placeholder ``type`` attribute plus
the placeholder's ``idx``. Singleton types (those that appear at most once
per layout) emit a bare type name with no suffix; repeatable types get an
``-{idx}`` suffix using the original OOXML idx so the name stays stable
across re-imports even when designers reorder placeholders inside PPT.

    title-like (title, ctrTitle)   → "title"            (singleton, no suffix)
    subTitle                       → "subtitle"         (singleton)
    date (dt)                      → "date"             (singleton)
    footer (ftr)                   → "footer"           (singleton)
    slide number (sldNum)          → "slide-number"     (singleton)
    body                           → "body-{idx}"
    object placeholder (obj)       → "content-{idx}"
    picture placeholder            → "picture-{idx}"
    unknown / None type            → "ph-{idx}"         (deterministic fallback)

The same string is used as the slot name, markdown marker, and CSS class.
"""
from __future__ import annotations

from typing import Optional

from ..model import Picture, Placeholder


# OOXML ``type=`` value → slot-name prefix.
# ctrTitle and title both collapse to ``"title"`` because PPT treats them as
# alternatives for the single title slot — they never co-occur within one
# layout, so collapsing them keeps deck markdown simple (``::title::``
# regardless of which variant the layout carries).
_TYPE_PREFIX: dict[str, str] = {
    "title":    "title",
    "ctrTitle": "title",
    "subTitle": "subtitle",
    "body":     "body",
    "obj":      "content",
    "dt":       "date",
    "ftr":      "footer",
    "sldNum":   "slide-number",
}

# Types that appear at most once per layout — emit the bare prefix with no
# numeric suffix. Matches Slidev's ``title`` convention from the official
# theme-authoring docs.
_SINGLETON_TYPES: frozenset[str] = frozenset({
    "title", "ctrTitle", "subTitle", "dt", "ftr", "sldNum",
})


def slot_name_for_placeholder(ph: Placeholder) -> str:
    """Return the slot/class/marker name for a text-bearing placeholder."""
    prefix = _TYPE_PREFIX.get(ph.type) if ph.type is not None else None
    if prefix is None:
        # Unknown or None type → deterministic idx-only fallback.
        return f"ph-{ph.idx}"
    if ph.type in _SINGLETON_TYPES:
        return prefix
    return f"{prefix}-{ph.idx}"


def slot_name_for_picture(pic: Picture) -> str:
    """Return the slot/class/marker name for a picture placeholder.

    Free ``<p:pic>`` shapes (``is_placeholder=False``) have no slot — they
    bake fully into the layout — so callers must guard with
    ``pic.is_placeholder and pic.ph_idx is not None`` before invoking this.
    """
    assert pic.is_placeholder and pic.ph_idx is not None, (
        "slot_name_for_picture called on a non-placeholder picture"
    )
    return f"picture-{pic.ph_idx}"


__all__ = ["slot_name_for_placeholder", "slot_name_for_picture"]
