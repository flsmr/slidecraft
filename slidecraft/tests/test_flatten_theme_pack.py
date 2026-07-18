"""Tests for slidecraft.scripts.flatten_theme_pack (ticket 10, T5 optional).

A safe, copy-based flatten of an old theme *pack* into a standalone theme:
locate the inner ``slidev-theme-<slug>/``, copy it to a destination, carry a
pack-root ``styleguide.md`` in if the theme lacks one, and never touch the
originals (no deletion). Dry-run by default.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from slidecraft.scripts import flatten_theme_pack as ftp


def _make_pack(root: Path, *, root_styleguide: bool = True,
               inner_styleguide: bool = False) -> Path:
    inner = root / "slidev-theme-general"
    (inner / "layouts").mkdir(parents=True)
    (inner / "layouts" / "title.vue").write_text("<template/>", encoding="utf-8")
    (inner / "package.json").write_text('{"name":"slidev-theme-general"}', "utf-8")
    (inner / "semantic-layouts.json").write_text("{}", encoding="utf-8")
    if inner_styleguide:
        (inner / "styleguide.md").write_text("# inner\n", encoding="utf-8")
    # dead pack cruft
    (root / "skeletons" / "briefing").mkdir(parents=True)
    (root / "skeletons" / "briefing" / "skeleton.json").write_text("{}", "utf-8")
    (root / "pack.json").write_text("{}", encoding="utf-8")
    if root_styleguide:
        (root / "styleguide.md").write_text("# pack style\n", encoding="utf-8")
    return root


def test_find_inner_theme(tmp_path):
    pack = _make_pack(tmp_path / "pack")
    inner = ftp.find_inner_theme(pack)
    assert inner.name == "slidev-theme-general"


def test_find_inner_theme_errors_when_missing(tmp_path):
    (tmp_path / "empty").mkdir()
    with pytest.raises(SystemExit):
        ftp.find_inner_theme(tmp_path / "empty")


def test_find_inner_theme_errors_when_ambiguous(tmp_path):
    root = tmp_path / "pack"
    (root / "slidev-theme-a").mkdir(parents=True)
    (root / "slidev-theme-b").mkdir()
    with pytest.raises(SystemExit):
        ftp.find_inner_theme(root)


def test_dry_run_copies_nothing(tmp_path):
    pack = _make_pack(tmp_path / "pack")
    dest = tmp_path / "out"
    plan = ftp.flatten(pack, dest, apply=False)
    assert plan["applied"] is False
    assert not dest.exists()  # dry-run touches nothing
    assert "styleguide.md" in plan["carried"]  # would carry pack-root styleguide


def test_apply_copies_inner_and_carries_styleguide(tmp_path):
    pack = _make_pack(tmp_path / "pack", root_styleguide=True, inner_styleguide=False)
    dest = tmp_path / "slidev-theme-general"
    plan = ftp.flatten(pack, dest, apply=True)

    assert plan["applied"] is True
    assert (dest / "package.json").is_file()
    assert (dest / "layouts" / "title.vue").is_file()
    assert (dest / "semantic-layouts.json").is_file()
    # pack-root styleguide carried into the flattened theme
    assert (dest / "styleguide.md").read_text(encoding="utf-8") == "# pack style\n"
    # dead cruft NOT copied
    assert not (dest / "skeletons").exists()
    assert not (dest / "pack.json").exists()
    # originals untouched (never deletes)
    assert (pack / "skeletons").is_dir()
    assert (pack / "pack.json").is_file()
    assert (pack / "slidev-theme-general").is_dir()


def test_apply_keeps_inner_styleguide_over_pack_root(tmp_path):
    pack = _make_pack(tmp_path / "pack", root_styleguide=True, inner_styleguide=True)
    dest = tmp_path / "out"
    ftp.flatten(pack, dest, apply=True)
    # inner theme already had its own styleguide → keep it, don't overwrite
    assert (dest / "styleguide.md").read_text(encoding="utf-8") == "# inner\n"


def test_apply_refuses_nonempty_dest(tmp_path):
    pack = _make_pack(tmp_path / "pack")
    dest = tmp_path / "out"
    dest.mkdir()
    (dest / "keep.txt").write_text("x", encoding="utf-8")
    with pytest.raises(SystemExit):
        ftp.flatten(pack, dest, apply=True)
