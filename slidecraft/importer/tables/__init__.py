"""Table extraction layer — Layer 4 of the PPTX → Slidev importer.

PPT tables live inside a ``<p:graphicFrame>`` whose ``<a:graphicData>`` URI
is ``http://schemas.openxmlformats.org/drawingml/2006/table``. The frame
carries position + size; the inner ``<a:tbl>`` carries grid columns,
row heights, and cells.

Each cell has:
  - ``<a:txBody>`` — same text-run model as placeholders/shapes
  - ``<a:tcPr>`` — per-cell anchor, padding, fill, and four edge borders
    (``<a:lnL>``/``<a:lnR>``/``<a:lnT>``/``<a:lnB>``) plus two diagonals
    (``<a:lnTlToBr>``/``<a:lnBlToTr>``) — diagonals not currently emitted

Out of scope for v1:
  - Merged cells (``gridSpan`` / ``rowSpan`` / ``vMerge`` / ``hMerge``)
  - Banded rows / banded columns / table style references
  - Diagonal borders
"""
from __future__ import annotations
