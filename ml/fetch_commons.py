"""Real-world street photos from Wikimedia Commons, per class, with their licences.

    ml/.venv/Scripts/python ml/fetch_commons.py [--per-class 220]

Walks each class's categories (and sub-categories, two levels), keeps only freely
licensed photos (CC0, CC BY, CC BY-SA, public domain), downloads 500 px thumbnails (a standard, pre-rendered Commons size)
and records author, licence and source page in ml/raw/commons/ATTRIBUTION-<class>.csv.
Commons is a completely independent source, so these photos are used as a
held-out *test* set first: the honest check of whether a model works on the
kind of photo a citizen actually takes.
"""
from __future__ import annotations

import argparse
import csv
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://commons.wikimedia.org/w/api.php"
UA = {"User-Agent": "image-dataset-fetch/1.0 (python-urllib; low request rate)"}
OUT = Path(__file__).resolve().parent / "raw" / "commons"
FREE = ("cc0", "cc by", "cc-by", "public domain", "pd")

#: class -> Commons categories. Sub-categories are walked two levels deep.
CATEGORIES = {
    "pothole": ["Potholes", "Potholes in India", "Road damage"],
    "waterlogging": ["Floods in India", "Flooded roads", "Floods in Mumbai", "Floods in Chennai", "Urban flooding"],
    "garbage": ["Garbage in India", "Litter in India", "Waste in India", "Illegal dumping", "Garbage dumps"],
    "manhole": ["Manhole covers in India", "Manhole covers in Delhi", "Manhole covers in Mumbai"],
    "open_manhole": ["Open manholes", "Manholes"],
    "blocked_road": ["Fallen trees", "Road closures", "Road barricades", "Trees fallen on roads"],
    "road_ok": ["Roads in Delhi", "Streets in Delhi", "Roads in India", "Streets in Bangalore", "Roads in Mumbai"],
    # junk a citizen might upload by mistake: the model should say "this is not a street photo"
    "not_street": ["Selfies", "Indian cuisine", "Living rooms", "Cats", "Dogs", "Screenshots of websites"],
}


def api(**params) -> dict:
    params |= {"format": "json", "formatversion": "2"}
    url = API + "?" + urllib.parse.urlencode(params)
    for attempt in range(5):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                time.sleep(0.6)  # polite: well under Commons' rate limits
                return json.load(r)
        except Exception:  # noqa: BLE001 - network errors and throttling: back off and retry
            time.sleep(3 * (attempt + 1))
    return {}


def members(cat: str, kind: str) -> list[str]:
    out, cont = [], {}
    while True:
        d = api(action="query", list="categorymembers", cmtitle=f"Category:{cat}", cmtype=kind, cmlimit="500", **cont)
        out += [m["title"] for m in d.get("query", {}).get("categorymembers", [])]
        if "continue" not in d or len(out) > 3000:
            return out
        cont = {"cmcontinue": d["continue"]["cmcontinue"]}


def files_under(cat: str, depth: int = 2) -> list[str]:
    found = members(cat, "file")
    if depth:
        for sub in members(cat, "subcat")[:25]:
            found += files_under(sub.removeprefix("Category:"), depth - 1)
    return found


def info(titles: list[str]) -> list[dict]:
    d = api(action="query", titles="|".join(titles), prop="imageinfo", iiprop="url|extmetadata|mime", iiurlwidth="500")
    return [p for p in d.get("query", {}).get("pages", []) if p.get("imageinfo")]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-class", type=int, default=220)
    ap.add_argument("--classes", nargs="*", default=list(CATEGORIES))
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    log = OUT / f"ATTRIBUTION-{'-'.join(args.classes)}.csv"   # one file per worker: parallel runs never interleave rows
    seen = set()
    if log.exists():
        seen = {r[1] for r in csv.reader(log.open(encoding="utf-8"))}
    with log.open("a", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        for cls in args.classes:
            cats = CATEGORIES[cls]
            (OUT / cls).mkdir(exist_ok=True)
            have = len(list((OUT / cls).iterdir()))
            titles = list(dict.fromkeys(t for c in cats for t in files_under(c)))
            titles = [t for t in titles if t.lower().endswith((".jpg", ".jpeg", ".png", ".webp")) and t not in seen]
            print(cls, "candidates", len(titles), flush=True)
            for i in range(0, len(titles), 40):
                if have >= args.per_class:
                    break
                for page in info(titles[i:i + 40]):
                    ii = page["imageinfo"][0]
                    meta = ii.get("extmetadata", {})
                    lic = meta.get("LicenseShortName", {}).get("value", "")
                    if not lic.lower().startswith(FREE) or have >= args.per_class:
                        continue
                    try:
                        with urllib.request.urlopen(urllib.request.Request(ii["thumburl"], headers=UA), timeout=60) as r:
                            data = r.read()
                        time.sleep(0.3)
                    except Exception:  # noqa: BLE001
                        continue
                    name = f"Commons_{cls}_{page['pageid']}.jpg"
                    (OUT / cls / name).write_bytes(data)
                    author = meta.get("Artist", {}).get("value", "")
                    w.writerow([f"{cls}/{name}", page["title"], lic, author[:200], ii.get("descriptionurl", "")])
                    have += 1
            print(cls, "kept", have, flush=True)


if __name__ == "__main__":
    main()
