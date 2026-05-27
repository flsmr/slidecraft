"""Tests for slidecraft.scripts.format_citations.

The strategy: every test synthesises a small ``references.bib`` in
``tmp_path`` covering the BibTeX entry types we care about (book,
article, inproceedings, phdthesis) and exercises one behaviour against
it. We rely on the bundled CSL files; we don't validate citeproc-py's
exact output character-for-character (that's citeproc-py's job) — we
assert on the load-bearing substrings (the surname, the year, the
locator, the style-distinguishing word like ``and`` vs ``&``).

That asymmetry is deliberate: citeproc-py's exact format is allowed to
drift across versions (e.g. extra spaces, slightly different
punctuation). What must not drift is "the citation contains the
surname, year, and the locator we passed in."
"""
from __future__ import annotations

from pathlib import Path

import pytest

from slidecraft.scripts.format_citations import (
    BUNDLED_CSL_DIR,
    USER_CSL_DIR,
    CitationSpec,
    format_bibliography,
    format_inline,
    list_bundled_styles,
    main,
    style_path,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


SAMPLE_BIB = r"""
@book{szeliski2022,
  author    = {Szeliski, Richard},
  title     = {Computer Vision: Algorithms and Applications},
  year      = {2022},
  publisher = {Springer},
  edition   = {2}
}

@book{hartley2003,
  author    = {Hartley, Richard and Zisserman, Andrew},
  title     = {Multiple View Geometry in Computer Vision},
  year      = {2003},
  publisher = {Cambridge University Press}
}

@article{zhang2000,
  author  = {Zhang, Zhengyou},
  title   = {A Flexible New Technique for Camera Calibration},
  journal = {IEEE Transactions on Pattern Analysis and Machine Intelligence},
  year    = {2000},
  volume  = {22},
  number  = {11},
  pages   = {1330-1334}
}

@inproceedings{lowe1999,
  author    = {Lowe, David G.},
  title     = {Object Recognition from Local Scale-Invariant Features},
  booktitle = {Proceedings of the International Conference on Computer Vision},
  year      = {1999},
  pages     = {1150-1157}
}

@phdthesis{smith2010,
  author = {Smith, Jane},
  title  = {Investigations into Camera Calibration Robustness},
  year   = {2010},
  school = {Stanford University}
}
""".strip()


@pytest.fixture()
def bib(tmp_path: Path) -> Path:
    """Write the sample bib into tmp_path and return its path."""
    p = tmp_path / "references.bib"
    p.write_text(SAMPLE_BIB, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# 1. Format one inline citation with locator → APA expected substring
# ---------------------------------------------------------------------------


def test_inline_single_with_locator_apa(bib: Path) -> None:
    """APA-7th: the rendered citation contains surname, year, and locator."""
    out = format_inline(bib, [CitationSpec("szeliski2022", "§2.1.4")],
                       style="apa-7th")
    assert "Szeliski" in out
    assert "2022" in out
    # Section sign must survive the round-trip — locator-label ``none``
    # passes the locator string through verbatim.
    assert "§2.1.4" in out


# ---------------------------------------------------------------------------
# 2. Format multiple inline citations → joined with '; '
# ---------------------------------------------------------------------------


def test_inline_multiple_joined_with_semicolon(bib: Path) -> None:
    """Multiple specs are joined with ``'; '`` in order."""
    out = format_inline(bib, [
        CitationSpec("szeliski2022", "§2.1.4"),
        CitationSpec("hartley2003", "p. 130"),
    ], style="apa-7th")
    # Two citations, one separator.
    assert out.count("; ") == 1
    # Order is preserved — Szeliski before Hartley.
    assert out.index("Szeliski") < out.index("Hartley")


# ---------------------------------------------------------------------------
# 3. Inline citation without locator → no locator clause appears
# ---------------------------------------------------------------------------


def test_inline_no_locator_omits_locator_clause(bib: Path) -> None:
    """A spec with locator=None renders the bare ``(Author, Year)`` form."""
    out = format_inline(bib, [CitationSpec("zhang2000")], style="apa-7th")
    assert "Zhang" in out
    assert "2000" in out
    # No locator marks should leak in.
    assert "§" not in out
    assert "p." not in out
    assert "pp." not in out


# ---------------------------------------------------------------------------
# 4. Bibliography with explicit keys (subset)
# ---------------------------------------------------------------------------


def test_bibliography_explicit_keys_subset(bib: Path) -> None:
    """Rendering with explicit keys returns one entry per key, in order."""
    entries = format_bibliography(bib, keys=["hartley2003", "szeliski2022"],
                                  style="apa-7th")
    assert len(entries) == 2
    # Order matches the request order.
    assert "Hartley" in entries[0]
    assert "Szeliski" in entries[1]


# ---------------------------------------------------------------------------
# 5. Bibliography without keys (render everything)
# ---------------------------------------------------------------------------


def test_bibliography_renders_all_when_keys_none(bib: Path) -> None:
    """``keys=None`` renders every entry in the bib (5 entries here)."""
    entries = format_bibliography(bib, style="apa-7th")
    assert len(entries) == 5
    # Spot-check: every cite key's surname appears somewhere.
    joined = " || ".join(entries)
    for surname in ("Szeliski", "Hartley", "Zhang", "Lowe", "Smith"):
        assert surname in joined


# ---------------------------------------------------------------------------
# 6. Style switch APA → Harvard produces different output
# ---------------------------------------------------------------------------


def test_style_switch_changes_output(bib: Path) -> None:
    """APA uses ``&`` between authors; Harvard uses ``and``."""
    specs = [CitationSpec("hartley2003", "p. 130")]
    apa = format_inline(bib, specs, style="apa-7th")
    harvard = format_inline(bib, specs, style="harvard")
    assert apa != harvard
    assert "&" in apa
    assert " and " in harvard


# ---------------------------------------------------------------------------
# 7. Missing cite key → KeyError with the key name in the message
# ---------------------------------------------------------------------------


def test_missing_cite_key_raises_keyerror(bib: Path) -> None:
    """KeyError surfaces the missing key and the bib path."""
    with pytest.raises(KeyError) as excinfo:
        format_inline(bib, [CitationSpec("does_not_exist")])
    msg = str(excinfo.value)
    assert "does_not_exist" in msg
    # The bib path is in the message so the user knows where to add it.
    assert "references.bib" in msg


# ---------------------------------------------------------------------------
# 8. Missing CSL → FileNotFoundError points at both lookup paths
# ---------------------------------------------------------------------------


def test_missing_style_filenotfound_names_both_paths(bib: Path) -> None:
    """Error message contains both the user-override and bundled paths."""
    with pytest.raises(FileNotFoundError) as excinfo:
        format_inline(bib, [CitationSpec("szeliski2022")],
                      style="not-a-real-style")
    msg = str(excinfo.value)
    # The user knows where to add a custom style…
    assert ".slidecraft" in msg or str(USER_CSL_DIR) in msg
    # …and where the bundled ones live.
    assert "references" in msg and "csl" in msg


# ---------------------------------------------------------------------------
# 9. CLI inline with 2 keys → exit 0, stdout matches expected substrings
# ---------------------------------------------------------------------------


def test_cli_inline_two_keys(bib: Path, capsys: pytest.CaptureFixture) -> None:
    """CLI: ``inline`` with two ``key:locator`` tokens prints joined string."""
    rc = main(["inline", "--bib", str(bib), "--style", "apa-7th",
               "--keys", "szeliski2022:§2.1.4", "hartley2003:p. 130"])
    assert rc == 0
    out = capsys.readouterr().out.strip()
    assert "Szeliski" in out and "Hartley" in out
    assert "§2.1.4" in out and "p. 130" in out
    assert "; " in out


# ---------------------------------------------------------------------------
# 10. CLI bibliography → exit 0, multi-line output
# ---------------------------------------------------------------------------


def test_cli_bibliography(bib: Path, capsys: pytest.CaptureFixture) -> None:
    """CLI: ``bibliography`` emits one line per cite key."""
    rc = main(["bibliography", "--bib", str(bib), "--style", "apa-7th"])
    assert rc == 0
    lines = [l for l in capsys.readouterr().out.splitlines() if l.strip()]
    assert len(lines) == 5


# ---------------------------------------------------------------------------
# 11. CLI list-styles → lists bundled CSL files
# ---------------------------------------------------------------------------


def test_cli_list_styles(capsys: pytest.CaptureFixture) -> None:
    """CLI: ``list-styles`` enumerates the bundled CSL stems."""
    rc = main(["list-styles"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "apa-7th" in out
    assert "harvard" in out
    # The user-override section appears only when there ARE user styles;
    # we don't assert on it here (would be flaky based on the dev's home).


# ---------------------------------------------------------------------------
# 12. User-override CSL is preferred over bundled
# ---------------------------------------------------------------------------


def test_user_override_csl_preferred(monkeypatch: pytest.MonkeyPatch,
                                     tmp_path: Path) -> None:
    """A CSL file under the user-override dir shadows the bundled one."""
    fake_home_csl = tmp_path / "user_csl"
    fake_home_csl.mkdir()
    # Copy the bundled apa-7th into the fake user dir under a known name.
    bundled = BUNDLED_CSL_DIR / "apa-7th.csl"
    user_file = fake_home_csl / "apa-7th.csl"
    user_file.write_bytes(bundled.read_bytes())

    # Point USER_CSL_DIR at our fake home for this test only.
    import slidecraft.scripts.format_citations as fc
    monkeypatch.setattr(fc, "USER_CSL_DIR", fake_home_csl)

    resolved = fc.style_path("apa-7th")
    assert resolved == user_file
    assert resolved != bundled


# ---------------------------------------------------------------------------
# 13. Locator with special characters (§, –, pp.) survives round-trip
# ---------------------------------------------------------------------------


def test_locator_special_chars_survive(bib: Path) -> None:
    """Section signs and en-dashes pass through the renderer verbatim."""
    out = format_inline(bib, [
        CitationSpec("szeliski2022", "§2.1.4"),
        CitationSpec("zhang2000", "pp. 22–23"),  # en-dash, not hyphen
    ], style="apa-7th")
    assert "§2.1.4" in out
    assert "pp. 22–23" in out


# ---------------------------------------------------------------------------
# 14. phdthesis-type entry renders correctly
# ---------------------------------------------------------------------------


def test_phdthesis_renders(bib: Path) -> None:
    """BibTeX ``@phdthesis`` is supported — surname + year + title present."""
    entries = format_bibliography(bib, keys=["smith2010"], style="apa-7th")
    assert len(entries) == 1
    e = entries[0]
    assert "Smith" in e
    assert "2010" in e
    assert "Investigations" in e


# ---------------------------------------------------------------------------
# Bonus — inproceedings + the bare CLI error path (exit 1)
# ---------------------------------------------------------------------------


def test_inproceedings_renders(bib: Path) -> None:
    """BibTeX ``@inproceedings`` is supported — Lowe SIFT entry visible."""
    entries = format_bibliography(bib, keys=["lowe1999"], style="apa-7th")
    assert len(entries) == 1
    assert "Lowe" in entries[0]
    assert "1999" in entries[0]


def test_cli_missing_key_exits_1(bib: Path,
                                  capsys: pytest.CaptureFixture) -> None:
    """CLI surfaces a missing-key as exit 1 with the key in stderr."""
    rc = main(["inline", "--bib", str(bib), "--keys", "not_a_key"])
    assert rc == 1
    err = capsys.readouterr().err
    assert "not_a_key" in err


def test_style_path_returns_bundled_when_no_user_override() -> None:
    """``style_path('apa-7th')`` resolves to the bundled file by default."""
    # Only assert this when the bundled file exists — it always should,
    # but we don't want the test to misreport a packaging problem.
    bundled = BUNDLED_CSL_DIR / "apa-7th.csl"
    assert bundled.is_file()
    # Either user override exists (skip) or resolution lands on bundled.
    if not (USER_CSL_DIR / "apa-7th.csl").is_file():
        assert style_path("apa-7th") == bundled


def test_list_bundled_styles_contains_both() -> None:
    """The bundled style list includes both apa-7th and harvard."""
    styles = list_bundled_styles()
    assert "apa-7th" in styles
    assert "harvard" in styles
