"""Tests for emit/naming.py — slot-name derivation."""
from __future__ import annotations

import pytest

from slidecraft.importer.emit.naming import (
    slot_name_for_picture,
    slot_name_for_placeholder,
)
from slidecraft.importer.model import Picture, Placeholder


def _make_ph(idx: int, type_: str | None) -> Placeholder:
    return Placeholder(
        idx=idx,
        type=type_,
        x_px=0.0, y_px=0.0, width_px=100.0, height_px=100.0,
    )


def _make_pic_ph(ph_idx: int) -> Picture:
    return Picture(
        asset_ref="x.png",
        x_px=0.0, y_px=0.0, width_px=100.0, height_px=100.0,
        is_placeholder=True,
        ph_idx=ph_idx,
        shape_id=1,
    )


class TestSingletonsHaveNoSuffix:
    """Singleton types (≤1 per layout) emit bare prefix — matches Slidev's
    `title` convention from the official theme-authoring docs."""

    @pytest.mark.parametrize("ooxml_type,expected", [
        ("title",    "title"),
        ("ctrTitle", "title"),       # ctrTitle collapses to title (mutually exclusive)
        ("subTitle", "subtitle"),
        ("dt",       "date"),
        ("ftr",      "footer"),
        ("sldNum",   "slide-number"),
    ])
    def test_singleton_emits_bare_prefix(self, ooxml_type, expected):
        ph = _make_ph(idx=99, type_=ooxml_type)
        assert slot_name_for_placeholder(ph) == expected


class TestRepeatableTypesHaveIdxSuffix:
    """Repeatable types include the OOXML idx as suffix so names stay stable
    across re-imports even when designers reorder placeholders inside PPT."""

    def test_body_uses_idx_suffix(self):
        ph = _make_ph(idx=19, type_="body")
        assert slot_name_for_placeholder(ph) == "body-19"

    def test_obj_maps_to_content_prefix(self):
        ph = _make_ph(idx=1, type_="obj")
        assert slot_name_for_placeholder(ph) == "content-1"

    def test_body_different_idx_yields_distinct_name(self):
        assert (
            slot_name_for_placeholder(_make_ph(idx=10, type_="body"))
            != slot_name_for_placeholder(_make_ph(idx=11, type_="body"))
        )


class TestUnknownTypeFallback:
    """Types not in the prefix table (None, or future/exotic OOXML types) get
    a deterministic ph-{idx} fallback so the emit pipeline never crashes."""

    def test_none_type_falls_back(self):
        ph = _make_ph(idx=42, type_=None)
        assert slot_name_for_placeholder(ph) == "ph-42"

    def test_unknown_type_falls_back(self):
        ph = _make_ph(idx=7, type_="exoticFutureType")
        assert slot_name_for_placeholder(ph) == "ph-7"


class TestPictureSlot:
    def test_picture_placeholder_uses_picture_prefix(self):
        pic = _make_pic_ph(ph_idx=22)
        assert slot_name_for_picture(pic) == "picture-22"

    def test_free_picture_raises(self):
        """Free <p:pic> shapes (is_placeholder=False) have no slot — calling
        slot_name_for_picture on one is a programmer error."""
        pic = Picture(
            asset_ref="bg.png",
            x_px=0.0, y_px=0.0, width_px=100.0, height_px=100.0,
            is_placeholder=False,
            shape_id=88,
        )
        with pytest.raises(AssertionError):
            slot_name_for_picture(pic)
