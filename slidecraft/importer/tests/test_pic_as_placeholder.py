"""Regression tests for the ``<p:pic>``-as-picture-placeholder bug.

OOXML lets a ``<p:pic>`` carry a ``<p:ph>`` reference inside its
``<p:nvPicPr>/<p:nvPr>`` — that's how PowerPoint stores a picture
placeholder whose default fill has been overridden with a specific
image on the slide. The IU template's slides 19 and 20 use this form
for their small icons.

The bug we're guarding against: ``_parse_pic`` used to always set
``is_placeholder=False``, so:
  * The slide's ``<p:pic>`` was emitted as a free picture at the
    slide's coordinates (the small icon position).
  * The placeholder idx never landed in ``slide_ph_idxes``, so the
    layout's matching idx=42 picture placeholder was inherited and
    emitted as a SECOND picture at the layout's coordinates (the
    larger icon position).
  * User saw the same icon doubled — once small, once large.
"""
from __future__ import annotations

from lxml import etree

from slidecraft.importer.parse import _parse_pic


_PIC_XML_TEMPLATES = {
    "free": """\
<p:pic xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
       xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
       xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <p:nvPicPr>
    <p:cNvPr id="9" name="Free Pic"/>
    <p:cNvPicPr/>
    <p:nvPr/>
  </p:nvPicPr>
  <p:blipFill>
    <a:blip r:embed=""/>
    <a:stretch><a:fillRect/></a:stretch>
  </p:blipFill>
  <p:spPr>
    <a:xfrm>
      <a:off x="0" y="0"/>
      <a:ext cx="2000000" cy="2000000"/>
    </a:xfrm>
  </p:spPr>
</p:pic>
""",
    "placeholder_pic": """\
<p:pic xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
       xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
       xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <p:nvPicPr>
    <p:cNvPr id="19" name="Bildplatzhalter 18"/>
    <p:cNvPicPr/>
    <p:nvPr>
      <p:ph type="pic" sz="quarter" idx="42"/>
    </p:nvPr>
  </p:nvPicPr>
  <p:blipFill>
    <a:blip r:embed=""/>
    <a:stretch><a:fillRect/></a:stretch>
  </p:blipFill>
  <p:spPr>
    <a:xfrm>
      <a:off x="769220" y="3459220"/>
      <a:ext cx="1007995" cy="1007995"/>
    </a:xfrm>
  </p:spPr>
</p:pic>
""",
}


class _StubPart:
    """Minimal slide-part stub — _resolve_blip_asset_ref tolerates rels=None."""
    rels = {}


class TestPicAsPlaceholder:
    def test_free_pic_remains_free_picture(self):
        el = etree.fromstring(_PIC_XML_TEMPLATES["free"])
        pic = _parse_pic(el, _StubPart(), order_index=0)
        assert pic is not None
        assert pic.is_placeholder is False
        assert pic.ph_idx is None

    def test_pic_with_ph_reference_becomes_placeholder(self):
        """The regression target: <p:pic> with <p:ph idx="42"/> must
        surface as is_placeholder=True with ph_idx=42 so the layout's
        matching idx=42 placeholder doesn't get inherited as a duplicate."""
        el = etree.fromstring(_PIC_XML_TEMPLATES["placeholder_pic"])
        pic = _parse_pic(el, _StubPart(), order_index=0)
        assert pic is not None
        assert pic.is_placeholder is True
        assert pic.ph_idx == 42

    def test_pic_with_ph_no_idx_becomes_placeholder_with_none_idx(self):
        """A <p:ph> without idx attribute is technically the "default"
        placeholder slot (idx defaults to 0 in PPT). We accept this
        edge case but surface ph_idx as None so the dedup logic can
        decide what to do — emitting at all is better than crashing."""
        xml = _PIC_XML_TEMPLATES["placeholder_pic"].replace(
            'idx="42"', ''
        ).replace(
            'sz="quarter" ', '',
        )
        el = etree.fromstring(xml)
        pic = _parse_pic(el, _StubPart(), order_index=0)
        assert pic is not None
        assert pic.is_placeholder is True
        assert pic.ph_idx is None
