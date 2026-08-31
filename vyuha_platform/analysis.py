"""Querying the books along any dimension.

The old agent handed Claude a fixed summary and hoped the question fitted it.
Anything outside the eight anticipated shapes — "which item has the worst margin
at Hubballi since June" — could not be answered, because the number was not in
the summary and nothing could go and fetch it.

This module is what the model calls instead. One general query function does the
work of thirty specific ones: group by any dimension, filter on any combination,
aggregate any measure. The model chooses *which* question to ask of the data;
every figure in the answer is still computed here, in Python, so it can be
checked against the books by hand.

Two properties matter more than the feature list.

**Nothing here calls a model.** These are ordinary functions over ``Book`` and
``money.Ledger``. The same call from a route, a test, or a tool loop returns the
same numbers, and a wrong answer is a bug in arithmetic rather than something
that has to be re-prompted out of a model.

**Every result is JSON-safe and small.** A tool result goes back into the
conversation and is paid for by the token, so lists are capped and rounded. A
query that would return four hundred rows returns the top slice and says how
many it left out, rather than quietly truncating.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta

#: What a sales query can group by, and how to get that key off a sale.
DIMENSIONS: dict[str, str] = {
    "party": "who bought it",
    "item": "what was sold",
    "sku": "item code",
    "month": "calendar month",
    "branch": "which branch rang it up",
    "category": "item category",
    "day": "calendar day",
}

#: What a sales query can measure.
MEASURES = ("revenue", "qty", "bills", "margin", "avg_bill", "customers")


def _month(iso: str) -> str:
    return iso[:7] if iso and len(iso) >= 7 else ""


def _days_ago(n: int) -> str:
    return (date.today() - timedelta(days=n)).isoformat()


def _label_month(key: str) -> str:
    try:
        return datetime.strptime(key, "%Y-%m").strftime("%b %Y")
    except ValueError:
        return key


def _in_window(iso: str, since: str, until: str) -> bool:
    if not iso:
        return False
    d = iso[:10]
    if since and d < since:
        return False
    if until and d > until:
        return False
    return True


def _matches(value: str, wanted: str) -> bool:
    """Loose match — the model will say "Ramu" for "Ramu Stores"."""
    if not wanted:
        return True
    return wanted.strip().lower() in (value or "").strip().lower()


# ------------------------------------------------------------------ the query

def query_sales(book, org=None, group_by: str = "item", measure: str = "revenue",
                since: str = "", until: str = "", party: str = "", item: str = "",
                branch: str = "", category: str = "", unpaid_only: bool = False,
                top_n: int = 10, ascending: bool = False) -> dict:
    """Group, filter and aggregate sales along any dimension.

    This one function is the reason the agent can answer questions nobody
    anticipated. ``ascending=True`` is not a detail — "which item sells worst"
    is asked as often as "which sells best", and without it the model has to
    fetch everything and sort in its head, which is exactly the arithmetic it
    should not be doing.
    """
    group_by = group_by if group_by in DIMENSIONS else "item"
    measure = measure if measure in MEASURES else "revenue"
    by_sku = {i.sku: i for i in book.items}

    buckets: dict[str, dict] = defaultdict(
        lambda: {"revenue": 0.0, "qty": 0.0, "bills": 0, "cost": 0.0,
                 "parties": set(), "unpaid": 0.0})
    matched = 0

    for sale in book.sales:
        if not _in_window(sale.date, since, until):
            continue
        if unpaid_only and sale.paid:
            continue
        if not _matches(sale.party, party):
            continue
        if item and not (_matches(sale.item, item) or _matches(sale.sku, item)):
            continue
        stock_item = by_sku.get(sale.sku)
        if category and not _matches(getattr(stock_item, "category", ""), category):
            continue
        if branch:
            name = org.name_of(sale.branch) if org is not None else sale.branch
            if not (_matches(name, branch) or _matches(sale.branch, branch)):
                continue

        if group_by == "party":
            key = sale.party or "Cash sale"
        elif group_by == "item":
            key = sale.item or sale.sku
        elif group_by == "sku":
            key = sale.sku
        elif group_by == "month":
            key = _label_month(_month(sale.date))
        elif group_by == "day":
            key = sale.date[:10]
        elif group_by == "branch":
            key = (org.name_of(sale.branch) if org is not None and sale.branch
                   else (sale.branch or "Unassigned"))
        else:
            key = getattr(stock_item, "category", "") or "Uncategorised"

        b = buckets[key]
        b["revenue"] += sale.amount
        b["qty"] += sale.qty
        b["bills"] += 1
        if sale.party:
            b["parties"].add(sale.party.strip().lower())
        if not sale.paid:
            b["unpaid"] += sale.amount
        if stock_item is not None and stock_item.cost:
            b["cost"] += stock_item.cost * sale.qty
        matched += 1

    rows = []
    for key, b in buckets.items():
        margin = b["revenue"] - b["cost"] if b["cost"] else 0.0
        rows.append({
            "group": key,
            "revenue": round(b["revenue"]),
            "qty": round(b["qty"], 2),
            "bills": b["bills"],
            "margin": round(margin),
            "margin_pct": round(margin / b["revenue"] * 100, 1) if b["revenue"] and b["cost"] else None,
            "avg_bill": round(b["revenue"] / b["bills"]) if b["bills"] else 0,
            "customers": len(b["parties"]),
            "unpaid": round(b["unpaid"]),
        })

    rows.sort(key=lambda r: (r.get(measure) if r.get(measure) is not None else 0),
              reverse=not ascending)
    total = sum(r["revenue"] for r in rows)

    out = {
        "grouped_by": group_by,
        "measure": measure,
        "rows": rows[:max(1, min(top_n, 50))],
        "groups_found": len(rows),
        "sales_matched": matched,
        "total_revenue": round(total),
    }
    if len(rows) > top_n:
        out["note"] = f"{len(rows) - top_n} more group(s) not shown."
    if matched == 0:
        out["note"] = "No sales matched those filters."
    return out


# ------------------------------------------------------------------ stock

def stock_report(book, state: str = "all", sort: str = "value",
                 category: str = "", top_n: int = 15) -> dict:
    """What is on the shelf, filtered by how worried to be about it."""
    sold = defaultdict(float)
    last_sold: dict[str, str] = {}
    for sale in book.sales:
        sold[sale.sku] += sale.qty
        if sale.date > last_sold.get(sale.sku, ""):
            last_sold[sale.sku] = sale.date

    rows = []
    for i in book.items:
        if category and not _matches(i.category, category):
            continue
        moved = sold.get(i.sku, 0.0)
        idle = 0
        if last_sold.get(i.sku):
            try:
                idle = (date.today() - date.fromisoformat(last_sold[i.sku][:10])).days
            except ValueError:
                idle = 0
        row = {
            "item": i.name, "sku": i.sku, "category": i.category,
            "in_stock": i.stock_qty, "unit": i.unit,
            "reorder_at": i.reorder_level, "rate": i.rate, "cost": i.cost,
            "value": round(i.value), "sold_total": round(moved, 2),
            "days_since_last_sale": idle if moved else None,
            "low": i.low, "out": i.stock_qty <= 0, "never_sold": moved == 0,
        }
        if state == "low" and not i.low:
            continue
        if state == "out" and i.stock_qty > 0:
            continue
        if state == "dead" and moved > 0:
            continue
        if state == "moving" and moved == 0:
            continue
        rows.append(row)

    keys = {"value": "value", "stock": "in_stock", "sold": "sold_total",
            "idle": "days_since_last_sale"}
    key = keys.get(sort, "value")
    rows.sort(key=lambda r: (r.get(key) or 0), reverse=True)

    return {
        "state": state,
        "rows": rows[:max(1, min(top_n, 50))],
        "items_matched": len(rows),
        "total_value": round(sum(r["value"] for r in rows)),
    }


# --------------------------------------------------------------- one party

def customer_detail(book, party: str, top_n: int = 12) -> dict:
    """Everything about one customer — the question a shop owner asks most."""
    sales = [s for s in book.sales if _matches(s.party, party)]
    if not sales:
        names = sorted({s.party for s in book.sales if s.party})[:12]
        return {"found": False, "asked_for": party,
                "note": "No customer matched that name.",
                "known_customers": names}

    by_item = defaultdict(lambda: {"qty": 0.0, "revenue": 0.0, "bills": 0})
    for s in sales:
        row = by_item[s.item or s.sku]
        row["qty"] += s.qty
        row["revenue"] += s.amount
        row["bills"] += 1

    dates = sorted(s.date for s in sales if s.date)
    unpaid = [s for s in sales if not s.paid]
    phones = book.customer_phones()
    exact = sales[0].party

    return {
        "found": True,
        "party": exact,
        "phone": phones.get(exact.strip(), ""),
        "bills": len(sales),
        "total_spend": round(sum(s.amount for s in sales)),
        "still_owes": round(sum(s.amount for s in unpaid)),
        "first_bought": dates[0] if dates else "",
        "last_bought": dates[-1] if dates else "",
        "days_since_last": (date.today() - date.fromisoformat(dates[-1][:10])).days
                           if dates else None,
        "buys": sorted(({"item": k, "qty": round(v["qty"], 2),
                         "revenue": round(v["revenue"]), "bills": v["bills"]}
                        for k, v in by_item.items()),
                       key=lambda r: r["revenue"], reverse=True)[:top_n],
        "unpaid_bills": [{"bill": s.id, "date": s.date, "due": s.due_date,
                          "amount": round(s.amount)} for s in unpaid][:top_n],
    }


def item_detail(book, item: str, top_n: int = 12) -> dict:
    """One product: what it costs, what it earns, who buys it."""
    match = next((i for i in book.items
                  if _matches(i.name, item) or _matches(i.sku, item)), None)
    if match is None:
        return {"found": False, "asked_for": item,
                "known_items": [i.name for i in book.items][:15]}

    sales = [s for s in book.sales if s.sku == match.sku]
    revenue = sum(s.amount for s in sales)
    qty = sum(s.qty for s in sales)
    margin = (revenue - match.cost * qty) if match.cost else None

    by_party = defaultdict(float)
    for s in sales:
        by_party[s.party or "Cash sale"] += s.amount

    return {
        "found": True,
        "item": match.name, "sku": match.sku, "category": match.category,
        "in_stock": match.stock_qty, "unit": match.unit,
        "reorder_at": match.reorder_level, "below_reorder": match.low,
        "sells_at": match.rate, "costs": match.cost,
        "stock_value": round(match.value),
        "units_sold": round(qty, 2), "revenue": round(revenue),
        "margin": round(margin) if margin is not None else None,
        "margin_pct": round(margin / revenue * 100, 1) if margin and revenue else None,
        "bills": len(sales),
        "bought_by": sorted(({"party": k, "revenue": round(v)}
                             for k, v in by_party.items()),
                            key=lambda r: r["revenue"], reverse=True)[:top_n],
        "last_sold": max((s.date for s in sales), default=""),
    }


# ------------------------------------------------------------- comparison

def compare_windows(book, org=None, days: int = 30, measure: str = "revenue",
                    group_by: str = "item", top_n: int = 8) -> dict:
    """This window against the one before it — where a trend actually lives.

    An owner rarely wants a total; he wants to know what changed. Reporting both
    windows and the delta in one call saves the model two round trips and stops
    it subtracting two numbers itself.
    """
    now_since, now_until = _days_ago(days), date.today().isoformat()
    prev_since, prev_until = _days_ago(days * 2), _days_ago(days + 1)

    current = query_sales(book, org, group_by=group_by, measure=measure,
                          since=now_since, until=now_until, top_n=50)
    previous = query_sales(book, org, group_by=group_by, measure=measure,
                           since=prev_since, until=prev_until, top_n=50)

    before = {r["group"]: r for r in previous["rows"]}
    rows = []
    for r in current["rows"]:
        was = before.get(r["group"], {})
        old = was.get(measure) or 0
        new = r.get(measure) or 0
        rows.append({
            "group": r["group"], "now": new, "before": old,
            "change": round(new - old),
            "change_pct": round((new - old) / old * 100, 1) if old else None,
        })
    gone = [{"group": g, "now": 0, "before": row.get(measure) or 0,
             "change": -(row.get(measure) or 0), "change_pct": -100.0}
            for g, row in before.items()
            if g not in {r["group"] for r in current["rows"]}]

    rows.sort(key=lambda r: abs(r["change"]), reverse=True)
    return {
        "measure": measure,
        "window_days": days,
        "current": {"from": now_since, "to": now_until,
                    "total_revenue": current["total_revenue"]},
        "previous": {"from": prev_since, "to": prev_until,
                     "total_revenue": previous["total_revenue"]},
        "total_change": round(current["total_revenue"] - previous["total_revenue"]),
        "total_change_pct": round(
            (current["total_revenue"] - previous["total_revenue"])
            / previous["total_revenue"] * 100, 1) if previous["total_revenue"] else None,
        "biggest_movers": rows[:top_n],
        "stopped_buying": sorted(gone, key=lambda r: r["before"], reverse=True)[:5],
    }
