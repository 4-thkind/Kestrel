"""Export a CLIP-family image encoder to ONNX for the browser, and measure what a phone pays for it.

    ml/.venv/Scripts/python ml/export_vision.py mobileclip_s1 [--out app/public/models/kestrel-vision.onnx]

The graph takes RGB in 0..1 (1x3xSxS), applies the model's own normalisation inside,
and returns an L2-normalised embedding. Text prompts are embedded once, offline
(build_vision_heads.py), so the phone never needs the text encoder.
Writes fp32 and int8 (dynamic weight quantisation) variants, checks both against
PyTorch on real images, and prints size and CPU latency.
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

import numpy as np
import onnxruntime as ort
import open_clip
import torch
from onnxruntime.quantization import QuantType, quantize_dynamic
from PIL import Image
from torch import nn

from clip_probe import MODELS

ROOT = Path(__file__).resolve().parent


class Encoder(nn.Module):
    def __init__(self, visual: nn.Module, mean: list[float], std: list[float]) -> None:
        super().__init__()
        self.visual = visual
        self.register_buffer("mean", torch.tensor(mean).view(1, 3, 1, 1))
        self.register_buffer("std", torch.tensor(std).view(1, 3, 1, 1))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        f = self.visual((x - self.mean) / self.std)
        return f / f.norm(dim=-1, keepdim=True)


def preprocess_info(preprocess) -> tuple[int, list[float], list[float]]:
    size = next(t.size for t in preprocess.transforms if t.__class__.__name__ == "CenterCrop")
    norm = next(t for t in preprocess.transforms if t.__class__.__name__ == "Normalize")
    size = size if isinstance(size, int) else size[0]
    return size, list(norm.mean), list(norm.std)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("model", choices=list(MODELS))
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    name, tag = MODELS[args.model]
    model, _, preprocess = open_clip.create_model_and_transforms(name, pretrained=tag)
    model.eval()
    if hasattr(open_clip, "utils") and hasattr(open_clip.utils, "reparameterize_model"):
        model = open_clip.utils.reparameterize_model(model)   # MobileCLIP: fold train-time branches for inference
    size, mean, std = preprocess_info(preprocess)
    enc = Encoder(model.visual, mean, std).eval()
    out = Path(args.out) if args.out else ROOT / "raw" / f"vision-{args.model}.onnx"
    out.parent.mkdir(parents=True, exist_ok=True)
    torch.onnx.export(enc, torch.rand(1, 3, size, size), str(out), input_names=["image"], output_names=["embedding"],
                      opset_version=17, dynamo=False)
    q8 = out.with_name(out.stem + "-int8.onnx")
    quantize_dynamic(str(out), str(q8), weight_type=QuantType.QUInt8)

    imgs = sorted((ROOT / "raw" / "classifier" / "pothole").glob("RDD2022_*"))[:16]
    to_tensor = lambda p: torch.tensor(  # noqa: E731 - resize+centre crop like open_clip, values 0..1
        np.asarray(Image.open(p).convert("RGB").resize((size, size), Image.BICUBIC), np.float32).transpose(2, 0, 1)[None] / 255)
    for path in (out, q8):
        sess = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
        cos = []
        for p in imgs:
            x = to_tensor(p)
            ref = enc(x).detach().numpy()[0]
            got = sess.run(None, {"image": x.numpy()})[0][0]
            cos.append(float(ref @ got))
        t0 = time.perf_counter()
        for _ in range(5):
            sess.run(None, {"image": to_tensor(imgs[0]).numpy()})
        ms = (time.perf_counter() - t0) / 5 * 1000
        print(f"{path.name}: {path.stat().st_size / 1e6:.1f} MB, min cosine vs torch {min(cos):.4f}, "
              f"laptop CPU {ms:.0f} ms, input {size}px, dim {got.shape[0]}", flush=True)


if __name__ == "__main__":
    main()
