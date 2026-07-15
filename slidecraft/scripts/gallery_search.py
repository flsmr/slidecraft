# -*- coding: utf-8 -*-
"""Find free-licensed real photos on Wikimedia Commons for a deck's example galleries.

Input is the sprint_deck workflow's `galleries.groups`:
  [ {"section": "Primary Shaping", "queries": [ {"label": "Sand casting", "query": "sand casting foundry"}, ... ]} ]

For each section it downloads up to --per verified free-licence images into <deck>/public/figures/gallery/
as g<sectionIndex>_<i>.jpg and writes <deck>/resources/gallery_group<sectionIndex>.json with attribution
({label, author, license, page_url, title, direct_url}) in the shape the assembler expects.

Free licences accepted: Public domain / CC0 / CC BY / CC BY-SA. NC and AI-generated are rejected.

Usage:
  python gallery_search.py --deck "<deck>" --queries "resources/gallery_queries.json" --per 6
"""
import os, io, re, json, time, argparse, urllib.parse

import requests
try:
    from PIL import Image
except Exception:
    Image = None

API = "https://commons.wikimedia.org/w/api.php"
UA = "SlidecraftBot/1.0 (https://github.com/flsmr/slidecraft; IU lecture decks; educational use)"
OK_LIC = ("public domain", "cc0", "cc-by", "cc by", "cc-by-sa", "cc by-sa")
BAD_LIC = ("nc", "non-commercial", "noncommercial")
QUERY_DELAY = 3.0   # polite pacing between API queries (Commons 429s aggressive clients)


def get_with_backoff(url, params=None, tries=4, base_wait=20):
    """GET with exponential backoff on 429 (honouring Retry-After)."""
    for attempt in range(tries):
        r = requests.get(url, params=params, headers={"User-Agent": UA}, timeout=60)
        if r.status_code != 429:
            r.raise_for_status()
            return r
        wait = int(r.headers.get("Retry-After") or base_wait * (2 ** attempt))
        print(f"   429 rate-limited, waiting {wait}s (attempt {attempt+1}/{tries})")
        time.sleep(wait)
    r.raise_for_status()
    return r


def strip_html(s):
    return re.sub(r"<[^>]+>", "", s or "").strip()


def license_ok(lic):
    l = (lic or "").lower()
    return any(k in l for k in OK_LIC) and not any(b in l for b in BAD_LIC)


def search_one(query):
    """Return the first free-licence bitmap for a query, or None."""
    params = {
        "action": "query", "format": "json", "generator": "search",
        "gsrsearch": f"{query} filetype:bitmap", "gsrnamespace": "6", "gsrlimit": "12",
        "prop": "imageinfo", "iiprop": "url|extmetadata|mime|size", "iiurlwidth": "800",
    }
    try:
        r = get_with_backoff(API, params=params)
        pages = (r.json().get("query") or {}).get("pages") or {}
    except Exception as e:
        print("   search error:", e); return None
    cands = sorted(pages.values(), key=lambda p: p.get("index", 999))
    for pg in cands:
        ii = (pg.get("imageinfo") or [None])[0]
        if not ii:
            continue
        if ii.get("mime") not in ("image/jpeg", "image/png"):
            continue
        if ii.get("width", 0) < 400:
            continue
        meta = ii.get("extmetadata") or {}
        lic = (meta.get("LicenseShortName") or {}).get("value") or (meta.get("License") or {}).get("value")
        if not license_ok(lic):
            continue
        return {
            "title": pg.get("title", "").replace("File:", ""),
            "author": strip_html((meta.get("Artist") or {}).get("value")) or "Unknown",
            "license": lic,
            "page_url": ii.get("descriptionurl", ""),
            "direct_url": ii.get("thumburl") or ii.get("url"),
        }
    return None


def download(url, dest, box=600):
    r = get_with_backoff(url)
    open(dest, "wb").write(r.content)
    if Image:
        try:
            im = Image.open(dest); im.thumbnail((box, box)); im.convert("RGB").save(dest, "JPEG", quality=85)
        except Exception:
            pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--deck", required=True)
    ap.add_argument("--queries", required=True, help="JSON (abs or relative to --deck): groups[{section,queries[]}]")
    ap.add_argument("--per", type=int, default=6)
    args = ap.parse_args()

    qpath = args.queries if os.path.isabs(args.queries) else os.path.join(args.deck, args.queries)
    groups = json.load(io.open(qpath, encoding="utf-8"))
    if isinstance(groups, dict):
        groups = groups.get("groups", [])
    gdir = os.path.join(args.deck, "public", "figures", "gallery")
    os.makedirs(gdir, exist_ok=True)

    for gi, group in enumerate(groups, 1):
        section = group.get("section", f"group{gi}")
        picked = []
        for q in group.get("queries", [])[: args.per * 2]:
            if len(picked) >= args.per:
                break
            hit = search_one(q.get("query", q.get("label", "")))
            time.sleep(QUERY_DELAY)  # be polite to the API
            if not hit:
                print(f"  [{section}] no free image for: {q.get('label')}")
                continue
            i = len(picked) + 1
            dest = os.path.join(gdir, f"g{gi}_{i}.jpg")
            try:
                download(hit["direct_url"], dest)
            except Exception as e:
                print(f"  [{section}] download failed {q.get('label')}: {e}"); continue
            hit["label"] = q.get("label", hit["title"])
            picked.append(hit)
            print(f"  [{section}] g{gi}_{i} <- {hit['label']} ({hit['license']})")
        outjson = os.path.join(args.deck, "resources", f"gallery_group{gi}.json")
        io.open(outjson, "w", encoding="utf-8").write(json.dumps({"section": section, "images": picked},
                                                                  ensure_ascii=False, indent=2))
        print(f"[{section}] {len(picked)}/{args.per} images -> gallery_group{gi}.json")


if __name__ == "__main__":
    main()
