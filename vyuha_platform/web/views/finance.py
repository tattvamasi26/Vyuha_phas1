"""Finance — the statements a CA would prepare, from the same book every screen reads.

Nothing is computed here: ``finance.py`` and ``tax.py`` own the arithmetic, so a figure on
this page and the same figure in a deck or an answer come from one place. Accrual and cash
are kept apart, and the balance sheet prints what it cannot see.
"""

from __future__ import annotations

from datetime import date

from ... import books, finance, invoice, money, tax
from .. import charts


def _short(v: float) -> str:
    from ..templating import money_short
    return money_short(v)


def _period(request, book, led) -> dict:
    """The period picker's state — offered from the data that exists, not a fixed list."""
    options = finance.periods(book, led)
    key = request.query_params.get("period", "all")
    if key not in {k for k, _label, _kind in options}:
        key = "all"
    start, end, label = finance.resolve(key)
    return {"periods": options, "period": key, "period_label": label,
            "start": start, "end": end}


def _load(client):
    return books.load(client.slug), money.load(client.slug)


# ------------------------------------------------------------------- overview

def overview(client, account, request) -> dict:
    book, led = _load(client)
    bs = finance.balance_sheet(book, led)
    pl = finance.profit_and_loss(book, led)
    rec, pay = finance.receivables_ageing(book), finance.payables_ageing(led)
    week = money.due_this_week(book, led)
    rows = finance.monthly(book, led, 12)
    return {
        "stats": [
            {"label": "Cash from trading", "value": _short(bs["cash_from_trading"]),
             "icon": "wallet", "sub": "receipts minus payments recorded here"},
            {"label": "Net profit, all time", "value": _short(pl["net_profit"]),
             "icon": "trending-up", "sub": f"{pl['net_margin_pct']:.1f}% of revenue",
             "tone": "bad" if pl["net_profit"] < 0 else ""},
            {"label": "To collect", "value": _short(rec["total"]), "icon": "hand-coins",
             "sub": (f"{_short(rec['overdue'])} of it overdue" if rec["overdue"]
                     else "nothing overdue"),
             "tone": "bad" if rec["overdue"] else ""},
            {"label": "To pay", "value": _short(pay["total"]), "icon": "receipt",
             "sub": (f"{_short(pay['overdue'])} of it overdue" if pay["overdue"]
                     else "nothing overdue"),
             "tone": "warn" if pay["overdue"] else ""},
        ],
        "chart": charts.columns([r["revenue"] for r in rows], [r["label"] for r in rows],
                                fmt=_short, partial_last=True, label="Revenue by month"),
        "monthly": list(reversed(rows))[:6],
        "incoming": week["incoming"][:6], "outgoing": week["outgoing"][:6],
        "incoming_total": week["incoming_total"], "outgoing_total": week["outgoing_total"],
        "filings": tax.calendar_()[:3],
        "scheme": tax.SCHEME_ASSUMED,
        "has_data": bool(book.sales or led.expenses),
    }


# --------------------------------------------------------------- profit & loss

def pnl(client, account, request) -> dict:
    book, led = _load(client)
    ctx = _period(request, book, led)
    pl = finance.profit_and_loss(book, led, ctx["start"], ctx["end"])
    heads = finance.expense_analysis(book, led, ctx["start"], ctx["end"])
    rows = finance.monthly(book, led, 12)
    ctx.update({
        "pl": pl, "heads": heads,
        "monthly": list(reversed(rows)),
        "chart": charts.columns([r["profit"] for r in rows], [r["label"] for r in rows],
                                fmt=_short, partial_last=True, label="Profit by month"),
        "break_even": finance.break_even(book, led, ctx["start"], ctx["end"]),
    })
    return ctx


# --------------------------------------------------------------- balance sheet

def balance(client, account, request) -> dict:
    book, led = _load(client)
    bs = finance.balance_sheet(book, led)
    return {"bs": bs, "as_of": bs["as_of"],
            "ratios": [r for r in finance.ratios(book, led)
                       if r["name"] in ("Current ratio", "Stock turns", "Cash cycle (CCC)")]}


# ------------------------------------------------------------------ cash flow

def cashflow(client, account, request) -> dict:
    book, led = _load(client)
    ctx = _period(request, book, led)
    rows = finance.monthly(book, led, 12)
    ctx.update({
        "cf": finance.cash_flow(book, led, ctx["start"], ctx["end"]),
        "monthly": list(reversed(rows)),
        "in_chart": charts.columns([r["received"] for r in rows],
                                   [r["label"] for r in rows], fmt=_short,
                                   partial_last=True, label="Money in by month"),
        "out_chart": charts.columns([r["paid"] for r in rows], [r["label"] for r in rows],
                                    fmt=_short, partial_last=True,
                                    label="Money out by month"),
    })
    return ctx


# ----------------------------------------------------------------------- dues

def dues(client, account, request) -> dict:
    book, led = _load(client)
    rec, pay = finance.receivables_ageing(book), finance.payables_ageing(led)
    return {
        "receivables": rec, "payables": pay,
        "stats": [
            {"label": "Owed to you", "value": _short(rec["total"]), "icon": "hand-coins",
             "sub": f"{_short(rec['overdue'])} past the due date",
             "tone": "bad" if rec["overdue"] else ""},
            {"label": "Not yet due, in", "value": _short(rec["not_due"]), "icon": "clock",
             "sub": "inside its credit period"},
            {"label": "You owe", "value": _short(pay["total"]), "icon": "receipt",
             "sub": f"{_short(pay['overdue'])} past the due date",
             "tone": "warn" if pay["overdue"] else ""},
            {"label": "Net position", "value": _short(rec["total"] - pay["total"]),
             "icon": "wallet", "sub": "what is owed to you, less what you owe"},
        ],
    }


# ------------------------------------------------------------------------ GST

def gst(client, account, request) -> dict:
    led = money.load(client.slug)
    invoices = invoice.load_all(client.slug)
    owed = tax.liability(invoices, led)
    return {
        "has_gstin": bool(client.gstin),
        "owed": owed,
        "by_rate": sorted(owed["by_rate"].items()),
        "taxed": owed["invoices"],
        "filings": tax.calendar_(),
        "scheme": tax.SCHEME_ASSUMED,
        "stats": [
            {"label": "Tax collected", "value": _short(owed["output"]), "icon": "landmark",
             "sub": f"on {owed['invoices']} invoice{'' if owed['invoices'] == 1 else 's'}"},
            {"label": "Taxable value", "value": _short(owed["taxable"]),
             "icon": "indian-rupee", "sub": "before tax"},
            {"label": "CGST + SGST", "value": _short(owed["cgst"] * 2), "icon": "percent",
             "sub": "sales within the state"},
            {"label": "IGST", "value": _short(owed["igst"]), "icon": "truck",
             "sub": "sales outside it"},
        ],
    }


# -------------------------------------------------------------------- reports

def reports(client, account, request) -> dict:
    book, led = _load(client)
    run = client.latest
    pl = finance.profit_and_loss(book, led)
    return {
        "run": run if (run and run.status == "ok") else None,
        "email_to": client.email,
        "subject": f"{client.name} — the month's numbers",
        "body": (f"Sir,\n\nThe figures for {client.name} are attached.\n\n"
                 f"Revenue {_short(pl['revenue'])}, gross profit "
                 f"{_short(pl['gross_profit'])} ({pl['gross_margin_pct']:.1f}%), "
                 f"net {_short(pl['net_profit'])}.\n\n"
                 f"Please tell us what else you need for the filing.\n\n"
                 f"Thank you,\n{client.name}"),
        "today_iso": date.today().isoformat(),
    }
