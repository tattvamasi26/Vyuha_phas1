"""Cash flow — which needs the half the product did not have yet.

``books.Sale`` already records everything coming *in*, including whether it was
paid or sold on credit, and ``analyze.py`` already ages the receivables. What
was missing was money going *out*: purchases, salary, rent, transport. Without
it there is no cash flow statement, only a receivables report wearing one.

So this module owns exactly one new thing — the ``Expense`` — and then computes
the statement by putting it beside the sales that already exist. Nothing here
re-derives revenue; it reads ``Book`` for that, so the money screen and the
dashboard can never disagree about what was earned.

Two distinctions the code keeps carefully apart, because a business owner cares
about the difference far more than an accountant does:

* **Earned vs collected.** A credit sale is revenue but it is not cash.
* **Committed vs paid.** An unpaid purchase is a bill you owe, not an outflow.

``position()`` therefore reports four numbers, not two, and the console shows
all four — what came in, what went out, what is still owed to you, and what you
still owe. That is the screen an owner checks before promising a supplier.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

from . import atomic

REPO = Path(__file__).resolve().parent.parent
MONEY = REPO / "vyuha_data" / "money"

#: Deliberately short. A long list makes categorising feel like bookkeeping,
#: and the whole point is that this takes ten seconds at the end of a day.
CATEGORIES = ["Purchase", "Salary", "Rent", "Transport", "Utilities",
              "Repairs", "Tax", "Other"]


def _today() -> str:
    return date.today().isoformat()


def _num(value, default: float = 0.0) -> float:
    try:
        return float(str(value).replace(",", "").replace("₹", "").strip())
    except (TypeError, ValueError):
        return default


def _month(iso: str) -> str:
    return iso[:7] if iso and len(iso) >= 7 else ""


@dataclass
class Expense:
    """One thing the business paid for, or owes."""

    id: str
    date: str
    category: str
    party: str                    # who it was paid to
    amount: float
    note: str = ""
    paid: bool = True             # False = a bill owed, not yet an outflow
    due_date: str = ""
    branch: str = ""              # branch id, when the business has branches
    added_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

    @property
    def overdue(self) -> bool:
        if self.paid or not self.due_date:
            return False
        return self.due_date < _today()


@dataclass
class Ledger:
    slug: str
    expenses: list[Expense] = field(default_factory=list)

    @property
    def paid_out(self) -> float:
        return sum(e.amount for e in self.expenses if e.paid)

    @property
    def to_pay(self) -> float:
        return sum(e.amount for e in self.expenses if not e.paid)

    @property
    def total(self) -> float:
        return sum(e.amount for e in self.expenses)

    def expense(self, expense_id: str) -> Expense | None:
        return next((e for e in self.expenses if e.id == expense_id), None)


# ------------------------------------------------------------------ persistence

def _path(slug: str) -> Path:
    MONEY.mkdir(parents=True, exist_ok=True)
    return MONEY / f"{slug}.json"


def load(slug: str) -> Ledger:
    path = _path(slug)
    if not path.exists():
        return Ledger(slug=slug)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return Ledger(slug=slug)
    out = []
    for e in raw.get("expenses", []):
        known = {k: v for k, v in e.items() if k in Expense.__dataclass_fields__}
        out.append(Expense(**known))
    return Ledger(slug=slug, expenses=out)


def save(ledger: Ledger) -> None:
    atomic.write_json(_path(ledger.slug),
                      {"expenses": [asdict(e) for e in ledger.expenses]})


# --------------------------------------------------------------------- editing

def add_expense(slug: str, category: str, party: str, amount, when: str = "",
                note: str = "", paid: bool = True, due_date: str = "",
                branch: str = "") -> tuple[Ledger, str]:
    ledger = load(slug)
    value = _num(amount)
    expense = Expense(
        id=uuid.uuid4().hex[:8],
        date=(when or _today())[:10],
        category=(category or "Other").strip() or "Other",
        party=party.strip(),
        amount=value,
        note=note.strip(),
        paid=paid,
        due_date=due_date[:10] if due_date else "",
        branch=branch,
    )
    ledger.expenses.append(expense)
    ledger.expenses.sort(key=lambda e: e.date, reverse=True)
    save(ledger)
    who = f" to {expense.party}" if expense.party else ""
    state = "paid" if paid else "owed"
    return ledger, f"Recorded ₹{value:,.0f} {state}{who} ({expense.category})."


def delete_expense(slug: str, expense_id: str) -> tuple[Ledger, str]:
    ledger = load(slug)
    expense = ledger.expense(expense_id)
    if expense is None:
        return ledger, "That entry was already gone."
    ledger.expenses = [e for e in ledger.expenses if e.id != expense_id]
    save(ledger)
    return ledger, f"Removed ₹{expense.amount:,.0f} ({expense.category})."


def mark_paid(slug: str, expense_id: str) -> tuple[Ledger, str]:
    ledger = load(slug)
    expense = ledger.expense(expense_id)
    if expense is None:
        return ledger, "That entry no longer exists."
    if expense.paid:
        return ledger, "That was already marked paid."
    expense.paid = True
    save(ledger)
    return ledger, f"Marked ₹{expense.amount:,.0f} to {expense.party or 'supplier'} as paid."


# ------------------------------------------------------------------- the views

def position(book, ledger: Ledger) -> dict:
    """The four numbers, and the two that follow from them.

    ``book`` is a ``books.Book``. Passed in rather than loaded here so the
    caller decides which client is being asked about, and so this stays
    testable without touching disk.
    """
    came_in = sum(s.amount for s in book.sales if s.paid)
    to_collect = sum(s.amount for s in book.sales if not s.paid)
    went_out = ledger.paid_out
    to_pay = ledger.to_pay
    return {
        "came_in": came_in,
        "went_out": went_out,
        "net": came_in - went_out,
        "to_collect": to_collect,
        "to_pay": to_pay,
        # What the position becomes if everyone pays and you pay everyone.
        "if_settled": (came_in - went_out) + to_collect - to_pay,
        "earned": book.earned,
        "margin": book.margin,
    }


def by_month(book, ledger: Ledger, months: int = 6) -> list[dict]:
    """In, out and net per calendar month, oldest first — the chart series."""
    buckets: dict[str, dict] = {}

    def bucket(key: str) -> dict:
        return buckets.setdefault(key, {"month": key, "in": 0.0, "out": 0.0})

    for s in book.sales:
        m = _month(s.date)
        if m:
            bucket(m)["in"] += s.amount
    for e in ledger.expenses:
        m = _month(e.date)
        if m:
            bucket(m)["out"] += e.amount

    rows = sorted(buckets.values(), key=lambda r: r["month"])[-months:]
    for r in rows:
        r["net"] = r["in"] - r["out"]
        try:
            r["label"] = datetime.strptime(r["month"], "%Y-%m").strftime("%b %y")
        except ValueError:
            r["label"] = r["month"]
    return rows


def by_category(ledger: Ledger) -> list[tuple[str, float]]:
    """Where the money went, biggest first."""
    totals: dict[str, float] = {}
    for e in ledger.expenses:
        totals[e.category] = totals.get(e.category, 0.0) + e.amount
    return sorted(totals.items(), key=lambda kv: kv[1], reverse=True)


def due_this_week(book, ledger: Ledger, days: int = 7) -> dict:
    """What lands in the next seven days, both directions.

    This is the demo's 15:00 beat and the most-used screen in the module: an
    owner does not want a statement, he wants to know whether Friday is a
    problem.
    """
    horizon = (date.today() + timedelta(days=days)).isoformat()
    today = _today()

    incoming = [s for s in book.sales
                if not s.paid and s.due_date and s.due_date <= horizon]
    outgoing = [e for e in ledger.expenses
                if not e.paid and e.due_date and e.due_date <= horizon]

    return {
        "days": days,
        "incoming": sorted(incoming, key=lambda s: s.due_date),
        "outgoing": sorted(outgoing, key=lambda e: e.due_date),
        "incoming_total": sum(s.amount for s in incoming),
        "outgoing_total": sum(e.amount for e in outgoing),
        "overdue_in": [s for s in incoming if s.due_date < today],
        "overdue_out": [e for e in outgoing if e.due_date < today],
    }


def facts(book, ledger: Ledger) -> dict:
    """A compact, JSON-safe summary — what the agent and the deck read.

    Kept deliberately small: the agent works better on twenty exact numbers
    than on a dump of every row, and a smaller context is a cheaper call.
    """
    pos = position(book, ledger)
    week = due_this_week(book, ledger)
    return {
        "cash_came_in": round(pos["came_in"]),
        "cash_went_out": round(pos["went_out"]),
        "net_cash": round(pos["net"]),
        "still_to_collect": round(pos["to_collect"]),
        "still_to_pay": round(pos["to_pay"]),
        "total_earned": round(pos["earned"]),
        "margin": round(pos["margin"]),
        "top_expense_categories": [
            {"category": c, "amount": round(v)} for c, v in by_category(ledger)[:5]
        ],
        "monthly": [
            {"month": r["label"], "in": round(r["in"]), "out": round(r["out"])}
            for r in by_month(book, ledger)
        ],
        "due_next_7_days": {
            "coming_in": round(week["incoming_total"]),
            "going_out": round(week["outgoing_total"]),
            "overdue_receivables": len(week["overdue_in"]),
            "overdue_bills": len(week["overdue_out"]),
        },
    }
