"""Extract text and images from every PDF in a deck's ``resources/`` tree.

Slidecraft decks are scaffolded with a ``resources/`` folder where the user
drops source material — PDFs, images, notes. The authoring skill needs to
read this material to draft slides, but a single reference PDF can be
hundreds or thousands of pages. Loading those into an LLM directly burns
tokens for content the model will mostly skim.

This script does the heavy, *deterministic* lift once and writes a cache the
skill can consume cheaply:

* Per PDF, one directory under ``<deck>/.slidecraft/cache/pdf/<doc-slug>/``.
* Small PDFs (≤ 50 pages AND ≤ 50,000 chars) get a single ``text.md`` with
  the whole document, page-delimited.
* Large PDFs get a per-chapter split under ``text/`` plus a ``map.md`` that
  lists each chapter with its first ~200 words — the "table of contents
  with thumbnails" the skill can scan to decide which chapters to read in
  full.
* Embedded images go to ``images/`` deduped by SHA1; tiny icon-sized
  images are skipped.

The script is idempotent — if ``manifest.json.source_sha1`` matches the
on-disk PDF's SHA1, the PDF is skipped. Use ``--force`` to override.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import io
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, Sequence


# ---------------------------------------------------------------------------
# Constants — extraction thresholds
# ---------------------------------------------------------------------------

#: A PDF is "small" only when BOTH limits are satisfied. Either one being
#: exceeded promotes the PDF to the "large" tier (per-chapter split + map).
SMALL_TIER_MAX_PAGES = 50
SMALL_TIER_MAX_CHARS = 50_000

#: When a large PDF has no usable TOC, we synthesise chapters by slicing
#: every N pages. 20 keeps each chunk in a comfortable read-into-context
#: range while not exploding the chapter count on big books.
FALLBACK_SECTION_PAGES = 20

#: Words to copy from the start of each chapter into ``map.md``.
MAP_WORDS_PER_CHAPTER = 200


# ---------------------------------------------------------------------------
# Data classes — also serve as the manifest schema
# ---------------------------------------------------------------------------


@dataclass
class ImageEntry:
    """One extracted image, as recorded in ``manifest.json``."""

    path: str           # POSIX-style relative path under the doc cache dir
    page: int           # 1-indexed PDF page the image first appeared on
    bbox: list[float]   # [x0, y0, x1, y1] in PDF page coordinates
    sha1: str
    width: int
    height: int


@dataclass
class ChapterEntry:
    """One chapter for the large tier — keyed off TOC or synthetic slicing."""

    title: str
    file: str           # POSIX-style relative path, e.g. "text/ch-01.md"
    page_start: int     # 1-indexed
    page_end: int       # 1-indexed, inclusive
    word_count: int


@dataclass
class Manifest:
    """The on-disk ``manifest.json`` schema, one per PDF.

    Attributes are stable — downstream consumers (the authoring skill) read
    them directly. Renaming a field is a breaking change.
    """

    source: str                                  # POSIX-style path relative to deck root
    doc_slug: str
    size_tier: str                               # "small" | "large"
    page_count: int
    char_count: int
    extracted_at: str                            # ISO-8601 UTC, second precision, trailing Z
    source_sha1: str
    images: list[ImageEntry] = field(default_factory=list)
    chapters: list[ChapterEntry] = field(default_factory=list)  # large tier only

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Slug + hash helpers
# ---------------------------------------------------------------------------

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(name: str) -> str:
    """Return a deterministic, lowercase, hyphen-separated slug.

    Strips the file extension before slugifying so
    ``"2022_Richard Szeliski - Computer Vision 1.pdf"`` becomes
    ``"2022-richard-szeliski-computer-vision-1"``. Collapses runs of
    non-alphanumerics into a single hyphen and trims leading/trailing
    hyphens. An all-punctuation input collapses to ``"doc"``.
    """
    stem = Path(name).stem
    slug = _SLUG_RE.sub("-", stem.lower()).strip("-")
    return slug or "doc"


def make_unique_slug(base: str, taken: set[str]) -> str:
    """Return *base*, suffixed with ``-2``, ``-3``, … on collision."""
    if base not in taken:
        return base
    n = 2
    while f"{base}-{n}" in taken:
        n += 1
    return f"{base}-{n}"


def sha1_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha1()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def sha1_bytes(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


# ---------------------------------------------------------------------------
# Page-text helpers
# ---------------------------------------------------------------------------


def _page_text(page) -> str:  # pragma: no cover - thin wrapper around pymupdf
    """Return the page's plain text, or empty string if extraction yields nothing.

    No OCR fallback — empty text is recorded as such in the manifest's
    ``char_count`` and downstream consumers can decide what to do.
    """
    try:
        return page.get_text() or ""
    except Exception:
        return ""


def _format_small_text(doc) -> str:
    """Concatenate ``## Page N`` blocks for the small-tier ``text.md``."""
    parts: list[str] = []
    for i in range(doc.page_count):
        page = doc.load_page(i)
        parts.append(f"## Page {i + 1}\n\n{_page_text(page)}\n")
    # Leading blank line keeps the first ``##`` heading well-separated when
    # the file is rendered (some markdown renderers eat a heading that's
    # immediately at byte 0).
    return "\n".join(parts) + "\n"


def _count_words(text: str) -> int:
    """Whitespace-split word count. Matches what humans expect for prose."""
    return len(text.split())


def _first_n_words(text: str, n: int) -> str:
    words = text.split()
    if len(words) <= n:
        return " ".join(words)
    return " ".join(words[:n]) + "…"


# ---------------------------------------------------------------------------
# Chapter planning
# ---------------------------------------------------------------------------


@dataclass
class _ChapterPlan:
    """Internal pre-text-extraction record: where a chapter starts/ends."""

    title: str
    page_start: int   # 1-indexed, inclusive
    page_end: int     # 1-indexed, inclusive


def _plan_chapters_from_toc(toc: Sequence, page_count: int) -> list[_ChapterPlan]:
    """Build top-level chapter ranges from a pymupdf ``get_toc()`` result.

    pymupdf ``get_toc()`` returns ``[level, title, page]`` triples with
    ``page`` being 1-indexed. Only ``level == 1`` entries become chapters;
    a chapter's ``page_end`` is the page before the next level-1 entry (or
    the final page for the last chapter).

    Returns an empty list when no level-1 entries exist.
    """
    tops = [(t[1], t[2]) for t in toc if t and t[0] == 1]
    if not tops:
        return []
    plans: list[_ChapterPlan] = []
    for idx, (title, start) in enumerate(tops):
        if idx + 1 < len(tops):
            end = tops[idx + 1][1] - 1
        else:
            end = page_count
        # Clamp to valid range and ensure start <= end. Some PDFs have TOC
        # entries that point past the last page (corrupted exports); we
        # don't want a negative range to silently swallow the tail.
        start = max(1, min(start, page_count))
        end = max(start, min(end, page_count))
        plans.append(_ChapterPlan(title=title.strip() or f"Chapter {idx + 1}",
                                  page_start=start, page_end=end))
    return plans


def _plan_chapters_fallback(page_count: int,
                            pages_per_section: int = FALLBACK_SECTION_PAGES,
                            ) -> list[_ChapterPlan]:
    """Synthesise ``Section N`` chapters when no TOC exists."""
    plans: list[_ChapterPlan] = []
    start = 1
    idx = 1
    while start <= page_count:
        end = min(start + pages_per_section - 1, page_count)
        plans.append(_ChapterPlan(title=f"Section {idx}",
                                  page_start=start, page_end=end))
        start = end + 1
        idx += 1
    return plans


# ---------------------------------------------------------------------------
# Image extraction
# ---------------------------------------------------------------------------


def _extract_page_images(doc, page, page_number: int,
                         images_dir: Path,
                         seen_sha1: set[str],
                         min_dim: int,
                         ) -> list[ImageEntry]:
    """Write images embedded in *page* under ``images/page-NNN-fig-NN.<ext>``.

    Dedupe is by SHA1 of the raw image bytes: subsequent occurrences of the
    same bytes (e.g. a logo on every page) are silently skipped and not
    re-recorded. *seen_sha1* is mutated to reflect what's been written.

    Images smaller than *min_dim* on either axis are skipped — they're
    almost always icons or vector-fragment rasterisations.

    Returns the manifest entries for *new* images extracted from this page.
    """
    entries: list[ImageEntry] = []
    try:
        xref_list = page.get_images(full=True)
    except Exception:
        return entries

    fig_idx = 0
    for img_info in xref_list:
        # pymupdf's get_images entry layout:
        #   (xref, smask, width, height, bpc, colorspace, alt_cs, name,
        #    filter, referencer)
        xref = img_info[0]
        try:
            extracted = doc.extract_image(xref)
        except Exception:
            continue
        if not extracted:
            continue
        data: bytes = extracted.get("image", b"")
        ext: str = extracted.get("ext", "png") or "png"
        width: int = int(extracted.get("width") or 0)
        height: int = int(extracted.get("height") or 0)
        if not data or width < min_dim or height < min_dim:
            continue

        digest = sha1_bytes(data)
        if digest in seen_sha1:
            # Already on disk under a different page — don't write a copy,
            # and don't pollute the manifest with the duplicate location.
            continue
        seen_sha1.add(digest)

        fig_idx += 1
        fname = f"page-{page_number:03d}-fig-{fig_idx:02d}.{ext}"
        out_path = images_dir / fname
        out_path.write_bytes(data)

        # Bounding box on the page (PDF coordinates). pymupdf returns a
        # list of rects for each image placement; for the first reference
        # we record the first rect. Some PDFs don't surface a rect — fall
        # back to a zero bbox.
        bbox = [0.0, 0.0, 0.0, 0.0]
        try:
            rects = page.get_image_rects(xref)
            if rects:
                r = rects[0]
                bbox = [float(r.x0), float(r.y0), float(r.x1), float(r.y1)]
        except Exception:
            pass

        entries.append(ImageEntry(
            path=f"images/{fname}",
            page=page_number,
            bbox=bbox,
            sha1=digest,
            width=width,
            height=height,
        ))
    return entries


# ---------------------------------------------------------------------------
# Per-PDF extraction
# ---------------------------------------------------------------------------


def _iso_now() -> str:
    """UTC timestamp in ``YYYY-MM-DDTHH:MM:SSZ`` format — second precision."""
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False),
                    encoding="utf-8")


def extract_pdf(pdf_path: Path,
                deck_dir: Path,
                cache_root: Path,
                doc_slug: str,
                *,
                min_image_dim: int = 100,
                force: bool = False,
                ) -> tuple[str, Manifest | None]:
    """Extract one PDF into ``cache_root / doc_slug``.

    Args:
        pdf_path:       PDF file on disk.
        deck_dir:       Deck root (used to record ``manifest.source`` as a
                        POSIX-style path relative to the deck).
        cache_root:     ``<deck>/.slidecraft/cache/pdf`` — extraction lands
                        in a subdirectory named *doc_slug*.
        doc_slug:       Pre-uniquified slug for this PDF.
        min_image_dim:  Skip images smaller than this on either axis (px).
        force:          Re-extract even when the cached manifest's SHA1
                        matches the on-disk PDF.

    Returns:
        ``(status, manifest)`` where ``status`` is one of
        ``"extracted" | "cached" | "error"`` and ``manifest`` is the freshly
        written :class:`Manifest` on success (None on error or cached).
    """
    import fitz  # local import keeps top-level import-failure path simple

    out_dir = cache_root / doc_slug
    manifest_path = out_dir / "manifest.json"

    source_sha1 = sha1_file(pdf_path)

    # ----- idempotency check -------------------------------------------------
    if not force and manifest_path.exists():
        try:
            existing = json.loads(manifest_path.read_text(encoding="utf-8"))
            if existing.get("source_sha1") == source_sha1:
                return "cached", None
        except (OSError, json.JSONDecodeError):
            # Corrupted manifest — fall through and re-extract.
            pass

    # ----- fresh extraction --------------------------------------------------
    # Clear any prior contents to avoid stale chapter files / images leaking
    # through a re-run against a modified source.
    if out_dir.exists():
        for p in sorted(out_dir.rglob("*"), reverse=True):
            if p.is_file():
                p.unlink()
            elif p.is_dir():
                p.rmdir()
    out_dir.mkdir(parents=True, exist_ok=True)

    images_dir = out_dir / "images"
    images_dir.mkdir(exist_ok=True)

    doc = fitz.open(pdf_path)
    try:
        page_count = doc.page_count

        # First pass — collect per-page text + extract images. We need the
        # full text up front to (a) compute char_count for tier selection
        # and (b) slice into chapters without reopening the doc.
        page_texts: list[str] = []
        seen_sha1: set[str] = set()
        images: list[ImageEntry] = []
        for i in range(page_count):
            page = doc.load_page(i)
            page_texts.append(_page_text(page))
            images.extend(_extract_page_images(
                doc, page, i + 1, images_dir, seen_sha1,
                min_dim=min_image_dim,
            ))

        char_count = sum(len(t) for t in page_texts)
        toc = doc.get_toc() or []
    finally:
        doc.close()

    # ----- TOC sidecar -------------------------------------------------------
    _write_json(out_dir / "toc.json", toc)

    # ----- tier selection ----------------------------------------------------
    is_small = (page_count <= SMALL_TIER_MAX_PAGES
                and char_count <= SMALL_TIER_MAX_CHARS)
    size_tier = "small" if is_small else "large"

    chapters: list[ChapterEntry] = []

    if is_small:
        text_md_parts: list[str] = []
        for i, t in enumerate(page_texts):
            text_md_parts.append(f"## Page {i + 1}\n\n{t}\n")
        (out_dir / "text.md").write_text("\n".join(text_md_parts) + "\n",
                                         encoding="utf-8")
        # Tiny note so a human poking around the cache knows why ``text/``
        # is absent and where to look instead.
        (out_dir / "map.md").write_text(
            f"# {pdf_path.name}\n\nSmall PDF — full text in `text.md`.\n",
            encoding="utf-8",
        )
    else:
        text_dir = out_dir / "text"
        text_dir.mkdir(exist_ok=True)

        plans = _plan_chapters_from_toc(toc, page_count)
        if not plans:
            plans = _plan_chapters_fallback(page_count)

        map_lines: list[str] = [f"# {pdf_path.name}", "",
                                f"- pages: {page_count}",
                                f"- chapters: {len(plans)}", ""]
        for idx, plan in enumerate(plans, start=1):
            # Slice page_texts by the plan's 1-indexed range.
            slice_texts = page_texts[plan.page_start - 1:plan.page_end]
            chapter_text = "\n\n".join(t for t in slice_texts if t).strip()
            word_count = _count_words(chapter_text)

            ch_filename = f"ch-{idx:02d}.md"
            ch_path = text_dir / ch_filename
            header = (f"# {plan.title}\n\n"
                      f"_pages {plan.page_start}–{plan.page_end}_\n\n")
            ch_path.write_text(header + chapter_text + "\n", encoding="utf-8")

            chapters.append(ChapterEntry(
                title=plan.title,
                file=f"text/{ch_filename}",
                page_start=plan.page_start,
                page_end=plan.page_end,
                word_count=word_count,
            ))

            preview = _first_n_words(chapter_text, MAP_WORDS_PER_CHAPTER)
            map_lines.extend([
                f"## {idx:02d}. {plan.title}",
                "",
                f"_pages {plan.page_start}–{plan.page_end} · {word_count} words_",
                "",
                preview if preview else "_(no extractable text)_",
                "",
            ])
        (out_dir / "map.md").write_text("\n".join(map_lines) + "\n",
                                        encoding="utf-8")

    # ----- manifest ----------------------------------------------------------
    try:
        rel_source = pdf_path.resolve().relative_to(deck_dir.resolve())
        source_str = rel_source.as_posix()
    except ValueError:
        # PDF lives outside the deck dir — fall back to the absolute path so
        # the manifest still uniquely identifies the source.
        source_str = pdf_path.resolve().as_posix()

    manifest = Manifest(
        source=source_str,
        doc_slug=doc_slug,
        size_tier=size_tier,
        page_count=page_count,
        char_count=char_count,
        extracted_at=_iso_now(),
        source_sha1=source_sha1,
        images=images,
        chapters=chapters,
    )
    _write_json(manifest_path, manifest.to_dict())

    return "extracted", manifest


# ---------------------------------------------------------------------------
# Top-level deck walk
# ---------------------------------------------------------------------------


def _find_pdfs(resources_dir: Path) -> list[Path]:
    """Return every ``*.pdf`` under *resources_dir*, sorted for determinism."""
    return sorted(p for p in resources_dir.rglob("*.pdf") if p.is_file())


def extract_deck(deck_dir: Path,
                 *,
                 min_image_dim: int = 100,
                 force: bool = False,
                 verbose: bool = False,
                 log=print,
                 ) -> dict:
    """Walk ``<deck>/resources/`` and cache every PDF found.

    Returns a summary dict with counts: ``{"scanned", "extracted", "cached",
    "errors"}``.

    Raises FileNotFoundError if the deck has no ``resources/`` folder — the
    caller is expected to have scaffolded one.
    """
    resources_dir = deck_dir / "resources"
    if not resources_dir.is_dir():
        raise FileNotFoundError(
            f"deck has no resources/ folder: {resources_dir}")

    cache_root = deck_dir / ".slidecraft" / "cache" / "pdf"
    cache_root.mkdir(parents=True, exist_ok=True)

    pdfs = _find_pdfs(resources_dir)
    summary = {"scanned": len(pdfs), "extracted": 0, "cached": 0, "errors": 0}

    used_slugs: set[str] = set()
    # Pre-seed used_slugs with whatever subdirectories already exist so
    # collisions between an in-progress run and a stale cache directory
    # don't silently overwrite an unrelated PDF's cache.
    if cache_root.is_dir():
        for child in cache_root.iterdir():
            if child.is_dir():
                used_slugs.add(child.name)

    for pdf in pdfs:
        base = slugify(pdf.name)
        # If the slug already exists AND its manifest points at *this* PDF
        # (same absolute resolved source), we want to reuse it rather than
        # uniquify — that's the cached-hit path.
        candidate = base
        existing_manifest = cache_root / candidate / "manifest.json"
        rel_pdf = pdf.resolve()
        if existing_manifest.exists():
            try:
                existing = json.loads(existing_manifest.read_text(encoding="utf-8"))
                existing_source = existing.get("source", "")
                # Match either as recorded (relative POSIX) or by resolving
                # against the deck root.
                resolved_existing = (deck_dir / existing_source).resolve()
                if resolved_existing != rel_pdf:
                    candidate = make_unique_slug(base, used_slugs)
            except (OSError, json.JSONDecodeError):
                candidate = make_unique_slug(base, used_slugs)
        else:
            candidate = make_unique_slug(base, used_slugs)
        used_slugs.add(candidate)

        try:
            status, _ = extract_pdf(
                pdf, deck_dir, cache_root, candidate,
                min_image_dim=min_image_dim, force=force,
            )
        except Exception as exc:  # noqa: BLE001 — top-level boundary
            summary["errors"] += 1
            log(f"error: {pdf.name}: {exc}")
            continue

        if status == "cached":
            summary["cached"] += 1
            if verbose:
                log(f"cached: {candidate}")
        elif status == "extracted":
            summary["extracted"] += 1
            log(f"extracted: {candidate}")

    return summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m slidecraft.scripts.extract_pdf_assets",
        description=("Extract text and images from every PDF under "
                     "<deck>/resources/ into a deterministic cache."),
    )
    p.add_argument("--deck", required=True, type=Path,
                   help="Path to the deck directory (must contain resources/).")
    p.add_argument("--min-image-dim", type=int, default=100,
                   help="Skip images smaller than this on either axis (px). "
                        "Default: 100.")
    p.add_argument("--force", action="store_true",
                   help="Re-extract even when the cached manifest is up to date.")
    p.add_argument("--verbose", action="store_true",
                   help="Print one line per cached PDF in addition to extracted ones.")
    return p


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point — returns the process exit code."""
    args = _build_arg_parser().parse_args(argv)

    try:
        import fitz  # noqa: F401 — presence check only
    except ImportError:
        print("error: pymupdf is required. Install with: pip install pymupdf",
              file=sys.stderr)
        return 1

    deck_dir: Path = args.deck
    if not deck_dir.is_dir():
        print(f"error: deck directory not found: {deck_dir}", file=sys.stderr)
        return 1

    try:
        summary = extract_deck(
            deck_dir,
            min_image_dim=args.min_image_dim,
            force=args.force,
            verbose=args.verbose,
        )
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(
        f"{summary['scanned']} pdfs scanned, "
        f"{summary['extracted']} extracted, "
        f"{summary['cached']} cached, "
        f"{summary['errors']} errors"
    )
    return 1 if summary["errors"] else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
