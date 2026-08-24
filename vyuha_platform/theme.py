"""Per-trade colour and backdrop.

A nursery should not open to the same screen as a bearings distributor. The
trade picks the accent colour and a generated backdrop, and the owner can drop
their own photograph over it (``/c/<slug>/cover``) — which is the point: the
first thing they see is their own business, not our branding.

Each trade has a **photograph** served from ``static/img/``, with the generated
SVG kept as ``fallback`` underneath it. The SVGs were the original choice — they
render instantly and never 404 — and they still cover the case where a photo has
not been chosen for a trade, or fails to load. What has not changed is the order
of precedence: a client's own uploaded cover always wins over both.

These are *platform* assets, served over localhost from disk. The generated
client dashboard stays strictly self-contained and never references them; that
guarantee lives in ``vyuha/report.py`` and is enforced by a test.
"""

from __future__ import annotations

import base64


#: Photographs live here rather than being read into memory: the browser caches
#: them, and a 200KB JPEG has no business being base64'd into every page render.
STATIC = "/static/img"


def _photo(name: str) -> str:
    return f"{STATIC}/{name}"


def _svg(markup: str) -> str:
    return "data:image/svg+xml;base64," + base64.b64encode(
        markup.strip().encode("utf-8")).decode("ascii")


def _leaves(a: str, b: str) -> str:
    """Botanical fronds — nursery, garden, agri."""
    fronds = "".join(
        f'<g transform="translate({x},{y}) rotate({r}) scale({s})" opacity="{o}">'
        f'<path d="M0 0 C 30 -46 76 -62 110 -58 C 104 -18 66 12 0 0 Z" fill="{b}"/>'
        f'<path d="M0 0 C 34 -20 78 -30 110 -58" stroke="{a}" stroke-width="2.4" fill="none"/>'
        f"</g>"
        for x, y, r, s, o in [(80, 640, -14, 1.5, .40), (330, 720, 26, 1.15, .30),
                              (620, 610, -34, 1.7, .34), (940, 700, 14, 1.3, .26),
                              (1180, 640, -22, 1.5, .30), (1420, 720, 32, 1.1, .22),
                              (210, 300, 156, 1.0, .14), (760, 250, 196, 1.2, .12),
                              (1290, 320, 168, .95, .12)])
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="760" viewBox="0 0 1600 760">
<defs><radialGradient id="g" cx="20%" cy="0%" r="95%">
<stop offset="0%" stop-color="{a}" stop-opacity=".40"/>
<stop offset="100%" stop-color="{a}" stop-opacity="0"/></radialGradient></defs>
<rect width="1600" height="760" fill="#070a08"/><rect width="1600" height="760" fill="url(#g)"/>
{fronds}</svg>"""


def _crates(a: str, b: str) -> str:
    """Stacked crates and pallets — distribution, warehousing."""
    boxes = "".join(
        f'<g opacity="{o}"><rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" fill="{b}"/>'
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" fill="none" '
        f'stroke="{a}" stroke-width="2"/>'
        f'<line x1="{x}" y1="{y + h / 2}" x2="{x + w}" y2="{y + h / 2}" '
        f'stroke="{a}" stroke-width="1.6" opacity=".65"/></g>'
        for x, y, w, h, o in [(90, 520, 190, 150, .34), (300, 560, 150, 110, .26),
                              (470, 500, 210, 170, .30), (700, 575, 165, 95, .22),
                              (890, 515, 195, 155, .28), (1105, 565, 145, 105, .22),
                              (1270, 495, 220, 175, .26), (250, 250, 120, 95, .10),
                              (820, 210, 150, 110, .09), (1330, 265, 130, 100, .09)])
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="760" viewBox="0 0 1600 760">
<defs><radialGradient id="g" cx="80%" cy="0%" r="95%">
<stop offset="0%" stop-color="{a}" stop-opacity=".38"/>
<stop offset="100%" stop-color="{a}" stop-opacity="0"/></radialGradient></defs>
<rect width="1600" height="760" fill="#08080d"/><rect width="1600" height="760" fill="url(#g)"/>
{boxes}</svg>"""


def _gears(a: str, b: str) -> str:
    """Cog teeth — manufacturing, engineering, spares."""
    def cog(cx, cy, r, teeth, o):
        pts = "".join(
            f'<rect x="{cx - 7}" y="{cy - r - 20}" width="14" height="26" rx="3" '
            f'fill="{b}" transform="rotate({i * 360 / teeth} {cx} {cy})"/>'
            for i in range(teeth))
        return (f'<g opacity="{o}">{pts}<circle cx="{cx}" cy="{cy}" r="{r}" fill="{b}"/>'
                f'<circle cx="{cx}" cy="{cy}" r="{r * .45}" fill="#08080d"/>'
                f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{a}" '
                f'stroke-width="2.5"/></g>')
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="760" viewBox="0 0 1600 760">
<defs><radialGradient id="g" cx="15%" cy="10%" r="95%">
<stop offset="0%" stop-color="{a}" stop-opacity=".34"/>
<stop offset="100%" stop-color="{a}" stop-opacity="0"/></radialGradient></defs>
<rect width="1600" height="760" fill="#08080d"/><rect width="1600" height="760" fill="url(#g)"/>
{cog(210, 600, 120, 12, .26)}{cog(430, 690, 78, 10, .20)}{cog(1290, 585, 135, 14, .24)}
{cog(1080, 690, 72, 10, .17)}{cog(760, 660, 95, 11, .15)}{cog(650, 230, 60, 9, .08)}</svg>"""


def _shelves(a: str, b: str) -> str:
    """Shelf runs — retail, hardware, general trade."""
    rows = "".join(
        f'<g opacity="{o}"><rect x="{x}" y="{y}" width="1400" height="8" rx="4" fill="{a}"/>'
        + "".join(f'<rect x="{x + 30 + i * 96}" y="{y - 62}" width="62" height="62" rx="5" '
                  f'fill="{b}"/>' for i in range(14))
        + "</g>"
        for x, y, o in [(100, 520, .22), (100, 660, .28), (100, 380, .12)])
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="760" viewBox="0 0 1600 760">
<defs><radialGradient id="g" cx="50%" cy="0%" r="90%">
<stop offset="0%" stop-color="{a}" stop-opacity=".32"/>
<stop offset="100%" stop-color="{a}" stop-opacity="0"/></radialGradient></defs>
<rect width="1600" height="760" fill="#08080d"/><rect width="1600" height="760" fill="url(#g)"/>
{rows}</svg>"""


TRADES: dict[str, dict] = {
    "nursery": {
        "label": "Nursery, plants & manure",
        "accent": "#4ade80", "accent2": "#bef264", "ink": "#06130c",
        "backdrop": _photo("trade-nursery.jpg"),
        "fallback": _svg(_leaves("#4ade80", "#14532d")),
        "words": ("plants", "stock", "sales"),
    },
    "distribution": {
        "label": "Distribution & wholesale",
        "accent": "#7c5cff", "accent2": "#22d3ee", "ink": "#0a0a12",
        "backdrop": _photo("trade-distribution.jpg"),
        "fallback": _svg(_crates("#7c5cff", "#241a52")),
        "words": ("SKUs", "stock", "invoices"),
    },
    "manufacturing": {
        "label": "Manufacturing & spares",
        "accent": "#f59e0b", "accent2": "#fb923c", "ink": "#130c02",
        "backdrop": _photo("trade-manufacturing.jpg"),
        "fallback": _svg(_gears("#f59e0b", "#3d2708")),
        "words": ("parts", "stock", "orders"),
    },
    "retail": {
        "label": "Retail & hardware",
        "accent": "#22d3ee", "accent2": "#60a5fa", "ink": "#04121a",
        "backdrop": _photo("trade-retail.jpg"),
        "fallback": _svg(_shelves("#22d3ee", "#0d3f4d")),
        "words": ("items", "stock", "bills"),
    },
    "general": {
        "label": "Something else",
        "accent": "#7c5cff", "accent2": "#22d3ee", "ink": "#0a0a12",
        "backdrop": _photo("hero-gears.jpg"),
        "fallback": _svg(_crates("#7c5cff", "#241a52")),
        "words": ("items", "stock", "sales"),
    },
}


#: The landing page hero. Named separately from any trade so changing a trade's
#: photograph never silently changes the front page.
HERO = _photo("hero-gears.jpg")


def trade(key: str) -> dict:
    return TRADES.get(key or "general", TRADES["general"])


def guess(name: str, industry: str = "") -> str:
    """Pick a sensible trade from what they typed, so nobody has to choose twice."""
    text = f"{name} {industry}".lower()
    for key, words in (
        ("nursery", ("nursery", "plant", "garden", "manure", "fertil", "seed",
                     "compost", "agri", "flor", "landscap")),
        ("manufacturing", ("manufact", "engineer", "spare", "bearing", "machin",
                           "fabricat", "industr", "tool", "auto")),
        ("retail", ("retail", "hardware", "shop", "store", "mart", "electric")),
        ("distribution", ("distribut", "wholesale", "trader", "agenc", "supply",
                          "pharma", "fmcg")),
    ):
        if any(w in text for w in words):
            return key
    return "general"
