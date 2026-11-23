"""Citizen-style street photos per class from Openverse (CC-licensed images from Flickr, Wikimedia and more).

    ml/.venv/Scripts/python ml/fetch_openverse.py [--per-class 200]

Only CC BY, CC BY-SA, CC0 and public-domain images. Every file is recorded with title, creator,
licence and landing page in ml/raw/openverse/ATTRIBUTION.csv. Labels come from keyword search,
so they are noisy: audit_labels.py samples each class for a manual check, and that measured
label precision is reported next to every accuracy number from this set.
The images are a test set only, never used for distillation or prompt writing.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image

API = "https://api.openverse.org/v1/images/"
UA = {"User-Agent": "image-dataset-fetch/1.0 (python-urllib; low request rate)"}
OUT = Path(__file__).resolve().parent / "raw" / "openverse"
QUERIES = {
    "pothole": ["pothole", "potholes road", "pothole street", "road pothole india"],
    "waterlogging": ["flooded street", "waterlogging", "flooded road", "street flooding rain"],
    "garbage": ["garbage dump street", "trash pile street", "garbage india street", "illegal dumping"],
    "open_manhole": ["open manhole", "uncovered manhole", "manhole open street"],
    "manhole": ["manhole cover", "manhole cover street"],
    "blocked_road": ["fallen tree road", "road closed barricade", "fallen tree street storm"],
    "road_ok": ["street india road", "empty road", "city street traffic india", "asphalt road"],
    "not_street": ["selfie", "plate of food", "living room interior", "cat portrait"],
}


def image(url: str) -> bytes | None:
    """One attempt: a host that refuses is skipped, not retried (retries made the run crawl)."""
    if not url:
        return None
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20) as r:
            return r.read()
    except Exception:  # noqa: BLE001
        return None


def get(url: str, as_json: bool = True):
    for attempt in range(6):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                data = r.read()
            return json.loads(data) if as_json else data
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(30 * (attempt + 1))   # anonymous quota: wait it out instead of hammering
                continue
            if e.code in (400, 404):
                return None
            time.sleep(5)
        except Exception:  # noqa: BLE001 - timeouts, resets
            time.sleep(5)
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-class", type=int, default=200)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    log = OUT / "ATTRIBUTION.csv"
    seen = {r[1] for r in csv.reader(log.open(encoding="utf-8"))} if log.exists() else set()
    with log.open("a", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        for cls, queries in QUERIES.items():
            (OUT / cls).mkdir(exist_ok=True)
            have = len(list((OUT / cls).glob("*.jpg")))
            for q in queries:
                for page in range(1, 13):
                    if have >= args.per_class:
                        break
                    params = {"q": q, "license": "by,by-sa,cc0,pdm", "page_size": "20", "page": str(page)}
                    d = get(API + "?" + urllib.parse.urlencode(params))
                    time.sleep(4)
                    if not d or not d.get("results"):
                        break
                    for r in d["results"]:
                        if r["id"] in seen or have >= args.per_class:
                            continue
                        seen.add(r["id"])
                        raw = image(r["url"]) or image(r.get("thumbnail") or "")
                        if not raw:
                            continue
                        try:
                            im = Image.open(io.BytesIO(raw)).convert("RGB")
                        except Exception:  # noqa: BLE001 - not an image (HTML error page, SVG...)
                            continue
                        if min(im.size) < 160:
                            continue
                        im.thumbnail((500, 500))
                        name = f"Openverse_{cls}_{r['id'][:13]}.jpg"
                        im.save(OUT / cls / name, quality=90)
                        w.writerow([f"{cls}/{name}", r["id"], r["license"], r.get("license_version", ""), (r.get("creator") or "")[:120],
                                    (r.get("title") or "")[:120], r.get("foreign_landing_url", ""), r.get("source", "")])
                        fh.flush()
                        have += 1
            print(cls, have, flush=True)


if __name__ == "__main__":
    main()
