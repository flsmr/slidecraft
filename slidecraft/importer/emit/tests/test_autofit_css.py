"""Emit-side regression tests for autofit/wrap CSS output.

Once the parse layer correctly populates ``Placeholder.shape_autofit`` and
``Placeholder.wrap_text``, the emit layer must translate those into CSS
that actually grows the box. Otherwise the slide-24-title bug — text
clipped inside a fixed box — recurs at the emit step.
"""
from __future__ import annotations

from pathlib import Path

from slidecraft.importer.model import (
    NoFill, Paragraph, Placeholder, Presentation, Run, Slide, TextFrame,
)
from slidecraft.importer.emit.layout import emit_layouts


def _make_ph(*, shape_autofit: bool, wrap_text: bool, idx: int = 5) -> Placeholder:
    return Placeholder(
        idx=idx,
        type="title",
        x_px=10.0, y_px=20.0, width_px=400.0, height_px=60.0,
        text_frame=TextFrame(
            paragraphs=[Paragraph(runs=[Run(text="hello")])],
        ),
        shape_autofit=shape_autofit,
        wrap_text=wrap_text,
    )


def _emit_and_get_slide1(tmp_path: Path, ph: Placeholder) -> str:
    pres = Presentation(
        slides=[Slide(index=1, placeholders=[ph])],
        canvas_width_px=1920, canvas_height_px=1080,
        typefaces_referenced=set(),
    )
    emit_layouts(pres, tmp_path / "theme")
    return (tmp_path / "theme" / "layouts" / "slide1.vue").read_text()


class TestAutofitCss:
    def test_default_fixed_box(self, tmp_path):
        """Backwards compat: when autofit/wrap are at their defaults,
        the box is fixed width AND height (the pre-fix behavior)."""
        ph = _make_ph(shape_autofit=False, wrap_text=True)
        css = _emit_and_get_slide1(tmp_path, ph)
        assert "width:400px" in css
        assert "height:60px" in css
        assert "max-content" not in css
        assert "white-space:nowrap" not in css

    def test_sp_auto_fit_alone_grows_height_only(self, tmp_path):
        """spAutoFit with wrap=square (default): width is fixed so text
        still wraps at the designed width, but height grows."""
        ph = _make_ph(shape_autofit=True, wrap_text=True)
        css = _emit_and_get_slide1(tmp_path, ph)
        assert "width:400px" in css       # fixed width
        assert "min-height:60px" in css   # designer's minimum
        assert "height:max-content" in css  # grows to fit
        assert "white-space:nowrap" not in css

    def test_wrap_none_alone_grows_width_only(self, tmp_path):
        """wrap=none without autofit: height fixed (no auto-grow), but
        width extends horizontally and text never wraps."""
        ph = _make_ph(shape_autofit=False, wrap_text=False)
        css = _emit_and_get_slide1(tmp_path, ph)
        assert "min-width:400px" in css
        assert "width:max-content" in css
        assert "height:60px" in css       # fixed height
        assert "white-space:nowrap" in css

    def test_sp_auto_fit_plus_wrap_none_grows_both_axes(self, tmp_path):
        """The IU template layout-11 title pattern: both dynamic. Box
        grows in both dimensions; text never wraps. This is the
        configuration that was producing clipped text before the fix."""
        ph = _make_ph(shape_autofit=True, wrap_text=False)
        css = _emit_and_get_slide1(tmp_path, ph)
        assert "min-width:400px" in css
        assert "width:max-content" in css
        assert "min-height:60px" in css
        assert "height:max-content" in css
        assert "white-space:nowrap" in css
