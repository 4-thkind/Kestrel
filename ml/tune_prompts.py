"""Choose the text prompts (and a small per-class bias) on the DEV split only.

    ml/.venv/Scripts/python ml/tune_prompts.py

Starts from a pool of phrasings per class and greedily drops any prompt whose removal raises
mean per-class recall on dev, then fits one bias per class (logit adjustment). The test split is
never read here. Writes ml/prompts.json, which evaluate_vision.py and build_vision_heads.py use.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import open_clip
import torch

from distill_student import DIMS, TEACHERS
from evaluate_vision import CLASSES

ROOT = Path(__file__).resolve().parent
POOL = {
    "pothole": ["a photo of a pothole in the road", "a damaged road with a deep pothole", "broken asphalt with a hole in the road surface",
                "a road full of potholes", "a crater in a city street", "a pothole filled with rainwater", "a close-up of a pothole in asphalt",
                "a broken road with loose gravel and a hole", "an Indian road with potholes"],
    "waterlogging": ["a flooded street with water covering the road", "a waterlogged road after heavy rain", "cars driving through a flooded road",
                     "a street submerged under muddy water", "people wading through a flooded street", "monsoon flooding in an Indian city",
                     "a road underpass filled with water"],
    "open_manhole": ["an open manhole without a cover", "an uncovered manhole hole in the street", "a dangerous open sewer hole in the road",
                     "workers in an open manhole", "a dark open hole in the pavement where the lid is missing", "a manhole with its cover removed"],
    "blocked_road": ["a fallen tree blocking the road", "a road blocked by debris", "a road closed with barricades",
                     "a tree fallen across a street after a storm", "construction rubble blocking a street", "a road closed sign and barriers"],
    "garbage": ["a pile of garbage dumped on the street", "an overflowing garbage bin", "trash and litter scattered on the ground",
                "a garbage heap beside a road", "plastic waste dumped in an open area", "garbage bags piled on a footpath"],
    "manhole_cover": ["a closed metal manhole cover in the road", "a round iron manhole lid in the pavement", "a sewer cover on a street",
                      "a patterned cast iron manhole cover", "a square utility cover set in the pavement", "a close-up of a manhole cover"],
    "road_ok": ["a clean empty road", "a smooth asphalt road", "an ordinary city street", "a road with traffic", "a paved road in good condition",
                "a close-up of an asphalt road surface", "a close-up of paving stones", "a grey concrete road surface", "a sidewalk next to a road"],
    "not_street": ["a selfie of a person", "a plate of food", "the inside of a room", "a pet cat or dog", "a screenshot of a website",
                   "a photo taken indoors", "a portrait photo of a person", "a living room with furniture", "a cat sitting on a sofa"],
}


def encode() -> dict[str, list[np.ndarray]]:
    """prompt embeddings per class, per teacher: {class: [array(n, d_rn50), array(n, d_vit)]}"""
    out: dict[str, list[np.ndarray]] = {c: [] for c in CLASSES}
    for name, tag in TEACHERS:
        m, _, _ = open_clip.create_model_and_transforms(name, pretrained=tag, device="cuda")
        tok = open_clip.get_tokenizer(name)
        with torch.no_grad():
            for c in CLASSES:
                t = m.encode_text(tok(POOL[c]).cuda()).float()
                out[c].append((t / t.norm(dim=-1, keepdim=True)).cpu().numpy())
    return out


def logits(emb: np.ndarray, enc: dict, sel: dict[str, list[int]], bias: np.ndarray) -> np.ndarray:
    a, b = emb[:, :DIMS[0]], emb[:, DIMS[0]:]
    cols = []
    for c in CLASSES:
        va, vb = enc[c][0][sel[c]].mean(0), enc[c][1][sel[c]].mean(0)
        cols.append(100 * (a @ (va / np.linalg.norm(va)) + b @ (vb / np.linalg.norm(vb))) / 2)
    return np.stack(cols, 1) + bias


def macro(l: np.ndarray, y: np.ndarray) -> float:
    pred = l.argmax(1)
    return float(np.mean([(pred[y == c] == c).mean() for c in np.unique(y)]))


def main() -> None:
    d = np.load(ROOT / "raw" / "dev_teacher_emb.npz")
    emb, y = d["emb"], d["y"]
    enc = encode()
    sel = {c: list(range(len(POOL[c]))) for c in CLASSES}
    bias = np.zeros(len(CLASSES))
    best = macro(logits(emb, enc, sel, bias), y)
    print("start macro recall", round(best, 3))
    improved = True
    while improved:
        improved = False
        for c in CLASSES:
            for i in list(sel[c]):
                if len(sel[c]) <= 2:
                    break
                trial = {**sel, c: [j for j in sel[c] if j != i]}
                score = macro(logits(emb, enc, trial, bias), y)
                if score > best + 1e-4:
                    best, sel, improved = score, trial, True
    print("after prompt pruning", round(best, 3))
    for _ in range(3):   # coordinate search on per-class bias, small range to limit overfitting
        for k in range(len(CLASSES)):
            for delta in np.linspace(-3, 3, 13):
                trial = bias.copy()
                trial[k] = delta
                score = macro(logits(emb, enc, sel, trial), y)
                if score > best + 1e-4:
                    best, bias = score, trial
    print("after bias", round(best, 3), dict(zip(CLASSES, bias.round(2))))
    pred = logits(emb, enc, sel, bias).argmax(1)
    print("dev recall", {CLASSES[c]: f"{int((pred[y == c] == c).sum())}/{int((y == c).sum())}" for c in np.unique(y)})
    (ROOT / "prompts.json").write_text(json.dumps({
        "prompts": {c: [POOL[c][i] for i in sel[c]] for c in CLASSES},
        "bias": {c: round(float(b), 3) for c, b in zip(CLASSES, bias)},
        "devMacroRecall": round(best, 3),
        "note": "chosen on the dev split only (tune_prompts.py); the test split is reported separately",
    }, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
