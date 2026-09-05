#!/usr/bin/env python3
"""
Render data/contributions.json as an isometric SKYLINE: one tower per day,
tower height = that day's contributions, laid out on the 53-week x 7-day
calendar in an oblique projection (weeks run left to right, weekdays recede
up and to the right), and animated so the city builds itself left to right
(CSS keyframes, plays once on load, then freezes).

Think GitHub Skyline, but live, daily and inside the README. Stdlib only.
Run by .github/workflows/update-profile-art.yml after fetch_contributions.py.

    python scripts/render_skyline_svg.py [contributions.json] [out.svg]
"""
import datetime
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from crt import crt_overlay  # noqa: E402

ROOT = os.path.join(HERE, "..")
IN_PATH = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "data", "contributions.json")
OUT_PATH = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, "assets", "contrib-skyline.svg")

USER = "mothilal"

# ---- geometry -------------------------------------------------------------
TW = 13            # tower footprint width, px
GAPX = 2           # gap between weeks
DX, DY = 5.5, -3.4 # depth step per weekday row: back rows sit up and to the right
MAX_H = 118        # tallest tower, px
MIN_H = 3          # zero-contribution slab
PAD = 22
TITLEBAR_H = 30
TOP_ROOM = 16      # air above the tallest tower
LABEL_H = 22       # month labels under the front edge
FOOTER_H = 44

# GitHub's dark-mode green ramp, level 0..4. Each tower gets three shades:
# a lit top, the base color on the front face, a darker right wall.
LEVELS = ["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"]

BG = "#0d1117"
BG2 = "#111722"
FRAME = "#30363d"
MUTED = "#7d8590"
ACCENT = "#22d3ee"
GOLD = "#f2cc60"
PLATE = "#131a24"
PLATE_EDGE = "#1f2937"

# reveal: left -> right sweep, back rows a beat before front rows
COL_T = 0.046
ROW_T = 0.03
RISE = 0.6


def shade(hex_color, f):
    """f > 0 mixes toward white, f < 0 toward black."""
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    if f >= 0:
        r, g, b = (int(c + (255 - c) * f) for c in (r, g, b))
    else:
        r, g, b = (int(c * (1 + f)) for c in (r, g, b))
    return f"#{r:02x}{g:02x}{b:02x}"


FACES = [(shade(c, 0.22), c, shade(c, -0.32)) for c in LEVELS]


def build_grid(days):
    """Sunday-first columns. Returns [[(date, count, level) | None] x7]."""
    first = datetime.date.fromisoformat(days[0]["date"])
    lead = (first.weekday() + 1) % 7
    grid, col = [], [None] * lead
    for d in days:
        col.append((d["date"], d["count"], max(0, min(4, int(d.get("level", 0))))))
        if len(col) == 7:
            grid.append(col)
            col = []
    if col:
        grid.append(col + [None] * (7 - len(col)))
    return grid


def month_labels(grid):
    out, seen = [], set()
    for ci, column in enumerate(grid):
        for cell in column:
            if cell is None:
                continue
            date = datetime.date.fromisoformat(cell[0])
            key = (date.year, date.month)
            if key not in seen and date.day <= 7:
                seen.add(key)
                out.append((ci, date.strftime("%b")))
            break
    return out


def render(data):
    days = data["days"]
    grid = build_grid(days)
    n_cols = len(grid)
    max_count = max(1, max(d["count"] for d in days))

    depth_w = 6 * DX
    depth_h = 6 * -DY
    art_w = n_cols * (TW + GAPX) - GAPX + depth_w
    canvas_w = PAD + art_w + PAD
    base_y = TITLEBAR_H + TOP_ROOM + MAX_H + depth_h + 6   # front-row ground line
    canvas_h = base_y + LABEL_H + FOOTER_H + PAD * 0.5
    left = PAD

    def height_for(count):
        if count <= 0:
            return MIN_H
        return MIN_H + (MAX_H - MIN_H) * math.sqrt(count / max_count)

    css = f"""
.lbl {{ fill:{MUTED}; font-size:10px; }}
.t {{ transform-box:fill-box; transform-origin:50% 100%; opacity:0; animation:rise {RISE:.2f}s cubic-bezier(.2,.8,.2,1) both; }}
.t.hi {{ animation:rise {RISE:.2f}s cubic-bezier(.2,.8,.2,1) both, flash .9s ease-out both; }}
@keyframes rise {{ 0%{{opacity:0;transform:scaleY(0)}} 100%{{opacity:1;transform:scaleY(1)}} }}
@keyframes flash {{ 0%{{filter:brightness(2.2)}} 50%{{filter:brightness(2.2)}} 100%{{filter:brightness(1)}} }}
.ft {{ opacity:0; animation:fade .7s ease-out {n_cols * COL_T + 0.5:.2f}s both; }}
@keyframes fade {{ to {{ opacity:1 }} }}
@media (prefers-reduced-motion: reduce) {{ .t, .ft {{ opacity:1 !important; animation:none !important; }} }}
""".strip()

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{canvas_w:.0f}" height="{canvas_h:.0f}" '
        f'viewBox="0 0 {canvas_w:.0f} {canvas_h:.0f}" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace">',
        f"<style>{css}</style>",
        '<defs>'
        f'<linearGradient id="sbg" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{BG2}"/><stop offset="1" stop-color="{BG}"/></linearGradient>'
        '</defs>',
        f'<rect width="{canvas_w:.0f}" height="{canvas_h:.0f}" rx="12" fill="url(#sbg)"/>',
        f'<rect x="0.5" y="0.5" width="{canvas_w-1:.0f}" height="{canvas_h-1:.0f}" rx="12" '
        f'fill="none" stroke="{FRAME}" stroke-width="1"/>',
        f'<line x1="0" y1="{TITLEBAR_H}" x2="{canvas_w:.0f}" y2="{TITLEBAR_H}" stroke="{FRAME}"/>',
    ]
    for i, dotcol in enumerate(["#ff5f56", "#ffbd2e", "#27c93f"]):
        parts.append(f'<circle cx="{PAD + i*16}" cy="{TITLEBAR_H/2}" r="5" fill="{dotcol}"/>')
    parts.append(f'<text x="{canvas_w/2:.0f}" y="{TITLEBAR_H/2 + 4}" fill="{MUTED}" font-size="12" '
                 f'text-anchor="middle">{USER}@github: ~$ ./skyline.sh --build</text>')

    # ground plate: the calendar footprint as a parallelogram
    fx0, fx1 = left, left + n_cols * (TW + GAPX) - GAPX
    plate = (f"{fx0:.1f},{base_y+2:.1f} {fx1:.1f},{base_y+2:.1f} "
             f"{fx1+depth_w:.1f},{base_y+2-depth_h:.1f} {fx0+depth_w:.1f},{base_y+2-depth_h:.1f}")
    parts.append(f'<polygon points="{plate}" fill="{PLATE}" stroke="{PLATE_EDGE}" stroke-width="1"/>')
    # faint weekday lanes on the plate
    for r in range(1, 7):
        y = base_y + 2 + r * DY
        parts.append(f'<line x1="{fx0 + r*DX:.1f}" y1="{y:.1f}" x2="{fx1 + r*DX:.1f}" y2="{y:.1f}" '
                     f'stroke="{PLATE_EDGE}" stroke-opacity="0.5"/>')

    # towers: painter's order = far rows first, then left -> right
    n_towers = 0
    for r in range(6, -1, -1):                     # r=6 is the back row
        for ci, column in enumerate(grid):
            cell = column[r]
            if cell is None:
                continue
            date_s, count, lvl = cell
            h = height_for(count)
            x0 = left + ci * (TW + GAPX) + r * DX
            y0 = base_y + r * DY
            top, front, side = FACES[lvl]
            delay = ci * COL_T + (6 - r) * ROW_T
            cls = "t hi" if lvl >= 4 else "t"
            plural = "" if count == 1 else "s"
            parts.append(
                f'<g class="{cls}" style="animation-delay:{delay:.3f}s">'
                f'<title>{date_s}: {count} contribution{plural}</title>'
                f'<rect x="{x0:.1f}" y="{y0-h:.1f}" width="{TW}" height="{h:.1f}" fill="{front}"/>'
                f'<polygon points="{x0+TW:.1f},{y0-h:.1f} {x0+TW+DX:.1f},{y0-h+DY:.1f} '
                f'{x0+TW+DX:.1f},{y0+DY:.1f} {x0+TW:.1f},{y0:.1f}" fill="{side}"/>'
                f'<polygon points="{x0:.1f},{y0-h:.1f} {x0+TW:.1f},{y0-h:.1f} '
                f'{x0+TW+DX:.1f},{y0-h+DY:.1f} {x0+DX:.1f},{y0-h+DY:.1f}" fill="{top}"/>'
                '</g>'
            )
            n_towers += 1

    # month labels under the front edge
    ly = base_y + LABEL_H - 4
    for ci, label in month_labels(grid):
        parts.append(f'<text class="lbl ft" x="{left + ci*(TW+GAPX):.0f}" y="{ly:.0f}">{label}</text>')

    # footer
    sep_y = base_y + LABEL_H + 4
    parts.append(f'<line x1="0" y1="{sep_y:.0f}" x2="{canvas_w:.0f}" y2="{sep_y:.0f}" stroke="{FRAME}"/>')
    best = data["best_day"]
    total = data["total_contributions"]
    fy = sep_y + 26
    parts.append(f'<text class="ft" x="{PAD}" y="{fy:.0f}" font-size="12" fill="{MUTED}">'
                 f'one tower per day &#183; height &#8733; &#8730;contributions &#183; '
                 f'<tspan fill="{ACCENT}" font-weight="700">{total:,}</tspan> in the last year</text>')
    parts.append(f'<text class="ft" x="{canvas_w - PAD:.0f}" y="{fy:.0f}" font-size="12" fill="{MUTED}" text-anchor="end">'
                 f'tallest <tspan fill="{GOLD}" font-weight="700">{best["count"]}</tspan> on {best["date"]}</text>')

    parts.append(crt_overlay(canvas_w, canvas_h, uid="sk"))
    parts.append("</svg>")
    return "".join(parts), n_towers, (canvas_w, canvas_h)


if __name__ == "__main__":
    with open(IN_PATH, encoding="utf-8") as f:
        data = json.load(f)
    svg, n, dims = render(data)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write(svg)
    print(f"wrote {os.path.relpath(OUT_PATH)} ({len(svg)//1024} KB, {n} towers, {dims[0]:.0f}x{dims[1]:.0f})")
