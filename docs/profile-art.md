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
