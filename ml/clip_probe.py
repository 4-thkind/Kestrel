"""Do web-scale image-text backbones (CLIP family) generalise to unseen sources where ImageNet ones failed?

    ml/.venv/Scripts/python ml/clip_probe.py [--models ...]

For each backbone: embed every image once, then score on the held-out sources (train_classifier.HELD_OUT):
  zero-shot     text prompts only, no training on our data at all
  linear probe  logistic regression on train-split embeddings
  blend         probe logits + zero-shot logits (zero-shot acts as a prior that knows the world)
Writes ml/clip_probe.json. Embeddings are cached in ml/raw/emb_<model>.npz for later stages.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import open_clip
import torch
from PIL import Image
from torch import nn

from train_classifier import CLASSES, DATA, split_of

ROOT = Path(__file__).resolve().parent
MODELS = {
    "mobileclip2_s0": ("MobileCLIP2-S0", "dfndr2b"),
    "mobileclip_s1": ("MobileCLIP-S1", "datacompdr"),
    "rn50_openai": ("RN50", "openai"),
    "vitb32_openai": ("ViT-B-32", "openai"),
    "vitb32_laion2b": ("ViT-B-32", "laion2b_s34b_b79k"),
    "vitb16_datacomp": ("ViT-B-16", "datacomp_xl_s13b_b90k"),
}
#: Several phrasings per class, averaged: the standard CLIP prompt-ensemble trick.
PROMPTS = {
    "pothole": ["a photo of a pothole on a road", "a damaged road with a large pothole", "broken asphalt with a hole in the road",
                "a crater in the street surface", "a road with potholes in India"],
    "garbage": ["a photo of garbage dumped on the street", "an overflowing garbage bin", "a pile of trash and litter on the ground",
                "waste dumped beside a road", "a garbage heap in an Indian street"],
    "manhole": ["a photo of a manhole cover on the street", "a metal sewer manhole lid in the pavement", "a drain cover on a road",
                "a round iron utility cover in the ground"],
    "road_ok": ["a photo of a clean empty road", "a smooth asphalt road surface", "an ordinary street with nothing wrong",
                "a paved road in good condition", "a plain road surface"],
}


def items() -> list[tuple[Path, int, str]]:
    return [(p, CLASSES.index(c.name), split_of(p)) for c in sorted(DATA.iterdir()) if c.is_dir() and c.name in CLASSES
            for p in sorted(c.iterdir())]


def embed(key: str, data: list[tuple[Path, int, str]], device: str) -> tuple[np.ndarray, np.ndarray]:
    cache = ROOT / "raw" / f"emb_{key}.npz"
    name, tag = MODELS[key]
    model, _, preprocess = open_clip.create_model_and_transforms(name, pretrained=tag, device=device)
    model.eval()
    tok = open_clip.get_tokenizer(name)
    with torch.no_grad():
        text = []
        for c in CLASSES:
            t = model.encode_text(tok(PROMPTS[c]).to(device)).float()
            t = t / t.norm(dim=-1, keepdim=True)
            text.append((t.mean(0) / t.mean(0).norm()).cpu().numpy())
        if cache.exists():
            return np.load(cache)["img"], np.stack(text)
        out = []
        for i in range(0, len(data), 64):
            x = torch.stack([preprocess(Image.open(p).convert("RGB")) for p, _, _ in data[i:i + 64]]).to(device)
            f = model.encode_image(x).float()
            out.append((f / f.norm(dim=-1, keepdim=True)).cpu().numpy())
    img = np.concatenate(out)
    np.savez_compressed(cache, img=img)
    return img, np.stack(text)


def probe(x: np.ndarray, y: np.ndarray, device: str) -> nn.Linear:
    xt, yt = torch.tensor(x, device=device), torch.tensor(y, device=device)
    head = nn.Linear(x.shape[1], len(CLASSES)).to(device)
    counts = np.bincount(y, minlength=len(CLASSES))
    loss_fn = nn.CrossEntropyLoss(weight=torch.tensor(len(y) / (len(CLASSES) * counts), dtype=torch.float32, device=device))
    opt = torch.optim.AdamW(head.parameters(), lr=5e-3, weight_decay=1e-2)
    for _ in range(400):
        opt.zero_grad()
        loss_fn(head(xt * 10), yt).backward()
        opt.step()
    return head


def score(pred: np.ndarray, truth: np.ndarray, sources: np.ndarray) -> dict:
    per = {s: round(float((pred[sources == s] == truth[sources == s]).mean()), 3) for s in sorted(set(sources))}
    return {"acc": round(float((pred == truth).mean()), 3), "macro": round(float(np.mean(list(per.values()))), 3), "bySource": per}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="*", default=list(MODELS))
    args = ap.parse_args()
    device = "cuda" if torch.cuda.is_available() else "cpu"
    data = items()
    y = np.array([c for _, c, _ in data])
    test = np.array([s == "test" for _, _, s in data])
    src = np.array([f"{p.name.split('_')[0]}/{CLASSES[c]}" for p, c, _ in data])
    out_path = ROOT / "clip_probe.json"
    report = json.loads(out_path.read_text()) if out_path.exists() else {}
    for key in args.models:
        img, text = embed(key, data, device)
        zs = img @ text.T * 100                                  # zero-shot logits
        head = probe(img[~test], y[~test], device)
        with torch.no_grad():
            pl = head(torch.tensor(img[test] * 10, device=device)).cpu().numpy()
        zt = zs[test]
        blend = torch.log_softmax(torch.tensor(pl), 1) + torch.log_softmax(torch.tensor(zt), 1)
        report[key] = {"zeroShot": score(zt.argmax(1), y[test], src[test]),
                       "linearProbe": score(pl.argmax(1), y[test], src[test]),
                       "blend": score(blend.argmax(1).numpy(), y[test], src[test]),
                       "dim": int(img.shape[1])}
        print(key, json.dumps({k: (v["acc"], v["macro"]) for k, v in report[key].items() if k != "dim"}), flush=True)
        out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
