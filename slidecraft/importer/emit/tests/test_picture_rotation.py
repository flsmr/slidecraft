"""Regression: Picture must honor its rotation_deg in the emitted CSS.

Before the fix, all three picture parsers in slidecraft.importer.parse
discarded the rot value from _get_sp_position as ``_rot``, so a layout-
inherited rotation (e.g. the IU template's slideLayout4 sets
``rot="-240000"`` ≈ -4° on its big image-placeholder idx=24) was
silently dropped on every slide that inherited that placeholder.
"""
from __future__ import annotations

from pathlib import Path

from slidecraft.importer.model import (
    Picture, Placeholder, Presentation, Slide,
)
from slidecraft.importer.emit.layout import emit_layouts


def _make_pic(*, rotation_deg: float, transforms: list[str] | None = None) -> Picture:
    return Picture(
        asset_ref="img.png",
        x_px=10.0, y_px=20.0, width_px=100.0, height_px=50.0,
        rotation_deg=rotation_deg,
        order_index=1,
        effects={
            "css_filter": "", "transforms": transforms or [],
            "opacity": None, "box_reflect": None, "mask_image": None,
            "derivatives_needed": [], "warnings": [],
        },
    )


def _emit_first_slide(tmp_path: Path, pic: Picture) -> str:
    pres = Presentation(
        slides=[Slide(index=1, placeholders=[], pictures=[pic])],
        canvas_width_px=1920, canvas_height_px=1080,
        typefaces_referenced=set(),
    )
    emit_layouts(pres, tmp_path / "theme")
    return (tmp_path / "theme" / "layouts" / "slide1.vue").read_text()


class TestPictureRotation:
    def test_zero_rotation_emits_no_transform(self, tmp_path):
        out = _emit_first_slide(tmp_path, _make_pic(rotation_deg=0.0))
        # No transform: declaration (since no transforms and no rotation).
        assert "transform:" not in out

    def test_nonzero_rotation_emits_rotate_in_transform(self, tmp_path):
        """A picture with rotation_deg=-4 must emit
        ``transform:rotate(-4deg)`` on its wrapper."""
        out = _emit_first_slide(tmp_path, _make_pic(rotation_deg=-4.0))
        assert "transform:rotate(-4deg)" in out

    def test_rotation_composes_with_existing_transforms(self, tmp_path):
        """When effects already provide transforms (e.g. ``scaleX(-1)`` for
        flip), the xfrm rotation joins the same ``transform:`` declaration —
        rotation FIRST (rotation is the geometric transform; effects are
        the visual overlay)."""
        out = _emit_first_slide(
            tmp_path,
            _make_pic(rotation_deg=15.5, transforms=["scaleX(-1)"]),
        )
        assert "transform:rotate(15.5deg) scaleX(-1)" in out
