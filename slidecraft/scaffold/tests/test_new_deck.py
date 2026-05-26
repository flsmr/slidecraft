"""Tests for slidecraft.scaffold.new_deck — pure scaffolding mechanics."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from slidecraft.scaffold.new_deck import (
    ScaffoldResult,
    _enumerate_layouts,
    _extract_slot_names,
    _natural_sort_key,
    _portable_relpath,
    _render_package_json,
    main,
    scaffold_deck,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_valid_theme(theme_dir: Path, name: str = "slidev-theme-test") -> Path:
    """Create a minimal valid Slidev theme directory for tests."""
    theme_dir.mkdir(parents=True, exist_ok=True)
    pkg = {
        "name": name,
        "version": "0.1.0",
        "slidev": {"colorSchema": "light"},
    }
    (theme_dir / "package.json").write_text(json.dumps(pkg), encoding="utf-8")
    return theme_dir


def _add_layout(theme_dir: Path, name: str, slots: list[str]) -> None:
    """Add a fake layout .vue file to a test theme directory."""
    layouts = theme_dir / "layouts"
    layouts.mkdir(exist_ok=True)
    slot_html = "\n".join(f'      <slot name="{s}" />' for s in slots)
    vue = f'<template>\n  <div class="slidev-layout">\n{slot_html}\n  </div>\n</template>\n'
    (layouts / f"{name}.vue").write_text(vue, encoding="utf-8")


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

class TestScaffoldWithTheme:
    def test_creates_expected_files(self, tmp_path):
        theme = _make_valid_theme(tmp_path / "slidev-theme-test")
        deck = tmp_path / "decks" / "my-deck"
        scaffold_deck(deck, theme, "my-deck", install=False)

        assert (deck / "slides.md").is_file()
        assert (deck / "package.json").is_file()
        assert (deck / ".gitignore").is_file()
        assert (deck / "public").is_dir()
        # resources/ for source material (papers, raw images, outlines)
        # plus a README explaining the convention.
        assert (deck / "resources").is_dir()
        assert (deck / "resources" / "README.md").is_file()

    def test_package_json_uses_portable_relative_path(self, tmp_path):
        """The file: dependency must use forward slashes (cross-platform)."""
        theme = _make_valid_theme(tmp_path / "slidev-theme-test")
        deck = tmp_path / "decks" / "my-deck"
        result = scaffold_deck(deck, theme, "my-deck", install=False)

        pkg = json.loads((deck / "package.json").read_text())
        dep = pkg["dependencies"]["slidev-theme-test"]
        assert dep.startswith("file:")
        # No backslashes anywhere in the file: path — critical on Windows.
        assert "\\" not in dep
        # Relative path goes up out of decks/ and back into the sibling theme.
        assert dep == "file:../../slidev-theme-test"
        assert result.theme_rel == "../../slidev-theme-test"

    def test_slides_md_references_theme_by_name(self, tmp_path):
        theme = _make_valid_theme(tmp_path / "slidev-theme-test", name="slidev-theme-acme")
        deck = tmp_path / "my-deck"
        scaffold_deck(deck, theme, "my-deck", install=False)

        slides = (deck / "slides.md").read_text()
        assert "theme: slidev-theme-acme" in slides
        assert "# my-deck" in slides

    def test_result_fields(self, tmp_path):
        theme = _make_valid_theme(tmp_path / "slidev-theme-test")
        deck = tmp_path / "my-deck"
        result = scaffold_deck(deck, theme, "my-deck", install=False)

        assert isinstance(result, ScaffoldResult)
        assert result.deck_dir == deck
        assert result.deck_name == "my-deck"
        assert result.theme_name == "slidev-theme-test"
        assert result.theme_dir == theme
        assert result.installed is False  # install=False
        assert result.preview_hint().endswith("npx slidev")


class TestResourcesFolder:
    """resources/ is the source-material folder — papers, raw images,
    outlines, meeting notes. NOT served by Slidev (that's what public/
    is for). Created on every scaffold so users have a consistent place
    to drop the inputs their deck is based on."""

    def test_created_for_themed_deck(self, tmp_path):
        theme = _make_valid_theme(tmp_path / "slidev-theme-test")
        deck = tmp_path / "my-deck"
        scaffold_deck(deck, theme, "my-deck", install=False)
        assert (deck / "resources").is_dir()

    def test_created_for_default_theme_deck(self, tmp_path):
        deck = tmp_path / "my-deck"
        scaffold_deck(deck, None, "my-deck", install=False)
        assert (deck / "resources").is_dir()

    def test_readme_explains_distinction_from_public(self, tmp_path):
        deck = tmp_path / "my-deck"
        scaffold_deck(deck, None, "my-deck", install=False)
        readme = (deck / "resources" / "README.md").read_text()
        # README must distinguish resources/ (source) from public/ (runtime).
        assert "public/" in readme
        assert "NOT served" in readme


class TestScaffoldWithDefaultTheme:
    """theme_dir=None ⇒ use Slidev's built-in default theme."""

    def test_no_theme_dep_in_package_json(self, tmp_path):
        deck = tmp_path / "my-deck"
        scaffold_deck(deck, None, "my-deck", install=False)

        pkg = json.loads((deck / "package.json").read_text())
        # Only @slidev/cli, no theme.
        assert pkg["dependencies"] == {"@slidev/cli": "^52.0.0"}

    def test_slides_md_omits_theme_frontmatter(self, tmp_path):
        deck = tmp_path / "my-deck"
        scaffold_deck(deck, None, "my-deck", install=False)

        slides = (deck / "slides.md").read_text()
        assert "theme:" not in slides.split("---")[1]  # frontmatter only

    def test_result_theme_fields(self, tmp_path):
        deck = tmp_path / "my-deck"
        result = scaffold_deck(deck, None, "my-deck", install=False)
        assert result.theme_name == "@slidev/theme-default"
        assert result.theme_dir is None
        assert result.theme_rel is None


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

class TestValidation:
    def test_raises_when_deck_dir_exists(self, tmp_path):
        deck = tmp_path / "existing"
        deck.mkdir()
        with pytest.raises(FileExistsError):
            scaffold_deck(deck, None, "x", install=False)

    def test_overwrite_allows_existing_dir(self, tmp_path):
        deck = tmp_path / "existing"
        deck.mkdir()
        # Should not raise; writes into the existing dir.
        scaffold_deck(deck, None, "x", install=False, overwrite=True)
        assert (deck / "slides.md").is_file()

    def test_raises_when_theme_missing_package_json(self, tmp_path):
        theme = tmp_path / "broken-theme"
        theme.mkdir()  # no package.json
        with pytest.raises(FileNotFoundError, match="no package.json"):
            scaffold_deck(tmp_path / "deck", theme, "x", install=False)

    def test_raises_when_theme_package_json_missing_slidev_key(self, tmp_path):
        theme = tmp_path / "fake-theme"
        theme.mkdir()
        (theme / "package.json").write_text('{"name": "x"}')
        with pytest.raises(ValueError, match="missing required 'slidev' key"):
            scaffold_deck(tmp_path / "deck", theme, "x", install=False)

    def test_raises_when_theme_package_json_missing_name(self, tmp_path):
        theme = tmp_path / "nameless-theme"
        theme.mkdir()
        (theme / "package.json").write_text('{"slidev": {}}')
        with pytest.raises(ValueError, match="missing 'name' field"):
            scaffold_deck(tmp_path / "deck", theme, "x", install=False)

    def test_raises_when_theme_package_json_invalid_json(self, tmp_path):
        theme = tmp_path / "malformed-theme"
        theme.mkdir()
        (theme / "package.json").write_text("not json{")
        with pytest.raises(ValueError, match="invalid JSON"):
            scaffold_deck(tmp_path / "deck", theme, "x", install=False)

    def test_rejects_uppercase_theme_name(self, tmp_path):
        """Regression: Slidev rejects uppercase theme names at startup.
        We catch it here so the deck never gets generated against a bad
        theme (which would otherwise error only at `npx slidev` time)."""
        bad = _make_valid_theme(tmp_path / "slidev-theme-bad", name="slidev-theme-BAD")
        with pytest.raises(ValueError, match="uppercase"):
            scaffold_deck(tmp_path / "deck", bad, "x", install=False)

    def test_rejects_uppercase_deck_name(self, tmp_path):
        """Same enforcement for the deck's own package.json name."""
        # deck_name is lowercased before going into package.json, so an
        # all-uppercase deck_name still produces a valid lowercased npm
        # name. We only error when lowercasing isn't enough — e.g. a name
        # with spaces or punctuation that npm rejects.
        with pytest.raises(ValueError, match="deck name"):
            scaffold_deck(tmp_path / "deck", None, "has spaces", install=False)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class TestPortableRelpath:
    def test_uses_forward_slashes(self, tmp_path):
        a = tmp_path / "a" / "deep" / "deck"
        b = tmp_path / "themes" / "x"
        a.mkdir(parents=True)
        b.mkdir(parents=True)
        rel = _portable_relpath(b, a)
        assert "\\" not in rel
        assert rel == "../../../themes/x"


class TestRenderPackageJson:
    def test_includes_theme_dep_when_rel_given(self):
        out = _render_package_json("mydeck", "slidev-theme-x", "../slidev-theme-x")
        pkg = json.loads(out)
        assert pkg["dependencies"]["slidev-theme-x"] == "file:../slidev-theme-x"
        assert pkg["name"] == "mydeck"  # lowercased

    def test_omits_theme_dep_when_rel_none(self):
        out = _render_package_json("mydeck", "@slidev/theme-default", None)
        pkg = json.loads(out)
        assert "@slidev/theme-default" not in pkg["dependencies"]
        assert pkg["dependencies"] == {"@slidev/cli": "^52.0.0"}

    def test_deck_name_lowercased_for_npm(self):
        # npm package names must be lowercase. We accept any case for the
        # human-facing deck name but lowercase it for the package field.
        out = _render_package_json("MyDeck-CamelCase", "@slidev/theme-default", None)
        pkg = json.loads(out)
        assert pkg["name"] == "mydeck-camelcase"


# ---------------------------------------------------------------------------
# CLI smoke
# ---------------------------------------------------------------------------

class TestCli:
    def test_cli_with_theme_succeeds(self, tmp_path, capsys):
        theme = _make_valid_theme(tmp_path / "slidev-theme-test")
        rc = main([
            "--name", "cli-deck",
            "--location", str(tmp_path / "decks"),
            "--theme", str(theme),
            "--no-install",
        ])
        assert rc == 0
        out = capsys.readouterr().out
        assert "deck_dir:" in out
        assert "theme_name:  slidev-theme-test" in out
        assert (tmp_path / "decks" / "cli-deck" / "slides.md").is_file()

    def test_cli_without_theme_succeeds(self, tmp_path, capsys):
        rc = main([
            "--name", "cli-deck-default",
            "--location", str(tmp_path),
            "--no-install",
        ])
        assert rc == 0
        out = capsys.readouterr().out
        assert "(Slidev built-in default)" in out

    def test_cli_minimal_flag_opts_out_of_gallery(self, tmp_path, capsys):
        theme = _make_valid_theme(tmp_path / "slidev-theme-test")
        for i in range(1, 4):
            _add_layout(theme, f"slide{i}", ["title"])
        rc = main([
            "--name", "cli-deck",
            "--location", str(tmp_path / "decks"),
            "--theme", str(theme),
            "--no-install",
            "--minimal",
        ])
        assert rc == 0
        assert "mode:        minimal" in capsys.readouterr().out

    def test_cli_returns_1_on_validation_error(self, tmp_path, capsys):
        # Invalid theme — should exit 1 with stderr message, not raise.
        bad_theme = tmp_path / "no-pkg"
        bad_theme.mkdir()
        rc = main([
            "--name", "x",
            "--location", str(tmp_path / "decks"),
            "--theme", str(bad_theme),
            "--no-install",
        ])
        assert rc == 1
        err = capsys.readouterr().err
        assert "error:" in err


# ---------------------------------------------------------------------------
# Gallery mode (default when theme has layouts/)
# ---------------------------------------------------------------------------

class TestGalleryMode:
    """When the theme has a layouts/ directory, the scaffolder emits one
    slide per layout — required because slides without explicit `layout:`
    frontmatter use Slidev's built-in default layout, NOT the theme."""

    def test_emits_one_slide_per_layout(self, tmp_path):
        theme = _make_valid_theme(tmp_path / "slidev-theme-test")
        _add_layout(theme, "slide1", ["title", "body-12"])
        _add_layout(theme, "slide2", ["title"])
        _add_layout(theme, "slide3", ["body-19"])
        deck = tmp_path / "my-deck"
        result = scaffold_deck(deck, theme, "my-deck", install=False)

        assert result.mode == "gallery"
        assert result.slide_count == 3

        slides = (deck / "slides.md").read_text()
        assert "layout: slide1" in slides
        assert "layout: slide2" in slides
        assert "layout: slide3" in slides

    def test_emits_title_slot_override_when_title_in_slots(self, tmp_path):
        theme = _make_valid_theme(tmp_path / "slidev-theme-test")
        _add_layout(theme, "slide1", ["title", "body-12"])
        deck = tmp_path / "my-deck"
        scaffold_deck(deck, theme, "my-deck", install=False)
        slides = (deck / "slides.md").read_text()

        assert "::title::" in slides
        assert "Layout: slide1" in slides

    def test_populates_every_text_slot(self, tmp_path):
        """Each text slot must get a ``::slot::`` override with placeholder
        copy so the layout looks visually populated when previewed —
        otherwise un-overridden slots render empty (the converter doesn't
        bake defaults into text slots, only picture slots)."""
        theme = _make_valid_theme(tmp_path / "slidev-theme-test")
        _add_layout(theme, "slide1", ["title", "body-12", "body-19"])
        deck = tmp_path / "my-deck"
        scaffold_deck(deck, theme, "my-deck", install=False)
        slides = (deck / "slides.md").read_text()

        assert "::title::" in slides
        assert "::body-12::" in slides
        assert "::body-19::" in slides
        # Title gets a layout-aware heading; body slots get generic copy.
        assert "Layout: slide1" in slides
        assert "body-12 content" in slides
        assert "body-19 content" in slides

    def test_picture_slots_not_overridden(self, tmp_path):
        """Picture slots are left un-overridden so the layout's default
        image (baked by the converter into ``<slot name="picture-N">{img}``)
        shows through. Overriding with empty content would suppress it."""
        theme = _make_valid_theme(tmp_path / "slidev-theme-test")
        _add_layout(theme, "slide1", ["title", "picture-22"])
        deck = tmp_path / "my-deck"
        scaffold_deck(deck, theme, "my-deck", install=False)
        slides = (deck / "slides.md").read_text()

        # Title is overridden as a block; picture-22 is NOT — i.e.,
        # ``::picture-22::`` does not appear on a line by itself.
        # (It does appear inside the comment hint, wrapped in backticks,
        # but that's documentation, not an active override.)
        assert any(line == "::title::" for line in slides.splitlines())
        assert not any(line == "::picture-22::" for line in slides.splitlines())
        # The user is told the picture slot exists via a comment hint.
        assert "default image" in slides
        assert "picture-22" in slides

    def test_singleton_slots_use_parenthesised_marker(self, tmp_path):
        """Singletons like footer/date/slide-number should get a clearly
        placeholder-y override so they're visible but obviously meant to
        be replaced. We use parens like ``(footer)``."""
        theme = _make_valid_theme(tmp_path / "slidev-theme-test")
        _add_layout(theme, "slide1", ["footer", "date", "slide-number"])
        deck = tmp_path / "my-deck"
        scaffold_deck(deck, theme, "my-deck", install=False)
        slides = (deck / "slides.md").read_text()

        assert "::footer::\n(footer)" in slides
        assert "::date::\n(date)" in slides
        assert "::slide-number::\n(slide-number)" in slides

    def test_layout_without_title_omits_title_override(self, tmp_path):
        theme = _make_valid_theme(tmp_path / "slidev-theme-test")
        _add_layout(theme, "slide1", ["body-12", "body-19"])  # no title slot
        deck = tmp_path / "my-deck"
        scaffold_deck(deck, theme, "my-deck", install=False)
        slides = (deck / "slides.md").read_text()

        # The slide has `layout: slide1` but no `::title::` block because
        # the layout doesn't expose a title slot.
        assert "layout: slide1" in slides
        slide1_section = slides.split("layout: slide1")[1].split("---")[0]
        assert "::title::" not in slide1_section

    def test_falls_back_to_minimal_when_theme_has_no_layouts_dir(self, tmp_path):
        theme = _make_valid_theme(tmp_path / "slidev-theme-test")  # no layouts/
        deck = tmp_path / "my-deck"
        result = scaffold_deck(deck, theme, "my-deck", install=False)
        assert result.mode == "minimal"
        # Minimal still pins layout: to "default" so Slidev knows what to
        # render. (Themes without layouts/ are typically hand-scaffolded
        # and rely on Slidev's built-in default layout.)
        assert "layout: default" in (deck / "slides.md").read_text()

    def test_minimal_flag_forces_minimal_mode_even_with_layouts(self, tmp_path):
        theme = _make_valid_theme(tmp_path / "slidev-theme-test")
        _add_layout(theme, "slide1", ["title"])
        _add_layout(theme, "slide2", ["title"])
        deck = tmp_path / "my-deck"
        result = scaffold_deck(deck, theme, "my-deck", install=False, minimal=True)
        assert result.mode == "minimal"
        assert result.slide_count == 2
        # Minimal pins the starter to the FIRST available layout so the
        # theme's styling actually applies on `npx slidev`.
        assert "layout: slide1" in (deck / "slides.md").read_text()

    def test_slide_count_matches_layout_count_exactly(self, tmp_path):
        """Regression: previously rendered an empty separator slide between
        every real slide, doubling the count (49 layouts → 99 slides).
        Slide boundaries in Slidev are ``---`` lines; the global frontmatter
        IS slide 1's frontmatter, so the count is (frontmatter_blocks)
        and equals N for N layouts."""
        theme = _make_valid_theme(tmp_path / "slidev-theme-test")
        n = 7
        for i in range(1, n + 1):
            _add_layout(theme, f"slide{i}", ["title", "body-1"])
        deck = tmp_path / "my-deck"
        result = scaffold_deck(deck, theme, "my-deck", install=False)
        slides = (deck / "slides.md").read_text()

        # ScaffoldResult reports the right number.
        assert result.slide_count == n
        # And the actual file has the right number of `layout: slideN` lines —
        # one per slide, none missing, none duplicated.
        layout_lines = [
            line for line in slides.splitlines()
            if line.startswith("layout: slide")
        ]
        assert len(layout_lines) == n

        # And there are no orphan `---` separators between slides — every
        # `---` is part of a frontmatter block. The total `---` count
        # should be exactly 2 * n (open + close for each slide's
        # frontmatter; the first close doubles as the body separator).
        dash_lines = [line for line in slides.splitlines() if line == "---"]
        assert len(dash_lines) == 2 * n

    def test_natural_sort_orders_slide2_before_slide10(self, tmp_path):
        theme = _make_valid_theme(tmp_path / "slidev-theme-test")
        for i in [1, 2, 10, 11]:
            _add_layout(theme, f"slide{i}", ["title"])
        deck = tmp_path / "my-deck"
        scaffold_deck(deck, theme, "my-deck", install=False)
        slides = (deck / "slides.md").read_text()
        # Indices in document order.
        i1 = slides.index("layout: slide1\n")
        i2 = slides.index("layout: slide2\n")
        i10 = slides.index("layout: slide10\n")
        i11 = slides.index("layout: slide11\n")
        assert i1 < i2 < i10 < i11


# ---------------------------------------------------------------------------
# Layout enumeration helpers
# ---------------------------------------------------------------------------

class TestEnumerateLayouts:
    def test_returns_empty_for_theme_without_layouts_dir(self, tmp_path):
        theme = _make_valid_theme(tmp_path / "slidev-theme-test")
        assert _enumerate_layouts(theme) == []

    def test_returns_layout_names_without_extension(self, tmp_path):
        theme = _make_valid_theme(tmp_path / "slidev-theme-test")
        _add_layout(theme, "cover", ["title"])
        _add_layout(theme, "section", ["title"])
        names = _enumerate_layouts(theme)
        assert set(names) == {"cover", "section"}

    def test_natural_sort_key_orders_numerically(self):
        keys = sorted(["slide10", "slide2", "slide1", "slide11"], key=_natural_sort_key)
        assert keys == ["slide1", "slide2", "slide10", "slide11"]


class TestExtractSlotNames:
    def test_returns_slot_names_in_document_order(self, tmp_path):
        layout = tmp_path / "slide1.vue"
        layout.write_text(
            '<template>\n'
            '  <slot name="title" />\n'
            '  <slot name="body-12" />\n'
            '  <slot name="picture-22" />\n'
            '</template>\n',
            encoding="utf-8",
        )
        assert _extract_slot_names(layout) == ["title", "body-12", "picture-22"]

    def test_returns_empty_for_layout_with_no_slots(self, tmp_path):
        layout = tmp_path / "slide1.vue"
        layout.write_text('<template>\n  <div>no slots</div>\n</template>\n', encoding="utf-8")
        assert _extract_slot_names(layout) == []

    def test_returns_empty_for_nonexistent_file(self, tmp_path):
        assert _extract_slot_names(tmp_path / "does-not-exist.vue") == []
