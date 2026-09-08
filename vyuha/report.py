"""The one file the client actually receives.

Everything else in this package exists to produce this document. It is opened on
a phone, in a shop, after arriving on WhatsApp — often with no internet by the
time it is read — so it carries no script, no stylesheet link, no font file and
no image. A test enforces that: no ``http://``, no ``https://``, no ``<script``,
no ``src=`` may appear anywhere in the output. That rules out webfonts and even
inline SVG, whose ``xmlns`` is a URL, so every chart here is drawn with CSS
boxes and every typeface is a system stack.

**Design.** A light document, not a dark dashboard. This gets forwarded,
printed, read in daylight in a shop doorway, and shown across a desk to an
accountant or a bank — all of which a near-black app screen is bad at. The
ground is warm paper rather than white so it does not glare; the ink is
near-black with a faint blue cast; one structural accent, a deep slate blue,
carries the hierarchy, and colour beyond that is reserved for meaning — red for
critical, amber for warning, green for settled. A dark palette follows the
phone's own setting for anybody reading at night. Since no webfont can be
loaded, the type does its work through role instead: system sans for words, a
monospace stack with tabular figures for every number, so columns of rupees line
up down the page. In a document that is almost entirely numbers, that alignment
is worth more than any typeface would be.

**Order.** The sections are arranged the way somebody needs them, not the way
the pipeline computed them:

1. what the file is, and one sentence on whether anything is wrong
2. what needs a decision, worst first
3. **how to read these numbers** — which figures rest on a guess
4. the headline figures
5. sales, stock, receivables
6. what Vyuha read from the file, sheet by sheet

Item 3 is the one that did not exist before. Every number used to print in the
same weight of type whether it was read off a column labelled "Invoice Amount"
or reconstructed as qty × rate from a sheet with no headings at all. A
distributor cannot tell those apart by looking, and the whole document's
credibility rests on the first number somebody checks against their own file.
`trust.py` computes the distinction; this module shows it.
"""

from __future__ import annotations

import html

from . import fmt, schema, trust
from .analyze import Alert, Insights

SEVERITY_STYLE = {
    "critical": ("crit", "Critical"),
    "warning": ("warn", "Warning"),
    "info": ("info", "Note"),
}

#: The chip that goes on a figure resting on something other than a labelled
#: column. Deliberately one word: the tile stays scannable and the full
#: sentence lives once, in the panel above.
BASIS_CHIP = {
    trust.DERIVED: ("calculated", "chip-warn"),
    trust.GUESSED: ("guessed", "chip-warn"),
    trust.MATCHED: ("matched", "chip-soft"),
}

#: What earns a mark on a headline figure. `matched` is not here for the same
#: reason it is not in `trust.NOTABLE`: a mark on every tile is no mark at all.
CHIP_ON_FIGURE = (trust.DERIVED, trust.GUESSED)


def render(insights: Insights, client: str | None = None) -> str:
    """Build the full HTML document for one analysed file."""
    title = client or insights.source
    body = "\n".join(
        part
        for part in (
            _masthead(insights, title),
            _decisions(insights.alerts),
            _trust_panel(insights),
            _figures(insights),
            _sales_section(insights),
            _stock_section(insights),
            _receivables_section(insights),
            _readback(insights),
        )
        if part
    )
    return _DOCUMENT.format(title=esc(f"{title} · Vyuha"), styles=_STYLES, body=body)


# --- 1. what this is ------------------------------------------------------


def _masthead(insights: Insights, title: str) -> str:
    period = ""
    if insights.period_start is not None and insights.period_end is not None:
        period = (
            f"<span class='meta-item'>{insights.period_start:%d %b %Y}"
            f" &ndash; {insights.period_end:%d %b %Y}</span>"
        )
    return f"""
<header class="masthead">
  <div class="mark">VYUHA</div>
  <h1>{esc(title)}</h1>
  <p class="verdict">{_verdict(insights)}</p>
  <p class="meta">
    <span class="meta-item">Read {insights.generated_at:%d %b %Y, %I:%M %p}</span>
    {period}
  </p>
</header>"""


def _verdict(insights: Insights) -> str:
    """One sentence, before any number.

    Somebody who reads nothing else should still close the file knowing whether
    it needed them.
    """
    alerts = insights.alerts
    if not alerts:
        return ("Nothing in this file needs a decision today &mdash; no stock-outs, "
                "no dead stock and nothing overdue.")
    worst = alerts[0]
    n = len(alerts)
    lead = "1 thing needs" if n == 1 else f"{n} things need"
    return f"{lead} a decision. The first is <strong>{esc(worst.title)}</strong>."


# --- 2. what needs doing --------------------------------------------------


def _decisions(alerts: list[Alert]) -> str:
    if not alerts:
        return """
<section class="panel settled">
  <h2>Nothing needs attention</h2>
  <p class="lede">No stock-outs, no dead stock and no overdue payments were found
    in this file.</p>
</section>"""
    rows = "\n".join(
        f"""
    <li class="decision d-{esc(SEVERITY_STYLE.get(a.severity, ('info', 'Note'))[0])}">
      <span class="sev">{esc(SEVERITY_STYLE.get(a.severity, ('info', 'Note'))[1])}</span>
      <div class="decision-body">
        <p class="decision-title">{esc(a.title)}</p>
        <p class="decision-detail">{esc(a.detail)}</p>
      </div>
    </li>"""
        for a in alerts
    )
    return f"""
<section class="panel">
  <h2>Needs a decision <span class="tally">{len(alerts)}</span></h2>
  <ol class="decisions">{rows}
  </ol>
</section>"""


# --- 3. how to read these numbers -----------------------------------------


def _trust_panel(insights: Insights) -> str:
    """What to check before trusting the figures below.

    Silent when every column was read off a heading that said what it was —
    which is the point. A caption that appears on every report is one nobody
    reads by the third report, so this only appears when it has something to
    say, and then it says exactly which column and exactly why.
    """
    concerns = trust.concerns(insights.tables)
    warnings = list(insights.warnings)
    if not concerns and not warnings:
        return ""

    items = "".join(f"<li>{esc(c)}</li>" for c in concerns)
    warned = "".join(f"<li>{esc(w)}</li>" for w in warnings)
    # The wording has to match what is actually listed. A file whose only note
    # is a skipped sheet was labelled fine, and telling its owner otherwise is
    # the sort of small inaccuracy that costs the whole document its authority.
    if concerns:
        lede = ("Your file did not label everything, so Vyuha worked some of it "
                "out. Every figure below resting on one of these carries a small "
                "mark. Check these against your own file before acting on a number.")
        head = "How to read these numbers"
    else:
        lede = ("Nothing was guessed &mdash; every figure below came from a column "
                "your file labelled. These are worth knowing all the same.")
        head = "Worth knowing about this file"
    return f"""
<section class="panel caution">
  <h2>{head}</h2>
  <p class="lede">{lede}</p>
  <ul class="checks">{warned}{items}</ul>
</section>"""


# --- 4. the headline figures ----------------------------------------------


def _figures(insights: Insights) -> str:
    tiles: list[str] = []
    sales, stock, rec = insights.sales, insights.stock, insights.receivables
    tables = insights.tables

    revenue_basis = trust.basis(tables, "Revenue", schema.AMOUNT)
    stock_basis = trust.basis(tables, "Stock", schema.STOCK_QTY, schema.RATE)
    rec_basis = trust.basis(tables, "Outstanding", schema.OUTSTANDING)

    if sales.get("revenue") is not None:
        tiles.append(_figure("Revenue", money_short(sales["revenue"]),
                             _trend_note(sales), revenue_basis))
    if sales.get("orders"):
        tiles.append(_figure("Orders", num(sales["orders"]),
                             f"Avg {money_short(sales.get('avg_order_value', 0))}",
                             revenue_basis))
    if sales.get("party_count"):
        share = sales.get("top3_share")
        note = f"Top 3 = {share:.0%} of revenue" if share else "Active customers"
        tiles.append(_figure("Customers", num(sales["party_count"]), note,
                             trust.basis(tables, "Customers", schema.PARTY)))
    if stock.get("value") is not None:
        tiles.append(_figure("Stock value", money_short(stock["value"]),
                             f"{num(stock.get('skus', 0))} SKUs", stock_basis))
    elif stock.get("skus"):
        tiles.append(_figure("SKUs tracked", num(stock["skus"]),
                             f"{num(stock.get('units', 0))} units on hand", stock_basis))
    if stock.get("below_reorder_count") is not None:
        tiles.append(_figure("Below reorder", num(stock["below_reorder_count"]),
                             "Raise a purchase order",
                             trust.basis(tables, "Reorder", schema.STOCK_QTY,
                                         schema.REORDER_LEVEL),
                             alarm=stock["below_reorder_count"] > 0))
    if stock.get("dead_stock_value"):
        tiles.append(_figure("Cash in dead stock", money_short(stock["dead_stock_value"]),
                             f"{num(stock.get('dead_stock_count', 0))} SKUs idle 90+ days",
                             stock_basis, alarm=True))
    if rec.get("total") is not None:
        tiles.append(_figure("Outstanding", money_short(rec["total"]),
                             f"{num(rec.get('invoices', 0))} open invoices", rec_basis))
    if rec.get("overdue_total"):
        tiles.append(_figure("Overdue", money_short(rec["overdue_total"]),
                             f"{num(rec.get('overdue_count', 0))} invoices past due",
                             rec_basis, alarm=True))

    if not tiles:
        return ""
    return f'<section class="figures">{"".join(tiles)}</section>'


def _figure(label: str, value: str, note: str, basis: trust.Basis,
            alarm: bool = False) -> str:
    chip = ""
    if basis.worst in CHIP_ON_FIGURE:
        word, tone = BASIS_CHIP.get(basis.worst, ("", ""))
        if word:
            chip = f'<span class="chip {tone}">{esc(word)}</span>'
    return f"""
  <div class="figure{' figure-alarm' if alarm else ''}">
    <span class="figure-label">{esc(label)}</span>
    <span class="figure-value">{value}{chip}</span>
    <span class="figure-note">{note}</span>
  </div>"""


def _trend_note(sales: dict) -> str:
    change = sales.get("mom_change")
    if change is None:
        return f"{num(sales.get('lines', 0))} line items"
    arrow = "&uarr;" if change >= 0 else "&darr;"
    tone = "up" if change >= 0 else "down"
    return (f'<span class="trend {tone}">{arrow} {abs(change):.0%}</span> '
            f"vs {esc(sales.get('mom_from', 'last month'))}")


# --- 5. the sections ------------------------------------------------------


def _sales_section(insights: Insights) -> str:
    sales = insights.sales
    if not sales.get("revenue"):
        return ""

    blocks = [_monthly_chart(sales.get("monthly") or [])]

    if sales.get("top_parties"):
        blocks.append(_table(
            "Top customers", ["Customer", "Revenue", "Share", "Orders"],
            [[esc(r["label"]), money(r["amount"]), _share_bar(r["share"]),
              num(r["lines"])] for r in sales["top_parties"]],
            numeric={1, 3}))
    if sales.get("top_items"):
        blocks.append(_table(
            "Top products", ["Product", "Revenue", "Share", "Lines"],
            [[esc(r["label"]), money(r["amount"]), _share_bar(r["share"]),
              num(r["lines"])] for r in sales["top_items"]],
            numeric={1, 3}))
    if sales.get("top_categories"):
        blocks.append(_table(
            "By category", ["Category", "Revenue", "Share"],
            [[esc(r["label"]), money(r["amount"]), _share_bar(r["share"])]
             for r in sales["top_categories"]],
            numeric={1}))

    return _section("Sales", insights, schema.AMOUNT, blocks)


def _stock_section(insights: Insights) -> str:
    stock = insights.stock
    if not stock.get("skus"):
        return ""

    blocks: list[str] = []
    if stock.get("below_reorder"):
        blocks.append(_table(
            "Reorder now", ["Item", "On hand", "Reorder level", "Short by"],
            [[esc(r["label"]), num(r["qty"]), num(r.get("reorder_level")),
              f'<span class="tone-crit">{num(r.get("shortfall"))}</span>']
             for r in stock["below_reorder"]],
            numeric={1, 2, 3}))
    if stock.get("cover"):
        blocks.append(_table(
            "Days of cover, at the current run rate",
            ["Item", "On hand", "Sells/day", "Days left"],
            [[esc(r["label"]), num(r["qty"]), f"{r['daily_run_rate']:g}",
              _days_pill(r["days_cover"])] for r in stock["cover"]],
            numeric={1, 2, 3}))
    if stock.get("dead_stock"):
        blocks.append(_table(
            f"Dead stock — nothing sold in 90+ days "
            f"({num(stock.get('dead_stock_count', 0))} SKUs)",
            ["Item", "Qty", "Value locked", "Last sold"],
            [[esc(r["label"]), num(r["qty"]),
              money(r["value"]) if r.get("value") else "—",
              esc(r.get("last_sold") or "never in this file")]
             for r in stock["dead_stock"]],
            numeric={1, 2}))
    if stock.get("top_value"):
        blocks.append(_table(
            "Where the stock money sits", ["Item", "Qty", "Value"],
            [[esc(r["label"]), num(r["qty"]), money(r["value"])]
             for r in stock["top_value"]],
            numeric={1, 2}))

    if not blocks:
        return ""
    return _section("Stock", insights, schema.STOCK_QTY, blocks)


def _receivables_section(insights: Insights) -> str:
    rec = insights.receivables
    if not rec.get("total"):
        return ""

    blocks: list[str] = []
    if rec.get("ageing"):
        blocks.append(_ageing_chart(rec["ageing"], rec.get("ageing_basis")))
    if rec.get("top_debtors"):
        blocks.append(_table(
            "Who owes the most", ["Customer", "Outstanding", "Share", "Invoices"],
            [[esc(r["label"]), money(r["amount"]), _share_bar(r["share"]),
              num(r["lines"])] for r in rec["top_debtors"]],
            numeric={1, 3}))
    if rec.get("worst_overdue"):
        blocks.append(_table(
            "Chase these first", ["Customer", "Invoice", "Amount", "Days overdue"],
            [[esc(r["party"]), esc(r.get("invoice") or "—"), money(r["amount"]),
              _days_overdue_pill(r.get("days"))] for r in rec["worst_overdue"]],
            numeric={2, 3}))

    return _section("Receivables", insights, schema.OUTSTANDING, blocks)


# --- 6. what was read -----------------------------------------------------


def _readback(insights: Insights) -> str:
    """Sheet by sheet, what Vyuha made of the file (ADR 004).

    Kept last because it answers a question somebody only asks once they doubt a
    number — but every column now carries how it was identified, so the doubt
    can be settled here rather than by opening the spreadsheet.
    """
    rows: list[str] = []
    for table in insights.tables:
        conf = getattr(table, "field_confidence", {}) or {}
        derived = getattr(table, "derived", set()) or set()
        marks = []
        for name in table.frame.columns:
            if name not in schema.LABELS:
                continue
            v = trust.verdict(conf.get(name, 0.0), derived=name in derived)
            label = esc(schema.LABELS.get(name, name))
            if v == trust.READ:
                marks.append(f'<span class="col">{label}</span>')
            else:
                word = BASIS_CHIP.get(v, ("", "chip-soft"))[0]
                marks.append(f'<span class="col col-{esc(v)}">{label}'
                             f'<em>{esc(word)}</em></span>')
        ignored = ""
        if table.unmapped:
            shown = ", ".join(str(c) for c in table.unmapped[:6])
            more = f" +{len(table.unmapped) - 6} more" if len(table.unmapped) > 6 else ""
            ignored = f'<p class="ignored">Ignored: {esc(shown)}{esc(more)}</p>'
        fixes = " ".join(table.issues) or "No repairs needed."
        rows.append(f"""
      <tr>
        <td><strong>{esc(table.sheet)}</strong>
          <p class='row-sub'>header on row {table.header_row}</p></td>
        <td><span class="kindpill kind-{esc(table.kind)}">{esc(
            schema.TABLE_LABELS.get(table.kind, table.kind))}</span></td>
        <td class="num">{num(table.rows_out)}</td>
        <td class="cols">{''.join(marks) or '&mdash;'}{ignored}</td>
        <td class="fixes">{esc(fixes)}</td>
      </tr>""")

    return f"""
<section class="panel readback">
  <h2>What Vyuha read from your file</h2>
  <p class="lede">Every column below, and how it was identified. A column marked
    <em>guessed</em> or <em>calculated</em> had no heading saying what it was.</p>
  <div class="scroll">
    <table>
      <thead><tr>
        <th>Sheet</th><th>Read as</th><th class="num">Rows used</th>
        <th>Columns understood</th><th>Repairs</th>
      </tr></thead>
      <tbody>{''.join(rows)}</tbody>
    </table>
  </div>
  <p class="source">Source file: {esc(insights.source)}</p>
</section>"""


# --- building blocks ------------------------------------------------------


def _section(title: str, insights: Insights, key_field: str,
             blocks: list[str]) -> str:
    """A titled band, captioned when the figures under it rest on a guess."""
    inner = "\n".join(b for b in blocks if b)
    if not inner:
        return ""
    basis = trust.basis(insights.tables, title, key_field)
    caption = "" if basis.worst not in CHIP_ON_FIGURE else (
        f'<p class="band-caution">{esc(basis.note)}</p>')
    return f"""
<section class="band">
  <div class="band-head">
    <h2>{esc(title)}</h2>
    <span class="band-rule"></span>
  </div>
  {caption}
  {inner}
</section>"""


def _table(title: str, headers: list[str], rows: list[list[str]],
           numeric: set[int]) -> str:
    if not rows:
        return ""
    head = "".join(
        f"<th class='{'num' if i in numeric else ''}'>{esc(h)}</th>"
        for i, h in enumerate(headers))
    body = "".join(
        "<tr>" + "".join(
            f"<td class='{'num' if i in numeric else ''}'>{cell}</td>"
            for i, cell in enumerate(row)) + "</tr>"
        for row in rows)
    return f"""
  <div class="block">
    <h3>{esc(title)}</h3>
    <div class="scroll">
      <table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>
    </div>
  </div>"""


def _monthly_chart(monthly: list[dict]) -> str:
    if len(monthly) < 2:
        return ""
    peak = max(m["amount"] for m in monthly) or 1
    bars = "".join(f"""
      <div class="col">
        <span class="col-value">{money_short(m['amount'])}</span>
        <span class="col-bar{' col-partial' if m.get('partial') else ''}"
              style="height:{max(m['amount'] / peak * 100, 1.5):.1f}%"></span>
        <span class="col-label">{esc(m['label'])}{'*' if m.get('partial') else ''}</span>
      </div>""" for m in monthly[-14:])
    note = ("<p class='foot-note'>* A part-month. The file ends mid-month, so this "
            "bar is not comparable to the others and is left out of the trend.</p>"
            if any(m.get("partial") for m in monthly[-14:]) else "")
    return f"""
  <div class="block">
    <h3>Revenue by month</h3>
    <div class="scroll"><div class="chart">{bars}</div></div>
    {note}
  </div>"""


def _ageing_chart(buckets: list[dict], basis: str | None) -> str:
    total = sum(b["amount"] for b in buckets) or 1
    rows = "".join(f"""
      <div class="age-row">
        <span class="age-label">{esc(b['label'])}</span>
        <span class="age-track">
          <span class="age-fill age-{i}"
                style="width:{b['amount'] / total * 100:.1f}%"></span>
        </span>
        <span class="age-amount">{money(b['amount'])}</span>
        <span class="age-count">{num(b['count'])} inv</span>
      </div>""" for i, b in enumerate(buckets))
    note = (f"<p class='foot-note'>Aged by {esc(basis)}.</p>" if basis else "")
    return f"""
  <div class="block">
    <h3>Ageing</h3>
    <div class="ageing">{rows}</div>
    {note}
  </div>"""


def _share_bar(share: float) -> str:
    pct = max(min(share, 1.0), 0.0) * 100
    return (f'<span class="share"><span class="share-track">'
            f'<span class="share-fill" style="width:{pct:.1f}%"></span>'
            f'</span><span class="share-num">{pct:.0f}%</span></span>')


def _days_pill(days: float) -> str:
    tone = "crit" if days <= 7 else ("warn" if days <= 14 else "good")
    return f'<span class="tone-{tone}">{days:g} d</span>'


def _days_overdue_pill(days: int | None) -> str:
    if days is None:
        return "—"
    tone = "crit" if days > 60 else ("warn" if days > 30 else "plain")
    return f'<span class="tone-{tone}">{days} d</span>'


# --- formatting -----------------------------------------------------------


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def money(amount: float | None) -> str:
    """Full rupee amount in Indian digit grouping: &#8377;12,34,567 (HTML)."""
    return fmt.rupees(amount, symbol=fmt.RUPEE_HTML, dash="—")


def money_short(amount: float | None) -> str:
    """Abbreviated rupee amount for HTML: &#8377;2.10 L."""
    return fmt.rupees_short(amount, symbol=fmt.RUPEE_HTML, dash="—")


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
  --paper:#FBFAF9; --card:#FFFFFF; --sunk:#F5F3EF;
  --ink:#15171C; --ink-2:#4C525F; --ink-3:#878D9B;
  --rule:#E5E2DC; --rule-2:#F0EEE9;
  --accent:#1F3B63;
  --crit:#A32017; --warn:#8A5300; --good:#186B47;
  --crit-bg:#FAEDEB; --warn-bg:#FAF3E4; --good-bg:#EBF4EF;
  --bar:#2F5484; --bar-soft:#9FB4CE;
  --sans:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;
  --mono:ui-monospace,SFMono-Regular,"SF Mono","Cascadia Mono",Consolas,"Liberation Mono",monospace;
}
@media (prefers-color-scheme:dark){
  :root{
    --paper:#101216; --card:#181B21; --sunk:#1E222A;
    --ink:#ECEEF3; --ink-2:#A6ACBA; --ink-3:#757C8B;
    --rule:#282C35; --rule-2:#1F232B;
    --accent:#8FB0E2;
    --crit:#FF8E82; --warn:#E8B961; --good:#63D2A0;
    --crit-bg:#2B1B19; --warn-bg:#27210F; --good-bg:#15241D;
    --bar:#5E88C4; --bar-soft:#3A4C68;
  }
}
*{box-sizing:border-box;margin:0;padding:0}
body{
  background:var(--paper); color:var(--ink); font-family:var(--sans);
  font-size:15px; line-height:1.55; padding:clamp(14px,3vw,44px);
  -webkit-font-smoothing:antialiased; -webkit-text-size-adjust:100%;
}
.sheet{max-width:900px;margin:0 auto;display:flex;flex-direction:column;gap:22px}

/* --- masthead --- */
.masthead{padding-bottom:22px;border-bottom:2px solid var(--ink)}
.mark{font-size:11px;letter-spacing:.4em;font-weight:800;color:var(--accent)}
.masthead h1{font-size:clamp(26px,4.4vw,38px);line-height:1.12;letter-spacing:-.021em;
  margin:9px 0 12px;font-weight:750;text-wrap:balance}
.verdict{font-size:16px;line-height:1.5;color:var(--ink-2);max-width:60ch}
.verdict strong{color:var(--ink);font-weight:650}
.meta{margin-top:13px;display:flex;flex-wrap:wrap;gap:8px}
.meta-item{font-family:var(--mono);font-size:11.5px;color:var(--ink-3);
  padding:3px 9px;border:1px solid var(--rule);border-radius:4px;white-space:nowrap}

/* --- panels --- */
.panel{background:var(--card);border:1px solid var(--rule);border-radius:10px;
  padding:clamp(16px,2.4vw,24px)}
.panel h2{font-size:17px;letter-spacing:-.012em;font-weight:700;margin-bottom:6px}
.lede{color:var(--ink-2);font-size:13.5px;max-width:68ch;margin-bottom:14px}
.settled h2{color:var(--good)}
.settled{background:var(--good-bg);border-color:transparent}
.settled .lede{margin-bottom:0}
.tally{display:inline-block;min-width:22px;text-align:center;padding:1px 8px;
  border-radius:99px;background:var(--crit);color:#fff;font-size:12px;
  font-family:var(--mono);vertical-align:2px;margin-left:5px;font-weight:600}

/* --- decisions --- */
.decisions{list-style:none;display:flex;flex-direction:column;gap:1px;
  background:var(--rule-2);border-radius:8px;overflow:hidden;margin-top:14px}
.decision{display:flex;gap:14px;align-items:flex-start;padding:14px 16px;
  background:var(--card);border-left:3px solid var(--ink-3)}
.decision-title{font-weight:650;font-size:14.5px;letter-spacing:-.006em}
.decision-detail{color:var(--ink-2);font-size:13px;margin-top:3px}
.sev{flex:none;width:62px;font-size:10px;font-weight:800;letter-spacing:.08em;
  text-transform:uppercase;padding:4px 0;color:var(--ink-3)}
.d-crit{border-left-color:var(--crit)} .d-crit .sev{color:var(--crit)}
.d-warn{border-left-color:var(--warn)} .d-warn .sev{color:var(--warn)}
.d-info{border-left-color:var(--accent)} .d-info .sev{color:var(--accent)}

/* --- how to read these numbers --- */
.caution{background:var(--warn-bg);border-color:transparent}
.caution h2{color:var(--warn)}
.checks{list-style:none;display:flex;flex-direction:column;gap:8px}
.checks li{font-size:13.5px;color:var(--ink);padding-left:20px;position:relative;
  line-height:1.5}
.checks li::before{content:"";position:absolute;left:4px;top:8px;width:6px;height:6px;
  border-radius:50%;background:var(--warn)}

/* --- figures --- */
.figures{display:grid;gap:11px;grid-template-columns:repeat(auto-fit,minmax(178px,1fr))}
.figure{background:var(--card);border:1px solid var(--rule);border-radius:9px;
  padding:15px 16px;display:flex;flex-direction:column;gap:5px}
.figure-alarm{border-color:var(--crit);background:var(--crit-bg)}
.figure-label{font-size:10.5px;letter-spacing:.1em;text-transform:uppercase;
  color:var(--ink-3);font-weight:750}
.figure-value{font-family:var(--mono);font-size:clamp(21px,2.9vw,27px);font-weight:600;
  letter-spacing:-.02em;font-variant-numeric:tabular-nums;line-height:1.15;
  display:flex;align-items:baseline;flex-wrap:wrap;gap:7px}
.figure-note{font-size:12px;color:var(--ink-3)}
.figure-alarm .figure-note{color:var(--crit)}
.trend{font-family:var(--mono);font-weight:600}
.trend.up{color:var(--good)} .trend.down{color:var(--crit)}
.chip{font-family:var(--sans);font-size:9.5px;font-weight:800;letter-spacing:.07em;
  text-transform:uppercase;padding:3px 6px;border-radius:4px;white-space:nowrap}
.chip-warn{background:var(--warn-bg);color:var(--warn);
  box-shadow:inset 0 0 0 1px var(--warn)}
.chip-soft{background:var(--sunk);color:var(--ink-3)}

/* --- bands --- */
.band{display:flex;flex-direction:column;gap:11px}
.band-head{display:flex;align-items:center;gap:14px}
.band-head h2{font-size:12px;letter-spacing:.26em;text-transform:uppercase;
  font-weight:800;color:var(--accent);white-space:nowrap}
.band-rule{flex:1;height:1px;background:var(--rule)}
.band-caution{font-size:12.5px;color:var(--warn);margin-top:-2px}
.block{background:var(--card);border:1px solid var(--rule);border-radius:10px;
  padding:clamp(15px,2.2vw,21px)}
.block h3{font-size:14px;font-weight:700;letter-spacing:-.008em;margin-bottom:13px}

/* --- tables --- */
.scroll{overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:13.5px;min-width:440px}
th{text-align:left;font-size:10px;letter-spacing:.09em;text-transform:uppercase;
  color:var(--ink-3);padding:0 11px 9px;font-weight:750;white-space:nowrap}
td{padding:10px 11px;border-top:1px solid var(--rule-2);vertical-align:top}
tbody tr:hover{background:var(--sunk)}
.num{text-align:right;font-family:var(--mono);font-variant-numeric:tabular-nums;
  white-space:nowrap}
th.num{font-family:var(--sans)}
.tone-crit{color:var(--crit);font-weight:600}
.tone-warn{color:var(--warn);font-weight:600}
.tone-good{color:var(--good)}
.tone-plain{color:var(--ink-2)}

/* --- share bars --- */
.share{display:flex;align-items:center;gap:8px;min-width:104px}
.share-track{flex:1;height:5px;border-radius:99px;background:var(--sunk);overflow:hidden}
.share-fill{display:block;height:100%;border-radius:99px;background:var(--bar)}
.share-num{font-family:var(--mono);font-size:11.5px;color:var(--ink-3);width:32px;
  text-align:right;font-variant-numeric:tabular-nums}

/* --- monthly chart --- */
.chart{display:flex;align-items:flex-end;gap:9px;height:200px;padding-top:20px;
  min-width:420px;border-bottom:1px solid var(--rule)}
.col{flex:1;min-width:44px;display:flex;flex-direction:column;justify-content:flex-end;
  align-items:center;height:100%;gap:5px}
.col-value{font-family:var(--mono);font-size:10.5px;color:var(--ink-3);
  white-space:nowrap;font-variant-numeric:tabular-nums}
.col-bar{width:100%;max-width:46px;border-radius:3px 3px 0 0;background:var(--bar)}
.col-partial{background:repeating-linear-gradient(135deg,var(--bar-soft) 0 5px,
  transparent 5px 10px);box-shadow:inset 0 0 0 1px var(--bar-soft)}
.col-label{font-size:10.5px;color:var(--ink-3);white-space:nowrap;
  padding-bottom:2px;font-family:var(--mono)}
.foot-note{font-size:11.5px;color:var(--ink-3);margin-top:11px;line-height:1.45}

/* --- ageing --- */
.ageing{display:flex;flex-direction:column;gap:9px}
.age-row{display:grid;grid-template-columns:92px 1fr 104px 58px;gap:11px;
  align-items:center;font-size:12.5px}
.age-track{height:9px;border-radius:99px;background:var(--sunk);overflow:hidden}
.age-fill{display:block;height:100%;border-radius:99px;min-width:2px;background:var(--bar)}
.age-0{background:var(--good)} .age-1{background:var(--bar)}
.age-2{background:var(--bar-soft)} .age-3{background:var(--warn)}
.age-4{background:var(--crit)} .age-5{background:var(--crit)}
.age-amount{text-align:right;font-family:var(--mono);font-variant-numeric:tabular-nums}
.age-count{text-align:right;color:var(--ink-3);font-size:11.5px;font-family:var(--mono)}

/* --- read-back --- */
.readback td{vertical-align:top}
.row-sub{font-size:11px;color:var(--ink-3);font-family:var(--mono);margin-top:2px}
.kindpill{font-size:10.5px;font-weight:750;letter-spacing:.05em;text-transform:uppercase;
  padding:3px 8px;border-radius:4px;background:var(--sunk);color:var(--ink-2);
  white-space:nowrap}
.cols{max-width:340px}
.col-guessed,.col-derived,.col-matched{}
.cols .col{display:inline-flex;align-items:baseline;gap:4px;font-size:12px;
  padding:2px 7px;margin:0 4px 4px 0;border-radius:4px;background:var(--sunk);
  color:var(--ink-2);height:auto;min-width:0;flex:none;white-space:nowrap}
.cols .col em{font-style:normal;font-size:9.5px;font-weight:800;letter-spacing:.05em;
  text-transform:uppercase;color:var(--warn)}
.cols .col-guessed,.cols .col-derived{background:var(--warn-bg);color:var(--ink)}
.ignored{font-size:11.5px;color:var(--ink-3);margin-top:6px;line-height:1.45}
.fixes{font-size:12px;color:var(--ink-2);max-width:280px}
.source{font-family:var(--mono);font-size:11.5px;color:var(--ink-3);margin-top:14px}

/* --- foot --- */
.foot{text-align:center;color:var(--ink-3);font-size:11.5px;padding:6px 0 4px;
  border-top:1px solid var(--rule);margin-top:4px}
.foot b{color:var(--accent);letter-spacing:.28em;font-weight:800}

@media (max-width:620px){
  .age-row{grid-template-columns:74px 1fr 88px}
  .age-count{display:none}
  .sev{width:auto;min-width:52px}
  table{font-size:12.5px}
  .cols,.fixes{max-width:none}
}
@media print{
  :root{
    --paper:#fff; --card:#fff; --sunk:#F4F4F4; --ink:#000; --ink-2:#333;
    --ink-3:#666; --rule:#CCC; --rule-2:#E4E4E4;
  }
  body{padding:0;font-size:11.5px}
  .panel,.block,.figure{break-inside:avoid;border-color:#CCC}
  .band,.decision{break-inside:avoid}
  .caution,.settled{border:1px solid #CCC}
  tbody tr:hover{background:transparent}
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
<div class="sheet">
{body}
<p class="foot">Built by <b>VYUHA</b> &mdash; read from your own file, automatically.</p>
</div>
</body>
</html>
"""
