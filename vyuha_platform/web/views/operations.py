"""Operations — the daily work: record a sale, watch the shelf, pay suppliers, raise bills.

Figures come from ``books``, ``money``, ``people`` and ``invoice`` — the modules the classic
screens and the agent read — and every form posts to the handler the classic screens use,
so recording a sale from either is one code path.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from ... import books, invoice, money, people

#: Units offered when adding an item. The engine reads any unit; these are the common ones.
UNITS = ["piece", "bag", "kg", "litre", "packet", "box", "metre", "dozen", "bundle", "tonne"]

#: Names that mean a walk-in rather than a customer — the set ``today.py`` uses too. Their
#: sales are offered last for billing, after the customers who actually get invoices.
WALK_IN = {"", "cash sale", "cash", "walk-in", "walkin", "counter sale"}

#: The window days-of-cover is read over — the classic stock screen's rule
#: (``console._cover``), so the two can never show different cover for the same item.
COVER_WINDOW = 90


def _short(v: float) -> str:
    from ..templating import money_short
    return money_short(v)


def _n(count: int, word: str, plural: str = "") -> str:
    return f"{count} {word if count == 1 else (plural or word + 's')}"


# --------------------------------------------------------------------- record

def record(client, account, request) -> dict:
    book = books.load(client.slug)
    items = sorted(book.items, key=lambda i: i.name.lower())
    today_iso = date.today().isoformat()
    todays = sorted((s for s in book.sales if (s.date or "")[:10] == today_iso),
                    key=lambda s: s.id, reverse=True)
    return {
        "has_items": bool(items),
        "items": [{"sku": i.sku, "name": i.name, "unit": i.unit, "stock": i.stock_qty}
                  for i in items],
        "item_data": {i.sku: {"rate": i.rate, "unit": i.unit} for i in items},
        "phones": book.customer_phones(),
        "customers": [c for c in book.customers() if c],
        "today_sales": todays[:12],
        "today_bills": len(todays),
        "today_total": sum(s.amount for s in todays),
        "categories": sorted({i.category for i in book.items if i.category} | {"Other"}),
        "units": UNITS,
        "today_iso": today_iso,
    }


# ------------------------------------------------------------------ inventory

def _state(item, dead: set) -> str:
    """How worried to be: out, below reorder, never sold, or fine — in that order."""
    if item.stock_qty <= 0:
        return "out"
    if item.low:
        return "low"
    if item.sku in dead:
        return "dead"
    return "ok"


def inventory(client, account, request) -> dict:
    book, org = books.load(client.slug), people.load(client.slug)
    summary = books.summary(book)
    dead = {i.sku for i in summary["never_sold"]}
    cutoff = (date.today() - timedelta(days=COVER_WINDOW)).isoformat()
    moved: dict[str, float] = defaultdict(float)
    for s in book.sales:
        if (s.date or "") >= cutoff:
            moved[s.sku] += s.qty

    rank = {"out": 0, "low": 1, "dead": 2, "ok": 3}
    everything = []
    for i in book.items:
        per_day = moved.get(i.sku, 0.0) / COVER_WINDOW
        # The bar reads against the reorder level, not a capacity nobody records: the
        # question is "how close am I to needing to order".
        ceiling = max(i.reorder_level * 2, i.stock_qty, 1)
        everything.append({
            "sku": i.sku, "name": i.name, "category": i.category, "unit": i.unit,
            "stock": i.stock_qty, "reorder": i.reorder_level, "rate": i.rate, "cost": i.cost,
            "value": i.value, "state": _state(i, dead),
            "cover": (i.stock_qty / per_day) if per_day > 0 else None,
            "fill": round(max(min(i.stock_qty / ceiling * 100, 100), 0), 1),
            "mark": (round(min(i.reorder_level / ceiling * 100, 100), 1)
                     if i.reorder_level > 0 else None),
        })
    everything.sort(key=lambda r: (rank[r["state"]], -r["value"]))
    counts = {k: sum(1 for r in everything if r["state"] == k) for k in rank}
    counts["all"] = len(everything)
    show = request.query_params.get("show", "all")
    show = show if show in counts else "all"

    need = counts["out"] + counts["low"]
    locked = sum(i.value for i in summary["never_sold"])
    return {
        "stats": [
            {"label": "Stock value", "value": _short(summary["stock_value"]), "icon": "boxes",
             "sub": f"{_n(summary['items'], 'item')} on the shelf"},
            {"label": "Needs ordering", "value": str(need), "icon": "shopping-cart",
             "sub": "out, or below the reorder level", "tone": "warn" if need else ""},
            {"label": "Out of stock", "value": str(counts["out"]), "icon": "triangle-alert",
             "sub": "losing sales right now" if counts["out"] else "nothing is out",
             "tone": "bad" if counts["out"] else ""},
            {"label": "Never sold", "value": _short(locked), "icon": "package",
             "sub": f"{_n(len(summary['never_sold']), 'item')} sitting idle",
             "tone": "info" if locked else ""},
        ],
        "rows": everything if show == "all" else [r for r in everything if r["state"] == show],
        "show": show, "counts": counts,
        "all_items": sorted(everything, key=lambda r: r["name"].lower()),
        "branches": [b for b in org.branches if b.active],
    }


# ------------------------------------------------------------------ purchases

def purchases(client, account, request) -> dict:
    led, org = money.load(client.slug), people.load(client.slug)
    q = request.query_params.get("q", "").strip()
    show = request.query_params.get("show", "all")
    show = show if show in ("all", "due", "paid") else "all"

    rows = sorted(led.expenses, key=lambda e: (e.date or "", e.added_at), reverse=True)
    if show == "due":
        rows = [e for e in rows if not e.paid]
    elif show == "paid":
        rows = [e for e in rows if e.paid]
    if q:
        needle = q.lower()
        rows = [e for e in rows if needle in (e.party or "").lower()
                or needle in e.category.lower() or needle in (e.note or "").lower()]

    month = date.today().isoformat()[:7]
    this_month = [e for e in led.expenses if (e.date or "")[:7] == month]
    heads: dict[str, float] = defaultdict(float)
    for e in this_month:
        heads[e.category] += e.amount
    top = max(heads.items(), key=lambda kv: kv[1], default=None)
    owed = [e for e in led.expenses if not e.paid]
    late = [e for e in owed if e.overdue]
    branches = [b for b in org.branches if b.active]
    return {
        "stats": [
            {"label": "Paid out this month",
             "value": _short(sum(e.amount for e in this_month if e.paid)), "icon": "wallet",
             "sub": f"{_n(len(this_month), 'entry', 'entries')} this month"},
            {"label": "Bills to pay", "value": _short(led.to_pay), "icon": "receipt",
             "sub": f"{_n(len(owed), 'bill')} not paid yet", "tone": "warn" if owed else ""},
            {"label": "Overdue", "value": _short(sum(e.amount for e in late)),
             "icon": "triangle-alert",
             "sub": f"{_n(len(late), 'bill')} past the due date" if late else "nothing is late",
             "tone": "bad" if late else ""},
            {"label": "Biggest head this month", "value": top[0] if top else "—",
             "icon": "chart-column",
             "sub": _short(top[1]) if top else "nothing recorded this month"},
        ],
        "rows": rows[:200], "matched": len(rows), "matched_total": sum(e.amount for e in rows),
        "q": q, "show": show,
        "counts": {"all": len(led.expenses), "due": len(owed),
                   "paid": len(led.expenses) - len(owed)},
        "categories": money.CATEGORIES,
        "payees": sorted({e.party for e in led.expenses if e.party}),
        "branches": branches,
        "branch_names": {b.id: b.name for b in org.branches},
        "today_iso": date.today().isoformat(),
    }


# ------------------------------------------------------------------- invoices

def invoices(client, account, request) -> dict:
    book = books.load(client.slug)
    raised = invoice.load_all(client.slug)
    billed = {sid for inv in raised for sid in inv.sale_ids}
    unbilled = [s for s in book.sales if s.id not in billed]

    # One invoice is for one customer, so the sales to bill are offered customer by
    # customer — named customers first, most recent first, walk-in sales last.
    groups: dict[str, dict] = {}
    for s in sorted(unbilled, key=lambda s: (s.date or "", s.id), reverse=True):
        name = (s.party or "").strip()
        g = groups.setdefault(name.lower(), {"party": name, "sales": [], "count": 0,
                                             "total": 0.0, "latest": s.date or ""})
        if len(g["sales"]) < 15:
            g["sales"].append(s)
        g["count"] += 1
        g["total"] += s.amount
    named = sorted((g for g in groups.values() if g["party"].lower() not in WALK_IN),
                   key=lambda g: g["latest"], reverse=True)
    walk_in = [g for g in groups.values() if g["party"].lower() in WALK_IN]
    nxt = invoice.next_number(client)[0]
    return {
        "stats": [
            {"label": "Invoices raised", "value": str(len(raised)), "icon": "file-text",
             "sub": f"next is {nxt}"},
            {"label": "Invoiced", "value": _short(sum(i.rounded for i in raised)),
             "icon": "indian-rupee", "sub": "including tax"},
            {"label": "Not yet billed", "value": str(len(unbilled)), "icon": "receipt",
             "sub": "sales with no invoice against them"},
            {"label": "Tax collected", "value": _short(sum(i.tax for i in raised)),
             "icon": "landmark", "sub": "CGST, SGST and IGST"},
        ],
        "gaps": invoice.missing(client),
        "groups": (named + walk_in)[:12],
        "unbilled_count": len(unbilled),
        "next_number": nxt,
        "invoices": raised[:50],
        "states": sorted(invoice.STATES.items(), key=lambda kv: kv[1]),
    }
