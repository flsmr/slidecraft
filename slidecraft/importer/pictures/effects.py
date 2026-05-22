"""Parse PPT picture effect XML into a structured dict consumed by the emit layer.

Handles elements inside ``<p:spPr>`` (shape properties) and ``<a:blipFill>``
(blip fill) and converts them to CSS filter strings, transform lists, and
derivative work orders for effects that cannot be expressed purely in CSS.
"""
from __future__ import annotations

import math
from typing import Any

# ---------------------------------------------------------------------------
# Namespace constants
# ---------------------------------------------------------------------------

_NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"

def _atag(local: str) -> str:
    """Return a Clark-notation tag for a drawingml element."""
    return f"{{{_NS_A}}}{local}"


# ---------------------------------------------------------------------------
# Unit conversion
# ---------------------------------------------------------------------------

EMU_PER_PX: int = 9525  # 1 px = 9525 EMU at 96 DPI (standard PPT)


def _emu_to_px(emu: int | float) -> float:
    """Convert EMU (English Metric Units) to CSS pixels."""
    return emu / EMU_PER_PX


def _60ths_to_deg(sixty_thousandths: int | float) -> float:
    """Convert PPT's 60000ths-of-a-degree unit to decimal degrees."""
    return sixty_thousandths / 60_000.0


# ---------------------------------------------------------------------------
# Color helpers
# ---------------------------------------------------------------------------

def _parse_srgb_clr(elem: Any) -> tuple[str | None, list[str]]:
    """Return ``(css_color, warnings)`` from an ``<a:srgbClr>`` element.

    If the element is not ``<a:srgbClr>`` (e.g. schemeClr, sysClr) the color
    cannot be resolved here and a warning is emitted instead.

    Args:
        elem: An lxml element that should be ``<a:srgbClr>``.

    Returns:
        A two-tuple ``(css_color_string, warnings)``.  *css_color_string* is
        ``None`` when the color cannot be resolved.
    """
    if elem is None:
        return None, []

    if elem.tag != _atag("srgbClr"):
        return None, ["unresolved_color"]

    hex_val: str = elem.get("val", "000000")
    r = int(hex_val[0:2], 16)
    g = int(hex_val[2:4], 16)
    b = int(hex_val[4:6], 16)

    # Alpha child element (if present)
    alpha_elem = elem.find(_atag("alpha"))
    if alpha_elem is not None:
        alpha_raw = int(alpha_elem.get("val", "100000"))
        a = alpha_raw / 100_000.0
        return f"rgba({r},{g},{b},{a:.3f})", []

    return f"rgb({r},{g},{b})", []


# ---------------------------------------------------------------------------
# blipFill effect parsers
# ---------------------------------------------------------------------------

def _parse_blip_fill(
    blip_fill_elem: Any,
) -> tuple[list[str], float | None, list[dict], list[str]]:
    """Parse ``<a:blipFill>`` into filter parts, opacity, derivatives, warnings.

    Returns:
        ``(filter_parts, opacity, derivatives_needed, warnings)``
    """
    filter_parts: list[str] = []
    opacity: float | None = None
    derivatives: list[dict] = []
    warnings: list[str] = []

    if blip_fill_elem is None:
        return filter_parts, opacity, derivatives, warnings

    # -- <a:blip> child effects ------------------------------------------------
    blip = blip_fill_elem.find(_atag("blip"))
    if blip is not None:
        # Luminance: <a:lum bright="" contrast="" />
        lum = blip.find(_atag("lum"))
        if lum is not None:
            bright_raw = int(lum.get("bright", "0"))
            contrast_raw = int(lum.get("contrast", "0"))
            # PPT values are in thousandths of percent (100 000 = +100%).
            # CSS brightness(1.0) = neutral; +20 000 → CSS brightness(1.2)
            bright_css = 1.0 + bright_raw / 100_000.0
            contrast_css = 1.0 + contrast_raw / 100_000.0
            filter_parts.append(f"brightness({bright_css:.4f})")
            filter_parts.append(f"contrast({contrast_css:.4f})")

        # Alpha modifier: <a:alphaModFix amt="" />
        alpha_mod = blip.find(_atag("alphaModFix"))
        if alpha_mod is not None:
            amt_raw = int(alpha_mod.get("amt", "100000"))
            opacity = amt_raw / 100_000.0

        # Grayscale: <a:grayscl/>
        grayscl = blip.find(_atag("grayscl"))
        if grayscl is not None:
            filter_parts.append("grayscale(1)")

        # Bi-level (threshold): <a:biLevel thresh="" />
        bi_level = blip.find(_atag("biLevel"))
        if bi_level is not None:
            # Approximated by full grayscale + extreme contrast
            filter_parts.append("grayscale(1)")
            filter_parts.append("contrast(1000)")

        # Blur: <a:blur rad="" />
        blur = blip.find(_atag("blur"))
        if blur is not None:
            rad_emu = int(blur.get("rad", "0"))
            rad_px = _emu_to_px(rad_emu)
            filter_parts.append(f"blur({rad_px:.2f}px)")

        # Duotone: <a:duotone><a:srgbClr val="..."/><a:srgbClr val="..."/></a:duotone>
        duotone = blip.find(_atag("duotone"))
        if duotone is not None:
            clr_elems = list(duotone)
            c1: str | None = None
            c2: str | None = None
            color_warnings: list[str] = []

            if len(clr_elems) >= 1:
                c1_str, w1 = _parse_srgb_clr(clr_elems[0])
                c1 = c1_str
                color_warnings.extend(w1)
            if len(clr_elems) >= 2:
                c2_str, w2 = _parse_srgb_clr(clr_elems[1])
                c2 = c2_str
                color_warnings.extend(w2)

            if "unresolved_color" in color_warnings:
                warnings.append("duotone_color_unresolved")
            else:
                derivatives.append({
                    "op": "duotone",
                    "params": {"c1": c1, "c2": c2},
                })

    # -- <a:srcRect> (crop) ---------------------------------------------------
    src_rect = blip_fill_elem.find(_atag("srcRect"))
    if src_rect is not None:
        l = int(src_rect.get("l", "0"))
        t = int(src_rect.get("t", "0"))
        r = int(src_rect.get("r", "0"))
        b = int(src_rect.get("b", "0"))
        derivatives.append({
            "op": "crop",
            "params": {"l": l, "t": t, "r": r, "b": b},
        })

    # -- <a:tile> (tiled fill) ------------------------------------------------
    tile = blip_fill_elem.find(_atag("tile"))
    if tile is not None:
        warnings.append("tiled_fill_unsupported")

    return filter_parts, opacity, derivatives, warnings


# ---------------------------------------------------------------------------
# spPr effect parsers
# ---------------------------------------------------------------------------

def _parse_sp_pr(
    sp_pr_elem: Any,
) -> tuple[list[str], list[str], str | None, str | None, list[dict], list[str]]:
    """Parse ``<p:spPr>`` into filter parts, transforms, mask, box_reflect, derivatives, warnings.

    Returns:
        ``(filter_parts, transforms, mask_image, box_reflect, derivatives_needed, warnings)``
    """
    filter_parts: list[str] = []
    transforms: list[str] = []
    mask_image: str | None = None
    box_reflect: str | None = None
    derivatives: list[dict] = []
    warnings: list[str] = []

    if sp_pr_elem is None:
        return filter_parts, transforms, mask_image, box_reflect, derivatives, warnings

    # -- <a:xfrm> transforms --------------------------------------------------
    xfrm = sp_pr_elem.find(_atag("xfrm"))
    if xfrm is not None:
        flip_h = xfrm.get("flipH", "0") == "1"
        flip_v = xfrm.get("flipV", "0") == "1"
        rot_raw = xfrm.get("rot")

        # Order: scale (flip) first, then rotate — CSS applies right-to-left
        # matching PPT's behaviour (flip THEN rotate).
        if flip_h:
            transforms.append("scaleX(-1)")
        if flip_v:
            transforms.append("scaleY(-1)")
        if rot_raw is not None:
            rot_deg = _60ths_to_deg(int(rot_raw))
            transforms.append(f"rotate({rot_deg:.4f}deg)")

    # -- <a:effectLst> --------------------------------------------------------
    effect_lst = sp_pr_elem.find(_atag("effectLst"))
    if effect_lst is not None:
        # Outer shadow: <a:outerShdw blurRad="" dist="" dir=""> + color child
        outer_shdw = effect_lst.find(_atag("outerShdw"))
        if outer_shdw is not None:
            blur_rad_emu = int(outer_shdw.get("blurRad", "0"))
            dist_emu = int(outer_shdw.get("dist", "0"))
            dir_raw = int(outer_shdw.get("dir", "0"))

            blur_px = _emu_to_px(blur_rad_emu)
            dist_px = _emu_to_px(dist_emu)

            # PPT dir is in 60000ths of a degree, measured clockwise from right
            # (East = 0°, South = 90°, West = 180°, North = 270°).
            # PPT's Y-axis points down, so:
            #   X offset = dist * cos(dir)  [positive = right]
            #   Y offset = dist * sin(dir)  [positive = down — PPT's downward Y matches CSS]
            # We convert to radians for math.cos/sin.
            dir_deg = _60ths_to_deg(dir_raw)
            dir_rad = math.radians(dir_deg)
            x_px = dist_px * math.cos(dir_rad)
            y_px = dist_px * math.sin(dir_rad)

            color_elem = outer_shdw.find(_atag("srgbClr"))
            if color_elem is None:
                # Try other color types (will fail resolution)
                color_children = list(outer_shdw)
                color_elem = color_children[0] if color_children else None

            css_color, color_warns = _parse_srgb_clr(color_elem)
            if "unresolved_color" in color_warns:
                warnings.extend(color_warns)
            else:
                color_str = css_color or "rgba(0,0,0,0.5)"
                filter_parts.append(
                    f"drop-shadow({x_px:.2f}px {y_px:.2f}px {blur_px:.2f}px {color_str})"
                )

        # Glow: <a:glow rad=""> + color child → drop-shadow(0 0 Rpx color)
        glow = effect_lst.find(_atag("glow"))
        if glow is not None:
            rad_emu = int(glow.get("rad", "0"))
            rad_px = _emu_to_px(rad_emu)

            color_elem = glow.find(_atag("srgbClr"))
            if color_elem is None:
                color_children = list(glow)
                color_elem = color_children[0] if color_children else None

            css_color, color_warns = _parse_srgb_clr(color_elem)
            if "unresolved_color" in color_warns:
                warnings.extend(color_warns)
            else:
                color_str = css_color or "rgba(0,0,0,0.5)"
                filter_parts.append(
                    f"drop-shadow(0 0 {rad_px:.2f}px {color_str})"
                )

        # Inner shadow: <a:innerShdw> → placeholder for emit layer
        inner_shdw = effect_lst.find(_atag("innerShdw"))
        if inner_shdw is not None:
            mask_image = "__inner_shadow__"
            warnings.append("inner_shadow_approximation")

        # Soft edge: <a:softEdge rad="" /> → derivative
        soft_edge = effect_lst.find(_atag("softEdge"))
        if soft_edge is not None:
            rad_emu = int(soft_edge.get("rad", "0"))
            rad_px = _emu_to_px(rad_emu)
            derivatives.append({
                "op": "soft_edge",
                "params": {"radius_px": rad_px},
            })

        # Reflection: <a:reflection> → box_reflect approximation
        reflection = effect_lst.find(_atag("reflection"))
        if reflection is not None:
            box_reflect = (
                "below 0 linear-gradient(transparent, rgba(0,0,0,0.35))"
            )
            warnings.append("reflection_approximation")

    # -- <a:scene3d> + <a:sp3d> (3-D rotation) --------------------------------
    scene3d = sp_pr_elem.find(_atag("scene3d"))
    sp3d = sp_pr_elem.find(_atag("sp3d"))

    if scene3d is not None or sp3d is not None:
        # Extract camera rotation from <a:scene3d><a:camera><a:rot rev="" lat="" lon=""/>
        rev_deg = lat_deg = lon_deg = 0.0

        if scene3d is not None:
            camera = scene3d.find(_atag("camera"))
            if camera is not None:
                rot_3d = camera.find(_atag("rot"))
                if rot_3d is not None:
                    rev_raw = rot_3d.get("rev")
                    lat_raw = rot_3d.get("lat")
                    lon_raw = rot_3d.get("lon")
                    if rev_raw is not None:
                        rev_deg = _60ths_to_deg(int(rev_raw))
                    if lat_raw is not None:
                        lat_deg = _60ths_to_deg(int(lat_raw))
                    if lon_raw is not None:
                        lon_deg = _60ths_to_deg(int(lon_raw))

        transforms.append(
            f"perspective(2000px) rotateX({lat_deg:.4f}deg)"
            f" rotateY({lon_deg:.4f}deg) rotateZ({rev_deg:.4f}deg)"
        )

        # Bevel / extrusion warnings
        if sp3d is not None:
            if sp3d.find(_atag("bevelT")) is not None:
                warnings.append("skipped_3d_bevel")
            if sp3d.find(_atag("extrusionClr")) is not None:
                warnings.append("skipped_3d_extrusion")

    return filter_parts, transforms, mask_image, box_reflect, derivatives, warnings


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_effects(
    sp_pr_elem: Any,
    blip_fill_elem: Any,
) -> dict:
    """Parse PPT picture effect XML into a structured dict for the emit layer.

    Converts drawingml effect attributes from ``<p:spPr>`` and ``<a:blipFill>``
    into CSS-ready values and derivative work orders for effects that require
    image processing.

    Args:
        sp_pr_elem:    lxml element for ``<p:spPr>``.  May be *None*.
        blip_fill_elem: lxml element for ``<a:blipFill>``.  May be *None*.

    Returns:
        A dict with the following keys:

        ``css_filter`` (str)
            Space-joined CSS ``filter`` function list, e.g.
            ``'grayscale(1) brightness(0.8) drop-shadow(2px 2px 4px rgba(0,0,0,0.5))'``.
            Empty string when no filter effects are present.

        ``transforms`` (list[str])
            Ordered list of CSS transform functions, e.g.
            ``['scaleX(-1)', 'rotate(15.0000deg)']``.  Scale/flip entries come
            before rotation, mirroring PPT's application order.

        ``opacity`` (float | None)
            Element-wide opacity derived from ``<a:alphaModFix amt="…"/>``.
            *None* when the element is absent.

        ``box_reflect`` (str | None)
            Value for the ``-webkit-box-reflect`` CSS property, set when a
            ``<a:reflection>`` element is detected.  *None* otherwise.

        ``mask_image`` (str | None)
            Set to ``'__inner_shadow__'`` when an inner shadow is present as a
            signal for the emit layer to handle the approximation.  *None*
            otherwise.

        ``derivatives_needed`` (list[dict])
            Work orders for effects that require image pre-processing.  Each
            entry has ``'op'`` (``'crop'``, ``'duotone'``, or ``'soft_edge'``)
            and ``'params'`` (op-specific dict).

        ``warnings`` (list[str])
            Diagnostic strings for effects that were approximated, skipped, or
            could not be resolved.
    """
    all_filter_parts: list[str] = []
    all_transforms: list[str] = []
    opacity: float | None = None
    box_reflect: str | None = None
    mask_image: str | None = None
    all_derivatives: list[dict] = []
    all_warnings: list[str] = []

    # Parse blipFill (image-level effects: lum, grayscale, blur, duotone, crop)
    bf_filters, opacity, bf_derivatives, bf_warnings = _parse_blip_fill(blip_fill_elem)
    all_filter_parts.extend(bf_filters)
    all_derivatives.extend(bf_derivatives)
    all_warnings.extend(bf_warnings)

    # Parse spPr (shape-level effects: shadow, glow, transforms, 3D)
    sp_filters, sp_transforms, mask_image, box_reflect, sp_derivatives, sp_warnings = (
        _parse_sp_pr(sp_pr_elem)
    )
    all_filter_parts.extend(sp_filters)
    all_transforms.extend(sp_transforms)
    all_derivatives.extend(sp_derivatives)
    all_warnings.extend(sp_warnings)

    return {
        "css_filter": " ".join(all_filter_parts),
        "transforms": all_transforms,
        "opacity": opacity,
        "box_reflect": box_reflect,
        "mask_image": mask_image,
        "derivatives_needed": all_derivatives,
        "warnings": all_warnings,
    }
