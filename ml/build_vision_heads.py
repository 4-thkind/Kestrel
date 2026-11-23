"""Package Kestrel Vision for the app: the distilled student (fp16 weights) and its text heads.

    ml/.venv/Scripts/python ml/build_vision_heads.py

Writes
  app/public/models/kestrel-vision.onnx        student encoder; weights stored as fp16 and cast to fp32
                                               on load, so it is half the size with no fp16 kernels needed
  app/public/models/kestrel-vision-heads.json  pre-computed text embeddings for every question the app asks,
                                               plus the confidence threshold calibrated on the dev split
The phone never runs a text encoder: a "head" is just a set of unit vectors, and a new question is a
new set of prompts embedded here once.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import onnx
import onnxruntime as ort
import open_clip
import torch
from onnx import helper, numpy_helper
from PIL import Image
from torchvision import transforms

from distill_student import DIMS, TEACHERS, Student
from evaluate_vision import BIAS, CLASS_TO_CATEGORY, CLASSES, PROMPTS

ROOT = Path(__file__).resolve().parent
APP_MODELS = ROOT.parent / "app" / "public" / "models"

#: Extra questions answered from the same photo embedding (no extra model, no extra download).
EXTRA = {
    # pothole size hint: offered as a suggestion for the "deep" detail chip, never applied silently
    "pothole_size": {"small": ["a small shallow pothole", "a minor crack in the road surface", "a tiny hole in the asphalt"],
                     "large": ["a large deep pothole", "a huge dangerous pothole full of water", "a wide crater in the road"]},
    # privacy: suggest retaking when a face fills the frame
    "privacy": {"face": ["a close-up photo of a person's face", "a selfie", "a portrait of a person"],
                "scene": ["a photo of a street", "a photo of a road", "a photo of a place"]},
}


def text_vectors(prompts: dict[str, list[str]]) -> dict[str, list[float]]:
    """Per label: [RN50 half | ViT-B/16 half], each half the unit-normalised mean of its prompt embeddings."""
    halves: dict[str, list[np.ndarray]] = {k: [] for k in prompts}
    for name, tag in TEACHERS:
        m, _, _ = open_clip.create_model_and_transforms(name, pretrained=tag)
        tok = open_clip.get_tokenizer(name)
        with torch.no_grad():
            for k, ps in prompts.items():
                t = m.encode_text(tok(ps)).float()
                t = t / t.norm(dim=-1, keepdim=True)
                halves[k].append((t.mean(0) / t.mean(0).norm()).numpy())
    return {k: [round(float(v), 5) for v in np.concatenate(h)] for k, h in halves.items()}


def fp16_weights(src: Path, dst: Path) -> None:
    """Store large float32 initialisers as float16 with a Cast back to float32 in the graph."""
    m = onnx.load(str(src))
    g = m.graph
    keep, casts = [], []
    for init in g.initializer:
        arr = numpy_helper.to_array(init)
        if arr.dtype == np.float32 and arr.size >= 1024:
            half = numpy_helper.from_array(arr.astype(np.float16), init.name + "__fp16")
            keep.append(half)
            casts.append(helper.make_node("Cast", [half.name], [init.name], to=onnx.TensorProto.FLOAT, name=init.name + "__cast"))
        else:
            keep.append(init)
    del g.initializer[:]
    g.initializer.extend(keep)
    nodes = list(g.node)
    del g.node[:]
    g.node.extend(casts + nodes)
    onnx.save(m, str(dst))


def main() -> None:
    APP_MODELS.mkdir(parents=True, exist_ok=True)
    out = APP_MODELS / "kestrel-vision.onnx"
    fp16_weights(ROOT / "raw" / "student.onnx", out)

    # parity: the shipped fp16-weight graph vs the PyTorch student, on real photos
    student = Student()
    student.load_state_dict(torch.load(ROOT / "raw" / "student.pt", map_location="cpu"))
    student.eval()
    tf = transforms.Compose([transforms.Resize(224, interpolation=transforms.InterpolationMode.BICUBIC),
                             transforms.CenterCrop(224), transforms.ToTensor()])
    sess = ort.InferenceSession(str(out), providers=["CPUExecutionProvider"])
    photos = sorted((ROOT / "raw" / "rdd_india").glob("*.jpg"))[:24]
    worst = 1.0
    for p in photos:
        x = tf(Image.open(p).convert("RGB")).unsqueeze(0)
        ref = student(x).detach().numpy()[0]
        got = sess.run(None, {"image": x.numpy()})[0][0]
        worst = min(worst, float((ref[:DIMS[0]] @ got[:DIMS[0]] + ref[DIMS[0]:] @ got[DIMS[0]:]) / 2))
    assert worst > 0.999, f"fp16 weights changed the embedding: cosine {worst}"

    dev_eval = json.loads((ROOT / "vision_eval_dev.json").read_text())
    dev = dev_eval["student"]["all"]["byConfidence"]
    # lowest threshold whose dev accuracy reaches 90%: below it the app only shows a hint, never pre-selects
    threshold = next((float(t) for t, v in sorted(dev.items(), key=lambda kv: float(kv[0]))
                      if v["accuracy"] is not None and v["accuracy"] >= 0.9), 0.9)
    heads = {
        "version": "kestrel-vision-1",
        "dims": DIMS,
        "scale": 100,
        "input": {"size": 224, "range": "0..1 RGB", "crop": "resize shorter side to 224, centre crop"},
        "preselectThreshold": threshold,
        "sameSpotThreshold": dev_eval["sameSpot"]["threshold"],
        "classes": [{"key": c, "category": CLASS_TO_CATEGORY[c]} for c in CLASSES],
        "classVectors": text_vectors(PROMPTS),
        "classBias": {c: float(b) for c, b in zip(CLASSES, BIAS)},
        "extra": {name: text_vectors(groups) for name, groups in EXTRA.items()},
        "provenance": "Distilled MobileNetV3-Large student (BSD-3 backbone) of CLIP RN50 (OpenAI, MIT) and "
                      "CLIP ViT-B/16 (DataComp-XL, MIT). See ml/ and the README.",
    }
    (APP_MODELS / "kestrel-vision-heads.json").write_text(json.dumps(heads, separators=(",", ":")), encoding="utf-8")
    print(f"kestrel-vision.onnx {out.stat().st_size / 1e6:.1f} MB (parity cosine {worst:.5f}); "
          f"heads {len(CLASSES)} classes + {list(EXTRA)}; pre-select threshold {threshold}")


if __name__ == "__main__":
    main()
