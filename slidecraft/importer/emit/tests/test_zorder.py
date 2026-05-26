"""Regression tests for unified z-order emission.

The bug we're guarding against: previously emit grouped all
placeholders BEFORE all pictures, regardless of their PPT spTree
order. Layout-inherited shapes (with positive ``order_index = 10_000+``)
ended up emitted LAST → highest z-index → on top of slide-level title
placeholders. Symptom on the IU template: slides 5-8's white "title
chip" boxes were rendered but hidden behind the layout's full-slide
image placeholder.

The fix is two-part: (1) parse uses NEGATIVE ``order_index`` for
inherited content so it sorts before slide-level; (2) emit interleaves
placeholders + pictures + slide text shapes by ``order_index`` in one
pass. These tests cover the emit side.
"""
from __future__ import annotations

from pathlib import Path

from slidecraft.importer.model import (
    NoFill, Paragraph, Picture, Placeholder, Presentation, Run, Slide,
    TextFrame,
)
from slidecraft.importer.emit.layout import emit_layouts


def _make_ph(order_index: int, idx: int) -> Placeholder:
    return Placeholder(
        idx=idx,
        type="title",
        x_px=10.0, y_px=20.0, width_px=100.0, height_px=50.0,
        text_frame=TextFrame(paragraphs=[Paragraph(runs=[Run(text=f"ph-{idx}")])]),
        order_index=order_index,
    )


def _make_pic(order_index: int, shape_id: int, is_placeholder: bool = False, ph_idx=None) -> Picture:
    return Picture(
        asset_ref="img.png",
        x_px=0.0, y_px=0.0, width_px=1280.0, height_px=720.0,
        is_placeholder=is_placeholder,
        ph_idx=ph_idx,
        shape_id=shape_id,
        order_index=order_index,
        effects={
            "css_filter": "", "transforms": [], "opacity": None,
            "box_reflect": None, "mask_image": None,
            "derivatives_needed": [], "warnings": [],
        },
    )


def _emit(tmp_path: Path, slide: Slide) -> str:
    pres = Presentation(
        slides=[slide],
        canvas_width_px=1920, canvas_height_px=1080,
        typefaces_referenced=set(),
    )
    emit_layouts(pres, tmp_path / "theme")
    return (tmp_path / "theme" / "layouts" / "slide1.vue").read_text()


class TestZOrder:
    def test_inherited_picture_renders_behind_slide_placeholder(self, tmp_path):
        """The regression target: a placeholder with positive order_index
        (slide-level) must appear AFTER a picture with negative
        order_index (layout-inherited) in DOM — putting the placeholder
        ON TOP of the inherited background image."""
        inherited_pic = _make_pic(order_index=-10_000, shape_id=99)
        slide_ph = _make_ph(order_index=5, idx=0)
        slide = Slide(
            index=1,
            placeholders=[slide_ph],
            pictures=[inherited_pic],
        )
        out = _emit(tmp_path, slide)

        pic_pos = out.index('class="pic-99"')
        ph_pos = out.index('class="title"')
        assert pic_pos < ph_pos, (
            "Inherited pic (order_index=-10_000) must render BEFORE the "
            "slide placeholder (order_index=5) in DOM order. Found pic at "
            f"{pic_pos}, placeholder at {ph_pos}."
        )

    def test_slide_picture_in_front_of_slide_placeholder(self, tmp_path):
        """When a slide-level pic comes after a placeholder in spTree
        (higher order_index), it should render IN FRONT — matching PPT's
        z-order semantics for stacked decorative elements."""
        slide_ph = _make_pic(order_index=3, shape_id=10)  # using pic for clarity
        # Actually, use a placeholder and a picture both at slide level.
        slide_ph_real = _make_ph(order_index=3, idx=0)
        foreground_pic = _make_pic(order_index=8, shape_id=20)
        slide = Slide(
            index=1,
            placeholders=[slide_ph_real],
            pictures=[foreground_pic],
        )
        out = _emit(tmp_path, slide)

        ph_pos = out.index('class="title"')
        pic_pos = out.index('class="pic-20"')
        assert ph_pos < pic_pos, (
            "Slide placeholder (order_index=3) must render BEFORE the "
            "foreground pic (order_index=8) in DOM order."
        )

    def test_multiple_inherited_pictures_preserve_their_relative_order(self, tmp_path):
        """Two inherited pictures with different order_index must
        emit in ascending order — keeps the layout's own z-order
        between background elements."""
        pic_back = _make_pic(order_index=-10_000, shape_id=1)
        pic_front = _make_pic(order_index=-9_998, shape_id=2)
        slide = Slide(index=1, placeholders=[], pictures=[pic_front, pic_back])
        out = _emit(tmp_path, slide)
        assert out.index('class="pic-1"') < out.index('class="pic-2"')

    def test_picture_placeholder_emitted_with_slot_when_inherited(self, tmp_path):
        """Inherited picture placeholders still emit as slots (so the
        deck can override the default image); they just render behind
        the slide's text placeholders due to the negative order_index."""
        inherited_pic = _make_pic(order_index=-10_000, shape_id=42, is_placeholder=True, ph_idx=22)
        slide_ph = _make_ph(order_index=4, idx=0)
        slide = Slide(index=1, placeholders=[slide_ph], pictures=[inherited_pic])
        out = _emit(tmp_path, slide)

        # The inherited picture placeholder gets a slot, not a baked img.
        assert '<slot name="picture-22"' in out
        # And it appears BEFORE the title in DOM.
        assert out.index('class="picture-22"') < out.index('class="title"')
