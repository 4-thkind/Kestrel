"""Which frozen backbone generalises to *unseen* sources? Linear probe comparison.

    ml/.venv/Scripts/python ml/probe_backbones.py

Fine-tuning MobileNetV3 end to end scored 99.6% on validation but 54.5% on held-out
sources: it learned each dataset's look. Here every backbone stays frozen (ImageNet
weights); only a logistic-regression head is trained on train-split features, and
the score that matters is accuracy on the held-out sources (train_classifier.HELD_OUT).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import torch
from PIL import Image
from torch import nn
from torchvision import models, transforms

from train_classifier import CLASSES, DATA, MEAN, STD, split_of

ROOT = Path(__file__).resolve().parent
BACKBONES = {
    "mobilenet_v3_large": (models.mobilenet_v3_large, models.MobileNet_V3_Large_Weights.IMAGENET1K_V2, "classifier"),
    "efficientnet_b0": (models.efficientnet_b0, models.EfficientNet_B0_Weights.IMAGENET1K_V1, "classifier"),
    "regnet_y_800mf": (models.regnet_y_800mf, models.RegNet_Y_800MF_Weights.IMAGENET1K_V2, "fc"),
    "convnext_tiny": (models.convnext_tiny, models.ConvNeXt_Tiny_Weights.IMAGENET1K_V1, "classifier"),
}
TF = transforms.Compose([transforms.Resize(256), transforms.CenterCrop(224), transforms.ToTensor(), transforms.Normalize(MEAN, STD)])


def items() -> list[tuple[Path, int, str]]:
    return [(p, CLASSES.index(c.name), split_of(p)) for c in sorted(DATA.iterdir()) if c.is_dir() and c.name in CLASSES
            for p in sorted(c.iterdir())]


def features(name: str, data: list[tuple[Path, int, str]], device: str) -> np.ndarray:
    ctor, weights, head = BACKBONES[name]
    net = ctor(weights=weights)
    if head == "fc":
        net.fc = nn.Identity()
    elif name == "convnext_tiny":
        net.classifier[2] = nn.Identity()   # keep LayerNorm + flatten, drop the linear layer
    else:
        net.classifier = nn.Identity()
    net.to(device).eval()
    out = []
    with torch.no_grad():
        for i in range(0, len(data), 64):
            x = torch.stack([TF(Image.open(p).convert("RGB")) for p, _, _ in data[i:i + 64]]).to(device)
            out.append(net(x).flatten(1).cpu().numpy())
    return np.concatenate(out)


def fit_head(x: np.ndarray, y: np.ndarray, device: str, epochs: int = 300) -> nn.Linear:
    """Class-balanced logistic regression on L2-normalised features."""
    xt, yt = torch.tensor(x, device=device), torch.tensor(y, device=device)
    head = nn.Linear(x.shape[1], len(CLASSES)).to(device)
    counts = np.bincount(y, minlength=len(CLASSES))
    loss_fn = nn.CrossEntropyLoss(weight=torch.tensor(len(y) / (len(CLASSES) * counts), dtype=torch.float32, device=device))
    opt = torch.optim.AdamW(head.parameters(), lr=1e-2, weight_decay=1e-3)
    for _ in range(epochs):
        opt.zero_grad()
        loss_fn(head(xt), yt).backward()
        opt.step()
    return head


def main() -> None:
    device = "cuda" if torch.cuda.is_available() else "cpu"
    data = items()
    y = np.array([c for _, c, _ in data])
    split = np.array([s for _, _, s in data])
    src = np.array([f"{p.name.split('_')[0]}/{CLASSES[c]}" for p, c, _ in data])
    report = {}
    for name in BACKBONES:
        x = features(name, data, device)
        x /= np.linalg.norm(x, axis=1, keepdims=True)
        train = split != "test"
        head = fit_head(x[train], y[train], device)
        with torch.no_grad():
            pred = head(torch.tensor(x[~train], device=device)).argmax(1).cpu().numpy()
        truth, sources = y[~train], src[~train]
        per = {s: f"{int((pred[sources == s] == truth[sources == s]).sum())}/{int((sources == s).sum())}" for s in sorted(set(sources))}
        # macro accuracy over held-out sources, so the big garbage source cannot dominate
        macro = float(np.mean([(pred[sources == s] == truth[sources == s]).mean() for s in set(sources)]))
        report[name] = {"heldOutAccuracy": round(float((pred == truth).mean()), 3), "heldOutMacroBySource": round(macro, 3), "bySource": per}
        print(name, json.dumps(report[name]), flush=True)
    (ROOT / "backbone_probe.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
