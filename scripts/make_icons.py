"""Kestrel app icons from the brand logo.

    python scripts/make_icons.py [--source assets/kestrel-logo.png]

The source is the full logo (bird-and-road mark + "Kestrel" wordmark). The mark
is cut out automatically: columns that contain logo pixels form runs, and the
mark is everything left of the widest empty gap. The mark is placed on a light
rounded tile for every PWA icon, and saved transparent for the app UI.
Needs Pillow.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
ICONS = ROOT / "app" / "public" / "icons"
TILE = "#FFFDF9"           # icon background: the mark's teal needs a light ground


def logo_mask(img: Image.Image) -> Image.Image:
    """255 where the logo is: alpha when the source has transparency, else distance from the corner colour."""
    alpha = img.getchannel("A")
    if alpha.getextrema()[0] < 250:
        return alpha.point(lambda a: 255 if a > 24 else 0)
    rgb = img.convert("RGB")
    diff = ImageChops.difference(rgb, Image.new("RGB", rgb.size, rgb.getpixel((2, 2)))).convert("L")
    return diff.point(lambda v: 255 if v > 40 else 0)


def cut_mark(src: Path) -> Image.Image:
    img = Image.open(src).convert("RGBA")
    mask = logo_mask(img)
    w, h = img.size
    px = mask.load()
    filled = [any(px[x, y] for y in range(0, h, 2)) for x in range(w)]
    runs, start = [], None
    for x, f in enumerate(filled + [False]):
        if f and start is None:
            start = x
        elif not f and start is not None:
            runs.append((start, x))
            start = None
    if not runs:
        raise SystemExit("no logo pixels found")
    gaps = [(runs[i + 1][0] - runs[i][1], i) for i in range(len(runs) - 1)]
    split = max(gaps)[1] if gaps else len(runs) - 1    # widest gap separates mark and wordmark
    box = (runs[0][0], 0, runs[split][1], h)
    mark, mark_mask = img.crop(box), mask.crop(box)
    bbox = mark_mask.getbbox()
    mark, mark_mask = mark.crop(bbox), mark_mask.crop(bbox)
    mark.putalpha(ImageChops.multiply(mark.getchannel("A"), mark_mask))  # transparent outside the mark
    return mark


def tile(mark: Image.Image, size: int, fill: float, radius: float) -> Image.Image:
    big = size * 4  # supersample for clean edges
    out = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    ImageDraw.Draw(out).rounded_rectangle((0, 0, big - 1, big - 1), radius=radius * big, fill=TILE)
    scale = fill * big / max(mark.size)
    m = mark.resize((round(mark.width * scale), round(mark.height * scale)), Image.LANCZOS)
    out.alpha_composite(m, ((big - m.width) // 2, (big - m.height) // 2))
    return out.resize((size, size), Image.LANCZOS)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default=str(ROOT / "assets" / "kestrel-logo.png"))
    src = Path(ap.parse_args().source)
    mark = cut_mark(src)
    ICONS.mkdir(parents=True, exist_ok=True)
    side = max(mark.size)
    square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    square.alpha_composite(mark, ((side - mark.width) // 2, (side - mark.height) // 2))
    square.resize((512, 512), Image.LANCZOS).save(ICONS / "logo-mark.png")      # transparent, for the UI
    for name, size, fill, radius in [("icon-192.png", 192, .78, .22), ("icon-512.png", 512, .78, .22),
                                     ("maskable-512.png", 512, .62, 0), ("apple-touch-icon.png", 180, .72, 0),
                                     ("favicon-32x32.png", 32, .9, .18), ("favicon-16x16.png", 16, .94, .15),
                                     ("app-logo.png", 1024, .78, .22)]:
        tile(mark, size, fill, radius).save(ICONS / name)
    tile(mark, 64, .9, .18).save(ROOT / "app" / "public" / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])
    print(f"mark {mark.size} cut from {src.name}; icons written to {ICONS}")


if __name__ == "__main__":
    main()
