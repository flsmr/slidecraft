"""Render citations from ``references.bib`` via citeproc-py + CSL styles.

The slide-author agent should stop hand-templating APA strings into slide
files. Templating by hand drifts — a missing ``&``, an inconsistent comma
before the year, ``pp.`` vs ``p.`` — and the drift only surfaces when a
human re-reads the deck. Worse, switching tone (academic → business) means
rewriting every citation string.

This module replaces that with deterministic rendering: read the deck's
``references.bib``, pick a CSL style, render every cite key the same way
every time. Pure ``citeproc-py``; no LLM in the loop.

Two surfaces:

* :func:`format_inline` — the short citation that goes next to a claim
  on a slide (or in speaker notes). For APA-7th this is the
  ``(Szeliski, 2022, §2.1.4)`` form; for Harvard it differs by a comma.
* :func:`format_bibliography` — full reference entries, one per cite key,
  for the bibliography slide.

Styles ship bundled in ``slidecraft/references/csl/``. Users can drop a
CSL file into ``~/.slidecraft/csl/`` to override or extend the set; the
user dir is consulted first, so a local ``apa-7th.csl`` shadows the
bundled one.

Locators (``§2.1.4``, ``p. 130``, ``pp. 22-23``) are passed through
verbatim — the caller has already chosen the label and number form, and
citeproc-py's ``none`` locator label prints whatever raw string we give
it. That keeps section signs and en-dashes intact.

Missing cite keys raise ``KeyError``; missing CSL files raise
``FileNotFoundError`` with a message naming both the bundled directory
and the user-override path so the user knows where to add the style.
"""
from __future__ import annotations

import argparse
import logging
import sys
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


# ---------------------------------------------------------------------------
# Style location — bundled + user-override
# ---------------------------------------------------------------------------

#: Directory shipped with the plugin holding CSL files. Resolved relative
#: to this module so the lookup works regardless of cwd.
BUNDLED_CSL_DIR = (Path(__file__).resolve().parent.parent
                   / "references" / "csl")

#: User override directory. A CSL file with the same name here takes
#: precedence over the bundled one — same pattern Pandoc uses for user
#: data dirs. We don't create the directory, only read from it.
USER_CSL_DIR = Path.home() / ".slidecraft" / "csl"


# ---------------------------------------------------------------------------
# Public dataclass + functions
# ---------------------------------------------------------------------------


@dataclass
class CitationSpec:
    """One inline-citation request — cite key plus optional locator.

    ``locator`` is the pre-formatted string the user wants printed
    (``"§2.1.4"``, ``"p. 130"``, ``"pp. 22-23"``). We pass it through to
    citeproc-py's ``none`` locator label, which prints the raw string
    without prepending ``Sections`` / ``Pages`` / etc. Callers thus pick
    the symbol form once and we honor it deterministically.

    ``locator`` is None (or empty) when no locator should be printed — the
    citation then renders as just ``(Author, Year)``.
    """

    key: str
    locator: str | None = None


def style_path(style: str) -> Path:
    """Resolve a style name to an absolute CSL file path.

    Lookup order:
      1. ``~/.slidecraft/csl/<style>.csl`` — user override.
      2. ``<plugin>/references/csl/<style>.csl`` — bundled styles.

    The user-override location is consulted first so a local file shadows
    the bundled one without requiring a code change.

    Raises:
        FileNotFoundError: if no CSL file is found under either location.
            The message names both paths so the user can act on it.
    """
    user = USER_CSL_DIR / f"{style}.csl"
    if user.is_file():
        return user
    bundled = BUNDLED_CSL_DIR / f"{style}.csl"
    if bundled.is_file():
        return bundled
    raise FileNotFoundError(
        f"CSL style '{style}' not found. Looked in:\n"
        f"  user override: {user}\n"
        f"  bundled:       {bundled}\n"
        f"Drop a <style>.csl file into the user-override directory to "
        f"add a style without modifying the plugin."
    )


def list_bundled_styles() -> list[str]:
    """Return the names (stems) of all CSL files bundled with the plugin."""
    if not BUNDLED_CSL_DIR.is_dir():
        return []
    return sorted(p.stem for p in BUNDLED_CSL_DIR.glob("*.csl"))


def list_user_styles() -> list[str]:
    """Return the names (stems) of all CSL files under the user override."""
    if not USER_CSL_DIR.is_dir():
        return []
    return sorted(p.stem for p in USER_CSL_DIR.glob("*.csl"))


def format_inline(bib_path: Path,
                  specs: list[CitationSpec],
                  style: str = "apa-7th",
                  narrative: bool = False,
                  ) -> str:
    """Render inline citations for the given specs.

    Each spec is rendered as one citeproc-py citation; the resulting
    strings are joined with ``"; "``. Order is preserved — the caller's
    spec order is the output order, no re-sorting.

    Args:
        bib_path:  Path to the deck's ``references.bib``.
        specs:     The cite keys (with optional locators) to render.
        style:     CSL style name (no extension), resolved via
            :func:`style_path`. Defaults to ``"apa-7th"``.
        narrative: When True, post-process citeproc-py's parenthetical
            output ``"(Author, Year, locator)"`` into the narrative form
            ``"Author (Year, locator)"`` — common on academic slides where
            the author name reads as part of the sentence. Default False
            (pure CSL output). Only safe for APA-style outputs whose
            structure is `(Author, Year[, locator])`; for styles with
            different shapes the post-processor falls back to the raw
            citeproc output unchanged.

    Returns:
        The joined citation string. Empty string when ``specs`` is empty.

    Raises:
        KeyError: a spec's key is missing from the bib.
        FileNotFoundError: the bib or the CSL style file is missing.
    """
    if not specs:
        return ""
    biblio, source = _load_bibliography(bib_path, style)
    _check_keys_present(source, bib_path, [s.key for s in specs])

    parts: list[str] = []
    for spec in specs:
        citation = _make_citation(spec)
        biblio.register(citation)
        # Render with a no-op warn callback — we already validated keys
        # are present, so anything citeproc-py warns about here is its
        # own internal noise (and we suppress its stderr separately).
        rendered = str(biblio.cite(citation, lambda _item: None))
        if narrative:
            rendered = _to_narrative(rendered)
        parts.append(rendered)
    return "; ".join(parts)


# ---------------------------------------------------------------------------
# Narrative-form post-processor
# ---------------------------------------------------------------------------

# Matches the parenthetical APA-style citation citeproc-py produces:
#   "(Author Name, 2022, §2.1.4)"  → groups: author, year, locator
#   "(Author Name, 2022)"          → groups: author, year, None
#   "(Author A. & Author B., 2003)"
# Author may contain spaces, dots, ampersands, apostrophes, hyphens.
# Year is 4 digits, optionally with a letter suffix (2022a) per APA.
import re as _re   # local alias to avoid shadowing module-level imports

# Match the author + year prefix of a parenthetical APA citation. The
# locator (which may contain its own parens, e.g. "eq. (1.1)") is
# extracted by balanced-paren parsing after the regex match — regex
# alone can't reliably handle nested parens.
_NARRATIVE_PREFIX_RE = _re.compile(
    r"\(([^,()]+(?:\s+&\s+[^,()]+)?),\s*(\d{4}[a-z]?)(?:,\s*)?"
)


def _to_narrative(parenthetical: str) -> str:
    """Convert one parenthetical citation to narrative form.

    ``"(Hartley & Zisserman, 2003, §6)"`` → ``"Hartley & Zisserman (2003, §6)"``.
    ``"(Author, 2024, eq. (1.1)–(1.2))"`` → ``"Author (2024, eq. (1.1)–(1.2))"``.

    Returns the input unchanged when the parenthetical pattern doesn't
    match — keeps the function safe across styles whose shape differs.
    """
    s = parenthetical.strip()
    if not (s.startswith("(") and s.endswith(")")):
        return parenthetical
    # Verify outer parens are balanced (depth 0 only at the very end);
    # otherwise this isn't a standard parenthetical citation.
    depth = 0
    for i, c in enumerate(s):
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0 and i != len(s) - 1:
                # Outer paren closed before end of string — input has
                # something after the citation; don't try to reformat.
                return parenthetical
    m = _NARRATIVE_PREFIX_RE.match(s)
    if not m:
        return parenthetical
    author, year = m.group(1), m.group(2)
    # The locator is everything between the end of the regex match and
    # the final ')'. May itself contain nested parens.
    locator = s[m.end():-1].strip()
    if locator:
        return f"{author} ({year}, {locator})"
    return f"{author} ({year})"


def format_bibliography(bib_path: Path,
                        keys: list[str] | None = None,
                        style: str = "apa-7th",
                        ) -> list[str]:
    """Render full bibliography entries, one string per cite key.

    Args:
        bib_path: Path to the deck's ``references.bib``.
        keys:     Cite keys to include, in the order they should appear.
            When ``None``, every entry in the bib is rendered, in the
            bib's own iteration order (insertion order for ``citeproc-py``).
        style:    CSL style name (no extension).

    Returns:
        One formatted reference string per requested key. The caller
        decides layout — typically one bullet per entry on a bibliography
        slide.

    Raises:
        KeyError: a requested key is missing from the bib.
        FileNotFoundError: the bib or CSL style file is missing.
    """
    biblio, source = _load_bibliography(bib_path, style)
    target_keys: list[str] = list(keys) if keys is not None else list(source.keys())
    _check_keys_present(source, bib_path, target_keys)

    # Every entry that should appear in the output bibliography must be
    # registered as a citation first — citeproc-py's bibliography() only
    # iterates over registered cites.
    for key in target_keys:
        biblio.register(Citation([CitationItem(key)]))
    rendered_all = [str(entry) for entry in biblio.bibliography()]

    # ``rendered_all`` is keyed off the underlying registry, which matches
    # registration order *de-duplicated*. When ``keys`` repeats a key, we
    # still want one entry per requested key — map by the key list.
    if not target_keys:
        return []
    # bibliography() returns one entry per unique registered key, in
    # registration order. Build the position map ourselves to be robust
    # against future citeproc-py changes that might reorder entries.
    seen: dict[str, int] = {}
    for idx, key in enumerate(target_keys):
        seen.setdefault(key, idx)
    # If citeproc returned exactly len(unique target_keys) entries, the
    # mapping is positional; otherwise fall back to whatever we have.
    unique_keys = list(seen.keys())
    if len(rendered_all) == len(unique_keys):
        per_key = dict(zip(unique_keys, rendered_all))
        return [per_key[k] for k in target_keys]
    return rendered_all


# ---------------------------------------------------------------------------
# Internals — lazy citeproc-py import + warning suppression
# ---------------------------------------------------------------------------


# citeproc-py is a heavy import (lxml etc.); keep it lazy so the module
# imports cleanly when the user only wants ``list_bundled_styles()`` for
# the CLI's ``list-styles`` subcommand.
_CITEPROC = None


def _citeproc():
    """Lazily import citeproc-py and stash the relevant symbols.

    Returns a small object exposing ``CitationStylesStyle``,
    ``CitationStylesBibliography``, ``Citation``, ``CitationItem``,
    ``Locator``, ``formatter``, and ``BibTeX``. Raises ``ImportError``
    with an install hint if the package is missing.
    """
    global _CITEPROC
    if _CITEPROC is not None:
        return _CITEPROC
    try:
        from citeproc import (CitationStylesStyle, CitationStylesBibliography,
                              Citation, CitationItem, Locator, formatter)
        from citeproc.source.bibtex import BibTeX
    except ImportError as exc:
        raise ImportError(
            "citeproc-py is required for citation rendering. "
            "Install with: pip install 'citeproc-py>=0.7'"
        ) from exc

    class _Ns:
        pass
    ns = _Ns()
    ns.CitationStylesStyle = CitationStylesStyle
    ns.CitationStylesBibliography = CitationStylesBibliography
    ns.Citation = Citation
    ns.CitationItem = CitationItem
    ns.Locator = Locator
    ns.formatter = formatter
    ns.BibTeX = BibTeX
    _CITEPROC = ns
    return ns


# Re-exported lazy names so the public functions read cleanly.
def _Citation(*args, **kwargs):
    return _citeproc().Citation(*args, **kwargs)


def _CitationItem(*args, **kwargs):
    return _citeproc().CitationItem(*args, **kwargs)


def _Locator(*args, **kwargs):
    return _citeproc().Locator(*args, **kwargs)


# Names used inside ``format_bibliography``'s tight loop — bound once via
# the lazy import path so we don't pay attribute-lookup overhead in tests.
Citation = _Citation
CitationItem = _CitationItem


def _silence_citeproc_warnings() -> None:
    """Quieten the noisy warnings citeproc-py emits on BibTeX parsing.

    citeproc-py logs a warning for every BibTeX feature it doesn't
    perfectly parse (custom macros, unrecognised fields). These are
    almost always fine for our slide-deck use case — the rendered
    entry is still correct. We suppress the noise so the script's
    stdout/stderr stays focused on the formatted citation strings.

    Idempotent — safe to call repeatedly.
    """
    warnings.filterwarnings("ignore", module=r"citeproc(\..*)?")
    # citeproc-py also routes some messages through the ``citeproc``
    # logger at WARNING level — silence those too.
    logging.getLogger("citeproc").setLevel(logging.ERROR)


def _load_bibliography(bib_path: Path, style: str):
    """Build a citeproc-py bibliography object from *bib_path* + *style*.

    Returns ``(bibliography, source)`` where ``source`` is the BibTeX
    source so callers can interrogate available keys.

    Raises:
        FileNotFoundError: the bib or the CSL style is missing.
    """
    if not bib_path.is_file():
        raise FileNotFoundError(f"bib file not found: {bib_path}")
    _silence_citeproc_warnings()
    cp = _citeproc()
    csl_file = style_path(style)
    # ``validate=False`` — the official CSL files have always validated
    # cleanly, but disabling validation skips a slow XSD load. We pay
    # the cost only when the user genuinely points at a broken style.
    style_obj = cp.CitationStylesStyle(str(csl_file), validate=False)
    # Explicit UTF-8 encoding — citeproc-py defaults to ASCII for BibTeX
    # files, which fails on any entry with non-ASCII characters (German
    # umlauts, en-dashes, etc.). Real-world references.bib files are
    # almost always UTF-8.
    #
    # citeproc-py's BibTeX parser only knows the classic entry types and
    # raises KeyError('online') on biblatex types — and ONE unknown type
    # aborts the whole parse (every key then reports as missing, which is
    # maddening to debug; found retrofitting SPRINT_3). Extend its type
    # map with the biblatex web types our bibtex-guide.md recommends.
    from citeproc.source.bibtex.bibtex import BibTeX as _BibTeXClass
    for _btype, _csl in (("online", "webpage"), ("electronic", "webpage"),
                         ("www", "webpage")):
        _BibTeXClass.types.setdefault(_btype, _csl)
    source = cp.BibTeX(str(bib_path), encoding="utf-8")
    biblio = cp.CitationStylesBibliography(style_obj, source,
                                            cp.formatter.plain)
    return biblio, source


def _check_keys_present(source, bib_path: Path, keys: Sequence[str]) -> None:
    """Raise ``KeyError`` for the first missing key (informative message)."""
    available = set(source.keys())
    for key in keys:
        if key not in available:
            raise KeyError(f"cite key '{key}' not in {bib_path}")


def _make_citation(spec: CitationSpec):
    """Build a citeproc-py ``Citation`` from a :class:`CitationSpec`.

    Uses the ``none`` locator label so the locator string we pass is
    printed verbatim — preserving user-chosen prefixes (``§``, ``p.``,
    ``pp.``, ``ll.``) and special characters (en/em dashes).
    """
    cp = _citeproc()
    if spec.locator:
        item = cp.CitationItem(spec.key,
                               locator=cp.Locator("none", spec.locator))
    else:
        item = cp.CitationItem(spec.key)
    return cp.Citation([item])


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_key_locator(token: str) -> CitationSpec:
    """Parse a ``--keys`` CLI token: ``key`` or ``key:locator``.

    The locator is everything after the first colon — colons inside the
    locator itself (``§2:3``, unlikely but legal) are preserved.
    """
    if ":" in token:
        key, _, loc = token.partition(":")
        key = key.strip()
        loc = loc.strip()
        return CitationSpec(key=key, locator=loc or None)
    return CitationSpec(key=token.strip())


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m slidecraft.scripts.format_citations",
        description=("Render citations from a BibTeX file using a CSL "
                     "style. Deterministic — no LLM in the loop."),
    )
    sub = p.add_subparsers(dest="command", required=True)

    # ---- inline ------------------------------------------------------------
    p_inline = sub.add_parser(
        "inline",
        help="Render one or more inline citations, joined with '; '.",
    )
    p_inline.add_argument("--bib", required=True, type=Path,
                          help="Path to references.bib.")
    p_inline.add_argument("--style", default="apa-7th",
                          help="CSL style name (no extension). Default: apa-7th.")
    p_inline.add_argument("--keys", nargs="+", required=True,
                          help="Cite keys, each optionally suffixed with "
                               "':<locator>'. e.g. 'szeliski2022:§2.1.4' "
                               "'hartley2003:p. 130'. Bare 'key' (no colon) "
                               "is allowed for no-locator citations.")
    p_inline.add_argument("--narrative", action="store_true",
                          help="Post-process to narrative form 'Author "
                               "(Year, locator)' instead of citeproc-py's "
                               "default parenthetical '(Author, Year, "
                               "locator)'. Safe for APA-style outputs.")

    # ---- bibliography ------------------------------------------------------
    p_bib = sub.add_parser(
        "bibliography",
        help="Render full bibliography entries — one per cite key.",
    )
    p_bib.add_argument("--bib", required=True, type=Path,
                       help="Path to references.bib.")
    p_bib.add_argument("--style", default="apa-7th",
                       help="CSL style name (no extension). Default: apa-7th.")
    p_bib.add_argument("--keys", nargs="*", default=None,
                       help="Specific cite keys to render. Omit to render "
                            "every entry in the bib.")

    # ---- list-styles -------------------------------------------------------
    sub.add_parser(
        "list-styles",
        help="List available CSL styles (bundled + user overrides).",
    )

    return p


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point — returns the process exit code."""
    args = _build_arg_parser().parse_args(argv)

    try:
        if args.command == "inline":
            specs = [_parse_key_locator(t) for t in args.keys]
            out = format_inline(args.bib, specs, style=args.style,
                                narrative=args.narrative)
            print(out)
            return 0

        if args.command == "bibliography":
            entries = format_bibliography(args.bib, keys=args.keys,
                                          style=args.style)
            for entry in entries:
                print(entry)
            return 0

        if args.command == "list-styles":
            bundled = list_bundled_styles()
            user = list_user_styles()
            print("bundled:")
            for name in bundled:
                print(f"  {name}")
            if user:
                print("user (~/.slidecraft/csl):")
                for name in user:
                    print(f"  {name}")
            return 0
    except (FileNotFoundError, KeyError) as exc:
        # KeyError stringifies with surrounding quotes; strip them so the
        # CLI message reads naturally.
        msg = str(exc)
        if isinstance(exc, KeyError):
            msg = msg.strip("'\"")
        print(f"error: {msg}", file=sys.stderr)
        return 1
    except ImportError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    # argparse already errors on unknown subcommands; we never reach here.
    return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
