# -*- coding: utf-8 -*-
"""Extract a course-book chapter PDF into the grounded cache a sprint deck is built from.

Generalized from the SPRINT_2 build. Produces, under <deck>/resources/:
  <prefix>_text_full.txt        full text, page-marked, UTF-8
  section_<slug>.txt            one file per TOC section (the grounding for each author)
  <prefix>_extract.json         manifest: sections, figures, captions, source lines, study goals
and, under <deck>/public/figures/:
  <prefix>_fig_NN.<ext>         deduped, non-tiny figures in page order

Usage:
  python extract_chapter.py --deck "<deck dir>" --pdf course_book_chapter_2.pdf --prefix ch2
"""
import os, io, re, json, argparse

import fitz  # PyMuPDF


def slug(s):
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")[:40]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--deck", required=True, help="deck root directory")
    ap.add_argument("--pdf", required=True, help="chapter PDF filename inside <deck>/resources/")
    ap.add_argument("--prefix", default="ch", help="figure/manifest prefix, e.g. ch2")
    ap.add_argument("--min-fig", type=int, default=120, help="skip figures where max(w,h) < this")
    args = ap.parse_args()

    deck = args.deck
    res = os.path.join(deck, "resources")
    figdir = os.path.join(deck, "public", "figures")
    os.makedirs(figdir, exist_ok=True)
    pdf = os.path.join(res, args.pdf)

    doc = fitz.open(pdf)
    n = doc.page_count

    # ---- sections from the table of contents ----
    toc = doc.get_toc()
    lvl2 = [(t, p) for (lvl, t, p) in toc if lvl == 2]
    entries = lvl2 if lvl2 else [(t, p) for (lvl, t, p) in toc if lvl == 1]
    sections = []
    for i, (title, start) in enumerate(entries):
        end = (entries[i + 1][1] - 1) if i + 1 < len(entries) else n
        sections.append({"title": title, "page_start": start, "page_end": end})
    if entries and entries[0][1] > 1:
        sections.insert(0, {"title": "Unit intro and study goals",
                            "page_start": 1, "page_end": entries[0][1] - 1})
    if not sections:  # no TOC at all
        sections = [{"title": "Full chapter", "page_start": 1, "page_end": n}]

    # ---- text (UTF-8) full + per section ----
    page_texts = [doc[p].get_text() for p in range(n)]
    full_text = "".join(f"\n\n===== PAGE {p+1} =====\n{page_texts[p]}" for p in range(n))
    io.open(os.path.join(res, f"{args.prefix}_text_full.txt"), "w", encoding="utf-8").write(full_text)

    for sec in sections:
        a, b = sec["page_start"], sec["page_end"]
        txt = "".join(page_texts[a - 1:b])
        sec["word_count"] = len(txt.split())
        fn = f"section_{slug(sec['title'])}.txt"
        sec["text_file"] = fn
        io.open(os.path.join(res, fn), "w", encoding="utf-8").write(f"# {sec['title']}  (pages {a}-{b})\n\n{txt}")

    # ---- figures: dedupe by xref, skip tiny ----
    seen, figs, idx = set(), [], 0
    for p in range(n):
        for img in doc[p].get_images(full=True):
            xref = img[0]
            if xref in seen:
                continue
            seen.add(xref)
            try:
                ext = doc.extract_image(xref)
            except Exception:
                continue
            w_, h_ = ext.get("width", 0), ext.get("height", 0)
            if max(w_, h_) < args.min_fig:
                continue
            idx += 1
            e = ext.get("ext", "png")
            name = f"{args.prefix}_fig_{idx:02d}.{'jpeg' if e in ('jpg', 'jpeg') else e}"
            open(os.path.join(figdir, name), "wb").write(ext["image"])
            figs.append({"file": name, "page": p + 1, "xref": xref, "width": w_, "height": h_})

    # ---- captions + printed Source lines + study goals ----
    captions = [re.sub(r"\s+", " ", c).strip()
                for c in re.findall(r"(Figure\s+\d+[:.\s].{0,160}?)(?:\n|$)", full_text, re.IGNORECASE)]
    sources = [re.sub(r"\s+", " ", s).strip()
               for s in re.findall(r"Source[:\s].{0,200}", full_text, re.IGNORECASE)]
    head = page_texts[0] + (page_texts[1] if n > 1 else "")
    m = re.search(r"STUDY GOALS(.{0,1200}?)(?:\n\s*\n|Introduction|\d\.\d)", head, re.IGNORECASE | re.DOTALL)
    study = re.sub(r"\s+\n", "\n", m.group(1)).strip() if m else ""

    manifest = {
        "pdf": args.pdf, "prefix": args.prefix, "pages": n,
        "sections": sections, "figures": figs, "figure_count": len(figs),
        "captions_found": captions, "source_lines_found": sources, "study_goals_raw": study,
    }
    io.open(os.path.join(res, f"{args.prefix}_extract.json"), "w", encoding="utf-8").write(
        json.dumps(manifest, ensure_ascii=False, indent=2))

    print(f"OK {args.prefix}: {len(sections)} sections, {len(figs)} figures, "
          f"{len(captions)} captions, {len(sources)} source-lines")
    for s in sections:
        print(f"  p{s['page_start']:>3}-{s['page_end']:<3} ({s['word_count']:>5}w) {s['title']} -> {s['text_file']}")


if __name__ == "__main__":
    main()
