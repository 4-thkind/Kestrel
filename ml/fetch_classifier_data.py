"""Download the photo-classifier training set from public Hugging Face datasets.

    ml/.venv/Scripts/python ml/fetch_classifier_data.py

Uses each dataset's Parquet export (a few large files with the image bytes
inside) instead of one request per image. Writes ml/raw/classifier/<class>/
plus SOURCES.csv (origin and licence of every image). ml/raw is git-ignored.

Classes and sources (licence checked on each dataset card, 2026-11-23):
  pothole   Arpitraj01/Pothole_classification  low/medium/severe       MIT
            keremberke/pothole-segmentation    (Roboflow export)       CC BY 4.0
            MirkoCompagno/Pothole-Frames       held out for testing    Apache-2.0
  road_ok   Arpitraj01/Pothole_classification  none                    MIT
            delima87/manhole_covers_dataset    label "void"            Apache-2.0
  garbage   Akhila-9849/Garbage_Bin_overflow_images                    CC BY 4.0
            Shynuaa/Street-garbage             held out for testing    MIT
  manhole   delima87/manhole_covers_dataset    label "manhole"         Apache-2.0
"""
from __future__ import annotations

import csv
import io
import json
import time
import urllib.request
from pathlib import Path

import pyarrow.parquet as pq
from PIL import Image

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "raw" / "classifier"
CACHE = ROOT / "raw" / "parquet"
HUB = "https://huggingface.co"
MIN_SIDE = 96  # anything smaller is a thumbnail or a broken record, not a usable photo
rows: list[tuple[str, str, str, str]] = []


def fetch(url: str) -> Path:
    target = CACHE / url.replace(HUB + "/", "").replace("/", "_")
    if target.exists():
        return target
    CACHE.mkdir(parents=True, exist_ok=True)
    for attempt in range(5):
        try:
            req = urllib.request.Request(url, headers={"user-agent": "kestrel-ml-fetch/1.0"})
            with urllib.request.urlopen(req, timeout=180) as r:
                target.write_bytes(r.read())
            return target
        except OSError:
            if attempt == 4:
                raise
            time.sleep(2 ** attempt)
    raise AssertionError("unreachable")


def parquet_urls(repo: str, split: str) -> list[str]:
    with urllib.request.urlopen(f"{HUB}/api/datasets/{repo}/parquet", timeout=60) as r:
        configs = json.load(r)
    return (configs.get("default") or configs.get("full") or next(iter(configs.values())))[split]


def resolve(img: dict | None) -> bytes:
    """Inline bytes, or the file an `hf://datasets/<repo>@<rev>/<path>` reference points to."""
    img = img or {}
    if img.get("bytes"):
        return img["bytes"]
    ref = img.get("path") or ""
    if not ref.startswith("hf://datasets/"):
        return b""
    owner, name_rev, file = ref[len("hf://datasets/"):].split("/", 2)
    name, _, rev = name_rev.partition("@")
    url = f"{HUB}/datasets/{owner}/{name}/resolve/{rev or 'main'}/{urllib.request.quote(file)}"
    return fetch(url).read_bytes()


def images(path: Path) -> list[tuple[bytes, int | None]]:
    from concurrent.futures import ThreadPoolExecutor

    table = pq.read_table(path)
    labels = table.column("label").to_pylist() if "label" in table.column_names else [None] * table.num_rows
    with ThreadPoolExecutor(8) as pool:  # referenced files: one request each, so fetch in parallel
        data = list(pool.map(resolve, table.column("image").to_pylist()))
    return list(zip(data, labels))


def save(cls: str, name: str, data: bytes, source: str, licence: str) -> bool:
    try:
        Image.open(io.BytesIO(data)).verify()
        if min(Image.open(io.BytesIO(data)).size) < MIN_SIDE:
            return False
    except Exception:  # noqa: BLE001 - corrupt or empty image records are skipped
        return False
    target = OUT / cls / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    rows.append((f"{cls}/{name}", source, licence, cls))
    return True


def take(repo: str, split: str, licence: str, label_to_class, cap: dict[str, int]) -> None:
    kept: dict[str, int] = {}
    for url in parquet_urls(repo, split):
        for i, (data, label) in enumerate(images(fetch(url))):
            cls = label_to_class(label)
            if cls is None or kept.get(cls, 0) >= cap.get(cls, 10**9):
                continue
            name = f"{repo.split('/')[0]}_{split}_{url.rsplit('/', 1)[-1].split('.')[0]}_{i}.jpg"
            if save(cls, name, data, f"hf:{repo} {split} #{i}", licence):
                kept[cls] = kept.get(cls, 0) + 1
    print(f"{repo} [{split}] -> {kept}", flush=True)


def main() -> None:
    names = ["low", "medium", "none", "severe"]  # Arpitraj01 ClassLabel order
    for split in ("train", "validation", "test"):
        take("Arpitraj01/Pothole_classification", split, "MIT",
             lambda l: "road_ok" if names[l] == "none" else "pothole", {})
    # more pothole sources, so the model learns potholes rather than one dataset's look
    for split in ("train", "validation", "test"):
        take("keremberke/pothole-segmentation", split, "CC-BY-4.0", lambda l: "pothole", {"pothole": 300})
    take("MirkoCompagno/Pothole-Frames", "train", "Apache-2.0", lambda l: "pothole", {})   # held out for testing
    take("Akhila-9849/Garbage_Bin_overflow_images", "train", "CC-BY-4.0", lambda l: "garbage", {"garbage": 600})
    take("Shynuaa/Street-garbage", "test", "MIT", lambda l: "garbage", {})
    for split in ("train", "test"):
        take("delima87/manhole_covers_dataset", split, "Apache-2.0",
             lambda l: "manhole" if l == 0 else "road_ok", {"manhole": 800, "road_ok": 450})

    with (OUT / "SOURCES.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["file", "source", "licence", "class"])
        w.writerows(rows)
    counts: dict[str, int] = {}
    for *_, cls in rows:
        counts[cls] = counts.get(cls, 0) + 1
    print("total", len(rows), counts)


if __name__ == "__main__":
    main()
