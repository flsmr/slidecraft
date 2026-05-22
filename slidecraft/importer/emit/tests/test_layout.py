"""Tests for emit/layout.py."""
from __future__ import annotations

from pathlib import Path

import pytest

from slidecraft.importer.model import (
    NoFill,
    Paragraph,
    Picture,
    Placeholder,
    Presentation,
    RGB,
    Run,
    Slide,
    SolidFill,
    TextFrame,
)
from slidecraft.importer.emit.layout import emit_layouts


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _make_ph(
    idx: int = 5,
    x: float = 120.0,
    y: float = 80.0,
    w: float = 1680.0,
    h: float = 120.0,
    rotation: float = 0.0,
    fill=None,
    anchor: str = "t",
    default_bold: bool = False,
    default_color: RGB | None = None,
    default_font: str | None = None,
    default_size_pt: float | None = None,
    paragraphs=None,
) -> Placeholder:
    tf = TextFrame(
        paragraphs=paragraphs or [],
        anchor=anchor,
    )
    default_run = Run(
        text="",
        bold=default_bold,
        color=default_color,
        font_family=default_font,
        font_size_pt=default_size_pt,
    )
    return Placeholder(
        idx=idx,
        type="body",
        x_px=x,
        y_px=y,
        width_px=w,
        height_px=h,
        rotation_deg=rotation,
        fill=fill or NoFill(),
        opacity=1.0,
        text_frame=tf,
        default_run_props=default_run,
    )


def _make_pres(slides) -> Presentation:
    return Presentation(
        slides=slides,
        canvas_width_px=1920,
        canvas_height_px=1080,
        typefaces_referenced=set(),
    )


def _emit_and_read(tmp_path: Path, pres: Presentation, slide_idx: int = 1) -> str:
    emit_layouts(pres, tmp_path / "theme")
    return (tmp_path / "theme" / "layouts" / f"slide{slide_idx}.vue").read_text()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestLayoutOnePlaceholder:
    def test_layout_one_placeholder(self, tmp_path):
        ph = _make_ph(idx=5, x=120, y=80, w=1680, h=120)
        slide = Slide(index=1, placeholders=[ph])
        pres = _make_pres([slide])
        content = _emit_and_read(tmp_path, pres)

        assert "<template>" in content
        assert 'class="slidev-layout"' in content
        assert 'class="slide-root"' in content
        assert 'class="ph-5"' in content
        assert 'name="ph_5"' in content
        assert "position:absolute" in content
        assert "left:120px" in content
        assert "top:80px" in content
        assert "width:1680px" in content
        assert "height:120px" in content

    def test_layout_no_rotation_by_default(self, tmp_path):
        ph = _make_ph(idx=5, rotation=0.0)
        slide = Slide(index=1, placeholders=[ph])
        pres = _make_pres([slide])
        content = _emit_and_read(tmp_path, pres)
        # transform:rotate(0deg) should NOT appear (we skip zero rotation)
        assert "rotate(0" not in content


class TestLayoutRotationApplied:
    def test_layout_rotation_applied(self, tmp_path):
        ph = _make_ph(idx=7, rotation=15.5)
        slide = Slide(index=1, placeholders=[ph])
        pres = _make_pres([slide])
        content = _emit_and_read(tmp_path, pres)
        assert "transform:rotate(15.5deg)" in content

    def test_layout_negative_rotation(self, tmp_path):
        ph = _make_ph(idx=7, rotation=-30.0)
        slide = Slide(index=1, placeholders=[ph])
        pres = _make_pres([slide])
        content = _emit_and_read(tmp_path, pres)
        assert "transform:rotate(-30deg)" in content


class TestLayoutScoping:
    def test_layout_scoping(self, tmp_path):
        """All CSS selectors in <style scoped> must be under .slidev-layout."""
        ph = _make_ph(idx=5)
        slide = Slide(index=1, placeholders=[ph])
        pres = _make_pres([slide])
        content = _emit_and_read(tmp_path, pres)

        assert "<style scoped>" in content
        # slide-root rule scoped
        assert ".slidev-layout .slide-root" in content
        # No bare .slide-root selector (would be unscoped)
        # Look for bare .slide-root not preceded by .slidev-layout
        import re
        bare_selectors = re.findall(r"(?<!\.slidev-layout )\.slide-root", content)
        assert not bare_selectors, f"Unscoped selectors found: {bare_selectors}"

    def test_layout_slide_root_dimensions(self, tmp_path):
        ph = _make_ph()
        slide = Slide(index=1, placeholders=[ph])
        pres = _make_pres([slide])
        content = _emit_and_read(tmp_path, pres)

        assert "width: 1920px" in content
        assert "height: 1080px" in content

    def test_layout_background_solid(self, tmp_path):
        ph = _make_ph()
        slide = Slide(
            index=1,
            placeholders=[ph],
            background_fill=SolidFill(RGB(255, 0, 0)),
        )
        pres = _make_pres([slide])
        content = _emit_and_read(tmp_path, pres)
        assert "#FF0000" in content or "rgb(255,0,0)" in content

    def test_layout_font_in_inline_style(self, tmp_path):
        ph = _make_ph(default_font="Calibri", default_size_pt=44.0, default_bold=True)
        slide = Slide(index=1, placeholders=[ph])
        pres = _make_pres([slide])
        content = _emit_and_read(tmp_path, pres)
        assert "Calibri" in content
        # 44pt → 44 * 96/72 ≈ 58.67px
        assert "font-size:" in content
        assert "font-weight: 700" in content

    def test_layout_center_anchor_uses_flex_center(self, tmp_path):
        ph = _make_ph(anchor="ctr")
        slide = Slide(index=1, placeholders=[ph])
        pres = _make_pres([slide])
        content = _emit_and_read(tmp_path, pres)
        assert "align-items:center" in content

    def test_layout_bullet_css_scoped(self, tmp_path):
        """Bullet CSS selectors must be scoped under .slidev-layout .ph-N."""
        bullet_para = Paragraph(
            runs=[Run(text="item")],
            bullet="char",
            level=0,
        )
        ph = _make_ph(idx=6, paragraphs=[bullet_para])
        slide = Slide(index=1, placeholders=[ph])
        pres = _make_pres([slide])
        content = _emit_and_read(tmp_path, pres)
        assert ".slidev-layout .ph-6 ul li" in content

    def test_layout_multiple_slides(self, tmp_path):
        ph1 = _make_ph(idx=1)
        ph2 = _make_ph(idx=2)
        slide1 = Slide(index=1, placeholders=[ph1])
        slide2 = Slide(index=2, placeholders=[ph2])
        pres = _make_pres([slide1, slide2])
        emit_layouts(pres, tmp_path / "theme")
        assert (tmp_path / "theme" / "layouts" / "slide1.vue").exists()
        assert (tmp_path / "theme" / "layouts" / "slide2.vue").exists()


class TestLayoutCapTextTransform:
    """Tests for cap → text-transform CSS emission."""

    def _make_ph_with_cap(self, cap: str | None) -> Placeholder:
        """Build a placeholder whose default_run_props has the given cap value."""
        tf = TextFrame(paragraphs=[], anchor="t")
        default_run = Run(text="", cap=cap)
        return Placeholder(
            idx=1,
            type="title",
            x_px=0.0, y_px=0.0, width_px=500.0, height_px=80.0,
            fill=NoFill(), opacity=1.0,
            text_frame=tf,
            default_run_props=default_run,
        )

    def test_cap_all_emits_uppercase(self, tmp_path):
        ph = self._make_ph_with_cap("all")
        slide = Slide(index=1, placeholders=[ph])
        pres = _make_pres([slide])
        content = _emit_and_read(tmp_path, pres)
        assert "text-transform: uppercase" in content

    def test_cap_small_emits_lowercase(self, tmp_path):
        ph = self._make_ph_with_cap("small")
        slide = Slide(index=1, placeholders=[ph])
        pres = _make_pres([slide])
        content = _emit_and_read(tmp_path, pres)
        assert "text-transform: lowercase" in content

    def test_cap_none_no_text_transform(self, tmp_path):
        ph = self._make_ph_with_cap(None)
        slide = Slide(index=1, placeholders=[ph])
        pres = _make_pres([slide])
        content = _emit_and_read(tmp_path, pres)
        assert "text-transform" not in content

    def test_cap_none_literal_no_text_transform(self, tmp_path):
        """cap='none' explicitly set should not emit text-transform."""
        ph = self._make_ph_with_cap("none")
        slide = Slide(index=1, placeholders=[ph])
        pres = _make_pres([slide])
        content = _emit_and_read(tmp_path, pres)
        assert "text-transform" not in content


# ---------------------------------------------------------------------------
# Picture emission (P6)
# ---------------------------------------------------------------------------

def _make_pic(
    *,
    asset_ref: str | None = "image1.png",
    x: float = 100.0,
    y: float = 200.0,
    w: float = 300.0,
    h: float = 200.0,
    shape_id: int = 42,
    is_placeholder: bool = False,
    ph_idx: int | None = None,
    preset_geom: str | None = None,
    preset_geom_av: dict | None = None,
    effects: dict | None = None,
    alt_text: str = "",
    order_index: int = 0,
) -> Picture:
    return Picture(
        asset_ref=asset_ref,
        x_px=x,
        y_px=y,
        width_px=w,
        height_px=h,
        preset_geom=preset_geom,
        preset_geom_av=preset_geom_av,
        effects=effects or {
            "css_filter": "",
            "transforms": [],
            "opacity": None,
            "box_reflect": None,
            "mask_image": None,
            "derivatives_needed": [],
            "warnings": [],
        },
        alt_text=alt_text,
        shape_id=shape_id,
        is_placeholder=is_placeholder,
        ph_idx=ph_idx,
        order_index=order_index,
    )


class TestPictureEmission:
    def test_free_picture_emits_baked_img(self, tmp_path):
        pic = _make_pic(asset_ref="image1.png", shape_id=42, x=100, y=200, w=300, h=200)
        slide = Slide(index=1, placeholders=[], pictures=[pic])
        pres = _make_pres([slide])
        content = _emit_and_read(tmp_path, pres)
        assert 'class="pic-42"' in content
        assert 'src="/assets/image1.png"' in content
        assert "left:100px" in content
        assert "width:300px" in content
        # Free picture: no slot.
        assert 'name="ph_' not in content or '<slot name="ph_' not in content

    def test_free_picture_alt_text_escaped(self, tmp_path):
        pic = _make_pic(asset_ref="img.png", alt_text='Tag "X" hits 99%')
        slide = Slide(index=1, placeholders=[], pictures=[pic])
        content = _emit_and_read(tmp_path, _make_pres([slide]))
        assert 'alt="Tag &quot;X&quot; hits 99%"' in content

    def test_picture_placeholder_emits_slot_with_default_img(self, tmp_path):
        pic = _make_pic(
            asset_ref="layout_default.png",
            is_placeholder=True,
            ph_idx=3,
            shape_id=99,
        )
        slide = Slide(index=1, placeholders=[], pictures=[pic])
        content = _emit_and_read(tmp_path, _make_pres([slide]))
        # Wrapper uses `ph-<idx>`, not `pic-<id>`.
        assert 'class="ph-3"' in content
        assert 'class="pic-99"' not in content
        # Slot named ph_<idx> with default <img> as fallback content.
        assert '<slot name="ph_3"><img src="/assets/layout_default.png"' in content

    def test_picture_placeholder_without_bound_image_emits_empty_slot(self, tmp_path):
        pic = _make_pic(asset_ref=None, is_placeholder=True, ph_idx=5)
        slide = Slide(index=1, placeholders=[], pictures=[pic])
        content = _emit_and_read(tmp_path, _make_pres([slide]))
        assert 'class="ph-5"' in content
        # Empty slot — no <img> default.
        assert '<slot name="ph_5" />' in content
        assert "<img" not in content

    def test_prst_geom_ellipse_applies_border_radius(self, tmp_path):
        pic = _make_pic(preset_geom="ellipse", w=200, h=200)
        slide = Slide(index=1, placeholders=[], pictures=[pic])
        content = _emit_and_read(tmp_path, _make_pres([slide]))
        assert "border-radius:50%" in content

    def test_prst_geom_triangle_applies_clip_path(self, tmp_path):
        pic = _make_pic(preset_geom="triangle", w=200, h=200)
        slide = Slide(index=1, placeholders=[], pictures=[pic])
        content = _emit_and_read(tmp_path, _make_pres([slide]))
        assert "clip-path:polygon(" in content

    def test_unmapped_prst_geom_omits_clip(self, tmp_path):
        pic = _make_pic(preset_geom="wave")
        slide = Slide(index=1, placeholders=[], pictures=[pic])
        content = _emit_and_read(tmp_path, _make_pres([slide]))
        # Unmapped preset → no clip-path / border-radius from prstGeom.
        assert "clip-path:" not in content
        assert "border-radius:" not in content

    def test_effects_transform_rotate_and_flip(self, tmp_path):
        pic = _make_pic(effects={
            "css_filter": "",
            "transforms": ["scaleX(-1)", "rotate(15deg)"],
            "opacity": None,
            "box_reflect": None,
            "mask_image": None,
            "derivatives_needed": [],
            "warnings": [],
        })
        slide = Slide(index=1, placeholders=[], pictures=[pic])
        content = _emit_and_read(tmp_path, _make_pres([slide]))
        assert "transform:scaleX(-1) rotate(15deg)" in content

    def test_effects_css_filter_applied(self, tmp_path):
        pic = _make_pic(effects={
            "css_filter": "grayscale(1) brightness(0.8)",
            "transforms": [],
            "opacity": None,
            "box_reflect": None,
            "mask_image": None,
            "derivatives_needed": [],
            "warnings": [],
        })
        slide = Slide(index=1, placeholders=[], pictures=[pic])
        content = _emit_and_read(tmp_path, _make_pres([slide]))
        assert "filter:grayscale(1) brightness(0.8)" in content

    def test_effects_opacity_applied_when_set(self, tmp_path):
        pic = _make_pic(effects={
            "css_filter": "",
            "transforms": [],
            "opacity": 0.5,
            "box_reflect": None,
            "mask_image": None,
            "derivatives_needed": [],
            "warnings": [],
        })
        slide = Slide(index=1, placeholders=[], pictures=[pic])
        content = _emit_and_read(tmp_path, _make_pres([slide]))
        assert "opacity:0.5" in content

    def test_effects_opacity_omitted_when_1(self, tmp_path):
        pic = _make_pic(effects={
            "css_filter": "",
            "transforms": [],
            "opacity": 1.0,
            "box_reflect": None,
            "mask_image": None,
            "derivatives_needed": [],
            "warnings": [],
        })
        slide = Slide(index=1, placeholders=[], pictures=[pic])
        content = _emit_and_read(tmp_path, _make_pres([slide]))
        assert "opacity:" not in content

    def test_box_reflect_applied(self, tmp_path):
        pic = _make_pic(effects={
            "css_filter": "",
            "transforms": [],
            "opacity": None,
            "box_reflect": "below 0 linear-gradient(transparent, rgba(0,0,0,0.35))",
            "mask_image": None,
            "derivatives_needed": [],
            "warnings": [],
        })
        slide = Slide(index=1, placeholders=[], pictures=[pic])
        content = _emit_and_read(tmp_path, _make_pres([slide]))
        assert "-webkit-box-reflect:below 0 linear-gradient" in content

    def test_derivative_url_chain(self, tmp_path):
        """A picture with a crop derivative URL points to the derived filename."""
        pic = _make_pic(
            asset_ref="photo.png",
            effects={
                "css_filter": "",
                "transforms": [],
                "opacity": None,
                "box_reflect": None,
                "mask_image": None,
                "derivatives_needed": [
                    {"op": "crop", "params": {"l": 10000, "t": 0, "r": 5000, "b": 0}},
                ],
                "warnings": [],
            },
        )
        slide = Slide(index=1, placeholders=[], pictures=[pic])
        content = _emit_and_read(tmp_path, _make_pres([slide]))
        assert 'src="/assets/photo__crop_l10000_t0_r5000_b0.png"' in content

    def test_derivative_chain_composes_multiple_ops(self, tmp_path):
        """Crop then duotone produces a chained derived filename."""
        pic = _make_pic(
            asset_ref="photo.jpg",
            effects={
                "css_filter": "",
                "transforms": [],
                "opacity": None,
                "box_reflect": None,
                "mask_image": None,
                "derivatives_needed": [
                    {"op": "crop", "params": {"l": 0, "t": 0, "r": 0, "b": 10000}},
                    {"op": "duotone", "params": {"c1": "ff0000", "c2": "0000ff"}},
                ],
                "warnings": [],
            },
        )
        slide = Slide(index=1, placeholders=[], pictures=[pic])
        content = _emit_and_read(tmp_path, _make_pres([slide]))
        # After crop the name becomes photo__crop_l0_t0_r0_b10000.jpg;
        # after duotone it becomes ..._duotone_ff0000_0000ff.png.
        assert "duotone_ff0000_0000ff.png" in content

    def test_pictures_emit_after_placeholders(self, tmp_path):
        """In a slide with both, pictures appear later in the DOM (visually on top)."""
        ph = _make_ph(idx=1)
        pic = _make_pic(shape_id=88)
        slide = Slide(index=1, placeholders=[ph], pictures=[pic])
        content = _emit_and_read(tmp_path, _make_pres([slide]))
        assert content.index('class="ph-1"') < content.index('class="pic-88"')

    def test_multiple_free_pictures_emit_in_list_order(self, tmp_path):
        pic_a = _make_pic(asset_ref="a.png", shape_id=10, order_index=0)
        pic_b = _make_pic(asset_ref="b.png", shape_id=20, order_index=1)
        pic_c = _make_pic(asset_ref="c.png", shape_id=30, order_index=2)
        slide = Slide(index=1, placeholders=[], pictures=[pic_a, pic_b, pic_c])
        content = _emit_and_read(tmp_path, _make_pres([slide]))
        idx_a = content.index('class="pic-10"')
        idx_b = content.index('class="pic-20"')
        idx_c = content.index('class="pic-30"')
        assert idx_a < idx_b < idx_c
