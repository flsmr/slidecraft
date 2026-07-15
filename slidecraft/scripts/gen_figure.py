# -*- coding: utf-8 -*-
"""Generate a deck figure (diagram/infographic) via OWUI Imagen, honouring the theme's style contract.

Reads the deck's `resources/diagram-style.md` and appends BOTH the STYLE block and a compact
"Consistency:" clause (the contract rule headings) to every prompt — so generation follows the exact
rules the image-critic later reviews against. Two modes:

  --source <book_fig>   VISION recreate: GPT-5.5 vision describes the actual book figure, then crafts a
                        clean English Imagen prompt (copyright-safe redraw). Use for book diagrams.
  --spec "<prompt>"     DIRECT: render a label-controlled prompt you built from the canonical labels.
                        Use for synthesized infographics.

Usage:
  python -m slidecraft.scripts.gen_figure --deck "<deck>" --slug rp_dev_loop \
      --spec "A left-to-right flow of five boxes: ..." [--size 1792x1024]
  python -m slidecraft.scripts.gen_figure --deck "<deck>" --slug af_process_chain \
      --source "resources/gebhardt/figures/geb_p46_x465.jpeg" --context "keep these English labels: ..."
"""
from __future__ import annotations
import argparse, base64, io, json, mimetypes, os, re, sys

OWUI_DIR = os.environ.get("OWUI_SKILL_DIR", os.path.expanduser("~/.claude/skills/owui"))
sys.path.insert(0, OWUI_DIR)

# Fallback STYLE if a deck has no diagram-style.md (keeps the script usable standalone).
DEFAULT_STYLE = ("Flat vector infographic style, pure white background, sans-serif typography, dark teal "
                 "primary boxes with white bold text, pale grey-blue rounded rectangles for secondary "
                 "elements, thin light-grey connectors, one coral accent used only on the key teaching "
                 "element, generous spacing, all text large and correctly spelled, no watermark, no clutter.")


def load_style_contract(deck: str):
    """Return (style_block, consistency_clause) parsed from <deck>/resources/diagram-style.md."""
    path = os.path.join(deck, "resources", "diagram-style.md")
    if not os.path.exists(path):
        return DEFAULT_STYLE, ""
    md = io.open(path, encoding="utf-8").read()

    # STYLE block = the blockquote lines under "## STYLE block"
    style = DEFAULT_STYLE
    m = re.search(r"##\s*STYLE block[^\n]*\n(.*?)(?:\n##\s|\Z)", md, re.S | re.I)
    if m:
        quoted = [ln.lstrip(">").strip() for ln in m.group(1).splitlines() if ln.strip().startswith(">")]
        if quoted:
            style = " ".join(quoted)

    # Consistency clause = the bold rule lead-ins under "## Consistency contract"
    clause = ""
    m = re.search(r"##\s*Consistency contract[^\n]*\n(.*?)(?:\n##\s|\Z)", md, re.S | re.I)
    if m:
        rules = re.findall(r"^\s*\d+\.\s*\*\*(.+?)\.?\*\*", m.group(1), re.M)
        if rules:
            clause = "Consistency (apply all): " + "; ".join(r.strip().rstrip(".") for r in rules) + "."
    return style, clause


def owui_client():
    from owui_client import OpenWebUIClient
    return OpenWebUIClient(timeout=300)


def build_prompt_from_source(client, src_path, context, style, clause, model_chat):
    mime = mimetypes.guess_type(src_path)[0] or "image/png"
    b64 = base64.b64encode(open(src_path, "rb").read()).decode()
    ask = (f"You are given ONE diagram from an academic book. Study it, then write ONE English image-generation "
           f"prompt that RECREATES an equivalent, copyright-clean teaching diagram (same structure and "
           f"information, redrawn, translated to English, NOT a copy).\n\n"
           f"Grounding (labels/meaning to preserve, translate any foreign labels to English): {context}\n\n"
           f"Rules for the prompt you write:\n"
           f"- Describe the layout precisely: every box/node, axis, arrow, grouping and the relationships.\n"
           f"- The ONLY text in the image must be short English labels; list each verbatim and say 'spelled exactly as given'.\n"
           f"- Paste this STYLE verbatim: {style}\n"
           f"- {clause}\n"
           f"Output ONLY the final image-generation prompt (one rich paragraph).")
    msg = [{"role": "user", "content": [
        {"type": "text", "text": ask},
        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}]}]
    res = client.chat(msg, model=model_chat, max_tokens=1400)
    p = (res.content or "").strip()
    if p.startswith("```"):
        p = p.strip("`"); p = p.split("\n", 1)[1] if "\n" in p else p
    return p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--deck", required=True)
    ap.add_argument("--slug", required=True)
    ap.add_argument("--source", default="", help="book figure to vision-recreate (abs or relative to --deck)")
    ap.add_argument("--context", default="", help="grounding for --source (labels to keep)")
    ap.add_argument("--spec", default="", help="direct prompt (label-controlled) for a synthesized figure")
    ap.add_argument("--size", default="1792x1024")
    ap.add_argument("--model-chat", default="gdpr.gpt-5.5")
    ap.add_argument("--model-img", default="imagen-3.0-generate-002")
    args = ap.parse_args()

    style, clause = load_style_contract(args.deck)
    print("STYLE contract loaded:", "diagram-style.md" if clause or style != DEFAULT_STYLE else "default")
    client = owui_client()

    if args.source:
        src = args.source if os.path.isabs(args.source) else os.path.join(args.deck, args.source)
        prompt = build_prompt_from_source(client, src, args.context, style, clause, args.model_chat)
    elif args.spec:
        # direct: the caller built a label-controlled spec; we append the shared style + consistency clause
        prompt = f"{args.spec.strip()} {style} {clause}".strip()
    else:
        print("ERROR: pass --source (vision recreate) or --spec (direct prompt)"); sys.exit(2)

    io.open(os.path.join(args.deck, "resources", f"imgprompt_{args.slug}.txt"), "w", encoding="utf-8").write(prompt)

    import requests
    body = {"prompt": prompt, "model": args.model_img, "n": 1, "size": args.size}
    data = client._request("POST", "/api/v1/images/generations", data=json.dumps(body))
    items = data if isinstance(data, list) else data.get("data") or data.get("images") or []
    url = next((it.get("url") for it in items if isinstance(it, dict) and it.get("url")), None)
    if not url:
        print("NO_IMAGE:", json.dumps(data)[:300]); sys.exit(1)
    if not url.startswith("http"):
        url = client.base_url + url
    hdr = {"Authorization": f"Bearer {client.token}"} if url.startswith(client.base_url) else {}
    rr = requests.get(url, headers=hdr, timeout=300); rr.raise_for_status()
    out = os.path.join(args.deck, "public", "figures", f"{args.slug}.png")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    open(out, "wb").write(rr.content)
    print("SAVED", out, len(rr.content), "bytes")


if __name__ == "__main__":
    main()
