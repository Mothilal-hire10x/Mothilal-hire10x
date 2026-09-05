# Profile art: how the animated SVGs work

Three hand-generated SVGs sit at the top of the README. None of them use
JavaScript: images in a README land in an `<img>` tag, and an SVG loaded that
way runs in restricted mode (no scripts, no external resources). It *does* run
[SMIL](https://developer.mozilla.org/en-US/docs/Web/SVG/SVG_animation_with_SMIL)
and CSS keyframe animations, which is all these need.

| File | What it is | Regenerated |
| --- | --- | --- |
| `assets/ascii-portrait.svg` | monochrome ASCII portrait that types itself in row by row | by hand, when the photo changes |
| `assets/wordmark.svg` | `MOTHI / LAL` extruded into a 3D slab, rasterized to ASCII, wipes in then rocks | by hand, when the text or font changes |
| `assets/contrib-heatmap.svg` | real contribution calendar, cells pop in along a diagonal, live stats footer | daily, by `.github/workflows/update-profile-art.yml` |
| `assets/contrib-skyline.svg` | the same year as an isometric city, one tower per day, builds itself on load | daily, same workflow |
| `assets/knight.svg` | the ♘ glyph extruded and spinning, beside the community chess board | by hand |

Every panel also carries a CRT overlay (scanlines, vignette, a slow refresh
band, a faint flicker) from `scripts/crt.py`.

The idea (and the wordmark pipeline) comes from
[AVIVASHISHTA29's profile](https://github.com/AVIVASHISHTA29); this repo
re-implements it with a Pillow-only photo prep so nothing heavy has to be
installed.

## Setup

```bash
pip install -r scripts/requirements.txt      # Pillow + numpy, only for the two static generators
```

## 1. ASCII portrait

```bash
python scripts/prep_photo.py                 # assets/portrait-source.png -> assets/portrait-prepped.png
python scripts/make_ascii_svg.py             # -> assets/ascii-portrait.svg
python scripts/make_ascii_svg.py --preview   # dump the ascii to the terminal first
```

`prep_photo.py` isolates the subject without rembg or OpenCV. The background of
the source image is a smooth sky gradient while the subject is full of detail
(hair strands, face lines), so a local standard-deviation map separates the
two. The smooth region is flood-filled inward from the image border to get the
background mask; smooth patches *inside* the subject (a cheek, a forehead) are
enclosed by detail and never reached by the fill, so they survive. The subject
is then unsharp-masked, auto-contrasted and composited onto pure black.

`make_ascii_svg.py` samples that into a 100 x 53 grid and maps **bright ->
dense** (`" .`:-=+*cs#%@"`), so the black background prints as spaces. Each row
is a single `<text>` element revealed by an animated `clipPath` wipe with a
block cursor riding the edge; rows are staggered top to bottom so one cursor
appears to raster the whole portrait, then it freezes.

Knobs (env vars): `ASCII_GAMMA` (default 1.5; higher pushes mid-tones toward
blank, which is what kills speckle on the shadowed side) and `ASCII_FLOOR`
(0.22; luminance below this is forced blank). `PREP_DETAIL_THRESH` (7.0) is the
std-dev cutoff for "this pixel is subject" -- raise it if sky leaks in, lower
it if wisps of hair get cut off.

## 2. 3D ASCII wordmark

```bash
python scripts/make_wordmark_svg.py --mode rock          # -> assets/wordmark.svg
python scripts/make_wordmark_svg.py --preview            # frame 0 to the terminal
python scripts/make_wordmark_svg.py --mode static --out /tmp/w.svg
```

Pipeline: draw the text with a bold TTF -> threshold to a mask -> extrude the
mask into a surface point cloud (front cap, back cap, boundary side walls with
outward normals) -> rotate + perspective-project each frame -> back-face cull,
Lambert shade against a light keyed near the view axis, depth fog -> z-buffer
splat into a character grid. Every frame that will ever be shown is
pre-rendered as a hidden `<g>` and cycled with a discrete opacity animation
(a flipbook), because nothing can be rotated at runtime.

Why two lines: five letters across one line at this panel width are only ~6
rows tall and the extrusion barely registers. Stacking `MOTHI` over `LAL`
doubles the letter height, and the resulting 532 x 418 panel shown at 490px
wide lands at the same 385px height as the portrait beside it.

| Env var | Default | Purpose |
| --- | --- | --- |
| `WORDMARK_TEXT` | `MOTHI\nLAL` | `\n` splits lines |
| `WORDMARK_FONT` | first found: `assets/fonts/Inter-Bold.ttf`, Segoe UI Bold, Arial Bold, Futura, DejaVu Bold | any bold TTF/TTC (geometric, even stroke weight works best; Impact does not) |
| `WORDMARK_FONT_INDEX` | `0` | face within a `.ttc` |
| `WORDMARK_COLS` | `62` | grid width; panel is `COLS x CELL_W + 36` px |
| `WORDMARK_CELL_W` | `8` | px per character column |
| `WORDMARK_ROW_MARGIN` | `5` | blank rows top and bottom -- the height knob |
| `WORDMARK_TRACKING` | `0.16` | extra letter-spacing (em); counters must survive the extrusion offset |
| `WORDMARK_DEPTH` | `0.30` | extrusion depth as a fraction of glyph height |
| `WORDMARK_TILT` | `4.0` | X tilt in degrees; keep shallow or the baseline slants |

Modes: `rock` (±11° oscillation, in use), `once` (one full turn then freeze),
`spin` (turntable), `static` (frozen frame 0).

## 3. Contribution heatmap

```bash
python scripts/fetch_contributions.py        # -> data/contributions.json
python scripts/render_heatmap_svg.py         # -> assets/contrib-heatmap.svg
```

Both scripts are stdlib-only. `fetch_contributions.py` reads the public
contributions API mirror first and falls back to regex-parsing the public
`github.com/users/<user>/contributions` fragment; it also derives current and
longest streak, best day and monthly totals. `render_heatmap_svg.py` draws the
Sunday-first 53 x 7 grid with GitHub's own 0-4 intensity levels, each cell
popping in with a brief flash along a diagonal sweep (CSS keyframes, plays once
on load), then fades in the legend and the stats footer. `prefers-reduced-motion`
disables the animation.

The workflow runs at ~06:17 UTC daily and commits only when the data changed.
Trigger it by hand from the Actions tab (`profile art` -> Run workflow).

## 4. Contribution skyline

```bash
python scripts/render_skyline_svg.py         # -> assets/contrib-skyline.svg
```

Same data as the heatmap, drawn as a city. Weeks run left to right and the
seven weekdays recede up and to the right (an oblique projection, so the long
axis stays horizontal and the panel stays short). Each day is a box with three
faces: a lit top, GitHub's level color on the front, a darker right wall.
Height is `sqrt(count / max)` so one huge day does not flatten the rest.

Towers are painted back row first, then left to right, which is all the
occlusion an oblique projection needs. Each tower is a `<g>` that grows from
its own base (`transform-origin: 50% 100%; scaleY(0 -> 1)`) with a delay that
sweeps left to right, so the city builds itself in about three seconds. Level-4
days flash as they land.

## 5. Spinning knight

The wordmark engine will extrude anything a font can draw. The knight is the
outline glyph `♘` (U+2658) from Segoe UI Symbol; the outline version keeps the
eye, mane and base as internal detail, where the solid `♞` becomes one blob.

```bash
WORDMARK_TEXT="♘" WORDMARK_FONT="C:/Windows/Fonts/seguisym.ttf" \
WORDMARK_COLS=32 WORDMARK_CELL_W=9 WORDMARK_DEPTH=0.22 WORDMARK_ROW_MARGIN=1 \
WORDMARK_TITLE='~$ ./knight.sh --spin' \
python scripts/make_wordmark_svg.py --mode spin --frames 32 --out assets/knight.svg
```

It lives inside the chess section template in `chess/play.py`, so it survives
every move the bot plays.

## 6. Chess by issues

`chess/play.py` was already in the repo; the README just had no
`<!--CHESS:START-->` / `<!--CHESS:END-->` markers for it to write into. Run
`python chess/play.py bootstrap` once (needs `pip install chess`) to render a
fresh game into the markers. After that the `chess` workflow handles every
issue titled `chess|move|<uci>`.

## 7. CRT overlay

`scripts/crt.py` exposes `crt_overlay(w, h, uid)`; every generator appends it
right before `</svg>` so it is painted last. A 1-in-3 px scanline pattern, a
radial vignette, a refresh band that drifts down every seven seconds and a
flicker that never exceeds 3% opacity. Pointer events are off so `<title>`
tooltips underneath still work. Pass `scan_opacity=0` to tone it down.
