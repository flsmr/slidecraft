"""Tests for emit/layout.py."""
from __future__ import annotations

from pathlib import Path

import pytest

from slidecraft.importer.model import (
    NoFill,
    Paragraph,
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
