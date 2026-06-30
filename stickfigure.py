"""
stickfigure.py  --  Self-built stick-figure cartoon engine (no paid assets).

Draws expressive stick-figure panels as SVG (rendered to PNG by Playwright),
for faceless "trades humor" shorts. Each panel = a big top caption + a figure
in a named POSE + an optional speech bubble + optional prop ($ , calculator,
sweat drops). Panels are stitched into a vertical MP4 by ugc_engine.assemble().

Poses supported: neutral, shrug, sweat, facepalm, think, point, flex, dead.
"""
import os

WIDTH, HEIGHT = 1080, 1920
INK = "#10243B"
PAPER = "#F3F1E9"
ACCENT = "#E5484D"
GOOD = "#1FA888"
FONT = "'Comic Sans MS','Segoe UI',sans-serif"

# Each pose maps to limb endpoints relative to the figure's torso anchor.
# Coordinates are in the figure's local space; (0,0) is the shoulder point.
POSES = {
    "neutral": {"hands": [(-70, 40), (70, 40)], "feet": [(-50, 200), (50, 200)]},
    "shrug":   {"hands": [(-100, -70), (100, -70)], "feet": [(-50, 200), (50, 200)]},
    "sweat":   {"hands": [(-60, 55), (60, 55)], "feet": [(-50, 200), (50, 200)], "sweat": True},
    "facepalm":{"hands": [(15, -150), (75, 40)], "feet": [(-50, 200), (50, 200)]},
    "think":   {"hands": [(20, -130), (70, 20)], "feet": [(-50, 200), (50, 200)]},
    "point":   {"hands": [(150, -30), (-65, 45)], "feet": [(-50, 200), (50, 200)]},
    "flex":    {"hands": [(-95, -150), (95, -150)], "feet": [(-55, 200), (55, 200)]},
    "dead":    {"hands": [(-110, 60), (110, 60)], "feet": [(-120, 120), (120, 120)],
                "rot": 90},
}


def _figure(cx, cy, scale, pose, color=INK):
    p = POSES[pose]
    sh = (0, -60)          # shoulder anchor (neck base)
    hip = (0, 95)
    head_c = (0, -135)
    parts = []
    rot = p.get("rot", 0)
    # head
    parts.append(f'<circle cx="{head_c[0]}" cy="{head_c[1]}" r="58" '
                 f'fill="none" stroke="{color}" stroke-width="12"/>')
    # simple face
    parts.append(f'<circle cx="-20" cy="-145" r="6" fill="{color}"/>')
    parts.append(f'<circle cx="20" cy="-145" r="6" fill="{color}"/>')
    if pose in ("sweat", "facepalm", "dead"):
        parts.append(f'<path d="M -22 -110 Q 0 -125 22 -110" fill="none" '
                     f'stroke="{color}" stroke-width="7"/>')  # worried mouth
    else:
        parts.append(f'<path d="M -22 -118 Q 0 -100 22 -118" fill="none" '
                     f'stroke="{color}" stroke-width="7"/>')  # smile
    # spine
    parts.append(f'<line x1="{sh[0]}" y1="{sh[1]}" x2="{hip[0]}" y2="{hip[1]}" '
                 f'stroke="{color}" stroke-width="12" stroke-linecap="round"/>')
    # arms
    for hx, hy in p["hands"]:
        parts.append(f'<line x1="{sh[0]}" y1="{sh[1]+15}" x2="{hx}" y2="{hy}" '
                     f'stroke="{color}" stroke-width="12" stroke-linecap="round"/>')
    # legs
    for fx, fy in p["feet"]:
        parts.append(f'<line x1="{hip[0]}" y1="{hip[1]}" x2="{fx}" y2="{fy}" '
                     f'stroke="{color}" stroke-width="12" stroke-linecap="round"/>')
    if p.get("sweat"):
        parts.append(f'<path d="M 55 -150 q 14 24 0 40 q -14 -16 0 -40 z" fill="#4FA8E5"/>')
        parts.append(f'<path d="M 80 -120 q 10 18 0 30 q -10 -12 0 -30 z" fill="#4FA8E5"/>')
    g = "".join(parts)
    return (f'<g transform="translate({cx},{cy}) scale({scale}) rotate({rot})">{g}</g>')


def _bubble(text, cx, cy, w=520, h=180):
    return (f'<g><rect x="{cx-w//2}" y="{cy-h//2}" rx="40" ry="40" width="{w}" height="{h}" '
            f'fill="#fff" stroke="{INK}" stroke-width="8"/>'
            f'<path d="M {cx-40} {cy+h//2-6} l 30 70 l 60 -64 z" fill="#fff" '
            f'stroke="{INK}" stroke-width="8"/>'
            f'<text x="{cx}" y="{cy+18}" font-family="{FONT}" font-size="56" '
            f'font-weight="700" fill="{INK}" text-anchor="middle">{text}</text></g>')


def _prop(kind, cx, cy):
    if kind == "money":
        return (f'<g transform="translate({cx},{cy})">'
                f'<rect x="-70" y="-46" rx="14" width="140" height="92" fill="{GOOD}" '
                f'stroke="{INK}" stroke-width="8"/>'
                f'<text x="0" y="22" font-family="{FONT}" font-size="72" font-weight="900" '
                f'fill="#fff" text-anchor="middle">$</text></g>')
    if kind == "calc":
        return (f'<g transform="translate({cx},{cy})">'
                f'<rect x="-60" y="-80" rx="14" width="120" height="160" fill="#2B3A55" '
                f'stroke="{INK}" stroke-width="8"/>'
                f'<rect x="-44" y="-66" width="88" height="40" fill="#9FE7D2"/>'
                f'<circle cx="-28" cy="0" r="9" fill="#fff"/><circle cx="0" cy="0" r="9" fill="#fff"/>'
                f'<circle cx="28" cy="0" r="9" fill="#fff"/>'
                f'<circle cx="-28" cy="34" r="9" fill="#fff"/><circle cx="0" cy="34" r="9" fill="#fff"/>'
                f'<circle cx="28" cy="34" r="9" fill="{ACCENT}"/></g>')
    return ""


def panel_svg(caption, pose, bubble=None, prop=None, accent=False):
    """Build one full 1080x1920 panel as an SVG string."""
    cap_color = ACCENT if accent else INK
    figure = _figure(WIDTH // 2, 1180, 1.55, pose)
    bub = _bubble(bubble, WIDTH // 2 + 250, 760) if bubble else ""
    pr = ""
    if prop == "money":
        pr = _prop("money", WIDTH // 2 + 300, 1150)
    elif prop == "calc":
        pr = _prop("calc", WIDTH // 2 + 300, 1150)
    # caption: simple word-wrap into <= 3 lines
    words = caption.split()
    lines, cur = [], ""
    for w in words:
        if len(cur) + len(w) + 1 <= 20:
            cur = (cur + " " + w).strip()
        else:
            lines.append(cur); cur = w
    if cur:
        lines.append(cur)
    lines = lines[:3]
    cap = ""
    for i, ln in enumerate(lines):
        cap += (f'<text x="{WIDTH//2}" y="{300 + i*96}" font-family="{FONT}" '
                f'font-size="80" font-weight="900" fill="{cap_color}" '
                f'text-anchor="middle">{ln}</text>')
    ground = (f'<line x1="120" y1="1430" x2="{WIDTH-120}" y2="1430" '
              f'stroke="{INK}" stroke-width="8" stroke-dasharray="4 26" '
              f'stroke-linecap="round" opacity="0.5"/>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" '
            f'viewBox="0 0 {WIDTH} {HEIGHT}"><rect width="{WIDTH}" height="{HEIGHT}" '
            f'fill="{PAPER}"/>{cap}{ground}{pr}{figure}{bub}</svg>')


def render_panel(page, svg, out_path):
    html = f'<!doctype html><html><body style="margin:0">{svg}</body></html>'
    page.set_content(html, wait_until="load")
    page.screenshot(path=out_path, clip={"x": 0, "y": 0, "width": WIDTH, "height": HEIGHT})
