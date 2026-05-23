"""Non-placeholder text-box layer for the PPTX → Slidev importer.

Scope: <p:sp> elements WITHOUT <p:ph> that carry a <p:txBody> containing
non-empty text. Located at any cascade level (master, slideLayout, slide).

OUT of scope (handled by other layers):
- Pure shapes with no text  (future shape layer)
- Pictures                  (Layer 2 / pictures/)
- <p:grpSp> group shapes
- <p:cxnSp> connectors
- Standalone <a:custGeom> freeforms
- Gradient fills, shadow/glow/reflection effects

Modules:
  model   — TextShape, BorderProps dataclasses
  parse   — walk_text_shapes(): spTree → list[TextShape]
  emit    — render_text_shape_host(): TextShape → Vue/HTML fragment

Property cascade reuses inheritance.resolve_placeholder() unchanged, called
with ph_type=None (→ master <a:otherStyle>), layout_ph=None, master_ph=None.

See ARCHITECTURE.md "Non-placeholder text boxes" section for full design.
"""
from __future__ import annotations
