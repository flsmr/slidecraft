#!/usr/bin/env python
"""Deterministic, extraction-only source conversion of a deck's input material.

Reads a deck's ``input/`` (skipping ``input/processed/``) and writes one
converted source record per file into ``sources/``. No LLM, no vision — pure
extraction, so the pipeline's expensive judgement stays in the miners.

Per input file:
  * PDF  -> paged markdown text (pymupdf4llm, page_chunks) + embedded images
           extracted with PyMuPDF to ``public/extracted/`` (Slidev serves
           ``public/`` at the site root, so a slide references the image as the
           root-absolute URL ``/extracted/<file>.png``). Each image carries
           its single nearest text block (smallest vertical gap from the image
           rect's top or bottom edge) as ``context_text`` — the figure's
           attribution anchor. No regex/caption matching (see
           docs/source-conversion-limitations.md).
  * .md/.txt -> one page/text block, type "text".

Idempotent: an input whose ``sources/<slug>.json`` already exists is skipped.

Deck root is resolved from ``--deck`` or by walking up from CWD for
``deck-context.json`` (same as km.py). Reads nothing but the inputs; writes
only under ``sources/`` and ``public/extracted/`` plus one line per run to
``logs/actions.jsonl``.

CLI: ``python source_converter.py [--deck ROOT]``
"""
import argparse, json, re, sys, time
from pathlib import Path

PDF_EXT = {".pdf"}
TEXT_EXT = {".md", ".txt"}

# ---------- deck root + stamp (mirrors km.py) ----------

def find_deck_root(explicit: str | None) -> Path:
    start = Path(explicit).resolve() if explicit else Path.cwd()
    for p in [start, *start.parents]:
        if (p / "deck-context.json").exists():
            return p
    sys.exit("ERROR: no deck-context.json found from " + str(start))

def stamp(root: Path) -> str:
    """Millisecond stamp, unique against existing source records."""
    t = time.time()
    base = time.strftime("%Y%m%d-%H%M%S-", time.localtime(t)) + f"{int((t%1)*1000):03d}"
    s, n = base, 1
    while (root / "sources" / f"{s}.json").exists():
        s = f"{base}-{n}"; n += 1
    return s

def slugify(name: str) -> str:
    stem = Path(name).stem
    s = re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-")
    return (s or "source")[:60]

def log(root: Path, agent: str, action: str, **payload):
    (root / "logs").mkdir(exist_ok=True)
    with (root / "logs" / "actions.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                            "agent": agent, "action": action, **payload}) + "\n")

def iso_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")

# ---------- image extraction ----------

def _block_text(block: dict) -> str:
    """Flatten a get_text('dict') text block into a single string."""
    parts = []
    for line in block.get("lines", []):
        for span in line.get("spans", []):
            parts.append(span.get("text", ""))
    return re.sub(r"[ \t]+", " ", " ".join(parts)).strip()

def _nearest_block_text(page, rect) -> str:
    """Text of the block with the smallest vertical gap to the image rect.

    Gap is measured from the image rect's top OR bottom edge to a block's
    nearest edge — whichever is smaller. No regex, no caption matching:
    the single nearest text block only (see source-conversion-limitations.md).
    """
    best_gap, best_text = None, ""
    for block in page.get_text("dict").get("blocks", []):
        if block.get("type", 0) != 0:  # 0 = text block; skip image blocks
            continue
        text = _block_text(block)
        if not text:
            continue
        bx0, by0, bx1, by1 = block["bbox"]
        gap_top = abs(rect.y0 - by1)     # image top edge vs block bottom
        gap_bottom = abs(by0 - rect.y1)  # image bottom edge vs block top
        gap = min(gap_top, gap_bottom)
        if best_gap is None or gap < best_gap:
            best_gap, best_text = gap, text
    return best_text

def _extract_images(fitz, doc, slug: str, extracted_dir: Path) -> list[dict]:
    """Extract embedded raster images; one record each with nearest-block context."""
    records = []
    for pno in range(doc.page_count):
        page = doc[pno]
        page_no = pno + 1
        img_idx = 0
        for info in page.get_images(full=True):
            xref = info[0]
            try:
                pix = fitz.Pixmap(doc, xref)
            except Exception:
                continue
            # Convert CMYK / alpha to plain RGB so PNG save always works.
            if pix.alpha or (pix.n - pix.alpha) >= 4 or pix.colorspace is None:
                try:
                    pix = fitz.Pixmap(fitz.csRGB, pix)
                except Exception:
                    continue
            img_idx += 1
            fname = f"{slug}-p{page_no}-img{img_idx}.png"
            out_path = extracted_dir / fname
            try:
                pix.save(str(out_path))
            except Exception:
                img_idx -= 1
                continue
            # Nearest text block for the first placement of this image.
            context_text = ""
            try:
                rects = page.get_image_rects(xref)
                if rects:
                    context_text = _nearest_block_text(page, rects[0])
            except Exception:
                pass
            records.append({
                "image_source_id": f"{slug}-p{page_no}-img{img_idx}",
                # Root-absolute URL: Slidev serves public/ at the site root, so
                # public/extracted/<file>.png is referenced as /extracted/<file>.png.
                "path": f"/extracted/{fname}",
                "page": page_no,
                "context_text": context_text,
            })
    return records

# ---------- per-file conversion ----------

def convert_pdf(root: Path, path: Path, slug: str) -> dict:
    import pymupdf4llm
    import fitz

    chunks = pymupdf4llm.to_markdown(str(path), page_chunks=True)
    pages = []
    for chunk in chunks:
        page_no = chunk["metadata"]["page_number"]  # 1-based; NOT "page"
        pages.append({"page": page_no, "text": chunk.get("text", "")})

    extracted_dir = root / "public" / "extracted"
    extracted_dir.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(str(path))
    try:
        images = _extract_images(fitz, doc, slug, extracted_dir)
    finally:
        doc.close()

    return {
        "source_id": stamp(root),
        "original_file": path.name,
        "type": "pdf",
        "converted_at": iso_now(),
        "pages": pages,
        "images": images,
    }

def convert_text(root: Path, path: Path, slug: str) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    return {
        "source_id": stamp(root),
        "original_file": path.name,
        "type": "text",
        "converted_at": iso_now(),
        "pages": [{"page": 1, "text": text}],
        "images": [],
    }

# ---------- deck walk ----------

def input_files(root: Path) -> list[Path]:
    in_dir = root / "input"
    if not in_dir.is_dir():
        return []
    out = []
    for p in sorted(in_dir.rglob("*")):
        if not p.is_file():
            continue
        # Skip the processed/ registry.
        if "processed" in {part.lower() for part in p.relative_to(in_dir).parts[:-1]}:
            continue
        if p.suffix.lower() in PDF_EXT | TEXT_EXT:
            out.append(p)
    return out

def cmd_convert(root: Path, a):
    (root / "sources").mkdir(exist_ok=True)
    files = input_files(root)
    written, skipped, errors = [], [], []
    for path in files:
        slug = slugify(path.name)
        src_path = root / "sources" / f"{slug}.json"
        if src_path.exists():
            skipped.append(slug)
            continue
        try:
            ext = path.suffix.lower()
            if ext in PDF_EXT:
                rec = convert_pdf(root, path, slug)
            else:
                rec = convert_text(root, path, slug)
        except Exception as exc:
            errors.append({"file": path.name, "error": str(exc)})
            continue
        src_path.write_text(json.dumps(rec, indent=2, ensure_ascii=False),
                            encoding="utf-8")
        written.append({"slug": slug, "pages": len(rec["pages"]),
                        "images": len(rec["images"])})
        log(root, "source-converter", "convert", source=slug,
            pages=len(rec["pages"]), images=len(rec["images"]))
    print(json.dumps({"written": written, "skipped": skipped, "errors": errors},
                     indent=2, ensure_ascii=False))
    if errors:
        sys.exit(2)

# ---------- dispatch ----------

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--deck")
    a = ap.parse_args()
    root = find_deck_root(a.deck)
    cmd_convert(root, a)

if __name__ == "__main__":
    main()
