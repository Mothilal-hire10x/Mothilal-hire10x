#!/usr/bin/env python3
"""
Convert the prepped portrait into a clean, monochrome ASCII-art SVG (one
light-gray ink, subject isolated on a dark terminal window) that "types"
itself in row by row like a terminal, then holds.

Monochrome is deliberate -- per-character rainbow color is what makes ASCII
portraits look noisy. One fill color + a good density ramp + an isolated
subject reads as neat and legible.

GitHub renders SVGs embedded via <img> and runs their SMIL animations there
(JS never runs). Each row is revealed with a left-to-right clip wipe plus a
small block cursor riding the wipe edge, staggered top -> bottom, so the whole
portrait prints once and freezes.

    python scripts/make_ascii_svg.py [prepped.png] [out.svg]
    python scripts/make_ascii_svg.py --preview      # dump the ascii to stdout
    python scripts/make_ascii_svg.py --static       # frozen, no animation
"""
import html
import os
import sys

from PIL import Image, ImageEnhance

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, HERE)
from crt import crt_overlay  # noqa: E402

args = [a for a in sys.argv[1:] if not a.startswith("--")]
PREVIEW = "--preview" in sys.argv
STATIC = "--static" in sys.argv or bool(os.environ.get("STATIC"))
SRC = args[0] if len(args) > 0 else os.path.join(ROOT, "assets", "portrait-prepped.png")
OUT = args[1] if len(args) > 1 else os.path.join(ROOT, "assets", "ascii-portrait.svg")

USER = "mothilal"
FULL_NAME = "Mothilal M"

COLS = 100
ROWS = 53
CELL_W = 8
CELL_H = 15
# blank(dark) -> dense(bright). The prepped image is the subject on pure black,
# so the background falls below BLACK_FLOOR and prints as spaces.
RAMP = " .`:-=+*cs#%@"

CONTRAST = 1.05
BRIGHTNESS = 1.0
# >1 pushes the mid-tones down so the shadowed side of the hair drops to sparse
# chars instead of speckle, and the floor blanks the dim leftovers entirely.
# 0.9 / 0.10 keeps far more of the image but reads as noise at this cell size.
GAMMA = float(os.environ.get("ASCII_GAMMA", 1.5))
BLACK_FLOOR = float(os.environ.get("ASCII_FLOOR", 0.22))  # luminance below this is forced blank

PAD = 20
TITLEBAR_H = 30
STATUS_H = 30
ART_W = COLS * CELL_W
ART_H = ROWS * CELL_H
CANVAS_W = ART_W + PAD * 2
CANVAS_H = TITLEBAR_H + ART_H + STATUS_H + PAD

BG = "#0d1117"
BG2 = "#111722"
FRAME = "#30363d"
TITLE_TEXT = "#7d8590"
INK = "#c9d1d9"       # the single ascii color
CURSOR = "#c9d1d9"

# ---- reveal timing (one-shot; a cursor rasters top -> bottom) -------------
ROW_DUR = 0.11
STAGGER = 0.11        # == ROW_DUR -> a single cursor sweeping down

# ---- 1. sample the image into a COLS x ROWS grayscale grid ----------------
im = Image.open(SRC).convert("L")
im = ImageEnhance.Brightness(im).enhance(BRIGHTNESS)
im = ImageEnhance.Contrast(im).enhance(CONTRAST)
im = im.resize((COLS, ROWS), Image.LANCZOS)
px = im.load()

rows_txt = []
for y in range(ROWS):
    chars = []
    for x in range(COLS):
        lum = pow(px[x, y] / 255.0, GAMMA)
        if lum <= BLACK_FLOOR:
            chars.append(" ")
            continue
        idx = int(lum * (len(RAMP) - 1) + 0.5)
        chars.append(RAMP[max(1, min(len(RAMP) - 1, idx))])
    rows_txt.append("".join(chars))

if PREVIEW:
    print("\n".join(r.rstrip() for r in rows_txt))
    sys.exit(0)

art_top = TITLEBAR_H + PAD * 0.35

# ---- 2. assemble SVG ------------------------------------------------------
parts = [
    f'<svg xmlns="http://www.w3.org/2000/svg" width="{CANVAS_W}" height="{CANVAS_H}" '
    f'viewBox="0 0 {CANVAS_W} {CANVAS_H}" font-family="ui-monospace, SFMono-Regular, '
    f'Menlo, Consolas, monospace">',
    '<defs>'
    f'<linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">'
    f'<stop offset="0" stop-color="{BG2}"/><stop offset="1" stop-color="{BG}"/>'
    '</linearGradient></defs>',
    f'<rect width="{CANVAS_W}" height="{CANVAS_H}" rx="12" fill="url(#bg)"/>',
    f'<rect x="0.5" y="0.5" width="{CANVAS_W-1}" height="{CANVAS_H-1}" rx="12" '
    f'fill="none" stroke="{FRAME}" stroke-width="1"/>',
    f'<line x1="0" y1="{TITLEBAR_H}" x2="{CANVAS_W}" y2="{TITLEBAR_H}" stroke="{FRAME}"/>',
]
for i, dotcol in enumerate(["#ff5f56", "#ffbd2e", "#27c93f"]):
    parts.append(f'<circle cx="{PAD + i*16}" cy="{TITLEBAR_H/2}" r="5" fill="{dotcol}"/>')
parts.append(f'<text x="{CANVAS_W/2}" y="{TITLEBAR_H/2 + 4}" fill="{TITLE_TEXT}" font-size="12" '
             f'text-anchor="middle">{USER}@github: ~$ ./portrait.sh</text>')

# one <text> per row (single color -> no per-char markup, tiny file)
font_size = CELL_H * 0.86
for ry, line in enumerate(rows_txt):
    y = art_top + ry * CELL_H + CELL_H * 0.74
    row_y = art_top + ry * CELL_H
    delay = ry * STAGGER
    safe = html.escape(line)
    text = (f'<text xml:space="preserve" x="{PAD}" y="{y:.1f}" fill="{INK}" '
            f'font-size="{font_size:.1f}" textLength="{ART_W}" lengthAdjust="spacing">{safe}</text>')

    if STATIC:
        parts.append(text)
        continue

    parts.append(
        f'<clipPath id="r{ry}"><rect x="{PAD}" y="{row_y:.1f}" height="{CELL_H}" width="0">'
        f'<animate attributeName="width" from="0" to="{ART_W}" begin="{delay:.3f}s" '
        f'dur="{ROW_DUR:.2f}s" fill="freeze"/></rect></clipPath>'
    )
    parts.append(f'<g clip-path="url(#r{ry})">{text}</g>')
    parts.append(
        f'<rect y="{row_y+1:.1f}" width="{CELL_W}" height="{CELL_H-2}" fill="{CURSOR}" opacity="0">'
        f'<animate attributeName="x" from="{PAD}" to="{PAD+ART_W}" begin="{delay:.3f}s" '
        f'dur="{ROW_DUR:.2f}s" fill="freeze"/>'
        f'<set attributeName="opacity" to="0.85" begin="{delay:.3f}s"/>'
        f'<set attributeName="opacity" to="0" begin="{delay+ROW_DUR:.3f}s"/></rect>'
    )

# status bar with a steady blinking cursor
status_line_y = TITLEBAR_H + ART_H + PAD * 0.35
status_y = status_line_y + 19
prompt = f"{USER}@github:~$ whoami "
status_w = (len(prompt) + len(FULL_NAME)) * 7.8   # pinned width -> cursor lands after the name everywhere
parts.append(f'<line x1="0" y1="{status_line_y:.1f}" x2="{CANVAS_W}" y2="{status_line_y:.1f}" stroke="{FRAME}"/>')
parts.append(f'<text xml:space="preserve" x="{PAD}" y="{status_y:.1f}" fill="{TITLE_TEXT}" font-size="13" '
             f'textLength="{status_w:.0f}" lengthAdjust="spacing">'
             f'{html.escape(prompt)}<tspan fill="{INK}">{html.escape(FULL_NAME)}</tspan></text>')
parts.append(f'<rect x="{PAD + status_w + 4:.0f}" y="{status_y-12:.1f}" width="8" height="14" fill="{INK}">'
             f'<animate attributeName="opacity" values="1;1;0;0" keyTimes="0;0.5;0.51;1" '
             f'dur="1s" repeatCount="indefinite"/></rect>')

parts.append(crt_overlay(CANVAS_W, CANVAS_H, uid="pt"))
parts.append("</svg>")
svg = "".join(parts)
with open(OUT, "w", encoding="utf-8") as f:
    f.write(svg)
print("wrote", OUT, len(svg), "bytes;", CANVAS_W, "x", CANVAS_H)
