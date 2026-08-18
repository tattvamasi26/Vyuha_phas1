"""Render insights as one self-contained HTML file.

No CDN, no build step, no server — the output is a single .html the founder can
WhatsApp or email to a prospect and they can open it on a phone. Charts are
hand-rolled inline SVG/CSS for the same reason.
"""

from __future__ import annotations

import html
from datetime import datetime

from . import schema
from .analyze import CRITICAL, INFO, WARNING, Alert, Insights

ACCENTS = {
    "sales": "#00C9A7",
    "stock": "#F0A500",
    "receivables": "#7C5CFC",
}

SEVERITY_STYLE = {
    CRITICAL: ("#FF5C7A", "Critical"),
    WARNING: ("#F0A500", "Watch"),
    INFO: ("#00C9A7", "FYI"),
}


def render(insights: Insights, client: str | None = None) -> str:
    """Build the full HTML document for one analysed file."""
    title = client or insights.source
    body = "\n".join(
        part
        for part in (
            _header(insights, title),
            _alerts(insights.alerts),
            _kpi_row(insights),
            _sales_section(insights),
            _stock_section(insights),
            _receivables_section(insights),
            _quality_section(insights),
        )
        if part
    )
    return _DOCUMENT.format(title=esc(f"{title} · Vyuha"), styles=_STYLES, body=body)


# --- sections -------------------------------------------------------------


def _header(insights: Insights, title: str) -> str:
    period = ""
    if insights.period_start is not None and insights.period_end is not None:
        period = (
            f"<span class='period'>{insights.period_start:%d %b %Y}"
            f" &rarr; {insights.period_end:%d %b %Y}</span>"
        )
    return f"""
<header class="hero">
  <div class="brand">VYUHA</div>
  <h1>{esc(title)}</h1>
  <p class="sub">Generated {insights.generated_at:%d %b %Y, %I:%M %p} {period}</p>
</header>"""


def _alerts(alerts: list[Alert]) -> str:
    if not alerts:
        return """
<section class="card ok">
  <h2>Nothing needs attention</h2>
  <p class="muted">No stock-outs, dead stock or overdue payments were found in this file.</p>
</section>"""
    rows = "\n".join(
        f"""
    <li class="alert alert-{esc(a.severity)}">
      <span class="tag">{esc(SEVERITY_STYLE.get(a.severity, ('#888', 'Note'))[1])}</span>
      <div>
        <strong>{esc(a.title)}</strong>
        <p>{esc(a.detail)}</p>
      </div>
    </li>"""
        for a in alerts
    )
    return f"""
<section class="card alerts">
  <h2>Needs attention <span class="count">{len(alerts)}</span></h2>
  <ul class="alert-list">{rows}
  </ul>
</section>"""


def _kpi_row(insights: Insights) -> str:
    tiles: list[str] = []
    sales, stock, rec = insights.sales, insights.stock, insights.receivables

    if sales.get("revenue") is not None:
        tiles.append(_kpi("Revenue", money_short(sales["revenue"]), _trend_note(sales), "sales"))
    if sales.get("orders"):
        tiles.append(_kpi("Orders", num(sales["orders"]),
                          f"Avg {money_short(sales.get('avg_order_value', 0))}", "sales"))
    if sales.get("party_count"):
        share = sales.get("top3_share")
        note = f"Top 3 = {share:.0%} of revenue" if share else "Active customers"
        tiles.append(_kpi("Customers", num(sales["party_count"]), note, "sales"))
    if stock.get("value") is not None:
        tiles.append(_kpi("Stock value", money_short(stock["value"]),
                          f"{num(stock.get('skus', 0))} SKUs", "stock"))
    elif stock.get("skus"):
        tiles.append(_kpi("SKUs tracked", num(stock["skus"]),
                          f"{num(stock.get('units', 0))} units on hand", "stock"))
    if stock.get("below_reorder_count") is not None:
        tiles.append(_kpi("Below reorder", num(stock["below_reorder_count"]),
                          "Raise a PO", "stock",
                          alarm=stock["below_reorder_count"] > 0))
    if stock.get("dead_stock_value"):
        tiles.append(_kpi("Cash in dead stock", money_short(stock["dead_stock_value"]),
                          f"{num(stock.get('dead_stock_count', 0))} SKUs idle "
                          f"90+ days", "stock", alarm=True))
    if rec.get("total") is not None:
        tiles.append(_kpi("Outstanding", money_short(rec["total"]),
                          f"{num(rec.get('invoices', 0))} open invoices", "receivables"))
    if rec.get("overdue_total"):
        tiles.append(_kpi("Overdue", money_short(rec["overdue_total"]),
                          f"{num(rec.get('overdue_count', 0))} invoices past due",
                          "receivables", alarm=True))

    if not tiles:
        return ""
    return f"<section class='kpis'>{''.join(tiles)}</section>"


def _trend_note(sales: dict) -> str:
    change = sales.get("mom_change")
    if change is None:
        return f"{num(sales.get('lines', 0))} line items"
    arrow = "&uarr;" if change >= 0 else "&darr;"
    return f"{arrow} {abs(change):.0%} vs {esc(sales.get('mom_from', 'last month'))}"


def _sales_section(insights: Insights) -> str:
    sales = insights.sales
    if not sales.get("revenue"):
        return ""

    blocks = [_monthly_chart(sales.get("monthly") or [])]

    if sales.get("top_parties"):
        blocks.append(
            _table(
                "Top customers",
                ["Customer", "Revenue", "Share", "Orders"],
                [
                    [
                        esc(r["label"]),
                        money(r["amount"]),
                        _share_bar(r["share"], "sales"),
                        num(r["lines"]),
                    ]
                    for r in sales["top_parties"]
                ],
                numeric={1, 3},
            )
        )
    if sales.get("top_items"):
        blocks.append(
            _table(
                "Top products",
                ["Product", "Revenue", "Share", "Lines"],
                [
                    [
                        esc(r["label"]),
                        money(r["amount"]),
                        _share_bar(r["share"], "sales"),
                        num(r["lines"]),
                    ]
                    for r in sales["top_items"]
                ],
                numeric={1, 3},
            )
        )
    if sales.get("top_categories"):
        blocks.append(
            _table(
                "By category",
                ["Category", "Revenue", "Share"],
                [
                    [esc(r["label"]), money(r["amount"]), _share_bar(r["share"], "sales")]
                    for r in sales["top_categories"]
                ],
                numeric={1},
            )
        )

    return _section("Sales", "sales", blocks)


def _stock_section(insights: Insights) -> str:
    stock = insights.stock
    if not stock.get("skus"):
        return ""

    blocks: list[str] = []

    if stock.get("below_reorder"):
        blocks.append(
            _table(
                "Reorder now",
                ["Item", "On hand", "Reorder level", "Short by"],
                [
                    [
                        esc(r["label"]),
                        num(r["qty"]),
                        num(r.get("reorder_level")),
                        f"<span class='bad'>{num(r.get('shortfall'))}</span>",
                    ]
                    for r in stock["below_reorder"]
                ],
                numeric={1, 2, 3},
            )
        )
    if stock.get("cover"):
        blocks.append(
            _table(
                "Days of cover (at current run rate)",
                ["Item", "On hand", "Sells/day", "Days left"],
                [
                    [
                        esc(r["label"]),
                        num(r["qty"]),
                        f"{r['daily_run_rate']:g}",
                        _days_pill(r["days_cover"]),
                    ]
                    for r in stock["cover"]
                ],
                numeric={1, 2, 3},
            )
        )
    if stock.get("dead_stock"):
        blocks.append(
            _table(
                f"Dead stock — no sale in 90+ days ({num(stock.get('dead_stock_count', 0))} SKUs)",
                ["Item", "Qty", "Value locked", "Last sold"],
                [
                    [
                        esc(r["label"]),
                        num(r["qty"]),
                        money(r["value"]) if r.get("value") else "—",
                        esc(r.get("last_sold") or "never in this file"),
                    ]
                    for r in stock["dead_stock"]
                ],
                numeric={1, 2},
            )
        )
    if stock.get("top_value"):
        blocks.append(
            _table(
                "Where the stock money sits",
                ["Item", "Qty", "Value"],
                [
                    [esc(r["label"]), num(r["qty"]), money(r["value"])]
                    for r in stock["top_value"]
                ],
                numeric={1, 2},
            )
        )

    if not blocks:
        return ""
    return _section("Stock", "stock", blocks)


def _receivables_section(insights: Insights) -> str:
    rec = insights.receivables
    if not rec.get("total"):
        return ""

    blocks: list[str] = []
    if rec.get("ageing"):
        blocks.append(_ageing_chart(rec["ageing"], rec.get("ageing_basis")))
    if rec.get("top_debtors"):
        blocks.append(
            _table(
                "Who owes the most",
                ["Customer", "Outstanding", "Share", "Invoices"],
                [
                    [
                        esc(r["label"]),
                        money(r["amount"]),
                        _share_bar(r["share"], "receivables"),
                        num(r["lines"]),
                    ]
                    for r in rec["top_debtors"]
                ],
                numeric={1, 3},
            )
        )
    if rec.get("worst_overdue"):
        blocks.append(
            _table(
                "Chase these first",
                ["Customer", "Invoice", "Amount", "Days overdue"],
                [
                    [
                        esc(r["party"]),
                        esc(r.get("invoice") or "—"),
                        money(r["amount"]),
                        _days_overdue_pill(r.get("days")),
                    ]
                    for r in rec["worst_overdue"]
                ],
                numeric={2, 3},
            )
        )

    return _section("Receivables", "receivables", blocks)


def _quality_section(insights: Insights) -> str:
    rows: list[str] = []
    for table in insights.tables:
        fields = ", ".join(
            schema.LABELS.get(f, f) for f in table.frame.columns if f in schema.LABELS
        )
        issues = " ".join(table.issues) or "Clean."
        rows.append(
            f"""
      <tr>
        <td>{esc(table.sheet)}</td>
        <td><span class="pill pill-{esc(table.kind)}">{esc(schema.TABLE_LABELS.get(table.kind, table.kind))}</span></td>
        <td class="num">{num(table.rows_out)}</td>
        <td class="tiny">{esc(fields) or '—'}</td>
        <td class="tiny">{esc(issues)}</td>
      </tr>"""
        )

    warnings = "".join(f"<p class='warn'>{esc(w)}</p>" for w in insights.warnings)
    return f"""
<section class="card quality">
  <h2>What Vyuha read from your file</h2>
  {warnings}
  <div class="scroll">
    <table>
      <thead><tr><th>Sheet</th><th>Read as</th><th class="num">Rows used</th><th>Columns understood</th><th>Fixes applied</th></tr></thead>
      <tbody>{''.join(rows)}</tbody>
    </table>
  </div>
  <p class="muted tiny">Source: {esc(insights.source)}</p>
</section>"""


# --- building blocks ------------------------------------------------------


def _section(title: str, accent: str, blocks: list[str]) -> str:
    inner = "\n".join(b for b in blocks if b)
    if not inner:
        return ""
    return f"""
<section class="band band-{accent}">
  <h2 class="band-title">{esc(title)}</h2>
  {inner}
</section>"""


def _kpi(label: str, value: str, note: str, accent: str, alarm: bool = False) -> str:
    return f"""
  <div class="kpi kpi-{accent}{' kpi-alarm' if alarm else ''}">
    <span class="kpi-label">{esc(label)}</span>
    <span class="kpi-value">{value}</span>
    <span class="kpi-note">{note}</span>
  </div>"""


def _table(title: str, headers: list[str], rows: list[list[str]], numeric: set[int]) -> str:
    if not rows:
        return ""
    head = "".join(
        f"<th class='{'num' if i in numeric else ''}'>{esc(h)}</th>"
        for i, h in enumerate(headers)
    )
    body = "".join(
        "<tr>"
        + "".join(
            f"<td class='{'num' if i in numeric else ''}'>{cell}</td>"
            for i, cell in enumerate(row)
        )
        + "</tr>"
        for row in rows
    )
    return f"""
  <div class="card">
    <h3>{esc(title)}</h3>
    <div class="scroll">
      <table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>
    </div>
  </div>"""


def _monthly_chart(monthly: list[dict]) -> str:
    if len(monthly) < 2:
        return ""
    peak = max(m["amount"] for m in monthly) or 1
    bars = "".join(
        f"""
      <div class="bar-col" title="{esc(m['label'])}: {money(m['amount'])}">
        <div class="bar-value">{money_short(m['amount'])}</div>
        <div class="bar{' bar-partial' if m.get('partial') else ''}"
             style="height:{max(m['amount'] / peak * 100, 1.5):.1f}%"></div>
        <div class="bar-label">{esc(m['label'])}{'*' if m.get('partial') else ''}</div>
      </div>"""
        for m in monthly[-14:]
    )
    note = (
        "<p class='muted tiny'>* part-month — the file ends mid-month, "
        "so this bar is not comparable to the others.</p>"
        if any(m.get("partial") for m in monthly[-14:])
        else ""
    )
    return f"""
  <div class="card">
    <h3>Revenue by month</h3>
    <div class="chart">{bars}</div>
    {note}
  </div>"""


def _ageing_chart(buckets: list[dict], basis: str | None) -> str:
    total = sum(b["amount"] for b in buckets) or 1
    colors = ["#00C9A7", "#5AD1B4", "#F0A500", "#FF9351", "#FF5C7A"]
    rows = "".join(
        f"""
      <div class="age-row">
        <span class="age-label">{esc(b['label'])}</span>
        <span class="age-track">
          <span class="age-fill" style="width:{b['amount'] / total * 100:.1f}%;background:{colors[i % len(colors)]}"></span>
        </span>
        <span class="age-amount">{money(b['amount'])}</span>
        <span class="age-count">{num(b['count'])} inv</span>
      </div>"""
        for i, b in enumerate(buckets)
    )
    note = f"Aged by {esc(basis)}." if basis else ""
    return f"""
  <div class="card">
    <h3>Ageing</h3>
    <p class="muted tiny">{note}</p>
    <div class="ageing">{rows}</div>
  </div>"""


def _share_bar(share: float, accent: str) -> str:
    pct = max(min(share, 1.0), 0.0) * 100
    return (
        f"<span class='share'><span class='share-track'>"
        f"<span class='share-fill share-{accent}' style='width:{pct:.1f}%'></span>"
        f"</span><span class='share-num'>{pct:.0f}%</span></span>"
    )


def _days_pill(days: float) -> str:
    if days <= 7:
        tone = "bad"
    elif days <= 14:
        tone = "warn-tone"
    else:
        tone = "good"
    return f"<span class='{tone}'>{days:g} d</span>"


def _days_overdue_pill(days: int | None) -> str:
    if days is None:
        return "—"
    tone = "bad" if days > 60 else ("warn-tone" if days > 30 else "")
    return f"<span class='{tone}'>{days} d</span>"


# --- formatting -----------------------------------------------------------


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def money(amount: float | None) -> str:
    """Full rupee amount in Indian digit grouping: ₹12,34,567."""
    if amount is None:
        return "—"
    amount = float(amount)
    sign = "-" if amount < 0 else ""
    whole = f"{abs(amount):.0f}"
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        pieces = []
        while len(head) > 2:
            pieces.insert(0, head[-2:])
            head = head[:-2]
        if head:
            pieces.insert(0, head)
        whole = ",".join(pieces) + "," + tail
    return f"{sign}&#8377;{whole}"


def money_short(amount: float | None) -> str:
    if amount is None:
        return "—"
    amount = float(amount)
    sign = "-" if amount < 0 else ""
    value = abs(amount)
    if value >= 1_00_00_000:
        return f"{sign}&#8377;{value / 1_00_00_000:.2f} Cr"
    if value >= 1_00_000:
        return f"{sign}&#8377;{value / 1_00_000:.2f} L"
    if value >= 1_000:
        return f"{sign}&#8377;{value / 1_000:.1f} K"
    return f"{sign}&#8377;{value:,.0f}"


def num(value: float | int | None) -> str:
    if value is None:
        return "—"
    value = float(value)
    if value == int(value):
        return f"{int(value):,}"
    return f"{value:,.2f}"


# --- document shell -------------------------------------------------------

_STYLES = """
:root{
  --bg:#08090C; --panel:#111319; --panel-2:#161922; --line:#232733;
  --text:#EEF1F7; --muted:#8B93A7; --sales:#00C9A7; --stock:#F0A500;
  --receivables:#7C5CFC; --bad:#FF5C7A;
}
*{box-sizing:border-box;margin:0;padding:0}
body{
  background:var(--bg); color:var(--text); font-family:"Manrope","Segoe UI",system-ui,-apple-system,sans-serif;
  line-height:1.5; padding:clamp(16px,3vw,40px); -webkit-font-smoothing:antialiased;
}
.wrap{max-width:1180px;margin:0 auto;display:flex;flex-direction:column;gap:26px}
.hero{position:relative;padding:34px 30px;border-radius:20px;overflow:hidden;
  background:radial-gradient(120% 160% at 12% 0%,rgba(0,201,167,.20),transparent 58%),
             radial-gradient(120% 160% at 88% 10%,rgba(124,92,252,.18),transparent 60%),var(--panel);
  border:1px solid var(--line)}
.brand{font-size:12px;letter-spacing:.42em;color:var(--sales);font-weight:800}
.hero h1{font-size:clamp(28px,4.6vw,46px);line-height:1.08;margin:10px 0 6px;letter-spacing:-.02em}
.sub{color:var(--muted);font-size:14px}
.period{margin-left:10px;padding:3px 10px;border-radius:99px;background:var(--panel-2);
  border:1px solid var(--line);font-size:12px;white-space:nowrap;display:inline-block}
.card{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:22px}
.card h2{font-size:19px;margin-bottom:14px;letter-spacing:-.01em}
.card h3{font-size:15px;margin-bottom:12px;color:var(--text);letter-spacing:-.01em}
.card.ok h2{color:var(--sales)}
.muted{color:var(--muted)}
.tiny{font-size:12px}
.warn{color:var(--stock);font-size:13px;margin-bottom:8px}
.count{display:inline-block;min-width:24px;text-align:center;padding:1px 8px;border-radius:99px;
  background:var(--bad);color:#fff;font-size:12px;vertical-align:middle;margin-left:6px}
.alert-list{list-style:none;display:flex;flex-direction:column;gap:10px}
.alert{display:flex;gap:14px;align-items:flex-start;padding:14px 16px;border-radius:12px;
  background:var(--panel-2);border-left:3px solid var(--muted)}
.alert p{color:var(--muted);font-size:13.5px;margin-top:3px}
.alert-critical{border-left-color:var(--bad)}
.alert-critical .tag{background:rgba(255,92,122,.16);color:var(--bad)}
.alert-warning{border-left-color:var(--stock)}
.alert-warning .tag{background:rgba(240,165,0,.16);color:var(--stock)}
.alert-info{border-left-color:var(--sales)}
.alert-info .tag{background:rgba(0,201,167,.16);color:var(--sales)}
.tag{flex:none;font-size:10.5px;font-weight:800;letter-spacing:.1em;text-transform:uppercase;
  padding:5px 9px;border-radius:6px;margin-top:2px}
.kpis{display:grid;gap:14px;grid-template-columns:repeat(auto-fit,minmax(190px,1fr))}
.kpi{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:18px 20px;
  display:flex;flex-direction:column;gap:6px;position:relative;overflow:hidden}
.kpi::after{content:"";position:absolute;inset:auto -30% -70% -30%;height:120px;border-radius:50%;
  opacity:.16;filter:blur(28px)}
.kpi-sales::after{background:var(--sales)} .kpi-stock::after{background:var(--stock)}
.kpi-receivables::after{background:var(--receivables)}
.kpi-alarm::after{background:var(--bad);opacity:.22}
.kpi-label{font-size:12px;letter-spacing:.09em;text-transform:uppercase;color:var(--muted);font-weight:700}
.kpi-value{font-size:clamp(24px,3.2vw,32px);font-weight:800;letter-spacing:-.02em;
  font-variant-numeric:tabular-nums}
.kpi-note{font-size:12.5px;color:var(--muted)}
.band{display:flex;flex-direction:column;gap:14px}
.band-title{font-size:13px;letter-spacing:.3em;text-transform:uppercase;font-weight:800;
  padding-left:12px;border-left:3px solid var(--muted)}
.band-sales .band-title{color:var(--sales);border-color:var(--sales)}
.band-stock .band-title{color:var(--stock);border-color:var(--stock)}
.band-receivables .band-title{color:var(--receivables);border-color:var(--receivables)}
.scroll{overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:13.5px;min-width:460px}
th{text-align:left;font-size:11px;letter-spacing:.09em;text-transform:uppercase;color:var(--muted);
  padding:0 12px 10px;font-weight:700;white-space:nowrap}
td{padding:11px 12px;border-top:1px solid var(--line);vertical-align:middle}
tbody tr:hover{background:var(--panel-2)}
.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.bad{color:var(--bad);font-weight:700}
.warn-tone{color:var(--stock);font-weight:700}
.good{color:var(--sales)}
.share{display:flex;align-items:center;gap:8px;min-width:110px}
.share-track{flex:1;height:6px;border-radius:99px;background:var(--panel-2);overflow:hidden}
.share-fill{display:block;height:100%;border-radius:99px}
.share-sales{background:var(--sales)} .share-receivables{background:var(--receivables)}
.share-num{font-size:12px;color:var(--muted);width:34px;text-align:right;font-variant-numeric:tabular-nums}
.chart{display:flex;align-items:flex-end;gap:10px;height:230px;padding-top:22px;overflow-x:auto}
.bar-col{flex:1;min-width:52px;display:flex;flex-direction:column;justify-content:flex-end;
  align-items:center;height:100%;gap:6px}
.bar{width:100%;max-width:56px;border-radius:8px 8px 3px 3px;
  background:linear-gradient(180deg,var(--sales),rgba(0,201,167,.25))}
.bar-partial{background:repeating-linear-gradient(135deg,rgba(0,201,167,.55) 0 6px,
  rgba(0,201,167,.16) 6px 12px)}
.bar-value{font-size:11px;color:var(--muted);font-variant-numeric:tabular-nums;white-space:nowrap}
.bar-label{font-size:11px;color:var(--muted);white-space:nowrap}
.ageing{display:flex;flex-direction:column;gap:10px}
.age-row{display:grid;grid-template-columns:96px 1fr 110px 64px;gap:12px;align-items:center;font-size:13px}
.age-track{height:10px;border-radius:99px;background:var(--panel-2);overflow:hidden}
.age-fill{display:block;height:100%;border-radius:99px;min-width:2px}
.age-amount{text-align:right;font-variant-numeric:tabular-nums}
.age-count{text-align:right;color:var(--muted);font-size:12px}
.pill{padding:3px 9px;border-radius:99px;font-size:11px;font-weight:700;white-space:nowrap}
.pill-sales{background:rgba(0,201,167,.15);color:var(--sales)}
.pill-stock{background:rgba(240,165,0,.15);color:var(--stock)}
.pill-receivables{background:rgba(124,92,252,.16);color:var(--receivables)}
.pill-unknown{background:var(--panel-2);color:var(--muted)}
.foot{text-align:center;color:var(--muted);font-size:12px;padding:6px 0 10px}
.foot b{color:var(--sales);letter-spacing:.3em}
@media (max-width:640px){
  .age-row{grid-template-columns:78px 1fr 88px;}
  .age-count{display:none}
  table{font-size:12.5px}
}
@media print{
  body{background:#fff;color:#111}
  .card,.kpi,.hero{border-color:#ddd;background:#fff}
  .hero{background:#fff}
}
"""

_DOCUMENT = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>{styles}</style>
</head>
<body>
<div class="wrap">
{body}
<p class="foot">Built by <b>VYUHA</b> — from your Excel file, automatically.</p>
</div>
</body>
</html>
"""
