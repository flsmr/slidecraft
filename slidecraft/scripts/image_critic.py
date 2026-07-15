# -*- coding: utf-8 -*-
"""Run the devil's-advocate image-critic over a deck's non-photographic figures, on ONE vision model.

Primary model: GPT-5.6 sol via OWUI (chosen in testing for the best hygiene+semantics recall AND
precision; a multi-model panel was deliberately rejected as too costly/slow). The occasional false
positive is filtered by reconciling against each slide's evidence sidecar, which is passed into the
prompt so the model checks labels/relationships against a written spec instead of guessing.

See agents/image-critic.md for the full checklist this condenses. Report-only: writes findings, edits
nothing.

Usage:
  python -m slidecraft.scripts.image_critic --deck "<deck>" [--model gpt-5.6-sol] [--figures a.png,b.png]
"""
from __future__ import annotations
import argparse, base64, glob, io, json, mimetypes, os, re, sys

OWUI_DIR = os.environ.get("OWUI_SKILL_DIR", os.path.expanduser("~/.claude/skills/owui"))
sys.path.insert(0, OWUI_DIR)

CHECKLIST = """You are a ruthless devil's-advocate IMAGE CRITIC for a university lecture slide. Inspect THIS figure and
report every defect you can defend. Do NOT rationalize an inconsistency as 'probably intentional' -- flag it and
let a human judge. Read the rendered text character by character; report what is ACTUALLY drawn, not what it 'should' say.

Run the peer-uniformity sweep ('one of these is not like the others') and the decoration audit ('name what every
mark means; if you cannot, it is noise'), then check:
A TEXT: every label spelled right; none missing/extra/duplicated/truncated; numbers+units correct; counts match.
B COLOUR: on-brand; exactly ONE accent, on the teaching point, executed one way.
C SHAPE/LAYOUT: peers share shape/size/border; aligned; no overlap; nothing clipped; right orientation.
D LOGIC: arrows/links/nesting connect the correct nodes; arrow direction right; groupings right; nothing dangling;
  order right; chart bars proportional; NO relationship the source does not support.
E COHERENCE: figure matches the slide's topic; alt text truthful; scope fidelity (no extra column/axis the slide
  never named).
F ARTEFACTS: no melted/phantom shapes, stray lines, or watermarks.
H HYGIENE: one connector style (weight + arrowhead); merged lines share ONE arrowhead; fill the canvas (no wasted
  margins forcing narrow boxes / line-breaks); uniform arrowhead-to-box + box-to-box spacing; text centred with
  uniform padding, no overflow; one annotation rule for peers; charts use one encoding for every series.

Return findings as lines: [severity high|med|low] <category> - <issue> - <evidence: quote/point precisely>.
Then a one-line verdict: pass | minor | fail. Be specific and exhaustive."""


def load_slides(deck):
    """Return {figure_rel: {slide, title, alt}} for every <img src="/figures/..."> in the deck."""
    figs = {}
    for md in glob.glob(os.path.join(deck, "slides", "*.md")):
        t = io.open(md, encoding="utf-8").read()
        title_m = re.search(r"(?m)^::title::\r?\n(.+)$", t)
        title = title_m.group(1).strip() if title_m else os.path.basename(md)
        slug = os.path.splitext(os.path.basename(md))[0]
        for m in re.finditer(r'<img\s+[^>]*src="/figures/([^"]+)"[^>]*>', t):
            rel = m.group(1)
            alt_m = re.search(r'alt="([^"]*)"', m.group(0))
            figs.setdefault(rel, {"slide": slug, "title": title, "alt": alt_m.group(1) if alt_m else ""})
    return figs


def sidecar_for(deck, slug):
    p = os.path.join(deck, "resources", "evidence", f"{slug}.json")
    return json.load(io.open(p, encoding="utf-8")) if os.path.exists(p) else None


def figure_spec(sidecar, rel):
    """Pull the intended_relationships + must_not for this figure file from the slide's sidecar."""
    if not sidecar:
        return ""
    base = os.path.basename(rel)
    for f in sidecar.get("figures", []) or []:
        if os.path.basename(f.get("file", "")) == base:
            lines = []
            if f.get("intended_relationships"):
                lines.append("INTENDED (the correct spec): " + f["intended_relationships"])
            if f.get("must_not"):
                lines.append("MUST NOT: " + "; ".join(f["must_not"]))
            if f.get("intended_labels"):
                lines.append("LABELS (verbatim): " + ", ".join(f["intended_labels"]))
            return "\n".join(lines)
    return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--deck", required=True)
    ap.add_argument("--model", default="gpt-5.6-sol", help="OWUI vision model (default: gpt-5.6-sol)")
    ap.add_argument("--figures", default="", help="comma-separated figure filenames to limit to")
    ap.add_argument("--max-tokens", type=int, default=2500)
    args = ap.parse_args()

    from owui_client import OpenWebUIClient
    client = OpenWebUIClient(timeout=300)

    only = {s.strip() for s in args.figures.split(",") if s.strip()}
    figs = load_slides(args.deck)
    # non-photographic = everything not in the gallery/ (real photos) folder
    targets = {rel: meta for rel, meta in figs.items()
               if "/gallery/" not in ("/" + rel) and "gallery/" not in rel
               and (not only or os.path.basename(rel) in only or rel in only)}

    report = [f"# Image-critic report ({args.model})  deck: {os.path.basename(args.deck.rstrip('/\\'))}\n"]
    results = []
    for rel, meta in sorted(targets.items()):
        path = os.path.join(args.deck, "public", "figures", rel)
        if not os.path.exists(path):
            print("MISSING", rel); continue
        sc = sidecar_for(args.deck, meta["slide"])
        spec = figure_spec(sc, rel)
        ctx = (f"SLIDE: {meta['title']}\nALT TEXT: {meta['alt']}\n"
               + (f"\n{spec}\n(Reconcile any text/label finding against the INTENDED spec above; do NOT flag a "
                  f"label as wrong if the spec confirms it.)\n" if spec else ""))
        mime = mimetypes.guess_type(path)[0] or "image/png"
        b64 = base64.b64encode(open(path, "rb").read()).decode()
        msg = [{"role": "user", "content": [
            {"type": "text", "text": CHECKLIST + "\n\n" + ctx},
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}]}]
        try:
            res = client.chat(msg, model=args.model, max_tokens=args.max_tokens)
            txt = (res.content or "").strip() or "(empty response)"
        except Exception as e:
            txt = f"(error: {str(e)[:200]})"
        verdict = "?"
        vm = re.search(r"\b(pass|minor|fail)\b\s*$", txt, re.I | re.M)
        if vm:
            verdict = vm.group(1).lower()
        print(f"  {rel}: {verdict}  ({len(txt)} chars, sidecar={'yes' if spec else 'no'})")
        report.append(f"## {rel}  (slide: {meta['slide']}, verdict: {verdict})\n\n{txt}\n")
        results.append({"figure": rel, "slide": meta["slide"], "verdict": verdict, "findings_text": txt})

    out_md = os.path.join(args.deck, "resources", "image_critic_report.md")
    io.open(out_md, "w", encoding="utf-8").write("\n".join(report))
    io.open(os.path.join(args.deck, "resources", "image_critic_findings.json"), "w", encoding="utf-8").write(
        json.dumps({"model": args.model, "results": results}, ensure_ascii=False, indent=2))
    print(f"\n{len(results)} figures inspected on {args.model} -> resources/image_critic_report.md")


if __name__ == "__main__":
    main()
