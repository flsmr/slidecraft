# -*- coding: utf-8 -*-
"""Write (or merge) per-slide evidence sidecars from an authoring workflow's structured output.

An evidence sidecar `<deck>/resources/evidence/<slide-slug>.json` records what a slide was built
from: each claim's source key + locator + verbatim excerpt, and each figure's intended labels /
relationships / must-not traps. Reviewers (grounding-critic, image-critic, house-style) read it so
they check against a written spec instead of re-deriving the truth. See references/evidence-sidecars.md.

This is deterministic glue: the author agents already return `evidence[]` (per slide) plus `facts[]`
and `figure_proposals[]`; this persists them. It MERGES into an existing sidecar (research agents can
append evidence over time) and never overwrites a hand-authored claim with a blank one.

Usage:
  # batch: a JSON list of per-slide payloads (the workflow's evidence[], slug-resolved)
  python -m slidecraft.scripts.write_evidence --deck "<deck>" --batch payloads.json [--source-key K] [--origin O]

payloads.json shape (list):
  [ { "slide": "model-classes", "title": "Model Classes", "origin": "gebhardt",
      "source_key": "gebhardt2025",
      "claims":  [ {"statement": "...", "locator": "p. 356", "excerpt": "...", "source": "gebhardt2025"} ],
      "figures": [ {"file": "model_class_mapping.png", "intended_labels": [...],
                    "intended_relationships": "...", "must_not": [...],
                    "based_on_source": "gebhardt2025", "based_on_locator": "p. 356", "prompt_file": "..."} ] },
    ... ]
"""
from __future__ import annotations
import argparse, io, json, os, re


def slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")


def _claim_key(c: dict) -> str:
    return (c.get("statement", "") + "|" + c.get("locator", "")).strip().lower()


def merge_sidecar(existing: dict, incoming: dict, source_key: str, origin: str) -> dict:
    out = dict(existing) if existing else {}
    out["slide"] = incoming.get("slide") or out.get("slide")
    out["title"] = incoming.get("title") or out.get("title", "")
    out.setdefault("origin", incoming.get("origin") or origin or "unknown")
    out.setdefault("_schema", "per-slide raw-reference sidecar; see references/evidence-sidecars.md")

    # ---- claims (merge by statement+locator) ----
    claims = list(out.get("claims", []))
    seen = {_claim_key(c) for c in claims}
    next_id = len(claims) + 1
    for c in incoming.get("claims", []) or []:
        if not c.get("statement"):
            continue
        if _claim_key(c) in seen:
            continue
        entry = {
            "id": f"c{next_id}",
            "statement": c["statement"],
            "source": c.get("source") or incoming.get("source_key") or source_key,
            "locator": c.get("locator", ""),
        }
        if c.get("excerpt"):
            entry["excerpt"] = c["excerpt"]
        if c.get("lang"):
            entry["lang"] = c["lang"]
        claims.append(entry)
        seen.add(_claim_key(c))
        next_id += 1
    if claims:
        out["claims"] = claims

    # ---- figures (merge by file) ----
    figs = {f.get("file"): dict(f) for f in out.get("figures", []) if f.get("file")}
    for f in incoming.get("figures", []) or []:
        fn = f.get("file")
        if not fn:
            continue
        cur = figs.get(fn, {"file": fn})
        for k in ("kind", "intended_labels", "intended_relationships", "must_not",
                  "based_on_source", "based_on_locator", "based_on_image", "prompt_file", "single_accent"):
            if f.get(k) not in (None, "", [], {}):
                cur[k] = f[k]
        figs[fn] = cur
    if figs:
        out["figures"] = list(figs.values())

    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--deck", required=True)
    ap.add_argument("--batch", required=True, help="JSON list of per-slide evidence payloads")
    ap.add_argument("--source-key", default="", help="default bib key when a claim/figure omits one")
    ap.add_argument("--origin", default="", help="default origin label (lecture-notes|gebhardt|research|...)")
    args = ap.parse_args()

    evdir = os.path.join(args.deck, "resources", "evidence")
    os.makedirs(evdir, exist_ok=True)
    payloads = json.load(io.open(args.batch, encoding="utf-8"))
    if isinstance(payloads, dict):
        payloads = [payloads]

    written = 0
    for p in payloads:
        slug = slugify(p.get("slide") or p.get("slug") or p.get("title", ""))
        if not slug:
            print("SKIP payload with no slide/slug/title"); continue
        path = os.path.join(evdir, f"{slug}.json")
        existing = json.load(io.open(path, encoding="utf-8")) if os.path.exists(path) else {}
        p.setdefault("slide", slug)
        merged = merge_sidecar(existing, p, args.source_key, args.origin)
        io.open(path, "w", encoding="utf-8").write(json.dumps(merged, ensure_ascii=False, indent=2) + "\n")
        written += 1
        print(f"  evidence/{slug}.json  ({len(merged.get('claims', []))} claims, {len(merged.get('figures', []))} figures)")
    print(f"wrote/merged {written} evidence sidecar(s) -> {evdir}")


if __name__ == "__main__":
    main()
