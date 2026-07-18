"""Tests for slidecraft.scripts.scan_theme.

Focus of ticket 10 (T3): a *local* theme that ships a ``semantic-layouts.json``
must surface, per physical layout, its **semantic slot-role map, the alias
intent, and the defaults** — the contract the slide-composer needs to fill a
cryptic physical slot (``body-26``, ``ph-1``) by role. A theme *without*
``semantic-layouts.json`` must still scan (bare physical slot names) plus a
``note`` that role/intent is unavailable, and the built-in default set must be
unaffected.

The tests build tiny fake themes under ``tmp_path`` rather than depend on the
user's real theme folders, so they run anywhere.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from slidecraft.scripts import scan_theme


# ---------------------------------------------------------------------------
# Fixtures — a minimal theme dir with cryptic physical slot names (ILSE-like)
# ---------------------------------------------------------------------------


def _write_theme(root: Path, *, semantic: dict | None = None,
                 styleguide: bool = False) -> Path:
    """Create a tiny local theme under ``root`` and return it.

    Two layouts: ``slide1`` (cover, cryptic slots) and ``slide4`` (content).
    Optionally drop a ``semantic-layouts.json`` and/or a ``styleguide.md``.
    """
    layouts = root / "layouts"
    layouts.mkdir(parents=True)
    (layouts / "slide1.vue").write_text(
        '<template><div>'
        '<slot name="body-26" /><slot name="body-25" />'
        '<slot name="body-19" /><slot name="body-12" />'
        "</div></template>\n",
        encoding="utf-8",
    )
    (layouts / "slide4.vue").write_text(
        '<template><div>'
        '<slot name="title" /><slot name="ph-1" /><slot name="body-13" />'
        "</div></template>\n",
        encoding="utf-8",
    )
    comps = root / "components"
    comps.mkdir()
    (comps / "SlideFooter.vue").write_text("<template><footer/></template>", "utf-8")
    if semantic is not None:
        (root / "semantic-layouts.json").write_text(
            json.dumps(semantic), encoding="utf-8")
    if styleguide:
        (root / "styleguide.md").write_text("# Style\n", encoding="utf-8")
    return root


ILSE_SEMANTIC = {
    "version": "1.2",
    "theme": "slidev-theme-fake",
    "aliases": {
        "cover": {
            "layout": "slide1",
            "slots": {"title": "body-26", "subtitle": "body-25",
                      "course_code": "body-19", "body": "body-12"},
            "intent": "Deck cover. TITLE (body-26) the deck name; BODY author.",
            "defaults": {},
        },
        "default": {
            "layout": "slide4",
            "slots": {"title": "title", "body": "ph-1", "citations": "body-13"},
            "intent": "Standard content slide.",
            "defaults": {"title": "Untitled"},
        },
    },
    "unmapped_layouts": [],
}


# ---------------------------------------------------------------------------
# local + semantic-layouts.json → enriched roles/intent/defaults
# ---------------------------------------------------------------------------


def test_local_enriches_layouts_with_roles_intent_defaults(tmp_path):
    theme = _write_theme(tmp_path / "t", semantic=ILSE_SEMANTIC, styleguide=True)
    caps = scan_theme.local_capabilities(str(theme))

    by_name = {l["name"]: l for l in caps["layouts"]}

    cover = by_name["slide1"]
    # Backward-compat fields survive (km validates on `name`; `slots` still bare).
    assert cover["name"] == "slide1"
    assert "body-26" in cover["slots"]
    # Enriched contract.
    assert cover["alias"] == "cover"
    assert cover["roles"]["title"] == "body-26"
    assert cover["roles"]["body"] == "body-12"
    assert "Deck cover" in cover["intent"]
    assert cover["defaults"] == {}

    content = by_name["slide4"]
    assert content["alias"] == "default"
    assert content["roles"]["body"] == "ph-1"
    assert content["defaults"] == {"title": "Untitled"}


def test_local_detects_styleguide(tmp_path):
    theme = _write_theme(tmp_path / "t", semantic=ILSE_SEMANTIC, styleguide=True)
    caps = scan_theme.local_capabilities(str(theme))
    assert caps["styleguide"].endswith("styleguide.md")
    assert Path(caps["styleguide"]).is_file()


def test_local_no_styleguide_key_when_absent(tmp_path):
    theme = _write_theme(tmp_path / "t", semantic=ILSE_SEMANTIC, styleguide=False)
    caps = scan_theme.local_capabilities(str(theme))
    assert "styleguide" not in caps


def test_components_still_listed(tmp_path):
    theme = _write_theme(tmp_path / "t", semantic=ILSE_SEMANTIC)
    caps = scan_theme.local_capabilities(str(theme))
    assert "SlideFooter" in caps["components"]


# ---------------------------------------------------------------------------
# local WITHOUT semantic-layouts.json → bare slots + a note
# ---------------------------------------------------------------------------


def test_local_without_semantic_falls_back_to_bare_slots_with_note(tmp_path):
    theme = _write_theme(tmp_path / "t", semantic=None)
    caps = scan_theme.local_capabilities(str(theme))

    by_name = {l["name"]: l for l in caps["layouts"]}
    cover = by_name["slide1"]
    assert cover["name"] == "slide1"
    assert "body-26" in cover["slots"]
    # No role/intent contract available.
    assert "roles" not in cover
    assert "intent" not in cover
    # A note flags that authoring quality drops without the contract.
    assert "note" in caps
    assert "semantic-layouts" in caps["note"]


def test_unmapped_physical_layout_stays_bare(tmp_path):
    # Alias map covers only slide1; slide4 has no alias → stays bare but present.
    semantic = {
        "aliases": {
            "cover": {"layout": "slide1", "slots": {"title": "body-26"},
                      "intent": "Cover.", "defaults": {}},
        },
    }
    theme = _write_theme(tmp_path / "t", semantic=semantic)
    caps = scan_theme.local_capabilities(str(theme))
    by_name = {l["name"]: l for l in caps["layouts"]}
    assert "roles" in by_name["slide1"]
    assert "roles" not in by_name["slide4"]
    # The unmapped layout is still usable by physical name (km compat).
    assert by_name["slide4"]["name"] == "slide4"


# ---------------------------------------------------------------------------
# builtin unaffected
# ---------------------------------------------------------------------------


def test_builtin_unaffected(tmp_path):
    caps = scan_theme.builtin_capabilities()
    names = {l["name"] for l in caps["layouts"]}
    assert "default" in names and "two-cols" in names
    assert "styleguide" not in caps
    for l in caps["layouts"]:
        assert "roles" not in l


@pytest.mark.parametrize("bad", [
    "{ not json",        # not JSON at all (JSONDecodeError)
    "[1, 2, 3]",         # valid JSON, top-level array (data["aliases"] → TypeError)
    "5",                 # valid JSON, top-level scalar
    '{"aliases": []}',   # valid JSON, `aliases` is not a dict
    "{}",                # valid JSON, no `aliases` key at all
])
def test_malformed_semantic_json_degrades_gracefully(tmp_path, bad):
    # A broken OR wrong-shaped semantic-layouts.json must not crash the scan —
    # fall back to bare slots + a note, so /init-deck still produces a usable
    # deck-context regardless of what the file contains.
    theme = _write_theme(tmp_path / "t", semantic=None)
    (theme / "semantic-layouts.json").write_text(bad, encoding="utf-8")
    caps = scan_theme.local_capabilities(str(theme))
    by_name = {l["name"]: l for l in caps["layouts"]}
    assert "roles" not in by_name["slide1"]
    assert "note" in caps
