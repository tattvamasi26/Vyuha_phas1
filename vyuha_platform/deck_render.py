"""A deck that looks like somebody made it.

The first version rendered a title and bullets onto a dark rectangle, which is
what python-pptx makes easy and is not what anybody means by a presentation. The
complaint was fair, and the fix is not "more styling on the same slide" — it is
that a deck has **slide kinds**, and the argument decides which one each point
needs. A figure wants the whole screen. A trend wants a chart. A comparison
wants two columns. Bullets are what you use when none of those fit, not the
default.

So: six kinds, and a renderer that gives each one a real layout.

**HTML first, exports second.** Full design is possible in a browser and barely
possible in python-pptx, so the good artefact is the HTML one — 16:9, one slide
per screen, arrow-key navigation, and a print stylesheet that puts exactly one
slide on each page so "save as PDF" produces a real deck rather than a
screenshot. ``decks.to_pptx`` still exists for someone who has to edit it.

**Charts are inline SVG drawn from the real series.** No library, no CDN, no
image — the whole page has to survive being emailed and opened on a train. Each
chart is generated from numbers ``finance.py`` computed, so a slide cannot claim
something the statements disagree with.
"""

from __future__ import annotations

import html
from datetime import datetime

E = html.escape

#: A deck's palette is its own, not the app's. Dark ground because these get
#: projected, and a single warm accent so a highlighted figure reads instantly
#: from the back of a room.
INK = "#0B0F14"
INK_2 = "#131A22"
PAPER = "#F2F5F7"
MUTED = "#8A97A3"
ACCENT = "#F0A93C"
ACCENT_2 = "#3FBFA4"
GOOD = "#5FC98B"
BAD = "#F0656F"


def _money(v) -> str:
    """Indian grouping, short form for a slide: 12.3L, 4.5Cr."""
    try:
        n = float(v or 0)
    except (TypeError, ValueError):
        return "₹0"
    sign = "-" if n < 0 else ""
    n = abs(n)
    if n >= 10_000_000:
        return f"{sign}₹{n / 10_000_000:.2f}Cr"
    if n >= 100_000:
        return f"{sign}₹{n / 100_000:.2f}L"
    if n >= 1_000:
        return f"{sign}₹{n / 1000:.0f}k"
    return f"{sign}₹{n:,.0f}"


# ------------------------------------------------------------------- charts

def bar_chart(series: list[dict], accent: str = ACCENT, height: int = 300) -> str:
    """A grouped bar chart as inline SVG.

    Hand-drawn rather than pulled from a library because the page must open with
    no network, and because a chart on a slide needs four things — bars, a
    baseline, labels and the endpoint called out — not an axis system.
    """
    if not series:
        return ""
    width, pad_l, pad_b, pad_t = 1000, 10, 46, 30
    values = [float(s.get("value") or 0) for s in series]
    second = [float(s.get("value2")) for s in series if s.get("value2") is not None]
    peak = max(values + second + [1])
    floor = min(values + second + [0])
    span = (peak - floor) or 1
    plot_h = height - pad_b - pad_t
    slot = (width - pad_l * 2) / max(len(series), 1)
    paired = bool(second)
    bar_w = (slot * 0.52) / (2 if paired else 1)

    def y_of(v: float) -> float:
        return pad_t + plot_h - ((v - floor) / span) * plot_h

    zero_y = y_of(0)
    bars = ""
    for i, point in enumerate(series):
        cx = pad_l + slot * i + slot / 2
        v1 = float(point.get("value") or 0)
        x1 = cx - (bar_w if paired else bar_w / 2)
        y1, h1 = min(y_of(v1), zero_y), abs(zero_y - y_of(v1))
        bars += (f'<rect x="{x1:.1f}" y="{y1:.1f}" width="{bar_w:.1f}" '
                 f'height="{max(h1, 2):.1f}" rx="3" fill="{accent}"'
                 f'{" opacity=\'.55\'" if i < len(series) - 1 else ""}/>')
        if point.get("value2") is not None:
            v2 = float(point["value2"])
            y2, h2 = min(y_of(v2), zero_y), abs(zero_y - y_of(v2))
            bars += (f'<rect x="{cx:.1f}" y="{y2:.1f}" width="{bar_w:.1f}" '
                     f'height="{max(h2, 2):.1f}" rx="3" fill="{ACCENT_2}" opacity=".8"/>')
        bars += (f'<text x="{cx:.1f}" y="{height - 16}" fill="{MUTED}" font-size="17" '
                 f'text-anchor="middle">{E(str(point.get("label", "")))}</text>')

    # The last bar is the one being talked about, so it gets its value printed.
    last = series[-1]
    lv = float(last.get("value") or 0)
    lx = pad_l + slot * (len(series) - 1) + slot / 2
    callout = (f'<text x="{lx:.1f}" y="{max(y_of(lv) - 12, 20):.1f}" fill="{PAPER}" '
               f'font-size="21" font-weight="700" text-anchor="middle">'
               f'{E(_money(lv))}</text>')

    return (f'<svg viewBox="0 0 {width} {height}" class="chart" '
            f'preserveAspectRatio="none" role="img">'
            f'<line x1="{pad_l}" y1="{zero_y:.1f}" x2="{width - pad_l}" '
            f'y2="{zero_y:.1f}" stroke="{MUTED}" stroke-width="1" opacity=".35"/>'
            f'{bars}{callout}</svg>')


def bars_h(rows: list[dict], accent: str = ACCENT) -> str:
    """Horizontal bars — the right shape when the labels are names, not dates."""
    if not rows:
        return ""
    peak = max((abs(float(r.get("value") or 0)) for r in rows), default=1) or 1
    out = ""
    for r in rows[:6]:
        v = float(r.get("value") or 0)
        out += (f'<div class="hb"><span class="hl">{E(str(r.get("label", "")))}</span>'
                f'<span class="ht"><i style="width:{abs(v) / peak * 100:.1f}%;'
                f'background:{accent}"></i></span>'
                f'<span class="hv">{E(r.get("display") or _money(v))}</span></div>')
    return f'<div class="hbars">{out}</div>'


# -------------------------------------------------------------------- slides

def _cover(sl, outline, client) -> str:
    return f"""<section class="s cover">
  <div class="rule"></div>
  <div class="eyebrow">{E(client.name)}</div>
  <h1>{E(sl.heading or outline.title)}</h1>
  <p class="sub">{E(outline.subtitle)}</p>
  <div class="foot">{datetime.now().strftime('%d %B %Y')} · prepared with Vyuha</div>
</section>"""


def _stats(sl) -> str:
    n = max(len(sl.stats), 1)
    cells = "".join(
        f'<div class="fig"><span class="k">{E(s.get("label", ""))}</span>'
        f'<b>{E(s.get("value", ""))}</b>'
        + (f'<span class="n">{E(s["note"])}</span>' if s.get("note") else "")
        + "</div>" for s in sl.stats)
    bullets = ("<ul class='under'>" + "".join(f"<li>{E(b)}</li>" for b in sl.bullets)
               + "</ul>") if sl.bullets else ""
    return f"""<section class="s">
  <h2>{E(sl.heading)}</h2>
  <div class="figs c{min(n, 4)}">{cells}</div>{bullets}
</section>"""


def _chart(sl) -> str:
    chart = sl.chart or {}
    body = (bars_h(chart.get("series", [])) if chart.get("type") == "hbar"
            else bar_chart(chart.get("series", [])))
    legend = ""
    if chart.get("legend"):
        legend = ('<div class="legend">' + "".join(
            f'<span><i style="background:{c}"></i>{E(l)}</span>'
            for l, c in chart["legend"]) + "</div>")
    bullets = ("<ul class='under'>" + "".join(f"<li>{E(b)}</li>" for b in sl.bullets)
               + "</ul>") if sl.bullets else ""
    return f"""<section class="s">
  <div class="row"><h2>{E(sl.heading)}</h2>{legend}</div>
  <div class="plot">{body}</div>{bullets}
</section>"""


def _split(sl) -> str:
    half = (len(sl.bullets) + 1) // 2
    left = "".join(f"<li>{E(b)}</li>" for b in sl.bullets[:half])
    right = "".join(f"<li>{E(b)}</li>" for b in sl.bullets[half:])
    figs = "".join(
        f'<div class="fig sm"><span class="k">{E(s.get("label", ""))}</span>'
        f'<b>{E(s.get("value", ""))}</b></div>' for s in sl.stats)
    return f"""<section class="s">
  <h2>{E(sl.heading)}</h2>
  {f'<div class="figs c{min(max(len(sl.stats), 1), 4)}">{figs}</div>' if figs else ''}
  <div class="two-col"><ul>{left}</ul><ul>{right}</ul></div>
</section>"""


def _points(sl) -> str:
    figs = "".join(
        f'<div class="fig sm"><span class="k">{E(s.get("label", ""))}</span>'
        f'<b>{E(s.get("value", ""))}</b></div>' for s in sl.stats)
    return f"""<section class="s">
  <h2>{E(sl.heading)}</h2>
  {f'<div class="figs c{min(max(len(sl.stats), 1), 4)}">{figs}</div>' if figs else ''}
  <ul class="big">{"".join(f"<li>{E(b)}</li>" for b in sl.bullets)}</ul>
</section>"""


def _closing(sl, client) -> str:
    return f"""<section class="s closing">
  <div class="rule"></div>
  <h1>{E(sl.heading)}</h1>
  <ul class="big">{"".join(f"<li>{E(b)}</li>" for b in sl.bullets)}</ul>
  <div class="foot">{E(client.name)}</div>
</section>"""


def render_html(outline, client) -> str:
    """The deck. Self-contained, keyboard-driven, one slide per printed page."""
    slides = [_cover(type("S", (), {"heading": outline.title, "bullets": [],
                                    "stats": [], "chart": None})(), outline, client)]
    for sl in outline.slides:
        kind = getattr(sl, "kind", "") or ("chart" if getattr(sl, "chart", None)
                                           else "stats" if sl.stats else "points")
        if kind == "chart":
            slides.append(_chart(sl))
        elif kind == "stats":
            slides.append(_stats(sl))
        elif kind == "split":
            slides.append(_split(sl))
        elif kind == "closing":
            slides.append(_closing(sl, client))
        else:
            slides.append(_points(sl))

    total = len(slides)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{E(outline.title)}</title>
<style>
  @page {{ size: 297mm 167mm; margin: 0; }}
  *{{box-sizing:border-box;margin:0;padding:0}}
  html,body{{background:{INK};color:{PAPER};
    font-family:'Segoe UI',-apple-system,'Helvetica Neue',Arial,sans-serif;
    -webkit-font-smoothing:antialiased;overflow:hidden}}
  .deck{{width:100vw;height:100vh;position:relative}}
  .s{{position:absolute;inset:0;display:none;flex-direction:column;
    justify-content:center;padding:6.5vh 7vw;
    background:linear-gradient(160deg,{INK} 55%,{INK_2});}}
  .s.on{{display:flex;animation:in .32s ease both}}
  @keyframes in{{from{{opacity:0;transform:translateY(10px)}}to{{opacity:1;transform:none}}}}
  h1{{font-size:clamp(34px,5.4vw,74px);line-height:1.03;letter-spacing:-.025em;
    font-weight:800;max-width:20ch}}
  h2{{font-size:clamp(22px,2.9vw,42px);line-height:1.1;letter-spacing:-.02em;
    font-weight:700;margin-bottom:3.4vh;max-width:26ch}}
  .rule{{width:74px;height:5px;background:{ACCENT};border-radius:99px;margin-bottom:3.4vh}}
  .eyebrow{{font-size:clamp(11px,1.15vw,15px);letter-spacing:.28em;text-transform:uppercase;
    color:{ACCENT};font-weight:700;margin-bottom:2.2vh}}
  .sub{{font-size:clamp(15px,1.7vw,24px);color:{MUTED};margin-top:2.6vh;max-width:46ch;
    line-height:1.5}}
  .foot{{position:absolute;left:7vw;bottom:6vh;font-size:clamp(11px,1.1vw,14px);
    color:{MUTED};letter-spacing:.05em}}
  .cover,.closing{{justify-content:center}}
  .row{{display:flex;justify-content:space-between;align-items:baseline;gap:20px;
    flex-wrap:wrap}}
  .figs{{display:grid;gap:2.4vw}}
  .figs.c1{{grid-template-columns:1fr}} .figs.c2{{grid-template-columns:repeat(2,1fr)}}
  .figs.c3{{grid-template-columns:repeat(3,1fr)}} .figs.c4{{grid-template-columns:repeat(4,1fr)}}
  .fig{{border-top:2px solid rgba(242,245,247,.16);padding-top:1.8vh}}
  .fig .k{{display:block;font-size:clamp(10px,1.05vw,14px);letter-spacing:.17em;
    text-transform:uppercase;color:{MUTED};font-weight:700}}
  .fig b{{display:block;font-size:clamp(30px,4.6vw,68px);line-height:1.04;
    margin-top:1.1vh;letter-spacing:-.03em;font-weight:800}}
  .fig.sm b{{font-size:clamp(22px,2.7vw,38px)}}
  .fig .n{{display:block;font-size:clamp(11px,1.1vw,15px);color:{MUTED};margin-top:.9vh}}
  ul{{list-style:none}}
  ul.big li,ul.under li,.two-col li{{position:relative;padding-left:26px;
    margin-bottom:1.7vh;line-height:1.45}}
  ul.big li{{font-size:clamp(15px,1.85vw,27px)}}
  ul.under{{margin-top:3.2vh}}
  ul.under li,.two-col li{{font-size:clamp(13px,1.4vw,20px);color:#C6D0D8}}
  ul.big li::before,ul.under li::before,.two-col li::before{{content:"";position:absolute;
    left:0;top:.62em;width:9px;height:9px;border-radius:2px;background:{ACCENT}}}
  .two-col{{display:grid;grid-template-columns:1fr 1fr;gap:2.6vw;margin-top:2.4vh}}
  .plot{{flex:1;min-height:0;display:flex;align-items:center}}
  .chart{{width:100%;height:min(42vh,340px)}}
  .legend{{display:flex;gap:18px;font-size:clamp(11px,1.1vw,15px);color:{MUTED}}}
  .legend i{{display:inline-block;width:11px;height:11px;border-radius:3px;
    margin-right:7px;vertical-align:middle}}
  .hbars{{width:100%;display:flex;flex-direction:column;gap:1.9vh}}
  .hb{{display:grid;grid-template-columns:minmax(120px,22%) 1fr minmax(90px,12%);
    gap:18px;align-items:center;font-size:clamp(12px,1.35vw,19px)}}
  .hl{{color:#C6D0D8;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
  .ht{{height:14px;border-radius:99px;background:rgba(242,245,247,.09);overflow:hidden}}
  .ht i{{display:block;height:100%;border-radius:99px}}
  .hv{{text-align:right;font-weight:700;font-variant-numeric:tabular-nums}}
  .bar{{position:fixed;left:0;bottom:0;height:3px;background:{ACCENT};
    transition:width .3s ease;z-index:5}}
  .num{{position:fixed;right:2.4vw;bottom:2.6vh;font-size:13px;color:{MUTED};
    letter-spacing:.08em;z-index:5}}
  .hint{{position:fixed;left:2.4vw;bottom:2.6vh;font-size:12px;color:{MUTED};z-index:5}}
  @media print{{
    html,body{{overflow:visible;background:#fff}}
    .deck{{width:auto;height:auto}}
    .s{{position:relative;display:flex !important;inset:auto;
      width:297mm;height:167mm;page-break-after:always;animation:none}}
    .bar,.num,.hint{{display:none}}
  }}
</style></head><body>
<div class="deck">{"".join(slides)}</div>
<div class="bar" id="bar"></div>
<div class="num" id="num"></div>
<div class="hint">← → to move · P to print</div>
<script>
(function(){{
  var s = document.querySelectorAll('.s'), i = 0, n = {total};
  function show(k){{
    i = Math.max(0, Math.min(n - 1, k));
    s.forEach(function(el, j){{ el.classList.toggle('on', j === i); }});
    document.getElementById('bar').style.width = ((i + 1) / n * 100) + '%';
    document.getElementById('num').textContent = (i + 1) + ' / ' + n;
  }}
  document.addEventListener('keydown', function(e){{
    if (e.key === 'ArrowRight' || e.key === ' ' || e.key === 'PageDown') {{ show(i + 1); e.preventDefault(); }}
    else if (e.key === 'ArrowLeft' || e.key === 'PageUp') {{ show(i - 1); e.preventDefault(); }}
    else if (e.key === 'Home') show(0);
    else if (e.key === 'End') show(n - 1);
    else if (e.key === 'p' || e.key === 'P') window.print();
  }});
  document.addEventListener('click', function(e){{
    show(i + (e.clientX < window.innerWidth * 0.28 ? -1 : 1));
  }});
  show(0);
}})();
</script></body></html>"""
