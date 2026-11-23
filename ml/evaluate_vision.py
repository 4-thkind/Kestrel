"""Evaluate the Kestrel vision heads: teachers vs distilled student, on photos neither ever trained on.

    ml/.venv/Scripts/python ml/evaluate_vision.py [--split dev|test]

Test sets (no image here was used for distillation or prompt writing):
  web        Wikimedia Commons and Openverse photos per class (fetch_commons.py, fetch_openverse.py).
             Hash-split in thirds: a pool third the student may see unlabelled during distillation, a dev
             third used to tune prompts, and a test third reported once.
  heldout    whole sources never trained on (train_classifier.HELD_OUT minus the news-video frames,
             which were audited and mostly show no pothole at all).
Reports accuracy, per-class recall, and accuracy-vs-coverage at confidence thresholds, which is
what decides when the app may pre-select a category. Writes ml/vision_eval_<split>.json.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import open_clip
import torch
from PIL import Image
from torchvision import transforms

from distill_student import CLIP_NORM, DIMS, TEACHERS, Student
from train_classifier import DATA, split_of

ROOT = Path(__file__).resolve().parent
WEB = [ROOT / "raw" / "commons", ROOT / "raw" / "openverse"]   # independent web photos, test only

#: Visual classes -> the Kestrel category a citizen would report (None = no issue to report).
CLASS_TO_CATEGORY = {
    "pothole": "POTHOLE", "waterlogging": "WATERLOGGING", "open_manhole": "OPEN_MANHOLE",
    "blocked_road": "BLOCKED_ROAD", "garbage": "GARBAGE_DUMP", "manhole_cover": None,
    "road_ok": None, "not_street": None,
}
PROMPTS: dict[str, list[str]] = {
    "pothole": ["a photo of a pothole in the road", "a damaged road with a deep pothole", "broken asphalt with a hole in the road surface",
                "a road full of potholes", "a crater in a city street"],
    "waterlogging": ["a flooded street with water covering the road", "a waterlogged road after heavy rain",
                     "cars driving through a flooded road", "a street submerged under muddy water", "people wading through a flooded street"],
    "open_manhole": ["an open manhole without a cover", "an uncovered manhole hole in the street", "a dangerous open sewer hole in the road",
                     "workers in an open manhole"],
    "blocked_road": ["a fallen tree blocking the road", "a road blocked by debris", "a road closed with barricades",
                     "a tree fallen across a street after a storm", "construction rubble blocking a street"],
    "garbage": ["a pile of garbage dumped on the street", "an overflowing garbage bin", "trash and litter scattered on the ground",
                "a garbage heap beside a road", "plastic waste dumped in an open area"],
    "manhole_cover": ["a closed metal manhole cover in the road", "a round iron manhole lid in the pavement", "a sewer cover on a street"],
    "road_ok": ["a clean empty road", "a smooth asphalt road", "an ordinary city street", "a road with traffic", "a paved road in good condition"],
    "not_street": ["a selfie of a person", "a plate of food", "the inside of a room", "a pet cat or dog", "a screenshot of a website",
                   "a photo taken indoors"],
}
CLASSES = list(PROMPTS)
#: tune_prompts.py (dev split only) may replace the hand-written prompts and add a per-class logit bias.
_TUNED = ROOT / "prompts.json"
if _TUNED.exists():
    _t = json.loads(_TUNED.read_text(encoding="utf-8"))
    PROMPTS = {c: _t["prompts"][c] for c in CLASSES}
    BIAS = np.array([_t["bias"][c] for c in CLASSES])
else:
    BIAS = np.zeros(len(CLASSES))
COMMONS_LABEL = {"pothole": "pothole", "waterlogging": "waterlogging", "garbage": "garbage", "manhole": "manhole_cover",
                 "open_manhole": "open_manhole", "blocked_road": "blocked_road", "road_ok": "road_ok", "not_street": "not_street"}
HELDOUT_LABEL = {"garbage": "garbage", "manhole": "manhole_cover", "road_ok": "road_ok"}


def web_split(p: Path) -> str:
    """Thirds by file-name hash: "pool" (unlabelled, distillation only), "dev" (prompt tuning), "test" (reported)."""
    return ("pool", "dev", "test")[int(hashlib.sha1(p.name.encode()).hexdigest(), 16) % 3]


def test_images(split: str) -> list[tuple[Path, str, str]]:
    # web photos count only when a person verified the label by looking at them (raw/verified.json):
    # keyword-search labels were 0-70% right depending on the class
    verified = json.loads((ROOT / "raw" / "verified.json").read_text())["classes"]
    out = [(Path(p), COMMONS_LABEL[c], "web") for c, ps in verified.items() for p in ps if web_split(Path(p)) == split]
    out += [(p, HELDOUT_LABEL[c.name], "heldout") for c in sorted(DATA.iterdir()) if c.name in HELDOUT_LABEL
            for p in sorted(c.iterdir()) if split_of(p) == "test" and not p.name.startswith("MirkoCompagno")
            and ("dev", "test")[int(hashlib.sha1(p.name.encode()).hexdigest(), 16) % 2] == split]   # halves: tuning never sees test
    return out


def text_heads(device: str) -> list[np.ndarray]:
    """Per teacher: one unit vector per class (prompt-ensemble mean). Also what the app ships."""
    heads = []
    for name, tag in TEACHERS:
        m, _, _ = open_clip.create_model_and_transforms(name, pretrained=tag, device=device)
        tok = open_clip.get_tokenizer(name)
        rows = []
        with torch.no_grad():
            for c in CLASSES:
                t = m.encode_text(tok(PROMPTS[c]).to(device)).float()
                t = t / t.norm(dim=-1, keepdim=True)
                rows.append((t.mean(0) / t.mean(0).norm()).cpu().numpy())
        heads.append(np.stack(rows))
    return heads


def embed_teachers(paths: list[Path], device: str) -> np.ndarray:
    tf = transforms.Compose([transforms.Resize(224, interpolation=transforms.InterpolationMode.BICUBIC),
                             transforms.CenterCrop(224), transforms.ToTensor(), transforms.Normalize(*CLIP_NORM)])
    parts = []
    for name, tag in TEACHERS:
        m, _, _ = open_clip.create_model_and_transforms(name, pretrained=tag, device=device)
        out = []
        with torch.no_grad():
            for i in range(0, len(paths), 64):
                x = torch.stack([tf(Image.open(p).convert("RGB")) for p in paths[i:i + 64]]).to(device)
                f = m.encode_image(x).float()
                out.append((f / f.norm(dim=-1, keepdim=True)).cpu().numpy())
        parts.append(np.concatenate(out))
    return np.concatenate(parts, axis=1)


def embed_student(paths: list[Path], device: str) -> np.ndarray:
    s = Student()
    s.load_state_dict(torch.load(ROOT / "raw" / "student.pt", map_location="cpu"))
    s.to(device).eval()
    tf = transforms.Compose([transforms.Resize(224, interpolation=transforms.InterpolationMode.BICUBIC),
                             transforms.CenterCrop(224), transforms.ToTensor()])
    out = []
    with torch.no_grad():
        for i in range(0, len(paths), 64):
            out.append(s(torch.stack([tf(Image.open(p).convert("RGB")) for p in paths[i:i + 64]]).to(device)).cpu().numpy())
    return np.concatenate(out)


def probabilities(emb: np.ndarray, heads: list[np.ndarray], scale: float = 100.0, bias: np.ndarray | None = None) -> np.ndarray:
    """Average of the two teachers' cosine logits (+ class bias), softmaxed: the app does exactly this."""
    a, b = np.split(emb, [DIMS[0]], axis=1)
    logits = scale * (a @ heads[0].T + b @ heads[1].T) / 2 + (0 if bias is None else bias)
    e = np.exp(logits - logits.max(1, keepdims=True))
    return e / e.sum(1, keepdims=True)


def report(probs: np.ndarray, labels: np.ndarray, groups: np.ndarray) -> dict:
    pred = probs.argmax(1)
    conf = probs.max(1)
    out = {}
    for g in ("web", "heldout", "all"):
        m = np.ones_like(groups, dtype=bool) if g == "all" else groups == g
        if not m.any():
            continue
        recall = {CLASSES[c]: f"{int((pred[m][labels[m] == c] == c).sum())}/{int((labels[m] == c).sum())}"
                  for c in sorted(set(labels[m]))}
        curve = {}
        for t in (0.0, 0.5, 0.6, 0.7, 0.8, 0.9):
            keep = m & (conf >= t)
            curve[str(t)] = {"coverage": round(float(keep.sum() / m.sum()), 3),
                             "accuracy": round(float((pred[keep] == labels[keep]).mean()), 3) if keep.any() else None}
        out[g] = {"n": int(m.sum()), "accuracy": round(float((pred[m] == labels[m]).mean()), 3), "recall": recall, "byConfidence": curve}
    return out


def same_spot(paths: list[Path], labels: np.ndarray, device: str, seed: int = 0) -> dict:
    """Duplicate-photo matching. Positives: two different crops + lighting of one photo (same spot,
    shot differently). Hard negatives: two different photos of the same class (e.g. two potholes).
    Returns the similarity threshold where at most 5% of different spots match, and the recall there."""
    s = Student()
    s.load_state_dict(torch.load(ROOT / "raw" / "student.pt", map_location="cpu"))
    s.to(device).eval()
    aug = transforms.Compose([transforms.RandomResizedCrop(224, scale=(0.45, 0.9)), transforms.ColorJitter(0.35, 0.35, 0.25),
                              transforms.ToTensor()])
    torch.manual_seed(seed)
    rng = np.random.default_rng(seed)
    a, b = [], []
    with torch.no_grad():
        for i in range(0, len(paths), 48):
            ims = [Image.open(p).convert("RGB") for p in paths[i:i + 48]]
            a.append(s(torch.stack([aug(im) for im in ims]).to(device)).cpu().numpy())
            b.append(s(torch.stack([aug(im) for im in ims]).to(device)).cpu().numpy())
    a, b = np.concatenate(a), np.concatenate(b)
    sim = lambda x, y: ((x[:, :DIMS[0]] * y[:, :DIMS[0]]).sum(1) + (x[:, DIMS[0]:] * y[:, DIMS[0]:]).sum(1)) / 2  # noqa: E731
    pos = sim(a, b)
    neg = []
    for c in set(labels):
        idx = np.flatnonzero(labels == c)
        if len(idx) > 1:
            other = rng.permutation(idx)
            keep = other != idx
            neg.append(sim(a[idx[keep]], b[other[keep]]))
    neg = np.concatenate(neg)
    threshold = float(np.quantile(neg, 0.95))
    return {"pairs": {"same": int(len(pos)), "different": int(len(neg))}, "threshold": round(threshold, 3),
            "recallAtThreshold": round(float((pos >= threshold).mean()), 3),
            "falseMatchAtThreshold": round(float((neg >= threshold).mean()), 3),
            "meanSimilarity": {"same": round(float(pos.mean()), 3), "different": round(float(neg.mean()), 3)}}


def severity(device: str) -> dict:
    """Does the "large pothole" prompt rank severe potholes above low ones? The Arpitraj01 set labels
    potholes low / medium / severe; the teachers never trained on it, so this is a fair check.
    Reports the ROC AUC of P(large) for severe vs low (0.5 = chance)."""
    import pyarrow.parquet as pq

    from build_vision_heads import EXTRA

    names = ["low", "medium", "none", "severe"]
    cache = ROOT / "raw" / "parquet"
    level = {}
    for split in ("train", "validation", "test"):
        f = cache / f"api_datasets_Arpitraj01_Pothole_classification_parquet_default_{split}_0.parquet"
        for i, lab in enumerate(pq.read_table(f).column("label").to_pylist()):
            level[f"Arpitraj01_{split}_0_{i}.jpg"] = names[lab]
    items = [(p, level[p.name]) for p in sorted((DATA / "pothole").glob("Arpitraj01_*")) if level.get(p.name) in ("low", "severe")]
    emb = embed_teachers([p for p, _ in items], device)
    groups = EXTRA["pothole_size"]
    heads = []
    for name, tag in TEACHERS:
        m, _, _ = open_clip.create_model_and_transforms(name, pretrained=tag, device=device)
        tok = open_clip.get_tokenizer(name)
        with torch.no_grad():
            rows = []
            for k in ("small", "large"):
                t = m.encode_text(tok(groups[k]).to(device)).float()
                t = t / t.norm(dim=-1, keepdim=True)
                rows.append((t.mean(0) / t.mean(0).norm()).cpu().numpy())
        heads.append(np.stack(rows))
    p_large = probabilities(emb, heads)[:, 1]
    severe = np.array([lab == "severe" for _, lab in items])
    pos, neg = p_large[severe], p_large[~severe]
    auc = float((pos[:, None] > neg[None, :]).mean() + 0.5 * (pos[:, None] == neg[None, :]).mean())
    return {"severe": int(severe.sum()), "low": int((~severe).sum()), "aucLargeVsSmall": round(auc, 3)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", choices=["dev", "test"], default="dev")
    args = ap.parse_args()
    device = "cuda" if torch.cuda.is_available() else "cpu"
    items = test_images(args.split)
    paths = [p for p, _, _ in items]
    labels = np.array([CLASSES.index(c) for _, c, _ in items])
    groups = np.array([g for _, _, g in items])
    heads = text_heads(device)
    result = {"split": args.split, "classes": CLASSES}
    result["teachers"] = report(probabilities(embed_teachers(paths, device), heads, bias=BIAS), labels, groups)
    if (ROOT / "raw" / "student.pt").exists():
        result["student"] = report(probabilities(embed_student(paths, device), heads, bias=BIAS), labels, groups)
        result["sameSpot"] = same_spot(paths, labels, device)
        print("same spot", result["sameSpot"], flush=True)
    result["potholeSize"] = severity(device)
    print("pothole size", result["potholeSize"], flush=True)
    (ROOT / f"vision_eval_{args.split}.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    for who in ("teachers", "student"):
        if who in result:
            r = result[who]
            print(who, {g: (v["n"], v["accuracy"], v["byConfidence"]["0.7"]) for g, v in r.items()}, flush=True)
            print("  recall", r["all"]["recall"], flush=True)


if __name__ == "__main__":
    main()
