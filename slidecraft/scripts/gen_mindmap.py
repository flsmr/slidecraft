# -*- coding: utf-8 -*-
"""Render a radial mind map from a nested-markdown outline via OWUI (GPT-5.5 -> Imagen 3).

Generalized from the SPRINT_2 build. Needs the OWUI client on the path — set OWUI_SKILL_DIR
or keep it at ~/.claude/skills/owui (see SETUP.md). The mind-map OUTLINE is produced by the
`mindmap-smith` agent in the sprint_deck workflow; this script only turns it into an image.

Usage:
  python gen_mindmap.py --deck "<deck>" --structure "resources/ch3_mindmap.md" \
                        --central "Additive Manufacturing (ch.3)" --out "mindmap_ch3.png"
"""
import sys, os, io, json, argparse

OWUI_DIR = os.environ.get("OWUI_SKILL_DIR", os.path.expanduser("~/.claude/skills/owui"))
sys.path.insert(0, OWUI_DIR)
try:
    import requests
    from owui_client import OpenWebUIClient
except Exception as e:
    print("OWUI client not importable. Set OWUI_SKILL_DIR to the owui skill dir. Error:", e)
    sys.exit(2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--deck", required=True)
    ap.add_argument("--structure", required=True, help="path (abs or relative to --deck) to the outline .md")
    ap.add_argument("--central", required=True, help="centre-node label")
    ap.add_argument("--out", default="mindmap.png", help="output filename under public/figures/")
    ap.add_argument("--model-chat", default="gdpr.gpt-5.5")
    ap.add_argument("--model-img", default="imagen-3.0-generate-002")
    args = ap.parse_args()

    struct_path = args.structure if os.path.isabs(args.structure) else os.path.join(args.deck, args.structure)
    structure = io.open(struct_path, encoding="utf-8").read()
    out = os.path.join(args.deck, "public", "figures", args.out)

    # single source of truth for the visual language: the deck's diagram-style.md
    try:
        from slidecraft.scripts.gen_figure import load_style_contract
    except Exception:
        sys.path.insert(0, os.path.dirname(__file__))
        from gen_figure import load_style_contract
    style, _clause = load_style_contract(args.deck)

    client = OpenWebUIClient(timeout=300)
    desc_rules = f"""Below is a nested-markdown outline distilled from a lecture chapter. Turn it into ONE
detailed image-generation prompt for a CLEAN, LEGIBLE radial mind map.

Rules for the mind map you describe:
- Central node: "{args.central}" as a dark teal rounded rectangle with white bold text.
- One main branch per top-level outline item, evenly spaced around the centre, each its own labelled node.
- Under each branch show its 3-4 KEY sub-nodes (short labels). Do not invent nodes not in the outline.
- Style (paste verbatim): {style}
- Landscape 16:9. Spell out every node label exactly as it should render.

Output ONLY the final image-generation prompt (one rich paragraph)."""

    res = client.chat(desc_rules + "\n\n<OUTLINE>\n" + structure + "\n</OUTLINE>",
                      model=args.model_chat, max_tokens=1600)
    desc = (res.content or "").strip()
    if desc.startswith("```"):
        desc = desc.strip("`"); desc = desc.split("\n", 1)[1] if "\n" in desc else desc
    io.open(os.path.join(args.deck, "resources", "mindmap_description.txt"), "w", encoding="utf-8").write(desc)

    body = {"prompt": desc, "model": args.model_img, "n": 1, "size": "1792x1024"}
    data = client._request("POST", "/api/v1/images/generations", data=json.dumps(body))
    items = data if isinstance(data, list) else data.get("data") or data.get("images") or []
    url = next((it.get("url") for it in items if isinstance(it, dict) and it.get("url")), None)
    if not url:
        print("NO_IMAGE:", json.dumps(data)[:300]); sys.exit(1)
    if not url.startswith("http"):
        url = client.base_url + url
    hdr = {"Authorization": f"Bearer {client.token}"} if url.startswith(client.base_url) else {}
    rr = requests.get(url, headers=hdr, timeout=300); rr.raise_for_status()
    open(out, "wb").write(rr.content)
    print("SAVED", out, len(rr.content), "bytes")


if __name__ == "__main__":
    main()
