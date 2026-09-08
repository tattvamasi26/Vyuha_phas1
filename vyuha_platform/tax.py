"""The Tax & GST agent: what is owed, and when it has to be filed.

The architecture gives this agent three responsibilities — "liabilities, filing
dates, GST returns" — and an arrow into the Notification Agent. Liabilities were
already computed, inline, inside the Financials screen. **Filing dates were not
computed anywhere**, which is why the arrow had nothing travelling down it: a
tax agent that cannot say when a return is due has no event to raise.

So this module owns both, and the screen calls it. That direction matters. A
figure computed on a screen can only ever be read by somebody looking at that
screen, and the moment a second caller wants it — a notification, a brief, an
export — it gets computed a second time and the two drift. `liability()` is now
the single answer, and `_fin_taxes` renders it rather than deriving it.

**What this refuses to be.** Not a filing document, and not a return. It says
what is roughly owed between filings and when the deadline is; a CA files. The
estimate of input credit is labelled an estimate everywhere it appears, because
the expense ledger holds no supplier GSTINs and a number that cannot be
substantiated must never be presented as one that can.

**The due dates are the standard monthly cadence.** GSTR-1 on the 11th and
GSTR-3B on the 20th of the following month is right for a monthly filer, and
wrong for one on the QRMP quarterly scheme, whose GSTR-1 is quarterly and whose
3B falls on the 22nd or 24th by state. Vyuha does not know which scheme a
business is on, so `SCHEME_ASSUMED` says so out loud and the screen prints it.
Guessing silently is how somebody misses a deadline while being told they had
nine days.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

#: Which returns, and the day of the month they fall due — always for the month
#: *before* the one they land in. Held as data so a rate or date change is an
#: edit here rather than a hunt through the screen code.
RETURNS: tuple[tuple[str, str, int], ...] = (
    ("GSTR-1", "Outward supplies — every sale invoice you raised", 11),
    ("GSTR-3B", "Summary return, and the month's payment", 20),
)

#: Said out loud wherever a due date is shown. See the module docstring.
SCHEME_ASSUMED = (
    "These dates assume monthly filing. On the QRMP quarterly scheme GSTR-1 is "
    "quarterly and 3B falls on the 22nd or 24th depending on your state — "
    "check with your CA which one you are on."
)

#: How commonly the rough input-credit estimate assumes purchases were taxed.
#: A single blended rate is indefensible as arithmetic and defensible as an
#: order-of-magnitude, which is exactly how it is labelled.
ASSUMED_INPUT_RATE = 5.0


def _month_before(day: date) -> tuple[int, int]:
    """The (year, month) a return landing in `day`'s month reports on."""
    return (day.year - 1, 12) if day.month == 1 else (day.year, day.month - 1)


def _period_label(year: int, month: int) -> str:
    return date(year, month, 1).strftime("%B %Y")


@dataclass(frozen=True)
class Filing:
    """One return, for one period, with one date on it."""

    name: str
    covers: str
    period: str              # "August 2026"
    due: date
    days_left: int

    @property
    def overdue(self) -> bool:
        return self.days_left < 0

    @property
    def severity(self) -> str:
        """How loudly this should be said.

        A missed GST deadline is a penalty plus interest that accrues daily, so
        an overdue return is critical rather than a warning — it is the one item
        in this product that gets more expensive every day it is ignored.
        """
        if self.overdue:
            return "critical"
        if self.days_left <= 3:
            return "critical"
        if self.days_left <= 7:
            return "warning"
        return "info"

    @property
    def when(self) -> str:
        if self.days_left < 0:
            return f"was due {abs(self.days_left)} day(s) ago"
        if self.days_left == 0:
            return "due today"
        if self.days_left == 1:
            return "due tomorrow"
        return f"due in {self.days_left} days"


def calendar_(as_of: date | None = None, horizon: int = 45) -> list[Filing]:
    """Returns falling due within `horizon` days, soonest first.

    Looks at both this month's deadlines and next month's, because a horizon
    wide enough to be useful in the last week of a month necessarily crosses
    into the next one. Anything already more than a month overdue is dropped —
    at that point it is a matter for a CA, not a reminder.
    """
    today = as_of or date.today()
    out: list[Filing] = []

    for offset in (0, 1):
        # The month this return would land in.
        m = today.month + offset
        y = today.year + (m - 1) // 12
        m = (m - 1) % 12 + 1
        landing = date(y, m, 1)
        py, pm = _month_before(landing)

        for name, covers, day in RETURNS:
            due = date(y, m, day)
            days_left = (due - today).days
            if days_left < -31 or days_left > horizon:
                continue
            out.append(Filing(name=name, covers=covers,
                              period=_period_label(py, pm),
                              due=due, days_left=days_left))

    return sorted(out, key=lambda f: f.due)


def next_due(as_of: date | None = None) -> Filing | None:
    """The one deadline somebody should have in mind. None if nothing is close."""
    upcoming = calendar_(as_of)
    return upcoming[0] if upcoming else None


# --- what is owed ---------------------------------------------------------


def liability(invoices, ledger) -> dict:
    """Output tax, estimated input credit, and what that leaves.

    Output tax comes from **invoices actually raised**, never from sales: a sale
    with no invoice against it collected no tax, and treating revenue as taxable
    would overstate the liability by exactly the amount of the business's
    uninvoiced trade — which for a shop is most of it.
    """
    taxed = [i for i in invoices if i.taxed]
    purchases = [e for e in ledger.expenses if e.category == "Purchase"]
    spent = sum(e.amount for e in purchases)

    # Tax already inside a GST-inclusive purchase price, at the assumed rate.
    est_input = spent * ASSUMED_INPUT_RATE / (100 + ASSUMED_INPUT_RATE)
    output = sum(i.tax for i in taxed)

    by_rate: dict[float, dict] = {}
    for inv in taxed:
        for g in inv.by_rate():
            row = by_rate.setdefault(g["gst_rate"], {"taxable": 0.0, "tax": 0.0})
            row["taxable"] += g["taxable"]
            row["tax"] += g["tax"]

    return {
        "invoices": len(taxed),
        "output": output,
        "taxable": sum(i.taxable for i in taxed),
        "cgst": sum(i.cgst for i in taxed),
        "igst": sum(i.igst for i in taxed),
        "purchases": spent,
        "est_input": est_input,
        "net": output - est_input,
        "by_rate": dict(sorted(by_rate.items())),
        "input_is_an_estimate": True,
    }


# --- what the Notification Agent reads ------------------------------------


def events(client, invoices, ledger, as_of: date | None = None) -> list[dict]:
    """Filing deadlines worth telling somebody about.

    Returns plain dicts rather than importing `notify` — the arrow in the
    architecture runs Tax -> Notification, and a module that imported its own
    consumer would reverse it. `notify` reads this; this knows nothing about who
    gets told, which is the Notification Agent's job and not the tax agent's.

    A business with no GSTIN raises nothing at all. It files no returns, so a
    reminder about one is noise about an obligation it does not have.
    """
    if not getattr(client, "gstin", ""):
        return []

    out = []
    owed = liability(invoices, ledger)
    for f in calendar_(as_of, horizon=10):
        if f.severity == "info":
            # Still a fortnight out. It belongs on the screen, not on a phone.
            continue
        detail = f"{f.name} for {f.period} — {f.covers.split(' — ')[0].lower()}."
        if f.name == "GSTR-3B" and owed["output"]:
            detail += (f" Roughly Rs {owed['net']:,.0f} net, on "
                       f"{owed['invoices']} taxed invoice(s).")
        out.append({
            "key": f"filing:{f.name}:{f.due.isoformat()}",
            "code": "filing_due",
            "severity": f.severity,
            "title": f"{f.name} {f.when} ({f.due.strftime('%d %b')})",
            "detail": detail,
            "value": max(owed["net"], 0.0) if f.name == "GSTR-3B" else 0.0,
            "source": "tax",
        })
    return out
