"""Sales — what is selling, who is buying, and who still has to pay.

Every figure comes from ``books``, ``analysis`` and ``followup`` — the same functions the
agent and Home call — so no two screens can disagree about a customer.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date

from ... import analysis, books, channels, followup, people
from .. import charts
from .home import _daily, _month_to_date


def _short(v: float) -> str:
    from ..templating import money_short
    return money_short(v)


def _month_keys(n: int = 12) -> list[str]:
    """The last ``n`` calendar months as "YYYY-MM", oldest first, this month last."""
    t = date.today()
    y, m = t.year, t.month
    keys = []
    for _ in range(n):
        keys.append(f"{y:04d}-{m:02d}")
        y, m = (y - 1, 12) if m == 1 else (y, m - 1)
    return keys[::-1]


def _month_label(key: str, first: bool) -> str:
    d = date(int(key[:4]), int(key[5:7]), 1)
    return d.strftime("%b %y") if first or d.month == 1 else d.strftime("%b")


def overview(client, account, request) -> dict:
    book, org = books.load(client.slug), people.load(client.slug)
    by_month: dict[str, float] = defaultdict(float)
    for s in book.sales:
        if s.date:
            by_month[s.date[:7]] += s.amount
    keys = _month_keys()
    by_day, _ = _daily(book)
    mtd, last_mtd = _month_to_date(by_day, date.today())
    return {
        "no_sales": not book.sales,
        "stats": [
            {"label": "Revenue", "value": _short(book.earned), "icon": "trending-up",
             "sub": f"{len(book.sales):,} bills, all time"},
            {"label": "Collected", "value": _short(book.collected), "icon": "wallet",
             "sub": "money in hand"},
            {"label": "Owed to you", "value": _short(book.owed), "icon": "hand-coins",
             "sub": "sold on credit, not yet paid", "tone": "bad" if book.owed else ""},
            {"label": "Customers", "value": f"{len(book.customers()):,}", "icon": "users",
             "sub": "who have bought"},
        ],
        "chart": charts.columns([by_month.get(k, 0.0) for k in keys],
                                [_month_label(k, i == 0) for i, k in enumerate(keys)],
                                fmt=_short, partial_last=True, label="Revenue by month"),
        "this_month": mtd,
        "change": ((mtd - last_mtd) / last_mtd * 100) if last_mtd else None,
        "top_items": analysis.query_sales(book, org, group_by="item", top_n=8)["rows"],
        "top_party": analysis.query_sales(book, org, group_by="party", top_n=8)["rows"],
    }


def bills(client, account, request) -> dict:
    book = books.load(client.slug)
    q = request.query_params.get("q", "").strip()
    show = request.query_params.get("show", "all")
    show = show if show in ("all", "credit", "paid") else "all"
    rows = sorted(book.sales, key=lambda s: (s.date or "", s.id), reverse=True)
    if show == "credit":
        rows = [s for s in rows if not s.paid]
    elif show == "paid":
        rows = [s for s in rows if s.paid]
    if q:
        needle = q.lower()
        rows = [s for s in rows if needle in (s.party or "").lower()
                or needle in (s.item or "").lower() or needle in s.id.lower()]
    credit = sum(1 for s in book.sales if not s.paid)
    return {
        "rows": rows[:200], "matched": len(rows),
        "matched_total": sum(s.amount for s in rows),
        "q": q, "show": show,
        "counts": {"all": len(book.sales), "credit": credit, "paid": len(book.sales) - credit},
        "today_iso": date.today().isoformat(),
    }


#: How the customer list can be ordered, and what each option is called on the page.
SORTS = {"spend": "Top spend", "owes": "Owe you", "recent": "Bought recently"}


def customers(client, account, request) -> dict:
    book = books.load(client.slug)
    q = request.query_params.get("q", "").strip()
    sort = request.query_params.get("sort", "spend")
    sort = sort if sort in SORTS else "spend"

    agg: dict[str, dict] = {}
    for s in book.sales:
        name = (s.party or "").strip() or "Cash sale"
        a = agg.setdefault(name.lower(), {"name": name, "bills": 0, "spend": 0.0,
                                          "owes": 0.0, "last": "", "phone": ""})
        a["bills"] += 1
        a["spend"] += s.amount
        if not s.paid:
            a["owes"] += s.amount
        if (s.date or "") > a["last"]:
            a["last"] = s.date or ""
        if s.party_phone:
            a["phone"] = s.party_phone
    rows = list(agg.values())
    if q:
        rows = [r for r in rows if q.lower() in r["name"].lower()]
    rows.sort(key=lambda r: r[{"spend": "spend", "owes": "owes", "recent": "last"}[sort]],
              reverse=True)

    picked = request.query_params.get("c", "").strip()
    detail = analysis.customer_detail(book, picked) if picked else None
    if detail and detail.get("found"):
        exact = detail["party"]
        detail["initials"] = "".join(w[0] for w in exact.split()[:2]).upper() or "?"
        detail["recent"] = sorted((s for s in book.sales if s.party == exact),
                                  key=lambda s: s.date or "", reverse=True)[:8]
    else:
        detail = None
    return {"rows": rows, "q": q, "sort": sort, "sorts": SORTS, "picked": picked,
            "detail": detail, "count": len(agg)}


def collections(client, account, request) -> dict:
    book = books.load(client.slug)
    rows = []
    for f in followup.queue(client.slug, book):
        text = followup.draft(f, client.name)
        rows.append({"f": f, "text": text,
                     "wa": channels.whatsapp_link(f.party_phone, text) if f.has_phone else ""})
    pay = [r for r in rows if r["f"].kind == "payment"]
    quiet = [r for r in rows if r["f"].kind != "payment"]
    late = sum(r["f"].amount for r in pay)
    oldest = max(pay, key=lambda r: r["f"].days, default=None)
    return {
        "payments": pay, "quiet": quiet,
        "stats": [
            {"label": "Late payments", "value": _short(late), "icon": "hand-coins",
             "sub": f"{len(pay)} customer{'' if len(pay) == 1 else 's'} past the due date",
             "tone": "bad" if pay else ""},
            {"label": "Oldest", "value": f"{oldest['f'].days} days" if oldest else "—",
             "icon": "clock", "sub": oldest["f"].party if oldest else "nobody is late",
             "tone": "warn" if oldest else ""},
            {"label": "Owed in total", "value": _short(book.owed), "icon": "wallet",
             "sub": "including bills not yet due"},
            {"label": "Gone quiet", "value": str(len(quiet)), "icon": "users",
             "sub": "regulars who stopped buying"},
        ],
    }
