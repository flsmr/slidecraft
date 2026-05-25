"""Tests for slidecraft.scaffold.new_deck — pure scaffolding mechanics."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from slidecraft.scaffold.new_deck import (
    ScaffoldResult,
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
        theme = _make_valid_theme(tmp_path / "slidev-theme-test", name="slidev-theme-ACME")
        deck = tmp_path / "my-deck"
        scaffold_deck(deck, theme, "my-deck", install=False)

        slides = (deck / "slides.md").read_text()
        assert "theme: slidev-theme-ACME" in slides
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
