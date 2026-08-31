"""The statements a chartered accountant would prepare, computed from the books.

``money.py`` owns the expense ledger and answers "what is my cash position".
This module answers the harder question the founder actually asked for: *what
would my CA produce for me*. Profit and loss, cash flow, a working balance
sheet, both ageing schedules, the ratios a lender looks at, concentration risk,
and the cash conversion cycle.

Three rules hold the whole thing together.

**One source, many views.** Every figure here derives from the same ``Book`` and
``money.Ledger`` the console shows. Nothing is stored, nothing is re-entered, so
the P&L can never disagree with the cash flow or with the dashboard. If a number
looks wrong, exactly one place produced it.

**Accrual and cash are reported separately, never blended.** Revenue is what was
billed; receipts are what arrived. A business that confuses them thinks it is
profitable while it runs out of money, which is the single most common way a
distributor dies. Every statement says which basis it is on.

**Say what is assumed.** A real balance sheet needs opening balances, fixed
assets, depreciation, loans and capital — none of which this product captures.
Rather than invent them, ``balance_sheet()`` returns what it can support and
lists what is missing in ``assumptions``, and the UI prints that list. A
statement that quietly omits half the liabilities is worse than no statement.

Period handling: every function takes an optional ``(start, end)`` ISO date pair.
Omitted means all of time. Indian businesses run April-March, so ``fy_range()``
and ``periods()`` default to that rather than the calendar year.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta

# --------------------------------------------------------------------- periods

#: Indian financial year starts 1 April.
FY_START_MONTH = 4


def fy_of(iso: str) -> str:
    """The financial year a date falls in, as "2026-27"."""
    try:
        d = date.fromisoformat(iso[:10])
    except (TypeError, ValueError):
        return ""
    start = d.year if d.month >= FY_START_MONTH else d.year - 1
    return f"{start}-{str(start + 1)[2:]}"


def fy_range(label: str) -> tuple[str, str]:
    """"2026-27" -> ("2026-04-01", "2027-03-31")."""
    start_year = int(label.split("-")[0])
    return (f"{start_year}-04-01", f"{start_year + 1}-03-31")


def periods(book, ledger) -> list[tuple[str, str, str]]:
    """Every period worth offering, newest first: (key, label, kind).

    Built from the data that exists rather than a fixed list — offering
    "FY 2019-20" to a business with three months of history is noise.
    """
    dates = [s.date for s in book.sales if s.date] + [e.date for e in ledger.expenses if e.date]
    if not dates:
        return [("all", "All time", "all")]

    out: list[tuple[str, str, str]] = [("all", "All time", "all")]
    for fy in sorted({fy_of(d) for d in dates if fy_of(d)}, reverse=True):
        out.append((f"fy:{fy}", f"FY {fy}", "fy"))
    for m in sorted({d[:7] for d in dates if len(d) >= 7}, reverse=True)[:12]:
        try:
            label = datetime.strptime(m, "%Y-%m").strftime("%B %Y")
        except ValueError:
            label = m
        out.append((f"month:{m}", label, "month"))
    return out


def resolve(key: str) -> tuple[str, str, str]:
    """A period key -> (start, end, label). Empty bounds mean unbounded."""
    if not key or key == "all":
        return "", "", "All time"
    if key.startswith("fy:"):
        label = key[3:]
        start, end = fy_range(label)
        return start, end, f"FY {label}"
    if key.startswith("month:"):
        m = key[6:]
        year, month = int(m[:4]), int(m[5:7])
        last = (date(year + (month == 12), (month % 12) + 1, 1) - timedelta(days=1))
        try:
            label = datetime.strptime(m, "%Y-%m").strftime("%B %Y")
        except ValueError:
            label = m
        return f"{m}-01", last.isoformat(), label
    return "", "", "All time"


def _within(iso: str, start: str, end: str) -> bool:
    if not iso:
        return False
    d = iso[:10]
    if start and d < start:
        return False
    if end and d > end:
        return False
    return True


def _slice(book, ledger, start: str, end: str):
    sales = [s for s in book.sales if _within(s.date, start, end)]
    expenses = [e for e in ledger.expenses if _within(e.date, start, end)]
    return sales, expenses


# ---------------------------------------------------------------- profit & loss

#: Heads that are cost of goods rather than running the business. Everything
#: else is an operating expense. Getting this split right is what makes gross
#: margin mean anything.
COGS_HEADS = {"Purchase"}


def profit_and_loss(book, ledger, start: str = "", end: str = "") -> dict:
    """Accrual basis: revenue billed, cost of what was sold, expenses incurred.

    Cost of goods sold is taken from **item cost × quantity sold**, not from
    purchases in the period, because purchases are lumpy — a distributor who
    buys a container in March has not made a loss in March. Purchases are shown
    separately so the difference is visible rather than hidden.
    """
    sales, expenses = _slice(book, ledger, start, end)
    by_sku = {i.sku: i for i in book.items}

    revenue = sum(s.amount for s in sales)
    cogs = 0.0
    costed = uncosted = 0
    for s in sales:
        item = by_sku.get(s.sku)
        if item is not None and item.cost:
            cogs += item.cost * s.qty
            costed += 1
        else:
            uncosted += 1

    gross = revenue - cogs
    opex_rows: dict[str, float] = defaultdict(float)
    purchases = 0.0
    for e in expenses:
        if e.category in COGS_HEADS:
            purchases += e.amount
        else:
            opex_rows[e.category] += e.amount

    opex = sum(opex_rows.values())
    net = gross - opex

    return {
        "basis": "accrual",
        "revenue": revenue,
        "cogs": cogs,
        "gross_profit": gross,
        "gross_margin_pct": (gross / revenue * 100) if revenue else 0.0,
        "opex": opex,
        "opex_rows": sorted(opex_rows.items(), key=lambda kv: kv[1], reverse=True),
        "net_profit": net,
        "net_margin_pct": (net / revenue * 100) if revenue else 0.0,
        "purchases_in_period": purchases,
        "bills": len(sales),
        # Honesty: gross margin is only as good as the cost data behind it.
        "lines_costed": costed,
        "lines_uncosted": uncosted,
        "cost_coverage_pct": (costed / (costed + uncosted) * 100) if (costed + uncosted) else 0.0,
    }


# ------------------------------------------------------------------- cash flow

def cash_flow(book, ledger, start: str = "", end: str = "") -> dict:
    """Cash basis: what actually moved, not what was billed.

    Deliberately kept beside the P&L in the UI, because the gap between the two
    lines is the number that matters — profit you have not collected is not
    money you can spend.
    """
    sales, expenses = _slice(book, ledger, start, end)
    received = sum(s.amount for s in sales if s.paid)
    billed = sum(s.amount for s in sales)
    paid_out = sum(e.amount for e in expenses if e.paid)
    incurred = sum(e.amount for e in expenses)

    return {
        "basis": "cash",
        "received": received,
        "paid_out": paid_out,
        "net_movement": received - paid_out,
        "billed_not_collected": billed - received,
        "incurred_not_paid": incurred - paid_out,
        # The reconciliation line: profit on paper vs cash in hand.
        "billed": billed,
        "incurred": incurred,
    }


# --------------------------------------------------------------- balance sheet

def balance_sheet(book, ledger, as_of: str = "") -> dict:
    """What the business owns and owes, as far as the books can say.

    Explicitly partial. ``assumptions`` lists everything a real balance sheet
    needs that this product does not capture, and the UI prints it, because a
    statement that silently omits loans and fixed assets will be believed.
    """
    end = as_of or date.today().isoformat()
    receivables = sum(s.amount for s in book.sales
                      if not s.paid and _within(s.date, "", end))
    payables = sum(e.amount for e in ledger.expenses
                   if not e.paid and _within(e.date, "", end))
    stock_value = sum(i.stock_qty * (i.cost or i.rate) for i in book.items)

    # Cash is derived, not counted: receipts minus payments since the books
    # began. It is not a bank balance and is labelled as such in the UI.
    received = sum(s.amount for s in book.sales if s.paid and _within(s.date, "", end))
    paid_out = sum(e.amount for e in ledger.expenses if e.paid and _within(e.date, "", end))
    cash = received - paid_out

    current_assets = cash + receivables + stock_value
    return {
        "as_of": end,
        "cash_from_trading": cash,
        "receivables": receivables,
        "stock_value": stock_value,
        "current_assets": current_assets,
        "payables": payables,
        "current_liabilities": payables,
        "working_capital": current_assets - payables,
        "net_worth_from_trading": current_assets - payables,
        "assumptions": [
            "Cash is receipts minus payments recorded here — not a bank balance.",
            "No opening balances: the books start when Vyuha started.",
            "Fixed assets, depreciation, loans and owner's capital are not captured.",
            "Stock is valued at cost where known, else at selling rate.",
        ],
    }


# ------------------------------------------------------------------- ageing

#: The first bucket is not an ageing bucket at all — it is money that is not yet
#: late. Folding a bill due next Friday into "0–30 days" makes a healthy ledger
#: look overdue and, worse, makes a genuinely overdue one look normal. Every
#: real ageing schedule separates current from overdue, so this one does too.
BUCKETS = [(-10 ** 6, -1, "Not yet due"), (0, 30, "0–30 days"),
           (31, 60, "31–60 days"), (61, 90, "61–90 days"),
           (91, 10 ** 6, "90+ days")]

#: The buckets that mean somebody is late. Used for the "overdue" headline, so
#: it never silently includes money that is simply not due yet.
OVERDUE_BUCKETS = {"0–30 days", "31–60 days", "61–90 days", "90+ days"}


def _age(iso: str) -> int:
    try:
        return (date.today() - date.fromisoformat(iso[:10])).days
    except (TypeError, ValueError):
        return 0


def _ageing(rows: list[tuple[str, float, str]]) -> dict:
    """rows: (party, amount, reference_date) -> bucketed totals and party rows."""
    buckets = {label: 0.0 for _, _, label in BUCKETS}
    by_party: dict[str, dict] = {}
    for party, amount, when in rows:
        age = _age(when)
        label = next((lbl for lo, hi, lbl in BUCKETS if lo <= age <= hi),
                     BUCKETS[-1][2])
        buckets[label] += amount
        p = by_party.setdefault(party, {"party": party, "total": 0.0, "oldest": 0,
                                        **{lbl: 0.0 for _, _, lbl in BUCKETS}})
        p["total"] += amount
        p[label] += amount
        p["oldest"] = max(p["oldest"], age)

    total = sum(buckets.values())
    overdue = sum(v for lbl, v in buckets.items() if lbl in OVERDUE_BUCKETS)
    return {
        "total": total,
        "overdue": overdue,
        "not_due": total - overdue,
        "buckets": [(lbl, buckets[lbl], (buckets[lbl] / total * 100) if total else 0.0)
                    for _, _, lbl in BUCKETS],
        "parties": sorted(by_party.values(), key=lambda r: r["total"], reverse=True),
    }


def receivables_ageing(book) -> dict:
    """Who owes you, and for how long. Ages from the due date where there is one."""
    return _ageing([(s.party or "Cash sale", s.amount, s.due_date or s.date)
                    for s in book.sales if not s.paid])


def payables_ageing(ledger) -> dict:
    """Who you owe, same buckets, so the two can be read side by side."""
    return _ageing([(e.party or e.category, e.amount, e.due_date or e.date)
                    for e in ledger.expenses if not e.paid])


# -------------------------------------------------------------------- ratios

def ratios(book, ledger, start: str = "", end: str = "") -> list[dict]:
    """The numbers a lender or a buyer asks for, each with a plain reading.

    Every ratio carries ``good`` — whether this value is healthy — so the UI can
    colour it without re-deriving the judgement, and ``note`` explaining what it
    means in a sentence, because a shop owner should not have to look them up.
    """
    pl = profit_and_loss(book, ledger, start, end)
    bs = balance_sheet(book, ledger, end)
    sales, expenses = _slice(book, ledger, start, end)

    days = 365
    if start and end:
        try:
            days = max((date.fromisoformat(end) - date.fromisoformat(start)).days, 1)
        except ValueError:
            days = 365
    elif book.sales:
        first = min(s.date for s in book.sales if s.date)
        days = max(_age(first), 1)

    revenue, cogs = pl["revenue"], pl["cogs"]
    dso = (bs["receivables"] / revenue * days) if revenue else 0.0
    dio = (bs["stock_value"] / cogs * days) if cogs else 0.0
    purchases = sum(e.amount for e in expenses if e.category in COGS_HEADS)
    dpo = (bs["payables"] / purchases * days) if purchases else 0.0
    ccc = dio + dso - dpo

    current = (bs["current_assets"] / bs["current_liabilities"]) if bs["current_liabilities"] else 0.0
    turns = (cogs / bs["stock_value"]) if bs["stock_value"] else 0.0

    def row(name, value, unit, good, note):
        return {"name": name, "value": value, "unit": unit, "good": good, "note": note}

    return [
        row("Gross margin", pl["gross_margin_pct"], "%", pl["gross_margin_pct"] >= 15,
            "What is left after the cost of the goods, before running costs."),
        row("Net margin", pl["net_margin_pct"], "%", pl["net_margin_pct"] > 0,
            "What is left after everything. Below zero means the business lost money."),
        row("Debtor days (DSO)", dso, "days", dso <= 45,
            "How long customers take to pay. Every day here is a day of your cash in their pocket."),
        row("Stock days (DIO)", dio, "days", 0 < dio <= 60,
            "How long stock sits before it sells. High means cash locked on the shelf."),
        row("Creditor days (DPO)", dpo, "days", dpo >= 30,
            "How long you take to pay suppliers. Higher is cheap working capital — up to a point."),
        row("Cash cycle (CCC)", ccc, "days", ccc <= 60,
            "Stock days plus debtor days minus creditor days. How long your money is tied up."),
        row("Current ratio", current, "x", current >= 1.2,
            "Short-term assets against short-term dues. Below 1 means a squeeze."),
        row("Stock turns", turns, "x", turns >= 4,
            "How many times stock sold through in the period. Higher is healthier."),
    ]


# ------------------------------------------------------------- concentration

def concentration(book, ledger, start: str = "", end: str = "", top: int = 8) -> dict:
    """Top customers and suppliers, with the risk that follows from them.

    A distributor with 60% of revenue in one customer does not have a good
    customer, he has a single point of failure — and nobody notices until that
    customer leaves.
    """
    sales, expenses = _slice(book, ledger, start, end)

    cust: dict[str, dict] = defaultdict(lambda: {"amount": 0.0, "bills": 0, "owed": 0.0})
    for s in sales:
        row = cust[s.party or "Cash sale"]
        row["amount"] += s.amount
        row["bills"] += 1
        if not s.paid:
            row["owed"] += s.amount

    supp: dict[str, float] = defaultdict(float)
    for e in expenses:
        supp[e.party or e.category] += e.amount

    revenue = sum(r["amount"] for r in cust.values()) or 1.0
    spend = sum(supp.values()) or 1.0

    customers = sorted(({"party": k, **v, "share": v["amount"] / revenue}
                        for k, v in cust.items()),
                       key=lambda r: r["amount"], reverse=True)
    suppliers = sorted(({"party": k, "amount": v, "share": v / spend}
                        for k, v in supp.items()),
                       key=lambda r: r["amount"], reverse=True)

    top_share = customers[0]["share"] if customers else 0.0
    top3 = sum(c["share"] for c in customers[:3])
    return {
        "customers": customers[:top],
        "suppliers": suppliers[:top],
        "top_customer_share": top_share,
        "top3_share": top3,
        "risk": ("high" if top_share >= 0.40 else
                 "watch" if top_share >= 0.25 else "spread"),
        "customer_count": len(customers),
        "supplier_count": len(suppliers),
    }


# ------------------------------------------------------------------- trends

def monthly(book, ledger, months: int = 12) -> list[dict]:
    """Revenue, cost, expenses and profit per month, oldest first."""
    by_sku = {i.sku: i for i in book.items}
    rows: dict[str, dict] = {}

    def bucket(m: str) -> dict:
        return rows.setdefault(m, {"month": m, "revenue": 0.0, "cogs": 0.0,
                                   "opex": 0.0, "received": 0.0, "paid": 0.0})

    for s in book.sales:
        if not s.date:
            continue
        b = bucket(s.date[:7])
        b["revenue"] += s.amount
        item = by_sku.get(s.sku)
        if item is not None and item.cost:
            b["cogs"] += item.cost * s.qty
        if s.paid:
            b["received"] += s.amount

    for e in ledger.expenses:
        if not e.date:
            continue
        b = bucket(e.date[:7])
        if e.category not in COGS_HEADS:
            b["opex"] += e.amount
        if e.paid:
            b["paid"] += e.amount

    out = sorted(rows.values(), key=lambda r: r["month"])[-months:]
    for i, r in enumerate(out):
        r["gross"] = r["revenue"] - r["cogs"]
        r["profit"] = r["gross"] - r["opex"]
        try:
            r["label"] = datetime.strptime(r["month"], "%Y-%m").strftime("%b %y")
        except ValueError:
            r["label"] = r["month"]
        prev = out[i - 1]["revenue"] if i else 0.0
        r["change_pct"] = ((r["revenue"] - prev) / prev * 100) if prev else 0.0
    return out


def expense_analysis(book, ledger, start: str = "", end: str = "") -> list[dict]:
    """Every expense head as an amount and as a share of revenue.

    Share of revenue is the useful column: rent of ₹18,000 means nothing until
    you know it is 3% of turnover or 30%.
    """
    sales, expenses = _slice(book, ledger, start, end)
    revenue = sum(s.amount for s in sales) or 1.0
    heads: dict[str, dict] = defaultdict(lambda: {"amount": 0.0, "count": 0, "unpaid": 0.0})
    for e in expenses:
        h = heads[e.category]
        h["amount"] += e.amount
        h["count"] += 1
        if not e.paid:
            h["unpaid"] += e.amount

    return sorted(({"head": k, **v, "pct_of_revenue": v["amount"] / revenue * 100}
                   for k, v in heads.items()),
                  key=lambda r: r["amount"], reverse=True)


def break_even(book, ledger, start: str = "", end: str = "") -> dict:
    """Monthly turnover needed to cover running costs.

    Treats every non-purchase head as fixed. That is a simplification — some
    transport scales with sales — but it is the right side to err on, and the
    UI says so.
    """
    pl = profit_and_loss(book, ledger, start, end)
    months = max(len(monthly(book, ledger, months=600)), 1)
    fixed_monthly = pl["opex"] / months
    cm = (pl["gross_margin_pct"] / 100) or 0.0
    needed = (fixed_monthly / cm) if cm > 0 else 0.0
    actual = pl["revenue"] / months
    return {
        "fixed_monthly": fixed_monthly,
        "contribution_margin_pct": pl["gross_margin_pct"],
        "break_even_monthly": needed,
        "actual_monthly": actual,
        "headroom": actual - needed,
        "clears": actual >= needed and needed > 0,
    }


# ------------------------------------------------------------------ everything

def statements(book, ledger, period: str = "all") -> dict:
    """The whole file, in one call. What the Money panel and the agent read."""
    start, end, label = resolve(period)
    return {
        "period": {"key": period, "label": label, "start": start, "end": end},
        "pl": profit_and_loss(book, ledger, start, end),
        "cash": cash_flow(book, ledger, start, end),
        "balance": balance_sheet(book, ledger, end),
        "receivables": receivables_ageing(book),
        "payables": payables_ageing(ledger),
        "ratios": ratios(book, ledger, start, end),
        "concentration": concentration(book, ledger, start, end),
        "monthly": monthly(book, ledger),
        "expenses": expense_analysis(book, ledger, start, end),
        "break_even": break_even(book, ledger, start, end),
    }


def facts(book, ledger, period: str = "all") -> dict:
    """A compact, JSON-safe digest for the agent and the deck.

    Deliberately not the full ``statements()`` dump — the agent reasons better
    over thirty exact figures than over every party row.
    """
    s = statements(book, ledger, period)
    pl, bs, cf = s["pl"], s["balance"], s["cash"]
    return {
        "period": s["period"]["label"],
        "profit_and_loss": {
            "revenue": round(pl["revenue"]), "cogs": round(pl["cogs"]),
            "gross_profit": round(pl["gross_profit"]),
            "gross_margin_pct": round(pl["gross_margin_pct"], 1),
            "operating_expenses": round(pl["opex"]),
            "net_profit": round(pl["net_profit"]),
            "net_margin_pct": round(pl["net_margin_pct"], 1),
            "cost_data_coverage_pct": round(pl["cost_coverage_pct"]),
        },
        "cash": {"received": round(cf["received"]), "paid_out": round(cf["paid_out"]),
                 "net_movement": round(cf["net_movement"]),
                 "billed_not_collected": round(cf["billed_not_collected"]),
                 "incurred_not_paid": round(cf["incurred_not_paid"])},
        "balance": {"cash_from_trading": round(bs["cash_from_trading"]),
                    "receivables": round(bs["receivables"]),
                    "stock_value": round(bs["stock_value"]),
                    "payables": round(bs["payables"]),
                    "working_capital": round(bs["working_capital"])},
        "ratios": [{"name": r["name"], "value": round(r["value"], 1),
                    "unit": r["unit"], "healthy": r["good"]} for r in s["ratios"]],
        "receivables_ageing": [{"bucket": b, "amount": round(v)}
                               for b, v, _ in s["receivables"]["buckets"]],
        "payables_ageing": [{"bucket": b, "amount": round(v)}
                            for b, v, _ in s["payables"]["buckets"]],
        "top_customers": [{"party": c["party"], "amount": round(c["amount"]),
                           "share_pct": round(c["share"] * 100, 1)}
                          for c in s["concentration"]["customers"][:5]],
        "customer_concentration_risk": s["concentration"]["risk"],
        "expense_heads": [{"head": e["head"], "amount": round(e["amount"]),
                           "pct_of_revenue": round(e["pct_of_revenue"], 1)}
                          for e in s["expenses"][:8]],
        "break_even_monthly": round(s["break_even"]["break_even_monthly"]),
        "actual_monthly_revenue": round(s["break_even"]["actual_monthly"]),
        "monthly_trend": [{"month": m["label"], "revenue": round(m["revenue"]),
                           "profit": round(m["profit"])} for m in s["monthly"]],
    }
