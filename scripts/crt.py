"""
Shared CRT overlay for the terminal-window SVGs: scanlines, a soft vignette, a
slow refresh band drifting down the glass and a faint flicker. SMIL only, so
it runs inside a README <img>.

    from crt import crt_overlay
    parts.append(crt_overlay(canvas_w, canvas_h, uid="p"))   # right before </svg>

It must be the last thing painted -- it sits on top of everything else -- and
pointer-events are off so <title> tooltips underneath still work.
"""


def crt_overlay(w, h, uid="crt", rx=12, scan_opacity=0.16, band=True, flicker=True):
    w, h = float(w), float(h)
    p = [
        "<defs>",
        f'<clipPath id="{uid}-clip"><rect width="{w:.0f}" height="{h:.0f}" rx="{rx}"/></clipPath>',
        # 1px dark line every 3px: the scanline raster
        f'<pattern id="{uid}-scan" width="4" height="3" patternUnits="userSpaceOnUse">'
        f'<rect width="4" height="1" fill="#000" fill-opacity="{scan_opacity}"/></pattern>',
        # edges fall off like a curved tube
        f'<radialGradient id="{uid}-vig" cx="50%" cy="50%" r="75%">'
        '<stop offset="55%" stop-color="#000" stop-opacity="0"/>'
        '<stop offset="100%" stop-color="#000" stop-opacity="0.45"/></radialGradient>',
        # the refresh band: a faint bright bar that keeps sweeping down
        f'<linearGradient id="{uid}-band" x1="0" y1="0" x2="0" y2="1">'
        '<stop offset="0" stop-color="#fff" stop-opacity="0"/>'
        '<stop offset="0.5" stop-color="#fff" stop-opacity="0.05"/>'
        '<stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>',
        "</defs>",
        f'<g clip-path="url(#{uid}-clip)" pointer-events="none">',
        f'<rect width="{w:.0f}" height="{h:.0f}" fill="url(#{uid}-scan)"/>',
        f'<rect width="{w:.0f}" height="{h:.0f}" fill="url(#{uid}-vig)"/>',
    ]
    if band:
        bh = max(40.0, h * 0.12)
        p.append(f'<rect x="0" y="{-bh:.0f}" width="{w:.0f}" height="{bh:.0f}" fill="url(#{uid}-band)">'
                 f'<animate attributeName="y" from="{-bh:.0f}" to="{h:.0f}" dur="7s" repeatCount="indefinite"/></rect>')
    if flicker:
        p.append(f'<rect width="{w:.0f}" height="{h:.0f}" fill="#fff" opacity="0">'
                 '<animate attributeName="opacity" values="0;0.015;0;0;0.03;0;0;0.01;0" '
                 'dur="5s" repeatCount="indefinite"/></rect>')
    p.append("</g>")
    return "".join(p)
