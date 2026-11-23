"""Indian road photos for the classifier, from RDD2022 (Arya et al., CC BY-SA 4.0), without the 13 GB download.

    ml/.venv/Scripts/python ml/fetch_rdd_india.py [--xml 2500]

The release is one zip on figshare. This reads it remotely with HTTP range requests:
the central directory, then only the India member (527 MB of the 13 GB), cached in ml/raw.
  pothole  crops around D40 (pothole) boxes, with context margin
  road_ok  same-size crops from the same photos that touch no damage box at all
Writes into ml/raw/classifier/{pothole,road_ok}/ as RDD2022_*.jpg and appends to SOURCES.csv.
"""
from __future__ import annotations

import argparse
import csv
import io
import random
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
import zlib
from pathlib import Path

from PIL import Image

URL = "https://ndownloader.figshare.com/files/38030910"
OUT = Path(__file__).resolve().parent / "raw" / "classifier"
CACHE = Path(__file__).resolve().parent / "raw" / "parquet"
LICENCE = "CC-BY-SA-4.0"


class HttpFile(io.RawIOBase):
    """Seekable read-only view of a remote file, one Range request per read."""

    def __init__(self, url: str) -> None:
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=60) as r:
            self.url, self.size = r.geturl(), int(r.headers["Content-Length"])  # follow the redirect once
        self.pos = 0

    def seekable(self) -> bool:
        return True

    def readable(self) -> bool:
        return True

    def tell(self) -> int:
        return self.pos

    def seek(self, offset: int, whence: int = 0) -> int:
        self.pos = {0: offset, 1: self.pos + offset, 2: self.size + offset}[whence]
        return self.pos

    def read(self, n: int = -1) -> bytes:
        end = self.size if n < 0 else min(self.size, self.pos + n)
        if end <= self.pos:
            return b""
        for attempt in range(4):
            try:
                req = urllib.request.Request(self.url, headers={"Range": f"bytes={self.pos}-{end - 1}"})
                with urllib.request.urlopen(req, timeout=120) as r:
                    data = r.read()
                break
            except OSError:
                if attempt == 3:
                    raise
        self.pos += len(data)
        return data

    def readinto(self, b) -> int:  # noqa: ANN001 - io protocol
        data = self.read(len(b))
        b[:len(data)] = data
        return len(data)


def boxes(xml: bytes) -> list[tuple[str, int, int, int, int]]:
    root = ET.fromstring(xml)
    out = []
    for o in root.iter("object"):
        bb = o.find("bndbox")
        out.append((o.findtext("name"), *(int(float(bb.findtext(k))) for k in ("xmin", "ymin", "xmax", "ymax"))))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--xml", type=int, default=2500, help="annotation files to sample")
    args = ap.parse_args()
    rng = random.Random(11)
    india = CACHE / "RDD2022_India.zip"
    if not india.exists():
        remote = HttpFile(URL)
        print(f"remote zip: {remote.size / 1e9:.1f} GB; fetching only India.zip")
        info = next(i for i in zipfile.ZipFile(remote).infolist() if i.filename.endswith("/India.zip"))
        remote.seek(info.header_offset)
        head = remote.read(30)   # local header: 30 bytes + name + extra, then the stored member
        start = info.header_offset + 30 + int.from_bytes(head[26:28], "little") + int.from_bytes(head[28:30], "little")
        CACHE.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(remote.url, headers={"Range": f"bytes={start}-{start + info.compress_size - 1}"})
        with urllib.request.urlopen(req, timeout=600) as r, india.open("wb") as out:
            raw = r.read()
            out.write(zlib.decompress(raw, -15) if info.compress_type == zipfile.ZIP_DEFLATED else raw)
    z = zipfile.ZipFile(india)
    xmls = [n for n in z.namelist() if "/train/" in n and n.endswith(".xml")]
    print("India annotation files:", len(xmls))
    picked = rng.sample(xmls, min(args.xml, len(xmls)))
    read = z.read
    anns = {n: read(n) for n in picked}
    with_holes = {n: b for n, b in ((n, boxes(x)) for n, x in anns.items()) if any(c == "D40" for c, *_ in b)}
    print("sampled", len(anns), "annotations,", len(with_holes), "with potholes (D40)")

    def image_name(xml_name: str) -> str:
        return xml_name.replace("/annotations/xmls/", "/images/").replace(".xml", ".jpg")

    chosen = list(with_holes)
    images = {n: read(image_name(n)) for n in chosen}
    rows, kept = [], {"pothole": 0, "road_ok": 0}
    for n, data in images.items():
        im = Image.open(io.BytesIO(data)).convert("RGB")
        W, H = im.size
        dmg = with_holes[n]
        for k, (cls, x0, y0, x1, y1) in enumerate(dmg):
            if cls != "D40":
                continue
            side = int(max(x1 - x0, y1 - y0) * 1.8)          # pothole plus surrounding road for context
            cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
            box = (max(0, cx - side // 2), max(0, cy - side // 2), min(W, cx + side // 2), min(H, cy + side // 2))
            if min(box[2] - box[0], box[3] - box[1]) < 96:
                continue
            name = f"RDD2022_{Path(n).stem}_{k}.jpg"
            im.crop(box).save(OUT / "pothole" / name, quality=92)
            rows.append((f"pothole/{name}", f"RDD2022 {n} D40 box {k}", LICENCE, "pothole"))
            kept["pothole"] += 1
        # one clean road patch per photo: lower half (road), touching no damage box of any class
        side = H // 3
        for _ in range(20):
            x, y = rng.randint(0, W - side), rng.randint(H // 2, H - side)
            if all(x + side < a or x > c or y + side < b or y > d for _, a, b, c, d in dmg):
                name = f"RDD2022_{Path(n).stem}_road.jpg"
                im.crop((x, y, x + side, y + side)).save(OUT / "road_ok" / name, quality=92)
                rows.append((f"road_ok/{name}", f"RDD2022 {n} clean patch", LICENCE, "road_ok"))
                kept["road_ok"] += 1
                break
    with (OUT / "SOURCES.csv").open("a", newline="", encoding="utf-8") as fh:
        csv.writer(fh).writerows(rows)
    print("RDD2022 India ->", kept)


if __name__ == "__main__":
    main()
