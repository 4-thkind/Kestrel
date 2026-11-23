"""Train the on-device photo classifier that suggests an issue category from a citizen's photo.

    ml/.venv/Scripts/python ml/train_classifier.py [--epochs 14]

MobileNetV3-Small (ImageNet weights) fine-tuned on ml/raw/classifier/<class>/.
Test set = whole held-out sources (see HELD_OUT); val = 10% hash split of the rest. Exports
ml/raw/issue-classifier-mnv3.onnx (input: 1x3x224x224 RGB in 0..1,
normalisation inside the graph; output: class probabilities) and writes
ml/classifier_metrics.json with test-set accuracy and the confusion matrix.

Not shipped in the app: on held-out sources it scores ~56% (see classifier_metrics.json). It ships
once Kestrel's own citizen-confirmed photos give it Indian street data to learn from.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import torch
from PIL import Image
from torch import nn
from torch.utils.data import DataLoader, Dataset, WeightedRandomSampler
from torchvision import models, transforms

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "raw" / "classifier"
CLASSES = ["pothole", "garbage", "manhole", "road_ok"]   # order is the model's output order
ONNX_OUT = ROOT / "raw" / "issue-classifier-mnv3.onnx"   # not shipped: see the docstring
MEAN, STD = [0.485, 0.456, 0.406], [0.229, 0.224, 0.225]


#: Whole sources the model never trains on. A random split scored 99% while every pothole from an
#: unseen source came out "garbage": the model had learned each dataset's look, not the problem.
HELD_OUT = {"MirkoCompagno", "Shynuaa"}


def split_of(path: Path) -> str:
    source, cls = path.name.split("_")[0], path.parent.name
    if source in HELD_OUT or (source == "delima87" and "_test_" in path.name) or \
            (source == "Arpitraj01" and cls == "road_ok"):  # plain road from a pothole source: the hardest negative
        return "test"
    return "val" if int(hashlib.sha1(path.name.encode()).hexdigest(), 16) % 10 == 0 else "train"


class Folder(Dataset):
    def __init__(self, split: str, tf: transforms.Compose) -> None:
        self.items = [(p, CLASSES.index(c.name)) for c in sorted(DATA.iterdir()) if c.is_dir() and c.name in CLASSES
                      for p in sorted(c.iterdir()) if split_of(p) == split]
        self.tf = tf

    def __len__(self) -> int:
        return len(self.items)

    def __getitem__(self, i: int):
        path, y = self.items[i]
        return self.tf(Image.open(path).convert("RGB")), y


class Exported(nn.Module):
    """Takes RGB in 0..1, normalises inside the graph, returns probabilities."""
    def __init__(self, net: nn.Module) -> None:
        super().__init__()
        self.net = net
        self.register_buffer("mean", torch.tensor(MEAN).view(1, 3, 1, 1))
        self.register_buffer("std", torch.tensor(STD).view(1, 3, 1, 1))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return torch.softmax(self.net((x - self.mean) / self.std), dim=1)


#: ImageNet classes that mean "this photo is a vehicle", not litter or a road surface.
#: 569 "garbage truck" is deliberately absent: it fires on wheelie bins, which are real garbage photos.
VEHICLES = {407, 436, 468, 479, 511, 555, 573, 575, 581, 603, 609, 627, 656, 661, 665, 670, 675, 705, 717,
            734, 751, 817, 864, 867}


def clean(device: str) -> list[str]:
    """Move vehicle photos out of the noisy web-scraped classes (garbage, road_ok) before splitting.
    Uses a stronger ImageNet model as a filter; every dropped file is logged to dropped.txt."""
    judge = models.efficientnet_b0(weights=models.EfficientNet_B0_Weights.IMAGENET1K_V1).to(device).eval()
    tf = transforms.Compose([transforms.Resize(256), transforms.CenterCrop(224), transforms.ToTensor(),
                             transforms.Normalize(MEAN, STD)])
    dropped = []
    out = DATA.parent / "dropped"
    with torch.no_grad():
        for cls in ("garbage", "road_ok"):
            for path in sorted((DATA / cls).iterdir()):
                top = judge(tf(Image.open(path).convert("RGB")).unsqueeze(0).to(device)).argmax(1).item()
                if top in VEHICLES:
                    (out / cls).mkdir(parents=True, exist_ok=True)
                    path.rename(out / cls / path.name)
                    dropped.append(f"{cls}/{path.name}\timagenet:{top}")
    log = DATA.parent / "dropped.txt"
    earlier = log.read_text(encoding="utf-8").splitlines() if log.exists() else []  # reruns keep the history
    log.write_text("\n".join(earlier + dropped), encoding="utf-8")
    return earlier + dropped


def shrink(max_side: int = 384) -> int:
    """Downscale large source photos once, in place: decoding 4000 px JPEGs on the CPU, not the GPU,
    was the bottleneck. 384 px still leaves room for the 224 px random crops."""
    n = 0
    for path in DATA.rglob("*.jpg"):
        im = Image.open(path)
        if max(im.size) > max_side:
            im = im.convert("RGB")
            im.thumbnail((max_side, max_side), Image.LANCZOS)
            im.save(path, quality=92)
            n += 1
    return n


def evaluate(net: nn.Module, loader: DataLoader, device: str) -> tuple[float, np.ndarray]:
    net.eval()
    cm = np.zeros((len(CLASSES), len(CLASSES)), dtype=int)
    with torch.no_grad():
        for x, y in loader:
            pred = net(x.to(device)).argmax(1).cpu().numpy()
            for t, p in zip(y.numpy(), pred):
                cm[t, p] += 1
    return float(np.trace(cm) / max(1, cm.sum())), cm


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=14)
    ap.add_argument("--batch", type=int, default=48)
    args = ap.parse_args()
    torch.manual_seed(0)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    dropped = clean(device)
    print(f"cleaning: moved {len(dropped)} vehicle photos out of garbage/road_ok (see ml/raw/dropped.txt)")
    print(f"resized {shrink()} large photos to 384 px")

    train_tf = transforms.Compose([
        transforms.RandomResizedCrop(224, scale=(0.55, 1.0)), transforms.RandomHorizontalFlip(),
        transforms.ColorJitter(0.3, 0.3, 0.25, 0.03), transforms.ToTensor(), transforms.Normalize(MEAN, STD)])
    eval_tf = transforms.Compose([transforms.Resize(256), transforms.CenterCrop(224), transforms.ToTensor(),
                                  transforms.Normalize(MEAN, STD)])
    train, val, test = Folder("train", train_tf), Folder("val", eval_tf), Folder("test", eval_tf)
    counts = np.bincount([y for _, y in train.items], minlength=len(CLASSES))
    print("train/val/test:", len(train), len(val), len(test), "per class (train):", dict(zip(CLASSES, counts.tolist())))
    weights = [1.0 / counts[y] for _, y in train.items]            # balance classes per batch
    loader = DataLoader(train, batch_size=args.batch, num_workers=4, persistent_workers=True,
                        sampler=WeightedRandomSampler(weights, num_samples=len(train), replacement=True))
    val_loader = DataLoader(val, batch_size=64)
    test_loader = DataLoader(test, batch_size=64)

    net = models.mobilenet_v3_small(weights=models.MobileNet_V3_Small_Weights.IMAGENET1K_V1)
    net.classifier[3] = nn.Linear(net.classifier[3].in_features, len(CLASSES))
    net.to(device)
    opt = torch.optim.AdamW(net.parameters(), lr=6e-4, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=args.epochs)
    loss_fn = nn.CrossEntropyLoss(label_smoothing=0.05)
    best, best_state = -1.0, None
    for epoch in range(args.epochs):
        net.train()
        total = 0.0
        for x, y in loader:
            opt.zero_grad()
            loss = loss_fn(net(x.to(device)), y.to(device))
            loss.backward()
            opt.step()
            total += loss.item() * len(y)
        sched.step()
        acc, _ = evaluate(net, val_loader, device)
        print(f"epoch {epoch + 1:2d}  loss {total / len(train):.3f}  val acc {acc:.3f}")
        if acc > best:
            best, best_state = acc, {k: v.detach().clone() for k, v in net.state_dict().items()}
    net.load_state_dict(best_state)
    test_acc, cm = evaluate(net, test_loader, device)
    recall = {c: round(float(cm[i, i] / max(1, cm[i].sum())), 3) for i, c in enumerate(CLASSES)}
    precision = {c: round(float(cm[i, i] / max(1, cm[:, i].sum())), 3) for i, c in enumerate(CLASSES)}
    print(f"best val acc {best:.3f}  test acc {test_acc:.3f}\nconfusion (rows = truth):\n{cm}")
    net.eval()
    preds: list[int] = []
    with torch.no_grad():
        for x, _ in test_loader:  # unshuffled, so predictions line up with test.items
            preds += net(x.to(device)).argmax(1).cpu().tolist()
    by_source: dict[str, list[int]] = {}
    for (path, y), p in zip(test.items, preds):
        key = f"{path.name.split('_')[0]}/{CLASSES[y]}"
        by_source.setdefault(key, [0, 0])
        by_source[key][0] += int(p == y)
        by_source[key][1] += 1
    per_source = {k: f"{c}/{n} ({c / n:.0%})" for k, (c, n) in sorted(by_source.items())}
    print("per held-out source:", per_source)

    exported = Exported(net.cpu()).eval()
    ONNX_OUT.parent.mkdir(parents=True, exist_ok=True)
    torch.onnx.export(exported, torch.rand(1, 3, 224, 224), str(ONNX_OUT), input_names=["image"], output_names=["probs"],
                      opset_version=17, dynamo=False)
    # parity: onnxruntime must agree with torch on real test images
    import onnxruntime as ort
    sess = ort.InferenceSession(str(ONNX_OUT))
    raw_tf = transforms.Compose([transforms.Resize(256), transforms.CenterCrop(224), transforms.ToTensor()])
    worst = 0.0
    for path, _ in test.items[:24]:
        x = raw_tf(Image.open(path).convert("RGB")).unsqueeze(0)
        worst = max(worst, float(np.abs(sess.run(None, {"image": x.numpy()})[0] - exported(x).detach().numpy()).max()))
    assert worst < 1e-4, f"onnx/torch mismatch {worst}"
    metrics = {"model": "mobilenet_v3_small (ImageNet) fine-tuned", "classes": CLASSES, "input": "1x3x224x224 RGB 0..1",
               "split": {"train": len(train), "val": len(val), "test": len(test)}, "epochs": args.epochs,
               "bestValAccuracy": round(best, 3), "testAccuracy": round(test_acc, 3), "testRecall": recall,
               "testPrecision": precision, "testBySource": per_source, "confusionRowsTruth": cm.tolist(),
               "heldOutSources": sorted(HELD_OUT), "onnxMaxAbsDiff": worst,
               "onnxBytes": ONNX_OUT.stat().st_size, "droppedVehiclePhotos": len(dropped),
               "sources": "ml/fetch_classifier_data.py (licences listed there)"}
    (ROOT / "classifier_metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
