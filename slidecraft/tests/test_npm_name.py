"""Tests for slidecraft.npm_name.validate_npm_package_name.

Rules come from npm's `validate-npm-package-name` library and Slidev's
runtime check (`isValidPackageName`). The user-facing pain we're guarding
against: Slidev rejects an invalid theme name at deck startup with a
cryptic stack trace buried in node_modules.
"""
from __future__ import annotations

import pytest

from slidecraft.npm_name import validate_npm_package_name


class TestValidNames:
    """Each of these must pass without raising."""

    @pytest.mark.parametrize("name", [
        "slidev-theme-ilse",
        "slidev-theme-iu",
        "my-deck",
        "deck",
        "a",
        "deck-1",
        "deck_1",
        "deck.config",
        "2026-05-26_ilse",
        "@scope/slidev-theme-ilse",
        "@my-org/my-package",
        "x" * 214,                     # exactly at the length ceiling
    ])
    def test_accepts(self, name):
        validate_npm_package_name(name)


class TestUppercaseRejection:
    """The bug that motivated this validator: uppercase theme names."""

    def test_rejects_uppercase_with_hint(self):
        with pytest.raises(ValueError, match="uppercase"):
            validate_npm_package_name("slidev-theme-ILSE")

    def test_error_suggests_lowercase_form(self):
        with pytest.raises(ValueError, match="slidev-theme-ilse"):
            validate_npm_package_name("slidev-theme-ILSE")

    def test_role_appears_in_message(self):
        with pytest.raises(ValueError, match="theme name"):
            validate_npm_package_name("BadName", role="theme")
        with pytest.raises(ValueError, match="deck name"):
            validate_npm_package_name("BadName", role="deck")


class TestOtherInvalidNames:
    @pytest.mark.parametrize("name,reason", [
        ("",                       "empty"),
        (".starts-with-dot",       "leading dot"),
        ("_starts-with-underscore","leading underscore"),
        ("has spaces",             "whitespace"),
        ("has!bang",               "punctuation"),
        ("has/slash",              "slash without scope"),
        ("x" * 215,                "too long"),
    ])
    def test_rejects(self, name, reason):
        with pytest.raises(ValueError):
            validate_npm_package_name(name)

    def test_rejects_non_string(self):
        with pytest.raises(ValueError, match="non-empty string"):
            validate_npm_package_name(None)  # type: ignore[arg-type]
