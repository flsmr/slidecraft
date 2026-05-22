"""Tests for slidecraft.importer.pictures.effects.parse_effects.

Each test exercises one or more XML effect elements via hand-written OOXML
fragments (parsed with lxml).  Namespace-qualified tags follow the drawingml
convention ``a:`` = ``http://schemas.openxmlformats.org/drawingml/2006/main``.
"""
from __future__ import annotations

import math

import pytest
from lxml import etree

from slidecraft.importer.pictures.effects import EMU_PER_PX, parse_effects

# ---------------------------------------------------------------------------
# Namespace helpers used throughout tests
# ---------------------------------------------------------------------------

_NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
_NS_P = "http://schemas.openxmlformats.org/presentationml/2006/main"

_NSMAP = {
    "a": _NS_A,
    "p": _NS_P,
}


def _xml(fragment: str) -> etree._Element:
    """Parse an XML *fragment* string into an lxml element."""
    return etree.fromstring(fragment)


def _spPr(inner: str = "") -> etree._Element:
    """Wrap *inner* XML in a ``<p:spPr>`` element."""
    return _xml(
        f'<spPr xmlns="{_NS_P}" xmlns:a="{_NS_A}">'
        f"{inner}"
        f"</spPr>"
    )


def _blipFill(inner: str = "") -> etree._Element:
    """Wrap *inner* XML in an ``<a:blipFill>`` element."""
    return _xml(
        f'<a:blipFill xmlns:a="{_NS_A}">'
        f"{inner}"
        f"</a:blipFill>"
    )


# ---------------------------------------------------------------------------
# Helper: quickly call parse_effects with only one input provided
# ---------------------------------------------------------------------------

def _effects_sp(sp_inner: str) -> dict:
    return parse_effects(sp_pr_elem=_spPr(sp_inner), blip_fill_elem=None)


def _effects_bf(bf_inner: str) -> dict:
    return parse_effects(sp_pr_elem=None, blip_fill_elem=_blipFill(bf_inner))


# ===========================================================================
# blipFill effects
# ===========================================================================

class TestLuminance:
    """<a:lum bright="" contrast=""/> inside <a:blip>."""

    def test_positive_brightness_and_contrast(self) -> None:
        result = _effects_bf('<a:blip><a:lum bright="20000" contrast="10000"/></a:blip>')
        # bright=20000 → 1.0 + 0.20 = 1.2; contrast=10000 → 1.0 + 0.10 = 1.1
        assert "brightness(1.2000)" in result["css_filter"]
        assert "contrast(1.1000)" in result["css_filter"]
        assert result["warnings"] == []

    def test_zero_luminance_produces_neutral_values(self) -> None:
        result = _effects_bf('<a:blip><a:lum bright="0" contrast="0"/></a:blip>')
        assert "brightness(1.0000)" in result["css_filter"]
        assert "contrast(1.0000)" in result["css_filter"]

    def test_negative_brightness(self) -> None:
        result = _effects_bf('<a:blip><a:lum bright="-20000" contrast="0"/></a:blip>')
        assert "brightness(0.8000)" in result["css_filter"]


class TestAlphaModFix:
    """<a:alphaModFix amt=""/> → opacity."""

    def test_half_opacity(self) -> None:
        result = _effects_bf('<a:blip><a:alphaModFix amt="50000"/></a:blip>')
        assert result["opacity"] == pytest.approx(0.5)

    def test_full_opacity(self) -> None:
        result = _effects_bf('<a:blip><a:alphaModFix amt="100000"/></a:blip>')
        assert result["opacity"] == pytest.approx(1.0)

    def test_no_alpha_mod_returns_none(self) -> None:
        result = _effects_bf("")
        assert result["opacity"] is None


class TestGrayscale:
    """<a:grayscl/> → css_filter grayscale(1)."""

    def test_grayscale_filter_present(self) -> None:
        result = _effects_bf('<a:blip><a:grayscl/></a:blip>')
        assert "grayscale(1)" in result["css_filter"]

    def test_no_grayscale_when_absent(self) -> None:
        result = _effects_bf("")
        assert "grayscale" not in result["css_filter"]


class TestBiLevel:
    """<a:biLevel thresh=""/> → grayscale(1) contrast(1000)."""

    def test_bilevel_produces_grayscale_and_contrast(self) -> None:
        result = _effects_bf('<a:blip><a:biLevel thresh="50000"/></a:blip>')
        assert "grayscale(1)" in result["css_filter"]
        assert "contrast(1000)" in result["css_filter"]


class TestBlur:
    """<a:blur rad=""/> → blur(Xpx). rad in EMU."""

    def test_blur_emu_to_px(self) -> None:
        rad_emu = 9525 * 4  # 4 px
        result = _effects_bf(f'<a:blip><a:blur rad="{rad_emu}"/></a:blip>')
        assert "blur(4.00px)" in result["css_filter"]

    def test_zero_blur(self) -> None:
        result = _effects_bf('<a:blip><a:blur rad="0"/></a:blip>')
        assert "blur(0.00px)" in result["css_filter"]


class TestDuotone:
    """<a:duotone> with two <a:srgbClr> children."""

    def test_two_srgb_colors_produce_derivative(self) -> None:
        result = _effects_bf(
            '<a:blip>'
            '  <a:duotone>'
            '    <a:srgbClr val="FF0000"/>'
            '    <a:srgbClr val="0000FF"/>'
            '  </a:duotone>'
            '</a:blip>'
        )
        assert len(result["derivatives_needed"]) == 1
        d = result["derivatives_needed"][0]
        assert d["op"] == "duotone"
        assert d["params"]["c1"] == "rgb(255,0,0)"
        assert d["params"]["c2"] == "rgb(0,0,255)"
        assert result["warnings"] == []

    def test_schemeClr_produces_warning_no_derivative(self) -> None:
        result = _effects_bf(
            '<a:blip>'
            '  <a:duotone>'
            '    <a:schemeClr val="accent1"/>'
            '    <a:srgbClr val="0000FF"/>'
            '  </a:duotone>'
            '</a:blip>'
        )
        assert "duotone_color_unresolved" in result["warnings"]
        duotone_ops = [d for d in result["derivatives_needed"] if d["op"] == "duotone"]
        assert duotone_ops == []


class TestSrcRect:
    """<a:srcRect l="" t="" r="" b=""/> → crop derivative."""

    def test_explicit_crop_values(self) -> None:
        result = _effects_bf('<a:srcRect l="5000" t="10000" r="5000" b="0"/>')
        assert len(result["derivatives_needed"]) == 1
        d = result["derivatives_needed"][0]
        assert d["op"] == "crop"
        assert d["params"] == {"l": 5000, "t": 10000, "r": 5000, "b": 0}

    def test_missing_attrs_default_to_zero(self) -> None:
        result = _effects_bf('<a:srcRect/>')
        d = result["derivatives_needed"][0]
        assert d["params"] == {"l": 0, "t": 0, "r": 0, "b": 0}


class TestTile:
    """<a:tile> → warning 'tiled_fill_unsupported'."""

    def test_tile_produces_warning(self) -> None:
        result = _effects_bf('<a:tile/>')
        assert "tiled_fill_unsupported" in result["warnings"]


# ===========================================================================
# spPr effects
# ===========================================================================

class TestFlipAndRotate:
    """<a:xfrm @flipH @flipV @rot> → transforms list (scale before rotate)."""

    def test_flip_h(self) -> None:
        result = _effects_sp('<a:xfrm flipH="1"/>')
        assert result["transforms"] == ["scaleX(-1)"]

    def test_flip_v(self) -> None:
        result = _effects_sp('<a:xfrm flipV="1"/>')
        assert result["transforms"] == ["scaleY(-1)"]

    def test_rotate_only(self) -> None:
        # 15° × 60000 = 900000
        result = _effects_sp('<a:xfrm rot="900000"/>')
        assert result["transforms"] == ["rotate(15.0000deg)"]

    def test_flip_h_and_rotate_order(self) -> None:
        """scaleX(-1) must appear before rotate() in the list."""
        result = _effects_sp('<a:xfrm flipH="1" rot="900000"/>')
        transforms = result["transforms"]
        assert transforms[0] == "scaleX(-1)"
        assert transforms[1] == "rotate(15.0000deg)"

    def test_flip_both_and_rotate_order(self) -> None:
        """Both scale transforms precede rotation."""
        result = _effects_sp('<a:xfrm flipH="1" flipV="1" rot="360000"/>')
        transforms = result["transforms"]
        assert "scaleX(-1)" in transforms
        assert "scaleY(-1)" in transforms
        assert "rotate(6.0000deg)" in transforms
        # scaleX and scaleY must both appear before rotate
        rotate_idx = next(i for i, t in enumerate(transforms) if t.startswith("rotate"))
        for t in ["scaleX(-1)", "scaleY(-1)"]:
            scale_idx = transforms.index(t)
            assert scale_idx < rotate_idx, f"{t} must precede rotate"

    def test_no_xfrm_produces_empty_transforms(self) -> None:
        result = _effects_sp("")
        assert result["transforms"] == []


class TestOuterShadow:
    """<a:outerShdw> → drop-shadow() in css_filter."""

    def _make_shdw(
        self,
        blur_rad: int = 38100,   # 4 px
        dist: int = 38100,       # 4 px
        dir_deg: int = 0,        # 60000ths-of-degree
        r: int = 0,
        g: int = 0,
        b: int = 0,
        alpha: int = 100000,
    ) -> dict:
        dir_raw = dir_deg  # already in 60000ths
        return _effects_sp(
            f'<a:effectLst>'
            f'  <a:outerShdw blurRad="{blur_rad}" dist="{dist}" dir="{dir_raw}">'
            f'    <a:srgbClr val="{r:02X}{g:02X}{b:02X}">'
            f'      <a:alpha val="{alpha}"/>'
            f'    </a:srgbClr>'
            f'  </a:outerShdw>'
            f'</a:effectLst>'
        )

    def test_shadow_to_the_right(self) -> None:
        """dir=0 → shadow offset is purely to the right (x > 0, y ≈ 0)."""
        result = self._make_shdw(dist=95250, dir_deg=0)  # 10 px, east
        css = result["css_filter"]
        assert "drop-shadow(" in css
        # x should be ~10px, y should be ~0
        assert "10.00px" in css

    def test_shadow_downward(self) -> None:
        """dir=90° (5400000 in 60000ths) → offset is purely downward."""
        dist_emu = 95250  # 10 px
        dir_raw = 90 * 60_000  # 5400000
        result = _effects_sp(
            f'<a:effectLst>'
            f'  <a:outerShdw blurRad="0" dist="{dist_emu}" dir="{dir_raw}">'
            f'    <a:srgbClr val="000000"/>'
            f'  </a:outerShdw>'
            f'</a:effectLst>'
        )
        css = result["css_filter"]
        # y offset should be ~10px
        assert "drop-shadow(" in css
        # Verify cos(90°) ≈ 0 → x near 0, sin(90°)=1 → y=10px
        import re
        m = re.search(r"drop-shadow\((-?[\d.]+)px (-?[\d.]+)px", css)
        assert m, f"drop-shadow not found in: {css}"
        x_px = float(m.group(1))
        y_px = float(m.group(2))
        assert abs(x_px) < 0.1, f"x_px={x_px} should be ~0 for dir=90°"
        assert abs(y_px - 10.0) < 0.1, f"y_px={y_px} should be ~10 for dir=90°"

    def test_schemeClr_shadow_produces_warning_no_filter(self) -> None:
        result = _effects_sp(
            '<a:effectLst>'
            '  <a:outerShdw blurRad="0" dist="0" dir="0">'
            '    <a:schemeClr val="accent1"/>'
            '  </a:outerShdw>'
            '</a:effectLst>'
        )
        assert "drop-shadow" not in result["css_filter"]
        assert "unresolved_color" in result["warnings"]


class TestGlow:
    """<a:glow rad=""> → drop-shadow(0 0 Rpx color)."""

    def test_glow_produces_drop_shadow(self) -> None:
        rad_emu = 9525 * 6  # 6 px
        result = _effects_sp(
            f'<a:effectLst>'
            f'  <a:glow rad="{rad_emu}">'
            f'    <a:srgbClr val="FFFF00"/>'
            f'  </a:glow>'
            f'</a:effectLst>'
        )
        css = result["css_filter"]
        assert "drop-shadow(0 0 6.00px" in css
        assert "255,255,0" in css

    def test_glow_schemeClr_warning(self) -> None:
        result = _effects_sp(
            '<a:effectLst>'
            '  <a:glow rad="9525">'
            '    <a:schemeClr val="dk1"/>'
            '  </a:glow>'
            '</a:effectLst>'
        )
        assert "drop-shadow" not in result["css_filter"]
        assert "unresolved_color" in result["warnings"]


class TestInnerShadow:
    """<a:innerShdw> → mask_image + warning."""

    def test_inner_shadow_sets_mask_and_warning(self) -> None:
        result = _effects_sp(
            '<a:effectLst>'
            '  <a:innerShdw blurRad="0" dist="0" dir="0">'
            '    <a:srgbClr val="000000"/>'
            '  </a:innerShdw>'
            '</a:effectLst>'
        )
        assert result["mask_image"] == "__inner_shadow__"
        assert "inner_shadow_approximation" in result["warnings"]


class TestSoftEdge:
    """<a:softEdge rad=""> → derivative."""

    def test_soft_edge_derivative(self) -> None:
        rad_emu = 9525 * 8  # 8 px
        result = _effects_sp(
            f'<a:effectLst>'
            f'  <a:softEdge rad="{rad_emu}"/>'
            f'</a:effectLst>'
        )
        soft_ops = [d for d in result["derivatives_needed"] if d["op"] == "soft_edge"]
        assert len(soft_ops) == 1
        assert soft_ops[0]["params"]["radius_px"] == pytest.approx(8.0)


class TestReflection:
    """<a:reflection> → box_reflect + warning."""

    def test_reflection_sets_box_reflect(self) -> None:
        result = _effects_sp(
            '<a:effectLst>'
            '  <a:reflection/>'
            '</a:effectLst>'
        )
        assert result["box_reflect"] is not None
        assert "below" in result["box_reflect"]
        assert "reflection_approximation" in result["warnings"]


class Test3DRotation:
    """<a:scene3d> + <a:sp3d> → perspective() transform."""

    def test_3d_rotation_perspective_transform(self) -> None:
        # lat=30°, lon=45°, rev=10° (all in 60000ths)
        lat_raw = 30 * 60_000
        lon_raw = 45 * 60_000
        rev_raw = 10 * 60_000
        result = _effects_sp(
            f'<a:scene3d>'
            f'  <a:camera prst="obliqueBottom">'
            f'    <a:rot lat="{lat_raw}" lon="{lon_raw}" rev="{rev_raw}"/>'
            f'  </a:camera>'
            f'</a:scene3d>'
        )
        transforms = result["transforms"]
        assert any("perspective(2000px)" in t for t in transforms), transforms
        assert any("rotateX(30.0000deg)" in t for t in transforms), transforms
        assert any("rotateY(45.0000deg)" in t for t in transforms), transforms
        assert any("rotateZ(10.0000deg)" in t for t in transforms), transforms

    def test_bevel_warning(self) -> None:
        result = _effects_sp(
            '<a:scene3d/>'
            '<a:sp3d><a:bevelT/></a:sp3d>'
        )
        assert "skipped_3d_bevel" in result["warnings"]

    def test_extrusion_clr_warning(self) -> None:
        result = _effects_sp(
            '<a:scene3d/>'
            '<a:sp3d><a:extrusionClr><a:srgbClr val="FF0000"/></a:extrusionClr></a:sp3d>'
        )
        assert "skipped_3d_extrusion" in result["warnings"]


# ===========================================================================
# Combination tests
# ===========================================================================

class TestCombinations:
    """Multiple simultaneous effects in deterministic order."""

    def test_lum_plus_grayscale_plus_outer_shadow(self) -> None:
        """Filter string contains brightness, contrast, grayscale, drop-shadow in order."""
        sp_pr = _spPr(
            '<a:effectLst>'
            '  <a:outerShdw blurRad="38100" dist="19050" dir="2700000">'
            '    <a:srgbClr val="404040"/>'
            '  </a:outerShdw>'
            '</a:effectLst>'
        )
        bf = _blipFill(
            '<a:blip>'
            '  <a:lum bright="10000" contrast="5000"/>'
            '  <a:grayscl/>'
            '</a:blip>'
        )
        result = parse_effects(sp_pr_elem=sp_pr, blip_fill_elem=bf)
        css = result["css_filter"]

        # All three effects must be present
        assert "brightness(" in css
        assert "contrast(" in css
        assert "grayscale(1)" in css
        assert "drop-shadow(" in css

        # Order: blipFill effects (lum brightness/contrast, grayscale) come
        # before spPr effects (drop-shadow) because _parse_blip_fill runs first.
        brightness_idx = css.index("brightness(")
        grayscale_idx = css.index("grayscale(")
        drop_shadow_idx = css.index("drop-shadow(")
        assert brightness_idx < grayscale_idx < drop_shadow_idx

    def test_grayscale_and_blur_and_opacity(self) -> None:
        bf = _blipFill(
            '<a:blip>'
            '  <a:grayscl/>'
            '  <a:blur rad="19050"/>'
            '  <a:alphaModFix amt="75000"/>'
            '</a:blip>'
        )
        result = parse_effects(sp_pr_elem=None, blip_fill_elem=bf)
        assert "grayscale(1)" in result["css_filter"]
        assert "blur(2.00px)" in result["css_filter"]
        assert result["opacity"] == pytest.approx(0.75)

    def test_crop_and_duotone_in_derivatives(self) -> None:
        bf = _blipFill(
            '<a:srcRect l="1000" t="2000" r="3000" b="4000"/>'
            '<a:blip>'
            '  <a:duotone>'
            '    <a:srgbClr val="123456"/>'
            '    <a:srgbClr val="ABCDEF"/>'
            '  </a:duotone>'
            '</a:blip>'
        )
        result = parse_effects(sp_pr_elem=None, blip_fill_elem=bf)
        ops = {d["op"] for d in result["derivatives_needed"]}
        assert "crop" in ops
        assert "duotone" in ops


class TestFlipRotateCombination:
    """Verify flip → rotate ordering in transforms list."""

    def test_flip_h_v_then_rotate(self) -> None:
        result = _effects_sp('<a:xfrm flipH="1" flipV="1" rot="1800000"/>')
        transforms = result["transforms"]
        # Both flips before rotation
        scale_indices = [i for i, t in enumerate(transforms) if t.startswith("scale")]
        rotate_indices = [i for i, t in enumerate(transforms) if t.startswith("rotate")]
        assert len(scale_indices) == 2
        assert len(rotate_indices) == 1
        assert max(scale_indices) < rotate_indices[0]
        # Correct rotation value: 1800000 / 60000 = 30°
        assert transforms[rotate_indices[0]] == "rotate(30.0000deg)"


class TestUnresolvedColorWarning:
    """schemeClr / sysClr produces 'unresolved_color' and no css output."""

    def test_scheme_clr_in_outer_shadow(self) -> None:
        result = _effects_sp(
            '<a:effectLst>'
            '  <a:outerShdw blurRad="9525" dist="9525" dir="0">'
            '    <a:schemeClr val="dk1"/>'
            '  </a:outerShdw>'
            '</a:effectLst>'
        )
        assert result["css_filter"] == ""
        assert "unresolved_color" in result["warnings"]

    def test_sys_clr_in_glow(self) -> None:
        result = _effects_sp(
            '<a:effectLst>'
            '  <a:glow rad="9525">'
            '    <a:sysClr lastClr="FFFFFF"/>'
            '  </a:glow>'
            '</a:effectLst>'
        )
        assert result["css_filter"] == ""
        assert "unresolved_color" in result["warnings"]


class TestNullInputs:
    """Both inputs None → empty result."""

    def test_both_none_returns_empty_dict(self) -> None:
        result = parse_effects(sp_pr_elem=None, blip_fill_elem=None)
        assert result["css_filter"] == ""
        assert result["transforms"] == []
        assert result["opacity"] is None
        assert result["box_reflect"] is None
        assert result["mask_image"] is None
        assert result["derivatives_needed"] == []
        assert result["warnings"] == []
