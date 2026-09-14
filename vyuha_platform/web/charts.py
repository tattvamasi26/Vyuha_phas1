"""Small charts drawn on the server as SVG — no JavaScript, nothing to load.

A sparkline on a phone is worth more than an interactive chart that has not finished
downloading. The interactive charts (ECharts) arrive with the sections that need them and
load only on those pages.
"""

from __future__ import annotations

from markupsafe import Markup


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
