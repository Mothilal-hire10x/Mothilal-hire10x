#!/usr/bin/env python3
"""
Render data/contributions.json (from fetch_contributions.py) as a GitHub-style
contribution heatmap SVG inside a terminal window: the classic 53-week x 7-day
grid of rounded boxes, each popping in with a brief flash along a diagonal
sweep (CSS keyframes -- plays once on load, then freezes), a Less -> More
legend, and a real stats footer (total, streaks, best day).

GitHub runs CSS animations in SVGs embedded via <img>. Stdlib only.
Run by .github/workflows/update-profile-art.yml after fetch_contributions.py.

    python scripts/render_heatmap_svg.py [contributions.json] [out.svg]
"""
import datetime
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from crt import crt_overlay  # noqa: E402

ROOT = os.path.join(HERE, "..")
IN_PATH = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "data", "contributions.json")
OUT_PATH = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, "assets", "contrib-heatmap.svg")

USER = "mothilal"

# GitHub's dark-mode green ramp, level 0..4 (levels come straight from GitHub)
PALETTE = ["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"]

CELL = 12
GAP = 3
STEP = CELL + GAP
PAD = 20
LEFT_LABEL_W = 30
TOP_LABEL_H = 20
TITLEBAR_H = 30

BG = "#0d1117"
BG2 = "#111722"
FRAME = "#30363d"
MUTED = "#7d8590"
TEXT = "#e6edf3"
ACCENT = "#22d3ee"     # cyan, matches the rest of the profile
GREEN = "#39d353"
GOLD = "#f2cc60"

# reveal timing (one-shot): a diagonal sweep, left -> right, top -> bottom
REVEAL = 3.6           # seconds until the last cell has started popping
CELL_DUR = 0.55
ROW_WEIGHT = 0.55      # how much a row shifts the delay vs. a column (diagonal angle)


def build_grid(days):
    """Sunday-first columns, like github.com. Returns [[(date, count, level) | None] x7]."""
    first = datetime.date.fromisoformat(days[0]["date"])
    lead_pad = (first.weekday() + 1) % 7
    grid, col = [], [None] * lead_pad
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
    art_w = n_cols * STEP - GAP
    art_h = 7 * STEP - GAP

    canvas_w = PAD + LEFT_LABEL_W + art_w + PAD
    stats_h = 84
    canvas_h = TITLEBAR_H + TOP_LABEL_H + art_h + stats_h + PAD
    maxorder = (n_cols - 1) + 6 * ROW_WEIGHT

    css = f"""
.lbl {{ fill:{MUTED}; font-size:10px; }}
.c {{ transform-box:fill-box; transform-origin:center; opacity:0; animation:pop {CELL_DUR:.2f}s ease-out both; }}
.g {{ animation:pop {CELL_DUR:.2f}s ease-out both, flash {CELL_DUR+0.15:.2f}s ease-out both; }}
@keyframes pop {{ 0%{{opacity:0;transform:scale(.2)}} 60%{{opacity:1;transform:scale(1.1)}} 100%{{opacity:1;transform:scale(1)}} }}
@keyframes flash {{ 0%{{filter:brightness(2.4)}} 45%{{filter:brightness(2.4)}} 100%{{filter:brightness(1)}} }}
.ft {{ opacity:0; animation:fade .6s ease-out {REVEAL + 0.3:.2f}s both; }}
@keyframes fade {{ to {{ opacity:1 }} }}
@media (prefers-reduced-motion: reduce) {{ .c, .ft {{ opacity:1 !important; animation:none !important; }} }}
""".strip()

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{canvas_w}" height="{canvas_h}" '
        f'viewBox="0 0 {canvas_w} {canvas_h}" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace">',
        f'<style>{css}</style>',
        '<defs>'
        f'<linearGradient id="hbg" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{BG2}"/><stop offset="1" stop-color="{BG}"/></linearGradient>'
        '</defs>',
        f'<rect width="{canvas_w}" height="{canvas_h}" rx="12" fill="url(#hbg)"/>',
        f'<rect x="0.5" y="0.5" width="{canvas_w-1}" height="{canvas_h-1}" rx="12" '
        f'fill="none" stroke="{FRAME}" stroke-width="1"/>',
        f'<line x1="0" y1="{TITLEBAR_H}" x2="{canvas_w}" y2="{TITLEBAR_H}" stroke="{FRAME}"/>',
    ]
    for i, dotcol in enumerate(["#ff5f56", "#ffbd2e", "#27c93f"]):
        parts.append(f'<circle cx="{PAD + i*16}" cy="{TITLEBAR_H/2}" r="5" fill="{dotcol}"/>')
    parts.append(f'<text x="{canvas_w/2}" y="{TITLEBAR_H/2 + 4}" fill="{MUTED}" font-size="12" '
                 f'text-anchor="middle">{USER}@github: ~$ ./contributions.sh --graph</text>')

    grid_top = TITLEBAR_H + TOP_LABEL_H
    grid_left = PAD + LEFT_LABEL_W

    for ci, label in month_labels(grid):
        parts.append(f'<text class="lbl" x="{grid_left + ci * STEP}" y="{TITLEBAR_H + 14}">{label}</text>')
    for wi, wname in [(1, "Mon"), (3, "Wed"), (5, "Fri")]:
        parts.append(f'<text class="lbl" x="{PAD}" y="{grid_top + wi * STEP + CELL * 0.8:.1f}" font-size="9">{wname}</text>')

    # the boxes -- diagonal pop-in, once, then freeze
    for ci, column in enumerate(grid):
        gx = grid_left + ci * STEP
        for ri, cell in enumerate(column):
            if cell is None:
                continue
            date_s, count, lvl = cell
            gy = grid_top + ri * STEP
            delay = (ci + ri * ROW_WEIGHT) / maxorder * REVEAL
            cls = "c g" if lvl >= 1 else "c"
            plural = "" if count == 1 else "s"
            parts.append(
                f'<rect class="{cls}" x="{gx}" y="{gy}" width="{CELL}" height="{CELL}" rx="2.5" '
                f'fill="{PALETTE[lvl]}" style="animation-delay:{delay:.3f}s">'
                f'<title>{date_s}: {count} contribution{plural}</title></rect>'
            )

    # legend: Less [][][][][] More (bottom-right, under the grid)
    leg_y = grid_top + art_h + 8
    leg_w = len(PALETTE) * CELL
    leg_x = canvas_w - PAD - leg_w - 34
    parts.append(f'<text class="lbl ft" x="{leg_x - 6}" y="{leg_y + CELL*0.8:.1f}" text-anchor="end">Less</text>')
    for lvl, color in enumerate(PALETTE):
        parts.append(f'<rect class="ft" x="{leg_x + lvl * CELL}" y="{leg_y}" width="{CELL-1}" height="{CELL-1}" rx="2.2" fill="{color}"/>')
    parts.append(f'<text class="lbl ft" x="{leg_x + leg_w + 4}" y="{leg_y + CELL*0.8:.1f}">More</text>')

    sep_y = leg_y + CELL + 12
    parts.append(f'<line x1="0" y1="{sep_y}" x2="{canvas_w}" y2="{sep_y}" stroke="{FRAME}"/>')

    cs = data["current_streak"]["length"]
    ls = data["longest_streak"]["length"]
    total = data["total_contributions"]
    best = data["best_day"]
    rng = data["range"]

    ly = sep_y + 24
    parts.append(f'<text class="ft" x="{PAD}" y="{ly}" font-size="13" fill="{GREEN}">'
                 f'<tspan font-weight="700">{total:,}</tspan>'
                 f'<tspan fill="{MUTED}"> contributions in the last year</tspan></text>')
    parts.append(f'<text class="ft" x="{canvas_w - PAD}" y="{ly}" font-size="12" fill="{MUTED}" text-anchor="end">'
                 f'{rng["start"]} &#8594; {rng["end"]}</text>')
    ly += 24
    parts.append(f'<text class="ft" x="{PAD}" y="{ly}" font-size="13" fill="{MUTED}">current streak '
                 f'<tspan fill="{ACCENT}" font-weight="700">{cs} days</tspan>'
                 f'<tspan fill="{MUTED}">   &#183;   longest </tspan>'
                 f'<tspan fill="{ACCENT}" font-weight="700">{ls} days</tspan></text>')
    parts.append(f'<text class="ft" x="{canvas_w - PAD}" y="{ly}" font-size="12" fill="{MUTED}" text-anchor="end">'
                 f'best day <tspan fill="{GOLD}" font-weight="700">{best["count"]}</tspan> on {best["date"]}</text>')

    parts.append(crt_overlay(canvas_w, canvas_h, uid="hm"))
    parts.append("</svg>")
    return "".join(parts)


if __name__ == "__main__":
    with open(IN_PATH, encoding="utf-8") as f:
        data = json.load(f)
    svg = render(data)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write(svg)
    print(f"wrote {os.path.relpath(OUT_PATH)} ({len(svg)//1024} KB, {len(data['days'])} days)")
