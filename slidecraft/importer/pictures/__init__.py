"""Picture-extraction pipeline for the PPTX → Slidev importer.

Modules:
  formats   — classify image bytes by format and fidelity
  extract   — walk pptx zip and copy media to theme/public/assets/
  manifest  — read/write theme/public/assets/manifest.json
"""
from __future__ import annotations
