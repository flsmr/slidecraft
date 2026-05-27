"""Tests for slidecraft.scripts.extract_pdf_assets.

We never vendor real PDFs into the repo — every fixture here is synthesised
on the fly with pymupdf so the tests are deterministic and add no binary
weight to the source tree.
"""
from __future__ import annotations

import io
import json
import tempfile
from pathlib import Path

import pytest

# Skip the entire module cleanly if pymupdf isn't installed — the script
# itself prints a friendly error in that case; the tests aren't useful
# without it.
fitz = pytest.importorskip("fitz")

from slidecraft.scripts.extract_pdf_assets import (  # noqa: E402
    SMALL_TIER_MAX_CHARS,
    extract_deck,
    extract_pdf,
    main,
    make_unique_slug,
    slugify,
)


# ---------------------------------------------------------------------------
# PDF fixture builders
# ---------------------------------------------------------------------------


def _make_pdf(path: Path,
              pages: list[str],
              toc: list[list] | None = None,
              page_images: dict[int, list[bytes]] | None = None,
              ) -> None:
    """Write a synthetic PDF with the given page texts (and optional images/TOC).

    Args:
        path:         Where to write the PDF.
        pages:        One string per page; rendered top-left on a Letter page.
        toc:          Optional ``[[level, title, page], ...]`` list.
        page_images:  Optional ``{1-indexed page: [png-bytes, ...]}``. Each
                      blob is inserted into a 200×150 rect on that page.
    """
    doc = fitz.open()
    for text in pages:
        page = doc.new_page()
        # Use insert_textbox with the full page area (minus margin) so long
        # strings wrap rather than spilling off-page (which would otherwise
        # silently drop characters from get_text() and break char_count
        # assertions).
        rect = fitz.Rect(36, 36, page.rect.width - 36, page.rect.height - 36)
        page.insert_textbox(rect, text, fontsize=8)
    if page_images:
        for page_no, blobs in page_images.items():
            page = doc.load_page(page_no - 1)
            x = 72
            y = 200
            for blob in blobs:
                rect = fitz.Rect(x, y, x + 200, y + 150)
                page.insert_image(rect, stream=blob)
                y += 160
    if toc:
        doc.set_toc(toc)
    doc.save(str(path))
    doc.close()


def _make_png(width: int = 200, height: int = 150,
              colour: tuple[int, int, int] = (200, 50, 50)) -> bytes:
    """Return PNG bytes for a solid-colour rectangle.

    pymupdf can both render and ingest PNG, which is enough for our dedupe
    and tiny-image tests — no Pillow dependency required.
    """
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, width, height))
    pix.set_rect(pix.irect, colour)
    return pix.tobytes("png")


def _lorem(words: int) -> str:
    """Deterministic filler text — repeats a short phrase to reach *words*."""
    base = ("lorem ipsum dolor sit amet consectetur adipiscing elit sed do "
            "eiusmod tempor incididunt ut labore et dolore magna aliqua")
    bag = base.split()
    out = []
    while len(out) < words:
        out.extend(bag)
    return " ".join(out[:words])


# ---------------------------------------------------------------------------
# slugify
# ---------------------------------------------------------------------------


class TestSlugify:
    """Slug generation must be deterministic and filesystem-safe."""

    @pytest.mark.parametrize("name,expected", [
        ("2022_Richard Szeliski - Computer Vision 1.pdf",
         "2022-richard-szeliski-computer-vision-1"),
        ("Simple.pdf", "simple"),
        ("  spaces  everywhere  .pdf", "spaces-everywhere"),
        ("Über-Größe.pdf", "ber-gr-e"),         # non-ASCII collapses to hyphens
        ("---.pdf", "doc"),                      # all-punctuation safety net
        ("MIXED_Case-File.PDF", "mixed-case-file"),
    ])
    def test_slugify_normalisation(self, name, expected):
        assert slugify(name) == expected

    def test_make_unique_slug_suffixes_collisions(self):
        taken: set[str] = {"foo", "foo-2"}
        assert make_unique_slug("foo", taken) == "foo-3"
        assert make_unique_slug("bar", taken) == "bar"


# ---------------------------------------------------------------------------
# Deck fixture + helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def deck_dir():
    """Yield a fresh deck directory with an empty ``resources/`` subfolder."""
    with tempfile.TemporaryDirectory() as tmp:
        deck = Path(tmp) / "deck"
        (deck / "resources").mkdir(parents=True)
        yield deck


def _load_manifest(deck: Path, slug: str) -> dict:
    return json.loads(
        (deck / ".slidecraft" / "cache" / "pdf" / slug / "manifest.json")
        .read_text(encoding="utf-8")
    )


# ---------------------------------------------------------------------------
# Small-tier extraction
# ---------------------------------------------------------------------------


class TestSmallTier:
    def test_small_pdf_writes_text_md(self, deck_dir):
        pdf = deck_dir / "resources" / "Small Note.pdf"
        _make_pdf(pdf, pages=["Hello world", "Page two prose"])

        summary = extract_deck(deck_dir)

        assert summary == {"scanned": 1, "extracted": 1, "cached": 0,
                           "errors": 0}
        slug = "small-note"
        cache = deck_dir / ".slidecraft" / "cache" / "pdf" / slug

        # The whole point of the small tier — single text.md, no text/ dir.
        assert (cache / "text.md").is_file()
        assert not (cache / "text").exists()

        body = (cache / "text.md").read_text(encoding="utf-8")
        assert "## Page 1" in body
        assert "Hello world" in body
        assert "## Page 2" in body
        assert "Page two prose" in body

        manifest = _load_manifest(deck_dir, slug)
        assert manifest["size_tier"] == "small"
        assert manifest["page_count"] == 2
        assert manifest["chapters"] == []
        # source path is recorded relative to the deck root, POSIX-style.
        assert manifest["source"] == "resources/Small Note.pdf"


# ---------------------------------------------------------------------------
# Large-tier extraction — by char count and by page count
# ---------------------------------------------------------------------------


class TestLargeTier:
    def test_large_by_char_count_uses_synthetic_sections(self, deck_dir):
        # 12 pages × ~5k chars each ≈ 60k chars — over the 50k char
        # threshold but well under the 50-page threshold, so only the
        # char-count condition trips large tier. No TOC → fallback to
        # ``Section N`` synthetic chapters.
        pdf = deck_dir / "resources" / "Wordy.pdf"
        # ~5.4k extracted chars per page at fontsize=8 in our fixture.
        big = _lorem(900)
        _make_pdf(pdf, pages=[big] * 12)

        # Force pymupdf to actually exceed the char limit by checking first.
        # (If our lorem generator changes, the assertion fails loudly here
        # rather than confusingly later.)
        summary = extract_deck(deck_dir)
        assert summary["extracted"] == 1

        slug = "wordy"
        manifest = _load_manifest(deck_dir, slug)
        assert manifest["size_tier"] == "large", (
            f"char_count={manifest['char_count']} should exceed "
            f"{SMALL_TIER_MAX_CHARS}")

        cache = deck_dir / ".slidecraft" / "cache" / "pdf" / slug
        assert not (cache / "text.md").exists()
        text_files = sorted((cache / "text").glob("ch-*.md"))
        assert len(text_files) >= 1
        assert all(f.name.startswith("ch-") for f in text_files)
        assert (cache / "map.md").is_file()
        map_body = (cache / "map.md").read_text(encoding="utf-8")
        assert "Section 1" in map_body
        # First-N-words preview should be present for chapter 1.
        assert "lorem" in map_body

        # Chapters in manifest follow the synthetic plan.
        assert len(manifest["chapters"]) >= 1
        first = manifest["chapters"][0]
        assert first["file"].startswith("text/ch-")
        assert first["page_start"] == 1
        assert first["word_count"] > 0

    def test_large_by_page_count(self, deck_dir):
        # 60 short pages → >50 page threshold trips large tier even though
        # total chars stay low.
        pdf = deck_dir / "resources" / "Many Pages.pdf"
        _make_pdf(pdf, pages=[f"page {i}" for i in range(1, 61)])

        extract_deck(deck_dir)
        manifest = _load_manifest(deck_dir, "many-pages")
        assert manifest["size_tier"] == "large"
        assert manifest["page_count"] == 60
        # 60 / 20 = 3 fallback sections.
        assert len(manifest["chapters"]) == 3
        # Page ranges tile the doc with no gaps.
        starts = [c["page_start"] for c in manifest["chapters"]]
        ends = [c["page_end"] for c in manifest["chapters"]]
        assert starts == [1, 21, 41]
        assert ends == [20, 40, 60]


# ---------------------------------------------------------------------------
# TOC handling
# ---------------------------------------------------------------------------


class TestTocHandling:
    def test_toc_drives_chapter_split(self, deck_dir):
        # Two top-level chapters at pages 1 and 31; a nested level-2 entry
        # that should be ignored by the chapter planner but still present
        # in toc.json.
        pdf = deck_dir / "resources" / "Manual.pdf"
        _make_pdf(
            pdf,
            pages=[f"chapter content page {i}" * 50 for i in range(1, 61)],
            toc=[
                [1, "Introduction", 1],
                [2, "Background", 5],
                [1, "Methods", 31],
            ],
        )
        extract_deck(deck_dir)

        slug = "manual"
        cache = deck_dir / ".slidecraft" / "cache" / "pdf" / slug

        # toc.json reflects the raw pymupdf get_toc() output.
        toc = json.loads((cache / "toc.json").read_text(encoding="utf-8"))
        titles = [entry[1] for entry in toc]
        assert "Introduction" in titles
        assert "Background" in titles  # level-2 still in the raw TOC
        assert "Methods" in titles

        manifest = _load_manifest(deck_dir, slug)
        assert manifest["size_tier"] == "large"
        chapter_titles = [c["title"] for c in manifest["chapters"]]
        # Only level-1 entries promoted to chapters.
        assert chapter_titles == ["Introduction", "Methods"]
        assert manifest["chapters"][0]["page_start"] == 1
        assert manifest["chapters"][0]["page_end"] == 30
        assert manifest["chapters"][1]["page_start"] == 31
        assert manifest["chapters"][1]["page_end"] == 60

    def test_no_toc_writes_empty_list(self, deck_dir):
        pdf = deck_dir / "resources" / "Plain.pdf"
        _make_pdf(pdf, pages=["a", "b"])
        extract_deck(deck_dir)
        toc_file = (deck_dir / ".slidecraft" / "cache" / "pdf" / "plain"
                    / "toc.json")
        assert json.loads(toc_file.read_text(encoding="utf-8")) == []


# ---------------------------------------------------------------------------
# Image extraction + dedupe + tiny-image skip
# ---------------------------------------------------------------------------


class TestImages:
    def test_images_extracted_and_recorded(self, deck_dir):
        pdf = deck_dir / "resources" / "Illustrated.pdf"
        png = _make_png(width=300, height=200, colour=(10, 200, 30))
        _make_pdf(pdf, pages=["page one", "page two"],
                  page_images={1: [png]})

        extract_deck(deck_dir)
        slug = "illustrated"
        cache = deck_dir / ".slidecraft" / "cache" / "pdf" / slug
        images = sorted((cache / "images").iterdir())
        assert len(images) == 1
        assert images[0].name.startswith("page-001-fig-01.")

        manifest = _load_manifest(deck_dir, slug)
        assert len(manifest["images"]) == 1
        entry = manifest["images"][0]
        assert entry["page"] == 1
        assert entry["path"].startswith("images/page-001-fig-01.")
        assert entry["width"] >= 100 and entry["height"] >= 100

    def test_dedupe_by_sha1_across_pages(self, deck_dir):
        # Same PNG embedded on two pages — only one file on disk, one
        # manifest entry, recorded against the page it first appeared on.
        pdf = deck_dir / "resources" / "Repeated.pdf"
        png = _make_png(colour=(20, 20, 200))
        _make_pdf(pdf, pages=["one", "two"],
                  page_images={1: [png], 2: [png]})

        extract_deck(deck_dir)
        cache = deck_dir / ".slidecraft" / "cache" / "pdf" / "repeated"
        images = list((cache / "images").iterdir())
        assert len(images) == 1
        manifest = _load_manifest(deck_dir, "repeated")
        assert len(manifest["images"]) == 1
        assert manifest["images"][0]["page"] == 1

    def test_tiny_images_skipped(self, deck_dir):
        # Default threshold is 100×100; this 50×50 image must be dropped.
        pdf = deck_dir / "resources" / "Tiny.pdf"
        tiny_png = _make_png(width=50, height=50, colour=(0, 0, 0))
        big_png = _make_png(width=200, height=200, colour=(255, 0, 0))
        _make_pdf(pdf, pages=["only"], page_images={1: [tiny_png, big_png]})

        extract_deck(deck_dir)
        manifest = _load_manifest(deck_dir, "tiny")
        # Only the big one survives.
        assert len(manifest["images"]) == 1
        assert manifest["images"][0]["width"] >= 100

    def test_min_image_dim_flag_honoured(self, deck_dir):
        # With --min-image-dim 250 even the 200×200 is below threshold.
        pdf = deck_dir / "resources" / "Mid.pdf"
        mid_png = _make_png(width=200, height=200, colour=(0, 128, 0))
        _make_pdf(pdf, pages=["only"], page_images={1: [mid_png]})

        extract_deck(deck_dir, min_image_dim=250)
        manifest = _load_manifest(deck_dir, "mid")
        assert manifest["images"] == []


# ---------------------------------------------------------------------------
# Idempotency + --force
# ---------------------------------------------------------------------------


class TestIdempotency:
    def test_second_run_reports_cached(self, deck_dir):
        pdf = deck_dir / "resources" / "Cacheable.pdf"
        _make_pdf(pdf, pages=["hello"])
        first = extract_deck(deck_dir)
        assert first["extracted"] == 1 and first["cached"] == 0

        # Capture the extracted_at timestamp; on a cached re-run it must
        # NOT be rewritten (proves extract_pdf short-circuited).
        manifest_path = (deck_dir / ".slidecraft" / "cache" / "pdf"
                         / "cacheable" / "manifest.json")
        before = json.loads(manifest_path.read_text(encoding="utf-8"))

        second = extract_deck(deck_dir)
        assert second == {"scanned": 1, "extracted": 0, "cached": 1,
                          "errors": 0}
        after = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert before["extracted_at"] == after["extracted_at"]

    def test_force_reextracts_even_when_cached(self, deck_dir):
        pdf = deck_dir / "resources" / "Forceme.pdf"
        _make_pdf(pdf, pages=["hello"])
        extract_deck(deck_dir)
        manifest_path = (deck_dir / ".slidecraft" / "cache" / "pdf"
                         / "forceme" / "manifest.json")
        before = json.loads(manifest_path.read_text(encoding="utf-8"))

        # Touch source untouched but pass force=True — manifest must be
        # rewritten (and at minimum its extracted_at may change; reliably,
        # the file mtime should advance).
        before_mtime = manifest_path.stat().st_mtime_ns
        summary = extract_deck(deck_dir, force=True)
        after_mtime = manifest_path.stat().st_mtime_ns
        assert summary["extracted"] == 1
        assert summary["cached"] == 0
        assert after_mtime >= before_mtime
        # SHA1 is stable across the re-extract for an unchanged source.
        after = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert before["source_sha1"] == after["source_sha1"]

    def test_modified_source_re_extracts(self, deck_dir):
        # Same filename, different contents → SHA1 mismatch → re-extract.
        pdf = deck_dir / "resources" / "Mutable.pdf"
        _make_pdf(pdf, pages=["v1"])
        extract_deck(deck_dir)
        manifest_path = (deck_dir / ".slidecraft" / "cache" / "pdf"
                         / "mutable" / "manifest.json")
        sha_v1 = json.loads(manifest_path.read_text(encoding="utf-8"))["source_sha1"]

        _make_pdf(pdf, pages=["v2 with different content entirely"])
        summary = extract_deck(deck_dir)
        assert summary["extracted"] == 1 and summary["cached"] == 0
        sha_v2 = json.loads(manifest_path.read_text(encoding="utf-8"))["source_sha1"]
        assert sha_v1 != sha_v2


# ---------------------------------------------------------------------------
# CLI surface
# ---------------------------------------------------------------------------


class TestCli:
    def test_main_returns_zero_on_success(self, deck_dir, capsys):
        _make_pdf(deck_dir / "resources" / "Cli.pdf", pages=["x"])
        rc = main(["--deck", str(deck_dir)])
        out = capsys.readouterr().out
        assert rc == 0
        assert "1 pdfs scanned" in out
        assert "1 extracted" in out

    def test_main_returns_one_on_missing_resources(self, tmp_path, capsys):
        # A deck dir that exists but has no resources/ subfolder.
        rc = main(["--deck", str(tmp_path)])
        err = capsys.readouterr().err
        assert rc == 1
        assert "resources" in err

    def test_main_returns_one_on_missing_deck(self, tmp_path, capsys):
        rc = main(["--deck", str(tmp_path / "does-not-exist")])
        err = capsys.readouterr().err
        assert rc == 1
        assert "deck directory not found" in err
