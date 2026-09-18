"""Analytics — any question of the numbers, and the documents made from them.

``analysis.query_sales`` is the same function the assistant calls, so a figure explored here
and one quoted in an answer come from one place.
"""

from __future__ import annotations

from ... import analysis, books, finance, money, people
from .. import charts


def _short(v: float) -> str:
    from ..templating import money_short
    return money_short(v)


def _clip(text: str, width: int = 11) -> str:
    """A chart label that fits under its column."""
    return text if len(text) <= width else text[: width - 1].rstrip() + "…"


#: What a measure is called on the page, and how it should be formatted.
MEASURES = {
    "revenue": ("Revenue", "money"), "qty": ("Quantity", "qty"),
    "bills": ("Bills", "count"), "margin": ("Margin", "money"),
    "avg_bill": ("Average bill", "money"), "customers": ("Customers", "count"),
}


def explore(client, account, request) -> dict:
    book, org = books.load(client.slug), people.load(client.slug)
    led = money.load(client.slug)
    q = request.query_params
    group = q.get("group", "item")
    group = group if group in analysis.DIMENSIONS else "item"
    measure = q.get("measure", "revenue")
    measure = measure if measure in MEASURES else "revenue"
    options = finance.periods(book, led)
    period = q.get("period", "all")
    if period not in {k for k, _l, _k in options}:
        period = "all"
    start, end, label = finance.resolve(period)
    party, item = q.get("party", "").strip(), q.get("item", "").strip()
    unpaid = q.get("unpaid", "") == "1"

    out = analysis.query_sales(book, org, group_by=group, measure=measure, since=start,
                               until=end, party=party, item=item, unpaid_only=unpaid,
                               top_n=25)
    rows = out["rows"]
    return {
        "dimensions": analysis.DIMENSIONS, "measures": MEASURES,
        "group": group, "measure": measure, "measure_label": MEASURES[measure][0],
        "measure_kind": MEASURES[measure][1],
        "periods": options, "period": period, "period_label": label,
        "party": party, "item": item, "unpaid": unpaid,
        "rows": rows, "out": out,
        # Eight columns, short labels: a dozen item names at this width collide into
        # something nobody can read, and the table below carries the rest anyway.
        "chart": charts.columns([r[measure] or 0 for r in rows[:8]],
                                [_clip(str(r["group"])) for r in rows[:8]],
                                fmt=(_short if MEASURES[measure][1] == "money"
                                     else lambda v: f"{v:,.0f}"),
                                label=f"{MEASURES[measure][0]} by {group}"),
    }


def ratios(client, account, request) -> dict:
    book, led = books.load(client.slug), money.load(client.slug)
    conc = finance.concentration(book, led)
    return {
        "ratios": finance.ratios(book, led),
        "concentration": conc,
        "heads": finance.expense_analysis(book, led),
        "break_even": finance.break_even(book, led),
        "risk_note": {
            "high": "One customer carries too much of this business. Losing them would hurt.",
            "watch": "Worth watching: a large share of revenue sits with one customer.",
            "spread": "Revenue is spread across customers — no single point of failure.",
        }[conc["risk"]],
    }


def documents(client, account, request) -> dict:
    run = client.latest
    return {"run": run if (run and run.status == "ok") else None}
