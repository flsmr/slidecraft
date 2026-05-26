"""npm package-name validation.

npm enforces strict rules on package names — Slidev calls
``isValidPackageName`` at startup and rejects the entire deck if the
theme's name is invalid. Catching this in our entry points lets us
fail fast with a clear actionable error instead of producing a deck
that mysteriously errors when the user finally runs ``npx slidev``.

Source of the rules (npm CLI, ``validate-npm-package-name``):
- Total length 1–214 characters
- Lowercase only (a–z)
- Digits (0–9), hyphen, underscore, dot allowed in the body
- Cannot start with ``.`` or ``_``
- Optional ``@scope/`` prefix (lowercase) before the package name
"""
from __future__ import annotations

import re


_NPM_NAME_RE = re.compile(
    r"^"
    r"(?:@[a-z0-9][a-z0-9\-_\.]*\/)?"      # optional @scope/
    r"[a-z0-9]"                            # first body char: letter or digit
    r"[a-z0-9\-_\.]*"                      # rest of the body
    r"$"
)


def validate_npm_package_name(name: str, *, role: str = "package") -> None:
    """Raise ValueError with a clear message if ``name`` is not a valid
    npm package name. ``role`` is interpolated into the message (e.g.
    "theme", "deck") so the user knows what to fix.
    """
    if not isinstance(name, str) or not name:
        raise ValueError(
            f"{role} name must be a non-empty string (got {name!r})"
        )
    if len(name) > 214:
        raise ValueError(
            f"{role} name {name!r} is too long (npm allows up to 214 chars)"
        )
    if name != name.lower():
        raise ValueError(
            f"{role} name {name!r} contains uppercase characters — "
            f"npm package names must be lowercase. "
            f"Use {name.lower()!r} instead."
        )
    if not _NPM_NAME_RE.match(name):
        raise ValueError(
            f"{role} name {name!r} is not a valid npm package name "
            f"(allowed: lowercase letters, digits, hyphens, underscores, "
            f"dots; optional @scope/ prefix; must start with a letter or "
            f"digit; max 214 chars)"
        )
