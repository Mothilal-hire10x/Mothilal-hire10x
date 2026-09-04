#!/usr/bin/env python3
"""
Prepare a portrait for clean ASCII conversion -- Pillow + NumPy only, no
rembg / OpenCV required.

  1. isolate the subject. The background is a smooth sky gradient while the
     subject is packed with detail (hair strands, face lines, cloth folds), so
     a local standard-deviation map splits the two. Flood-filling the smooth
     region inward from the image border yields the background mask; smooth
     patches INSIDE the subject (cheeks, forehead) survive because they are
     enclosed by detail and never reached by the fill.
  2. boost local contrast (unsharp mask + autocontrast) so strands and edges
     survive the downsample to a ~100x53 character grid.
  3. composite the subject onto pure BLACK. make_ascii_svg.py maps bright
     pixels to dense characters, so black background -> blank cells.

Output: assets/portrait-prepped.png (grayscale), consumed by make_ascii_svg.py.
Run once whenever the source image changes; the ascii SVG itself is static.

    python scripts/prep_photo.py [input.png] [output.png] [mask-debug.png]
"""
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageOps

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
INP = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "assets", "portrait-source.png")
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, "assets", "portrait-prepped.png")
MASK_OUT = sys.argv[3] if len(sys.argv) > 3 else None

DETAIL_RADIUS = int(os.environ.get("PREP_DETAIL_RADIUS", 3))      # px window for the local std-dev map
DETAIL_THRESH = float(os.environ.get("PREP_DETAIL_THRESH", 7.0))  # std-dev (0..255) that counts as "detail"
OPEN = 5                 # kills isolated specks (clouds, noise) out in the sky
CLOSE = 9                # bridges gaps between strands so the fill can't leak in
FEATHER = 1.2            # edge softening, px
UNSHARP = (3, 140, 2)    # radius, percent, threshold
AUTOCONTRAST_CUTOFF = 1  # percent clipped at each end of the histogram
GAMMA = float(os.environ.get("PREP_GAMMA", 1.0))  # >1 darkens mids, <1 lifts them


def box_mean(a: np.ndarray, radius: int) -> np.ndarray:
    """Mean over a (2r+1)^2 window via an integral image (edge-replicated)."""
    p = np.pad(a, radius, mode="edge").astype(np.float64)
    s = np.pad(p.cumsum(0).cumsum(1), ((1, 0), (1, 0)))
    k = 2 * radius + 1
    h, w = a.shape
    total = s[k:k + h, k:k + w] - s[:h, k:k + w] - s[k:k + h, :w] + s[:h, :w]
    return (total / (k * k)).astype(np.float32)


def local_std(gray: Image.Image, radius: int) -> np.ndarray:
    """Per-pixel standard deviation over a (2r+1)^2 box window."""
    g = np.asarray(gray, dtype=np.float32)
    mean = box_mean(g, radius)
    mean_sq = box_mean(g * g, radius)
    return np.sqrt(np.clip(mean_sq - mean * mean, 0, None))


def subject_mask(rgb: Image.Image) -> Image.Image:
    gray = rgb.convert("L")
    std = local_std(gray, DETAIL_RADIUS)
    detail = Image.fromarray((std > DETAIL_THRESH).astype(np.uint8) * 255, mode="L")
    # open: drop specks in the sky; close: bridge gaps between hair strands
    detail = detail.filter(ImageFilter.MinFilter(OPEN)).filter(ImageFilter.MaxFilter(OPEN))
    detail = detail.filter(ImageFilter.MaxFilter(CLOSE)).filter(ImageFilter.MinFilter(CLOSE))

    # flood the smooth region from every border pixel -- that is the background.
    # smooth areas enclosed by detail (a cheek, a forehead) are never reached.
    canvas = detail.copy()
    w, h = canvas.size
    px = canvas.load()
    seeds = [(x, y) for x in range(w) for y in (0, h - 1)]
    seeds += [(x, y) for y in range(h) for x in (0, w - 1)]
    for xy in seeds:
        if px[xy] == 0:
            ImageDraw.floodfill(canvas, xy, 128)
    mask = (np.asarray(canvas) != 128).astype(np.uint8) * 255
    return Image.fromarray(mask, mode="L").filter(ImageFilter.GaussianBlur(FEATHER))


def main():
    rgb = Image.open(INP).convert("RGB")
    mask = subject_mask(rgb)
    if MASK_OUT:
        mask.save(MASK_OUT)

    gray = rgb.convert("L").filter(ImageFilter.UnsharpMask(*UNSHARP))
    gray = ImageOps.autocontrast(gray, cutoff=AUTOCONTRAST_CUTOFF)
    g = np.asarray(gray, dtype=np.float32) / 255.0
    g = np.power(g, GAMMA) * 255.0
    m = np.asarray(mask, dtype=np.float32) / 255.0
    out = np.clip(g * m, 0, 255).astype(np.uint8)
    Image.fromarray(out, mode="L").save(OUT)
    print(f"wrote {OUT} {out.shape[1]}x{out.shape[0]}  subject covers {m.mean():.0%} of the frame")


if __name__ == "__main__":
    main()
