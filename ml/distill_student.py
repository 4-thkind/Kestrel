"""Distil two MIT-licensed CLIP teachers into a phone-sized, permissively licensed student.

    ml/.venv/Scripts/python ml/distill_student.py [--epochs 12]

Teachers: CLIP RN50 (OpenAI, MIT) and CLIP ViT-B/16 (DataComp-XL, MIT). Each image is
described by both L2-normalised embeddings side by side (1024 + 512 dims).
Student: MobileNetV3-Large (torchvision ImageNet weights, BSD-3) with a projection head
trained to reproduce both embeddings (cosine loss per half).

No labels are used: the pool is every Indian road photo in RDD2022 (CC BY-SA 4.0) plus the
non-test images of ml/raw/classifier. Test images and held-out sources are excluded, so
evaluate_vision.py measures the student on photos it never saw. Because the student lives in the
teachers' embedding space, it scores any text prompt the teachers understand: new categories
are new prompts, not new training runs.
Outputs ml/raw/student.pt and ml/raw/student.onnx (input 1x3x224x224 RGB 0..1, ImageNet
normalisation inside; output 1536 = [RN50 half | ViT-B/16 half], each half unit length).
"""
from __future__ import annotations

import argparse
import io
import random
import zipfile
from pathlib import Path

import open_clip
import torch
from PIL import Image
from torch import nn
from torch.utils.data import DataLoader, Dataset
from torchvision import models, transforms

from train_classifier import DATA, split_of

WEB = [Path(__file__).resolve().parent / "raw" / d for d in ("commons", "openverse")]
#: The web pool is small (floods, garbage heaps, manholes, junk photos) next to 13k road photos: repeat it.
WEB_REPEAT = 6

ROOT = Path(__file__).resolve().parent
RDD_ZIP = ROOT / "raw" / "parquet" / "RDD2022_India.zip"
RDD_DIR = ROOT / "raw" / "rdd_india"
TEACHERS = [("RN50", "openai"), ("ViT-B-16", "datacomp_xl_s13b_b90k")]
DIMS = [1024, 512]
IMAGENET = ([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
CLIP_NORM = ([0.48145466, 0.4578275, 0.40821073], [0.26862954, 0.26130258, 0.27577711])


def prepare_rdd(max_side: int = 384) -> None:
    """All RDD2022 India photos, downscaled once (decoding 600 px JPEGs every epoch wastes the GPU)."""
    if RDD_DIR.exists() and any(RDD_DIR.iterdir()):
        return
    RDD_DIR.mkdir(parents=True)
    with zipfile.ZipFile(RDD_ZIP) as z:
        for name in z.namelist():
            if name.endswith(".jpg"):
                im = Image.open(io.BytesIO(z.read(name))).convert("RGB")
                im.thumbnail((max_side, max_side))
                im.save(RDD_DIR / Path(name).name, quality=90)


def pool() -> list[Path]:
    from evaluate_vision import web_split

    labelled = [p for c in DATA.iterdir() if c.is_dir() for p in c.iterdir() if split_of(p) != "test"]
    web = [p for root in WEB if root.exists() for p in sorted(root.rglob("*.jpg")) if web_split(p) == "pool"]
    return labelled + sorted(RDD_DIR.glob("*.jpg")) + web * WEB_REPEAT


class Views(Dataset):
    """One random augmented 224 px view per image; teacher and student see the same pixels."""

    def __init__(self, paths: list[Path]) -> None:
        self.paths = paths
        self.tf = transforms.Compose([
            transforms.RandomResizedCrop(224, scale=(0.35, 1.0), interpolation=transforms.InterpolationMode.BICUBIC),
            transforms.RandomHorizontalFlip(), transforms.ColorJitter(0.3, 0.3, 0.2, 0.02), transforms.ToTensor()])

    def __len__(self) -> int:
        return len(self.paths)

    def __getitem__(self, i: int) -> torch.Tensor:
        return self.tf(Image.open(self.paths[i]).convert("RGB"))


class Student(nn.Module):
    """RGB 0..1 in, [RN50-space | ViT-B/16-space] unit-length halves out."""

    def __init__(self) -> None:
        super().__init__()
        net = models.mobilenet_v3_large(weights=models.MobileNet_V3_Large_Weights.IMAGENET1K_V2)
        self.features, self.pool = net.features, nn.AdaptiveAvgPool2d(1)
        self.head = nn.Sequential(nn.Linear(960, 1536), nn.Hardswish(), nn.Dropout(0.1), nn.Linear(1536, sum(DIMS)))
        self.register_buffer("mean", torch.tensor(IMAGENET[0]).view(1, 3, 1, 1))
        self.register_buffer("std", torch.tensor(IMAGENET[1]).view(1, 3, 1, 1))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        f = self.head(self.pool(self.features((x - self.mean) / self.std)).flatten(1))
        a, b = f.split(DIMS, dim=1)
        return torch.cat([a / a.norm(dim=1, keepdim=True), b / b.norm(dim=1, keepdim=True)], dim=1)


def teacher_embed(teachers: list[nn.Module], x: torch.Tensor) -> torch.Tensor:
    mean = torch.tensor(CLIP_NORM[0], device=x.device).view(1, 3, 1, 1)
    std = torch.tensor(CLIP_NORM[1], device=x.device).view(1, 3, 1, 1)
    with torch.no_grad(), torch.autocast("cuda", dtype=torch.float16):
        outs = [t.encode_image((x - mean) / std).float() for t in teachers]
    return torch.cat([o / o.norm(dim=1, keepdim=True) for o in outs], dim=1)


def loss_fn(s: torch.Tensor, t: torch.Tensor) -> torch.Tensor:
    sa, sb = s.split(DIMS, dim=1)
    ta, tb = t.split(DIMS, dim=1)
    return (2 - (sa * ta).sum(1) - (sb * tb).sum(1)).mean()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=12)
    ap.add_argument("--batch", type=int, default=96)
    ap.add_argument("--init", action="store_true", help="continue from ml/raw/student.pt (e.g. after widening the pool)")
    args = ap.parse_args()
    torch.manual_seed(0)
    random.seed(0)
    device = "cuda"
    prepare_rdd()
    paths = pool()
    print("distillation pool:", len(paths), "images", flush=True)
    teachers = [open_clip.create_model_and_transforms(n, pretrained=t, device=device)[0].eval() for n, t in TEACHERS]
    student = Student()
    if args.init:
        student.load_state_dict(torch.load(ROOT / "raw" / "student.pt", map_location="cpu"))
    student.to(device)
    loader = DataLoader(Views(paths), batch_size=args.batch, shuffle=True, num_workers=6, persistent_workers=True, drop_last=True)
    opt = torch.optim.AdamW([{"params": student.features.parameters(), "lr": 4e-4},
                             {"params": student.head.parameters(), "lr": 2e-3}], weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=[4e-4, 2e-3], total_steps=args.epochs * len(loader), pct_start=0.1)
    scaler = torch.amp.GradScaler()
    for epoch in range(args.epochs):
        student.train()
        total = 0.0
        for x in loader:
            x = x.to(device, non_blocking=True)
            target = teacher_embed(teachers, x)
            with torch.autocast("cuda", dtype=torch.float16):
                loss = loss_fn(student(x).float(), target)
            opt.zero_grad()
            scaler.scale(loss).backward()
            scaler.step(opt)
            scaler.update()
            sched.step()
            total += loss.item()
        print(f"epoch {epoch + 1:2d}  mean (1 - cosine) per teacher {total / len(loader) / 2:.4f}", flush=True)
    student.eval().cpu()
    torch.save(student.state_dict(), ROOT / "raw" / "student.pt")
    torch.onnx.export(student, torch.rand(1, 3, 224, 224), str(ROOT / "raw" / "student.onnx"), input_names=["image"],
                      output_names=["embedding"], opset_version=17, dynamo=False)
    print("saved ml/raw/student.pt and ml/raw/student.onnx")


if __name__ == "__main__":
    main()
