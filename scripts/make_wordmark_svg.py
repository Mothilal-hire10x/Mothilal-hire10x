#!/usr/bin/env python3
"""
Render the wordmark (default "MOTHI") as an EXTRUDED 3D slab rasterized to
ASCII, and emit it as an SVG that animates on GitHub (SMIL only -- GitHub runs
SVG animations inside <img>, but never JS).

Pipeline: draw the word with a bold TTF -> threshold to a mask -> extrude the
mask along +z into a surface voxel shell (front cap, back cap, boundary sides)
-> rotate / project each frame -> z-buffer splat into a character grid, char
picked by Lambert shading of the surface normal.

Rotation is a pre-rendered ASCII flipbook: one <g> per frame, cycled with a
discrete opacity animation. Only surface voxels are kept and blank rows/edges
are trimmed, which is what keeps the file to a sane size.

All modes open with the same left-to-right wipe, then differ in the rotation:
  rock   -- oscillates +/-11 deg around the rest pose, forever (wired into README)
  once   -- one full 360 deg turn, then freezes on the 3/4 rest pose
  spin   -- continuous 360 deg turntable, forever
  static -- frozen frame 0, no animation, for eyeballing a render

Env overrides: WORDMARK_TEXT, WORDMARK_FONT, WORDMARK_FONT_INDEX, WORDMARK_TILT,
WORDMARK_COLS, WORDMARK_ROW_MARGIN, WORDMARK_CELL_W, WORDMARK_TRACKING,
WORDMARK_DEPTH.  See docs/profile-art.md.
"""
import argparse
import html
import math
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
import sys  # noqa: E402
sys.path.insert(0, HERE)
from crt import crt_overlay  # noqa: E402

USER = "mothilal"

# ---- geometry / grid ------------------------------------------------------
COLS = int(os.environ.get("WORDMARK_COLS", 62))
ROWS = 0               # derived from the art -- see fit()
# blank rows above and below the art. fit() hugs the wordmark, the margin pads
# the panel back out so it lands at the same height as the portrait beside it.
ROW_MARGIN = int(os.environ.get("WORDMARK_ROW_MARGIN", 5))
CELL_W = float(os.environ.get("WORDMARK_CELL_W", 8.0))
CELL_H = 15.5

# a geometric bold with even stroke weight shades consistently across a letter.
# very heavy faces (Impact) have counters that shrink below one grid cell.
FONT_CANDIDATES = [
    os.environ.get("WORDMARK_FONT", ""),
    os.path.join(ROOT, "assets", "fonts", "Inter-Bold.ttf"),
    os.path.expanduser("~/Documents/agent-flow/browser_agent/ui/fonts/Inter-Bold.ttf"),
    "C:/Windows/Fonts/segoeuib.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "/System/Library/Fonts/Futura.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]
FONT_PATH = next((p for p in FONT_CANDIDATES if p and os.path.exists(p)), None)
if FONT_PATH is None:
    raise SystemExit("no bold TTF found -- set WORDMARK_FONT=/path/to/font.ttf")
FONT_INDEX = int(os.environ.get("WORDMARK_FONT_INDEX", 0))   # face within a .ttc
# two stacked lines: five letters on one line would only be ~6 rows tall at this
# width and the extrusion walls barely register. stacking doubles the letter
# height and the panel lands at the same height as the portrait beside it.
TEXT = os.environ.get("WORDMARK_TEXT", "MOTHI\\nLAL").replace("\\n", "\n")
# the same engine renders any glyph a font can draw -- e.g. WORDMARK_TEXT="♞"
# with a symbol font gives the spinning chess knight (assets/knight.svg).
TITLE = os.environ.get("WORDMARK_TITLE", f"{USER}@github: ~$ ./wordmark.sh --3d")

MASK_H = 300           # glyph raster height in mask px (drives voxel density)
TRACKING = float(os.environ.get("WORDMARK_TRACKING", 0.16))
                       # extra letter-spacing, in em. counter gaps must survive the
                       # extrusion offset or the word rasterizes to one solid slab.
LINE_GAP = 1.20        # baseline-to-baseline, in cap heights (multi-line TEXT only)
DEPTH_FRAC = float(os.environ.get("WORDMARK_DEPTH", 0.30))  # extrusion depth, fraction of glyph height
TILT_DEG = float(os.environ.get("WORDMARK_TILT", 4.0))
                       # fixed X tilt so the top face stays visible. keep it shallow:
                       # tilt slants the whole baseline in screen space.
CAM_DIST = 6.0         # camera distance in world units (1.0 == wordmark width)
FOCAL = 4.15
FIT = 0.92             # fraction of the grid the widest pose may use

# sparse/dim -> dense/bright. index 0 is blank.
RAMP = " .`:-=+*csS#%@"
# keyed close to the view axis: letter faces stay solid and dense, the extruded
# walls fall away to a dimmer char. that contrast gap is the 3D read.
LIGHT = np.array([-0.15, -0.45, -1.00])
LIGHT = LIGHT / np.linalg.norm(LIGHT)
AMBIENT = 0.22
FOG = 0.34             # how much the far end of the word dims, 0..1
FOG_SPAN = 0.55        # world-units of depth the fog ramp covers

# ---- palette (matches the portrait panel) --------------------------------
BG = "#0d1117"
BG2 = "#111722"
FRAME = "#30363d"
TITLE_TEXT = "#7d8590"
INK = "#c9d1d9"

PAD = 18
TITLEBAR_H = 28


# ---------------------------------------------------------------- voxel shell
def build_shell():
    """Rasterize TEXT, then return (points Nx3, normals Nx3) for its surface."""
    probe = TEXT.replace("\n", "")
    font_size = MASK_H
    for _ in range(40):                       # shrink until one line fits a sane raster
        font = ImageFont.truetype(FONT_PATH, font_size, index=FONT_INDEX)
        l, t, r, b = font.getbbox(probe)
        if b - t <= MASK_H:
            break
        font_size = int(font_size * 0.92)
    h = b - t
    track = int(round(TRACKING * font_size))
    lines = TEXT.split("\n")
    line_h = int(round(h * LINE_GAP))

    def line_w(s):
        return sum(font.getlength(c) for c in s) + track * (len(s) - 1)

    total_w = int(round(max(line_w(s) for s in lines))) + 8
    total_h = line_h * (len(lines) - 1) + h + 8
    img = Image.new("L", (total_w, total_h), 0)
    d = ImageDraw.Draw(img)
    for li, s in enumerate(lines):
        pen = 4.0 + (total_w - 8 - line_w(s)) / 2.0      # center each line
        base = -t + 4 + li * line_h
        for ch in s:                                      # glyph by glyph, for tracking
            d.text((pen, base), ch, font=font, fill=255)
            pen += font.getlength(ch) + track
    mask = np.array(img) > 127
    xs_any = np.nonzero(mask.any(0))[0]
    ys_any = np.nonzero(mask.any(1))[0]
    mask = mask[ys_any[0]:ys_any[-1] + 1, xs_any[0]:xs_any[-1] + 1]

    H, W = mask.shape
    depth = max(4, int(round(H * DEPTH_FRAC)))

    cy, cx = np.nonzero(mask)

    pts, nrm = [], []
    # the front cap sits a hair proud of z=0, where the side walls begin, so it
    # wins every z-buffer tie and the letter faces don't streak with wall chars.
    front = np.stack([cx, cy, np.full_like(cx, -0.6, dtype=float)], 1)
    pts.append(front)
    nrm.append(np.tile([0.0, 0.0, -1.0], (len(front), 1)))
    back = np.stack([cx, cy, np.full_like(cx, depth)], 1).astype(float)
    pts.append(back)
    nrm.append(np.tile([0.0, 0.0, 1.0], (len(back), 1)))

    # side walls: boundary pixels extruded through the full depth
    pad = np.pad(mask, 1)
    empty_r = ~pad[1:-1, 2:]
    empty_l = ~pad[1:-1, :-2]
    empty_d = ~pad[2:, 1:-1]
    empty_u = ~pad[:-2, 1:-1]
    edge = mask & (empty_r | empty_l | empty_d | empty_u)
    ey, ex = np.nonzero(edge)
    nx = empty_r[ey, ex].astype(float) - empty_l[ey, ex].astype(float)
    ny = empty_d[ey, ex].astype(float) - empty_u[ey, ex].astype(float)
    ln = np.sqrt(nx * nx + ny * ny)
    ln[ln == 0] = 1.0
    nx, ny = nx / ln, ny / ln
    zsteps = np.linspace(0, depth, max(3, depth // 2))
    for z in zsteps:
        pts.append(np.stack([ex, ey, np.full_like(ex, z, dtype=float)], 1))
        nrm.append(np.stack([nx, ny, np.zeros_like(nx)], 1))

    P = np.concatenate(pts).astype(np.float32)
    N = np.concatenate(nrm).astype(np.float32)

    # center on the origin and normalize so the wordmark is 1.0 unit wide
    P[:, 0] -= W / 2.0
    P[:, 1] -= H / 2.0
    P[:, 2] -= depth / 2.0
    P /= float(W)
    return P, N


def rot_y(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]], np.float32)


def rot_x(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]], np.float32)


def project(P, N, yaw):
    """Rotate + perspective-divide. Returns visible (x, y, depth, shade-index)."""
    M = rot_x(math.radians(TILT_DEG)) @ rot_y(yaw)
    p = P @ M.T
    n = N @ M.T
    vis = n[:, 2] < 0.0                       # back-face cull; camera sits at -z
    p, n = p[vis], n[vis]

    z = p[:, 2] + CAM_DIST
    f = FOCAL / z
    lam = n @ LIGHT
    inten = AMBIENT + (1 - AMBIENT) * np.clip(lam, 0, 1)
    t = np.clip((z - CAM_DIST) / FOG_SPAN, -1.0, 1.0)   # depth fog
    inten *= 1.0 - FOG * (t + 1.0) / 2.0
    idx = np.clip((inten * (len(RAMP) - 1)).round().astype(int), 1, len(RAMP) - 1)
    return p[:, 0] * f, p[:, 1] * f, z, idx


def fit(projected):
    """Width-driven scale + offset. Also derives the row count the art needs,
    so the panel hugs the wordmark instead of leaving dead terminal space."""
    global ROWS
    xs = np.concatenate([q[0] for q in projected])
    ys = np.concatenate([q[1] for q in projected])
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    ar = CELL_W / CELL_H
    scale = FIT * (COLS - 1) / (x1 - x0)
    ROWS = int(math.ceil((y1 - y0) * ar * scale)) + 1 + 2 * ROW_MARGIN
    cx = (COLS - 1) / 2.0 - (x0 + x1) / 2.0 * scale
    cy = (ROWS - 1) / 2.0 - (y0 + y1) / 2.0 * scale * ar
    return scale, cx, cy


def rasterize(q, scale, cx, cy):
    """Z-buffer splat one projected frame into a COLS x ROWS list of strings."""
    x, y, z, idx = q
    col = np.round(cx + x * scale).astype(int)
    row = np.round(cy + y * scale * (CELL_W / CELL_H)).astype(int)
    ok = (col >= 0) & (col < COLS) & (row >= 0) & (row < ROWS)
    col, row, z, idx = col[ok], row[ok], z[ok], idx[ok]

    grid = np.zeros((ROWS, COLS), np.int8)
    order = np.argsort(-z)                    # far -> near, nearest wins
    grid[row[order], col[order]] = idx[order]
    return ["".join(RAMP[i] for i in r) for r in grid]


# ---------------------------------------------------------------------- svg
def emit(frames, mode, out, dur, reveal):
    art_w = COLS * CELL_W
    art_h = ROWS * CELL_H
    canvas_w = art_w + PAD * 2
    canvas_h = TITLEBAR_H + art_h + PAD
    art_top = TITLEBAR_H + PAD * 0.3
    fs = CELL_H * 0.92
    n = len(frames)

    p = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{canvas_w:.0f}" height="{canvas_h:.0f}" '
        f'viewBox="0 0 {canvas_w:.0f} {canvas_h:.0f}" font-family="ui-monospace, SFMono-Regular, '
        f'Menlo, Consolas, monospace">',
        '<defs><linearGradient id="wbg" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{BG2}"/><stop offset="1" stop-color="{BG}"/>'
        '</linearGradient></defs>',
        f'<rect width="{canvas_w:.0f}" height="{canvas_h:.0f}" rx="12" fill="url(#wbg)"/>',
        f'<rect x="0.5" y="0.5" width="{canvas_w-1:.0f}" height="{canvas_h-1:.0f}" rx="12" '
        f'fill="none" stroke="{FRAME}" stroke-width="1"/>',
        f'<line x1="0" y1="{TITLEBAR_H}" x2="{canvas_w:.0f}" y2="{TITLEBAR_H}" stroke="{FRAME}"/>',
    ]
    for i, dot in enumerate(["#ff5f56", "#ffbd2e", "#27c93f"]):
        p.append(f'<circle cx="{PAD + i*15}" cy="{TITLEBAR_H/2}" r="4.5" fill="{dot}"/>')
    p.append(f'<text x="{canvas_w/2:.0f}" y="{TITLEBAR_H/2 + 4:.0f}" fill="{TITLE_TEXT}" '
             f'font-size="11.5" text-anchor="middle">{html.escape(TITLE)}</text>')

    def frame_g(rows, extra=""):
        out_rows = []
        for ry, line in enumerate(rows):
            s = line.rstrip()
            if not s.strip():
                continue
            lead = len(s) - len(s.lstrip(" "))
            body = s[lead:]
            x = PAD + lead * CELL_W
            y = art_top + ry * CELL_H + CELL_H * 0.78
            out_rows.append(
                f'<text xml:space="preserve" x="{x:.1f}" y="{y:.1f}" font-size="{fs:.1f}" '
                f'textLength="{len(body)*CELL_W:.1f}" lengthAdjust="spacing">{html.escape(body)}</text>'
            )
        return f'<g fill="{INK}"{extra}>' + "".join(out_rows) + "</g>"

    if mode == "static":                      # frozen frame 0, for eyeballing a render
        p.append(frame_g(frames[0]))
        p.append(crt_overlay(canvas_w, canvas_h, uid="wm"))
        p.append("</svg>")
        with open(out, "w", encoding="utf-8") as fh:
            fh.write("".join(p))
        print("wrote", out)
        return

    # intro (all modes): the resting pose wipes in left -> right behind a soft bar
    p.append(f'<clipPath id="wipe"><rect x="{PAD}" y="{art_top:.1f}" height="{art_h:.1f}" width="0">'
             f'<animate attributeName="width" from="0" to="{art_w:.0f}" begin="0s" '
             f'dur="{reveal:.2f}s" fill="freeze"/></rect></clipPath>')
    p.append(f'<g clip-path="url(#wipe)">{frame_g(frames[0])}'
             f'<set attributeName="opacity" to="0" begin="{reveal:.2f}s"/></g>')
    p.append(f'<rect x="{PAD}" y="{art_top+2:.1f}" width="{CELL_W*1.6:.1f}" height="{art_h-4:.1f}" '
             f'fill="{INK}" opacity="0.16">'
             f'<animate attributeName="x" from="{PAD}" to="{PAD+art_w:.0f}" begin="0s" '
             f'dur="{reveal:.2f}s" fill="freeze"/>'
             f'<set attributeName="opacity" to="0" begin="{reveal:.2f}s"/></rect>')

    if mode == "once":
        step = dur / n                        # play once, hold the last (rest) frame
        for i, rows in enumerate(frames):
            begin = reveal + i * step
            sets = f'<set attributeName="opacity" to="1" begin="{begin:.3f}s"/>'
            if i != n - 1:
                sets += f'<set attributeName="opacity" to="0" begin="{begin+step:.3f}s"/>'
            p.append(frame_g(rows, ' opacity="0"').replace("</g>", sets + "</g>"))
    else:
        # cycle the flipbook forever; each frame owns one dur/n slice of the loop
        for i, rows in enumerate(frames):
            if i == 0:
                vals, kt = "1;0", f"0;{1/n:.5f}"
            else:
                vals, kt = "0;1;0", f"0;{i/n:.5f};{(i+1)/n:.5f}"
            anim = (f'<animate attributeName="opacity" calcMode="discrete" values="{vals}" '
                    f'keyTimes="{kt}" dur="{dur:.2f}s" begin="{reveal:.2f}s" '
                    f'repeatCount="indefinite"/>')
            p.append(frame_g(rows, ' opacity="0"').replace("</g>", anim + "</g>"))

    p.append(crt_overlay(canvas_w, canvas_h, uid="wm"))
    p.append("</svg>")
    svg = "".join(p)
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(svg)
    print(f"wrote {out}  {len(svg)/1024:.1f} KB  {n} frames  {canvas_w:.0f}x{canvas_h:.0f}  "
          f"font={os.path.basename(FONT_PATH)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["spin", "once", "rock", "static"], default="rock")
    ap.add_argument("--out", default=None)
    ap.add_argument("--frames", type=int, default=None)
    ap.add_argument("--dur", type=float, default=None)
    ap.add_argument("--reveal", type=float, default=1.6)
    ap.add_argument("--preview", action="store_true", help="print frame 0 to stdout instead")
    a = ap.parse_args()

    P, N = build_shell()
    rest = math.radians(-13)                  # the 3/4 pose the wordmark rests in
    if a.mode == "spin":
        nf = a.frames or 36
        yaws = [rest + 2 * math.pi * i / nf for i in range(nf)]
        dur = a.dur or 7.0
    elif a.mode == "once":
        nf = a.frames or 32
        yaws = [rest + 2 * math.pi * i / nf for i in range(nf)] + [rest]
        dur = a.dur or 3.6
    else:                                     # rock: ping-pong, cosine-eased
        nf = a.frames or 20
        amp = math.radians(11)
        yaws = [rest + amp * math.sin(2 * math.pi * i / nf) for i in range(nf)]
        dur = a.dur or 5.0

    proj = [project(P, N, y) for y in yaws]
    scale, cx, cy = fit(proj)
    frames = [rasterize(q, scale, cx, cy) for q in proj]

    if a.preview:
        print(f"[{TEXT!r} font={os.path.basename(FONT_PATH)} cols={COLS} rows={ROWS}]")
        for row in frames[0]:
            print(row.rstrip())
        return

    out = a.out or os.path.join(ROOT, "assets", "wordmark.svg")
    emit(frames, a.mode, out, dur, a.reveal)


if __name__ == "__main__":
    main()
