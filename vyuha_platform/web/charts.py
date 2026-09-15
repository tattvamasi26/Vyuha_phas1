"""Small charts drawn on the server as SVG — no JavaScript, nothing to load.

A sparkline on a phone is worth more than an interactive chart that has not finished
downloading. The interactive charts (ECharts) arrive with the sections that need them and
load only on those pages.
"""

from __future__ import annotations

from markupsafe import Markup, escape


def sparkline(values, width: int = 160, height: int = 40, pad: float = 3.0) -> Markup:
    """A trend line with a soft fill under it. Flat when there is nothing to show."""
    vals = [float(v or 0) for v in values] or [0.0]
    if len(vals) == 1:
        vals = vals * 2
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1.0
    step = (width - 2 * pad) / (len(vals) - 1)
    pts = [(pad + i * step, pad + (height - 2 * pad) * (1 - (v - lo) / span))
           for i, v in enumerate(vals)]
    line = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    base = height - pad
    area = f"{line} L{pts[-1][0]:.1f},{base:.1f} L{pts[0][0]:.1f},{base:.1f} Z"
    return Markup(
        f'<svg class="spark" viewBox="0 0 {width} {height}" preserveAspectRatio="none" '
        f'aria-hidden="true" focusable="false">'
        f'<path class="spark-area" d="{area}"/>'
        f'<path class="spark-line" d="{line}" fill="none" vector-effect="non-scaling-stroke"/>'
        f'</svg>')


def bars(values, width: int = 160, height: int = 40, gap: float = 2.0) -> Markup:
    """Tiny column chart — for a handful of months, where a line would imply continuity."""
    vals = [max(float(v or 0), 0.0) for v in values] or [0.0]
    hi = max(vals) or 1.0
    w = (width - gap * (len(vals) - 1)) / len(vals)
    rects = []
    for i, v in enumerate(vals):
        h = max(1.5, (height - 2) * v / hi)
        x = i * (w + gap)
        rects.append(f'<rect x="{x:.1f}" y="{height - h:.1f}" width="{w:.1f}" '
                     f'height="{h:.1f}" rx="1.5"/>')
    return Markup(f'<svg class="bars" viewBox="0 0 {width} {height}" preserveAspectRatio="none" '
                  f'aria-hidden="true" focusable="false">{"".join(rects)}</svg>')


def columns(values, labels, *, fmt=None, partial_last: bool = False, label: str = "",
            width: int = 960, height: int = 240) -> Markup:
    """Labelled columns for a laptop page — one per month, its value above it.

    ``partial_last`` draws the last column lighter: the current month is not over, and
    half a month drawn like a whole one reads as a collapse.
    """
    fmt = fmt or (lambda v: f"{v:,.0f}")
    vals = [max(float(v or 0), 0.0) for v in values] or [0.0]
    n = len(vals)
    hi = max(vals) or 1.0
    top, bottom = 26.0, 30.0
    plot = height - top - bottom
    slot = width / n
    bw = min(slot * 0.6, 56.0)
    base_y = height - bottom
    out = [f'<line class="cols-base" x1="0" x2="{width}" y1="{base_y:.1f}" y2="{base_y:.1f}"/>']
    for i, (v, lab) in enumerate(zip(vals, labels)):
        h = max(plot * v / hi, 2.0)
        x = i * slot + (slot - bw) / 2
        cx = i * slot + slot / 2
        cls = ' class="cols-part"' if partial_last and i == n - 1 else ""
        value = (f'<text class="cols-value" x="{cx:.1f}" y="{base_y - h - 8:.1f}" '
                 f'text-anchor="middle">{escape(fmt(v))}</text>' if v else "")
        out.append(
            f'<g{cls}><title>{escape(lab)}: {escape(fmt(v))}</title>'
            f'<rect x="{x:.1f}" y="{base_y - h:.1f}" width="{bw:.1f}" height="{h:.1f}" rx="5"/>'
            f'{value}<text class="cols-label" x="{cx:.1f}" y="{height - 9:.1f}" '
            f'text-anchor="middle">{escape(lab)}</text></g>')
    return Markup(f'<svg class="cols" viewBox="0 0 {width} {height}" role="img" '
                  f'aria-label="{escape(label or "Chart")}" focusable="false">{"".join(out)}</svg>')
