# Source conversion — known limitations (accepted for v1)

Source conversion (`source_converter.py`) is deterministic, extraction-only (no LLM/vision). These cases are known
gaps. Each is either accepted as-is for v1 or has a noted future fix. Nothing here blocks
the core path (well-behaved single-column PDFs with embedded raster figures).

## Image extraction

| # | Limitation | Status | Future fix |
|---|---|---|---|
| L1 | **Vector-drawn figures** — charts drawn as paths (not embedded raster) return nothing from `page.get_images()`. Rare in textbooks, common in papers exported from R/matplotlib/TikZ. | Accepted; figure is silently missed. | Render the figure's page region to PNG and mine that. |
| L2 | **Multi-column layouts** — "nearest text block above/below" assumes a single column; across columns the adjacency is meaningless. This course book is single-column. | Accepted; wrong caption possible on 2-column sources. | Column-aware banding before nearest-block search. |
| L3 | **Tiled images** — one visual figure sometimes arrives as several `xref`s; adjacency then mines fragments. | Accepted; may yield fragment nuggets. | Merge adjacent image rects into one figure before mining. |
| L4 | **Full-page backgrounds / logos** — adjacency returns garbage text. | Mitigated downstream: the image-miner's "decorative → return `[]`" rule drops these at mining time. | — |
| L5 | **Scanned PDFs** — no text layer → no blocks, no caption, no text nuggets. | Accepted; out of scope. | OCR (see below). |

## Caption / context capture (Round 9 decision)

Each image source carries the **single nearest text block**, measured as the smallest
vertical gap from the image rectangle's top or bottom edge (`page.get_text("dict")`
blocks vs `page.get_image_rects(xref)`). **No regex, no `Figure N:` matching** — the
variety across publishers and languages is too great, and the text layer is often
imperfect. The nearest block is passed to the image-miner as context and is the figure's
attribution anchor. It can be wrong (L2), which is why attribution is context, not a
verified citation.

## Future direction (parked)

**Mistral OCR → Markdown.** A likely future change: run source PDFs through Mistral OCR,
which emits Markdown with embedded images as base64. That would replace the pymupdf text
split *and* the image-extraction/adjacency logic in one step (images arrive already
associated with their surrounding markdown), removing L1–L3 and L5 at once. Not built;
recorded so the source-conversion interface is kept swappable.
