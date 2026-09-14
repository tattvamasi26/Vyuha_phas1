"""Home — what needs the owner today, and how the business is doing.

Every figure here comes from a function the classic screens already use —
``today.findings``, ``money.position``, ``books.summary``, ``followup.queue`` — so the new
Home and the classic Desk cannot disagree about the same morning.
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, timedelta

from ... import books, followup, invoice, ledger as activity, money, people, today
from .. import charts

#: How a finding's severity reads on the page.
TONE = {"critical": "bad", "warning": "warn", "info": "info"}

#: A phone number inside an activity summary — ten digits, with or without 91 in front.
_PHONE = re.compile(r"\+?\b(?:91)?(\d{10})\b")


def _daily(book) -> tuple[dict[str, float], dict[str, int]]:
    amount: dict[str, float] = defaultdict(float)
    bills: dict[str, int] = defaultdict(int)
    for s in book.sales:
        if s.date:
            amount[s.date[:10]] += s.amount
            bills[s.date[:10]] += 1
    return amount, bills


def _month_to_date(by_day: dict[str, float], t: date) -> tuple[float, float]:
    """This month so far, and the same number of days of last month."""
    start = t.replace(day=1)
    mtd = sum(v for d, v in by_day.items() if start.isoformat() <= d <= t.isoformat())
    prev_end = start - timedelta(days=1)
    prev_start = prev_end.replace(day=1)
    cut = prev_start.replace(day=min(t.day, prev_end.day)).isoformat()
    last = sum(v for d, v in by_day.items() if prev_start.isoformat() <= d <= cut)
    return mtd, last


def _freshness(client, book) -> dict:
    """Where the numbers came from, and how recently — shown beside them."""
    if client.data_mode == "books" or not client.latest:
        last = max((s.date for s in book.sales if s.date), default="")
        return {"source": "Typed in", "when": last or client.created_at,
                "icon": "notebook-pen"}
    run = client.latest
    return {"source": f"From {run.filename}", "when": run.uploaded_at, "icon": "file-spreadsheet"}


def _names(client, org) -> dict[str, str]:
    """The last ten digits of every number this business knows, and whose it is."""
    names: dict[str, str] = {}
    for s in org.staff:
        digits = re.sub(r"\D", "", s.phone or "")[-10:]
        if len(digits) == 10:
            names[digits] = f"{s.name}, {s.role}" if s.role else s.name
    own = re.sub(r"\D", "", client.phone or "")[-10:]
    if len(own) == 10:
        names[own] = "you"           # Home speaks to the owner, as its greeting does
    return names


def _who(text: str, names: dict[str, str]) -> str:
    """"CEO 8am brief → 919845000111" reads as "CEO 8am brief → you".

    The activity log records where a message went as the number it was sent to, and on
    Home a string of twelve digits is somebody nobody recognises.
    """
    def swap(m: re.Match) -> str:
        d = m.group(1)
        return names.get(d) or f"+91 {d[:5]} {d[5:]}"
    return _PHONE.sub(swap, text)


def build(client, account) -> dict:
    slug = client.slug
    book = books.load(slug)
    led = money.load(slug)
    org = people.load(slug)
    invoices = invoice.load_all(slug)

    found = today.findings(client, book, led, org, invoices)
    pos = money.position(book, led)
    summary = books.summary(book)
    queue = followup.queue(slug, book)
    overdue = [f for f in queue if f.kind == "payment"]

    t = date.today()
    by_day, bills_by_day = _daily(book)
    days30 = [(t - timedelta(days=d)).isoformat() for d in range(29, -1, -1)]
    mtd, last_mtd = _month_to_date(by_day, t)
    change = ((mtd - last_mtd) / last_mtd * 100) if last_mtd else None
    months = money.by_month(book, led, 6)

    low = [i for i in summary["low_stock"] if i.stock_qty > 0]
    out = summary["out_of_stock"]

    kpis = [
        {"key": "sales", "label": "Sales this month", "icon": "trending-up",
         "value": mtd, "delta": change,
         "sub": (f"vs {_short(last_mtd)} by this day last month" if last_mtd else
                 "Nothing to compare with last month yet"),
         "spark": charts.sparkline([by_day.get(d, 0.0) for d in days30]),
         "spark_label": "Daily sales, last 30 days",
         "href": f"/app/{slug}/sales/overview"},
        {"key": "cash", "label": "Cash position", "icon": "wallet",
         "value": pos["net"], "delta": None,
         "sub": f"{_short(pos['to_collect'])} to come in · {_short(pos['to_pay'])} to go out",
         "spark": charts.bars([m["net"] for m in months]),
         "spark_label": "Net cash by month, last 6 months",
         "href": f"/app/{slug}/finance/overview"},
        {"key": "dues", "label": "Owed to you", "icon": "hand-coins",
         "value": pos["to_collect"], "delta": None,
         "sub": (f"{len(overdue)} overdue · worst {overdue[0].days} days"
                 if overdue else "Nobody is late"),
         "tone": "bad" if overdue else "",
         "href": f"/app/{slug}/sales/collections"},
        {"key": "stock", "label": "Stock on the shelf", "icon": "boxes",
         "value": summary["stock_value"], "delta": None,
         "sub": (f"{len(low)} running low · {len(out)} out" if (low or out)
                 else f"{summary['items']} items, none low"),
         "tone": "warn" if (low or out) else "",
         "href": f"/app/{slug}/operations/inventory"},
    ]

    names = _names(client, org)
    entries = []
    for e in activity.read(client.owner_id, limit=8, client=slug):
        label, tone = activity.KINDS.get(e.kind, (e.kind.replace(".", " ").title(), "dim"))
        entries.append({"when": e.ts, "label": label, "tone": tone,
                        "text": _who(getattr(e, "summary", "") or label, names)})

    return {
        "greeting": today.greeting(client, account),
        "summary_line": today.summary_line(client, book, led),
        "freshness": _freshness(client, book),
        "findings": [{"key": f.key, "tone": TONE.get(f.severity, "info"),
                      "severity": f.severity, "title": f.title, "detail": f.detail,
                      "action": f.action, "href": f.href} for f in found],
        "minutes": today.minutes(found),
        "kpis": kpis,
        "today": {"sales": by_day.get(t.isoformat(), 0.0),
                  "bills": bills_by_day.get(t.isoformat(), 0),
                  "date": t.isoformat()},
        "activity": entries,
        # Not "empty": that name is a macro in components/ui.html, and a template
        # importing it would read the macro — always truthy — instead of this.
        "is_empty": not book.items and not book.sales,
        "counts": {"items": summary["items"], "customers": summary["customers"],
                   "bills": summary["bills"]},
    }


def _short(value: float) -> str:
    from ..templating import money_short
    return money_short(value)
