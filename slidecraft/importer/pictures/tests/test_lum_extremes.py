"""Regression tests for `<a:lum>` extreme-value handling.

The bug we're guarding: PowerPoint's standard "monochrome icon recolour"
uses ``<a:lum bright="100000" contrast="100000"/>`` (= +100% / +100%)
to force the image to pure white. CSS ``filter: brightness(N)`` is
multiplicative and never reaches pure white, so the previous mapping
``brightness(1 + raw/100000)`` produced ``brightness(2.0) contrast(2.0)``
— visually "twice as bright" but still showing the original colors.
The IU template's slide 19 small icon hit this: PPT renders pure white
(invisible on white background), our render kept it dark.

Fix: special-case the extreme combinations to ``brightness(0) invert(1)``
(force-to-white) and ``brightness(0)`` (force-to-black). Non-extreme
values keep the existing linear approximation.
"""
from __future__ import annotations

from lxml import etree

from slidecraft.importer.pictures.effects import parse_effects


def _make_blip_fill(lum_xml: str) -> etree._Element:
    """Wrap a <a:lum .../> fragment into a parseable <p:blipFill>."""
    return etree.fromstring(
        '<p:blipFill xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"'
        '            xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"'
        '            xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'  <a:blip r:embed="">{lum_xml}</a:blip>'
        '  <a:stretch><a:fillRect/></a:stretch>'
        '</p:blipFill>'
    )


class TestLumExtremes:
    def test_force_to_white_uses_brightness_zero_invert_one(self):
        """The IU template's recipe: bright=+100% contrast=+100% must emit
        the brightness(0) invert(1) combo so the rendered image is pure
        white (alpha preserved), matching PowerPoint."""
        bf = _make_blip_fill('<a:lum bright="100000" contrast="100000"/>')
        result = parse_effects(None, bf)
        css = result["css_filter"]
        assert "brightness(0)" in css
        assert "invert(1)" in css
        # And NO multiplicative brightness/contrast (which would never reach white).
        assert "brightness(2" not in css

    def test_force_to_white_tolerant_threshold(self):
        """Values >= 95% (in absolute terms) should still hit the
        pure-white path — tolerates near-extreme values like 98% that
        PPT also renders as essentially-white."""
        bf = _make_blip_fill('<a:lum bright="98000" contrast="98000"/>')
        result = parse_effects(None, bf)
        assert "brightness(0)" in result["css_filter"]
        assert "invert(1)" in result["css_filter"]

    def test_force_to_black_emits_brightness_zero_alone(self):
        """bright=-100% with contrast=+100% pushes everything to pure
        black (alpha preserved). No invert."""
        bf = _make_blip_fill('<a:lum bright="-100000" contrast="100000"/>')
        result = parse_effects(None, bf)
        assert "brightness(0)" in result["css_filter"]
        assert "invert(1)" not in result["css_filter"]

    def test_moderate_brightness_uses_linear_approximation(self):
        """For non-extreme values, the existing linear formula still
        applies — PPT's exact rendering is non-linear but linear is
        close enough for small adjustments and matches what users
        usually mean."""
        bf = _make_blip_fill('<a:lum bright="20000" contrast="10000"/>')
        result = parse_effects(None, bf)
        css = result["css_filter"]
        assert "brightness(1.2" in css
        assert "contrast(1.1" in css
        assert "invert" not in css

    def test_zero_lum_emits_neutral_filters(self):
        """bright=0 contrast=0 (or absent) → no-op filters; we still emit
        the multiplicative form for consistency."""
        bf = _make_blip_fill('<a:lum/>')
        result = parse_effects(None, bf)
        css = result["css_filter"]
        # Either no filter or neutral (brightness(1.0) contrast(1.0))
        assert "invert" not in css
        # Should NOT emit brightness(0) when both attrs missing/zero.
        assert "brightness(0)" not in css
