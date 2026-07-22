"""Tests for slidecraft.scripts.scaffold_deck.

Ticket 10 wiring:
  * T3 — the theme's ``styleguide.md`` path reaches the deck context: recorded
    in the ``theme`` block and injected as ``STYLE-GUIDE`` for both the
    slide-composer and the image-composer (empty when the theme has none). The
    enriched slot-role capabilities (roles/intent/defaults) flow through from
    ``scan_theme`` into ``theme.capabilities``.
  * T6 — the deck metadata the old skeleton substituted (presenter, institution,
    course, date) is captured into ``deck`` and exposed to the slide-composer,
    with a derived ``FOOTER``. These are optional — absence must not break.

Tests build a tiny local theme + answers file under ``tmp_path`` and call
``scaffold`` with an explicit root, so nothing depends on the real CWD.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from slidecraft.scripts import scaffold_deck


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_theme(root: Path, *, styleguide: bool = True) -> Path:
    """A minimal local theme with a semantic-layouts contract + styleguide."""
    layouts = root / "layouts"
    layouts.mkdir(parents=True)
    (layouts / "slide1.vue").write_text(
        '<template><slot name="body-26" /></template>', encoding="utf-8")
    (root / "semantic-layouts.json").write_text(json.dumps({
        "aliases": {
            "cover": {"layout": "slide1", "slots": {"title": "body-26"},
                      "intent": "Deck cover.", "defaults": {}},
        }
    }), encoding="utf-8")
    if styleguide:
        (root / "styleguide.md").write_text("# Style\n", encoding="utf-8")
    return root


def _answers(theme: dict, **extra) -> dict:
    base = {
        "topic": "Object Tracking",
        "audience": "students",
        "language": "en",
        "deck_type": "lecture",
        "setting": "university course",
        "max_slides": 20,
        "max_duration_minutes": 45,
        "theme": theme,
    }
    base.update(extra)
    return base


# ---------------------------------------------------------------------------
# T3 — style guide reaches theme block + both composer injections
# ---------------------------------------------------------------------------


def test_styleguide_recorded_and_injected_for_local_theme(tmp_path):
    theme_dir = _make_theme(tmp_path / "theme", styleguide=True)
    deck = tmp_path / "deck"
    deck.mkdir()
    ans = _answers({"type": "local", "source": str(theme_dir)})

    scaffold_deck.scaffold(deck, ans)
    ctx = json.loads((deck / "deck-context.json").read_text(encoding="utf-8"))

    sg = ctx["theme"]["styleguide"]
    assert sg.endswith("styleguide.md") and Path(sg).is_file()
    assert ctx["injection"]["slide-composer"]["STYLE-GUIDE"] == sg
    assert ctx["injection"]["image-composer"]["STYLE-GUIDE"] == sg


def test_enriched_capabilities_flow_into_theme_block(tmp_path):
    theme_dir = _make_theme(tmp_path / "theme")
    deck = tmp_path / "deck"
    deck.mkdir()
    ans = _answers({"type": "local", "source": str(theme_dir)})

    scaffold_deck.scaffold(deck, ans)
    ctx = json.loads((deck / "deck-context.json").read_text(encoding="utf-8"))

    layout = ctx["theme"]["capabilities"]["layouts"][0]
    assert layout["alias"] == "cover"
    assert layout["roles"] == {"title": "body-26"}


def test_styleguide_empty_for_builtin_theme(tmp_path):
    deck = tmp_path / "deck"
    deck.mkdir()
    ans = _answers({"type": "builtin", "source": "default"})

    scaffold_deck.scaffold(deck, ans)
    ctx = json.loads((deck / "deck-context.json").read_text(encoding="utf-8"))

    assert ctx["theme"]["styleguide"] == ""
    assert ctx["injection"]["slide-composer"]["STYLE-GUIDE"] == ""
    assert ctx["injection"]["image-composer"]["STYLE-GUIDE"] == ""


# ---------------------------------------------------------------------------
# T6 — deck metadata captured + exposed + FOOTER derived
# ---------------------------------------------------------------------------


def test_deck_metadata_captured_and_exposed(tmp_path):
    deck = tmp_path / "deck"
    deck.mkdir()
    ans = _answers(
        {"type": "builtin", "source": "default"},
        presenter="Dr. Jane Roe", institution="IU", course="DLBAI01",
        date="2026-07-18",
    )

    scaffold_deck.scaffold(deck, ans)
    ctx = json.loads((deck / "deck-context.json").read_text(encoding="utf-8"))

    d = ctx["deck"]
    assert d["presenter"] == "Dr. Jane Roe"
    assert d["institution"] == "IU"
    assert d["course"] == "DLBAI01"
    assert d["date"] == "2026-07-18"

    comp = ctx["injection"]["slide-composer"]
    assert comp["PRESENTER"] == "Dr. Jane Roe"
    assert comp["INSTITUTION"] == "IU"
    assert comp["COURSE"] == "DLBAI01"
    assert comp["DATE"] == "2026-07-18"
    # FOOTER derived as "presenter · date".
    assert comp["FOOTER"] == "Dr. Jane Roe · 2026-07-18"


def test_deck_metadata_optional_absent_is_empty(tmp_path):
    deck = tmp_path / "deck"
    deck.mkdir()
    ans = _answers({"type": "builtin", "source": "default"})

    scaffold_deck.scaffold(deck, ans)
    ctx = json.loads((deck / "deck-context.json").read_text(encoding="utf-8"))

    d = ctx["deck"]
    assert d["presenter"] == ""
    assert d["institution"] == ""
    assert d["date"] == ""
    comp = ctx["injection"]["slide-composer"]
    assert comp["PRESENTER"] == ""
    assert comp["FOOTER"] == ""


def test_footer_derived_from_presenter_only(tmp_path):
    deck = tmp_path / "deck"
    deck.mkdir()
    ans = _answers({"type": "builtin", "source": "default"},
                   presenter="Jane Roe")
    scaffold_deck.scaffold(deck, ans)
    ctx = json.loads((deck / "deck-context.json").read_text(encoding="utf-8"))
    assert ctx["injection"]["slide-composer"]["FOOTER"] == "Jane Roe"


# ---------------------------------------------------------------------------
# D38 — duration → slides pacing (max_slides derived when not given)
# ---------------------------------------------------------------------------


def test_max_slides_derived_from_duration_at_1_5_min(tmp_path):
    deck = tmp_path / "deck"
    deck.mkdir()
    # 45 min lecture at the default 1.5 min/slide -> 30 slides.
    ans = _answers({"type": "builtin", "source": "default"},
                   max_duration_minutes=45)
    ans.pop("max_slides")
    scaffold_deck.scaffold(deck, ans)
    ctx = json.loads((deck / "deck-context.json").read_text(encoding="utf-8"))
    assert ctx["deck"]["max_slides"] == 30
    assert ctx["injection"]["storyteller"]["MAX-SLIDES"] == "30"


def test_explicit_max_slides_overrides_duration(tmp_path):
    deck = tmp_path / "deck"
    deck.mkdir()
    ans = _answers({"type": "builtin", "source": "default"},
                   max_duration_minutes=45, max_slides=12)
    scaffold_deck.scaffold(deck, ans)
    ctx = json.loads((deck / "deck-context.json").read_text(encoding="utf-8"))
    assert ctx["deck"]["max_slides"] == 12


def test_pacing_varies_by_deck_type():
    # Pitch is faster (0.75 min/slide) than a lecture (1.5), so the same
    # duration yields more slides.
    assert scaffold_deck.minutes_per_slide("lecture") == 1.5
    assert scaffold_deck.minutes_per_slide("pitch") == 0.75
    # Unknown type falls back to the 1.5 default.
    assert scaffold_deck.minutes_per_slide("mystery") == 1.5
    assert scaffold_deck.derive_max_slides(
        {"max_duration_minutes": 30, "deck_type": "pitch"}) == 40


# ---------------------------------------------------------------------------
# D38 — local theme localized into ./theme (self-contained deck)
# ---------------------------------------------------------------------------


def test_local_theme_copied_into_deck_and_referenced_relatively(tmp_path):
    theme_dir = _make_theme(tmp_path / "brand-theme", styleguide=True)
    deck = tmp_path / "deck"
    deck.mkdir()
    ans = _answers({"type": "local", "source": str(theme_dir)})

    scaffold_deck.scaffold(deck, ans)

    # The theme is copied into the deck's theme/ subfolder...
    assert (deck / "theme" / "layouts" / "slide1.vue").is_file()
    assert (deck / "theme" / "styleguide.md").is_file()

    ctx = json.loads((deck / "deck-context.json").read_text(encoding="utf-8"))
    # ...and referenced by the portable ./theme path in the context + slides.md.
    assert ctx["theme"]["type"] == "local"
    assert ctx["theme"]["source"] == "./theme"
    assert "theme: ./theme" in (deck / "slides.md").read_text(encoding="utf-8")
    # Capabilities are scanned from the *copied* theme (alias contract intact).
    assert ctx["theme"]["capabilities"]["layouts"][0]["alias"] == "cover"


def test_localize_theme_idempotent_when_theme_dir_exists(tmp_path):
    theme_dir = _make_theme(tmp_path / "brand-theme")
    deck = tmp_path / "deck"
    deck.mkdir()
    # Pre-create theme/ (as a prewarm would) with a marker file; localize must
    # not overwrite it.
    (deck / "theme").mkdir()
    (deck / "theme" / "MARKER").write_text("kept", encoding="utf-8")

    portable, scan_source = scaffold_deck.localize_theme(
        deck, {"type": "local", "source": str(theme_dir)})

    assert portable == {"type": "local", "source": "./theme"}
    assert (deck / "theme" / "MARKER").read_text(encoding="utf-8") == "kept"
    assert not (deck / "theme" / "layouts").exists()  # copy skipped


def test_local_theme_own_deps_folded_into_package_json(tmp_path):
    theme_dir = _make_theme(tmp_path / "brand-theme")
    # The theme declares its own runtime dep + a self-ref + a workspace spec.
    (theme_dir / "package.json").write_text(json.dumps({
        "name": "slidev-theme-brand",
        "dependencies": {
            "slidev-theme-brand": "1.0.0",          # self-ref -> dropped
            "@slidev/theme-default": "^0.25.0",     # real dep -> kept
            "some-mono-pkg": "workspace:*",         # non-registry -> dropped
        },
    }), encoding="utf-8")
    deck = tmp_path / "deck"
    deck.mkdir()
    ans = _answers({"type": "local", "source": str(theme_dir)})

    scaffold_deck.scaffold(deck, ans)
    pkg = json.loads((deck / "package.json").read_text(encoding="utf-8"))

    deps = pkg["dependencies"]
    assert deps["@slidev/cli"] == "latest"            # deck's own pin
    assert deps["@slidev/theme-default"] == "^0.25.0"  # theme dep folded in
    assert "slidev-theme-brand" not in deps           # self-ref dropped
    assert "some-mono-pkg" not in deps                # workspace spec dropped


def test_builtin_theme_not_localized(tmp_path):
    deck = tmp_path / "deck"
    deck.mkdir()
    portable, scan_source = scaffold_deck.localize_theme(
        deck, {"type": "builtin", "source": "default"})
    assert portable == {"type": "builtin", "source": "default"}
    assert scan_source == "default"
    assert not (deck / "theme").exists()


# ---------------------------------------------------------------------------
# D38 — prewarm phase (folders + theme copy + package.json, no deck-context)
# ---------------------------------------------------------------------------


def test_prewarm_lays_down_npm_project_without_deck_context(tmp_path):
    theme_dir = _make_theme(tmp_path / "brand-theme")
    deck = tmp_path / "deck"
    deck.mkdir()
    ans = {"topic": "Object Tracking",
           "theme": {"type": "local", "source": str(theme_dir)}}

    summary = scaffold_deck.prewarm(deck, ans)

    assert summary["phase"] == "prewarm"
    assert summary["node_modules_present"] is False
    # Physical scaffold present...
    assert (deck / "package.json").is_file()
    assert (deck / ".gitignore").is_file()
    assert (deck / "theme" / "layouts" / "slide1.vue").is_file()
    assert (deck / "input" / "processed").is_dir()
    # ...but NOT the full-phase artifacts.
    assert not (deck / "deck-context.json").exists()
    assert not (deck / "slides.md").exists()


def test_full_scaffold_after_prewarm_is_idempotent(tmp_path):
    theme_dir = _make_theme(tmp_path / "brand-theme")
    deck = tmp_path / "deck"
    deck.mkdir()
    prewarm_ans = {"topic": "Object Tracking",
                   "theme": {"type": "local", "source": str(theme_dir)}}
    scaffold_deck.prewarm(deck, prewarm_ans)

    # Then the full scaffold with the same (localized) theme completes the deck.
    full_ans = _answers({"type": "local", "source": str(theme_dir)},
                        max_duration_minutes=30)
    full_ans.pop("max_slides")
    summary = scaffold_deck.scaffold(deck, full_ans)

    assert summary["phase"] == "full"
    ctx = json.loads((deck / "deck-context.json").read_text(encoding="utf-8"))
    assert ctx["theme"]["source"] == "./theme"
    assert ctx["deck"]["max_slides"] == 20  # 30 min / 1.5


def test_prewarm_refuses_existing_deck(tmp_path):
    deck = tmp_path / "deck"
    deck.mkdir()
    (deck / "deck-context.json").write_text("{}", encoding="utf-8")
    ans = {"topic": "X", "theme": {"type": "builtin", "source": "default"}}
    with pytest.raises(SystemExit):
        scaffold_deck.prewarm(deck, ans)


# ---------------------------------------------------------------------------
# D47 — variant-cycling browser wiring (vite.config.ts + setup/shortcuts.ts)
# ---------------------------------------------------------------------------


def test_scaffold_writes_variant_browser_wiring(tmp_path):
    deck = tmp_path / "deck"
    deck.mkdir()
    ans = _answers({"type": "builtin", "source": "default"})

    scaffold_deck.scaffold(deck, ans)

    assert (deck / "vite.config.ts").exists()
    assert (deck / "setup" / "shortcuts.ts").exists()
    vite = (deck / "vite.config.ts").read_text(encoding="utf-8")
    assert "/__variant" in vite            # the cycle endpoint
    assert "cycle-variant" in vite         # shells out to km
