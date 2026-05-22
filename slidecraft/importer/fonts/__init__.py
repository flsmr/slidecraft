"""Fonts pipeline for PPTX → Slidev importer.

Resolves typefaces referenced in a PPTX through a 4-stage pipeline
(embedded → Google Fonts → metric-substitute → generic fallback)
and writes font binaries + manifest.json + @font-face CSS.
"""
from .manifest import resolve_fonts, strip_weight_suffix

__all__ = ["resolve_fonts", "strip_weight_suffix"]
