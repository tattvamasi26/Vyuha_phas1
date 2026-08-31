"""Who to chase, and what to say to them.

The queue is **computed from the book every time, never stored**. Storing a list
of follow-ups means the day a customer pays, the reminder to chase him is still
sitting there — and one wrong chase costs more goodwill than ten right ones
earn. So the only thing persisted is what the operator *did*: dismissed this,
snoozed that until Friday, sent the other. Everything else is re-derived.

That makes ``key`` the load-bearing idea. It is a stable identity for "chase
Ramu about bill B-104", so a decision taken on Monday still applies on Tuesday
even though the queue was rebuilt in between.

Three kinds, in the order they earn their place:

* **payment** — sold on credit, due date passed, still unpaid. The money is
  already yours; this is the only kind that is strictly owed.
* **dormant** — a repeat customer who has stopped coming. Nobody notices these
  without being told, which is exactly why they are worth telling.
* **quote** — a quotation sent, a week gone, no order. The trigger fires off
  ``quote.id`` / ``quote.status``; ``quotes.py`` is the other lane's item 6, so
  ``from_quotes()`` takes the list rather than importing it, and simply has
  nothing to do until that module lands.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

from . import atomic

REPO = Path(__file__).resolve().parent.parent
FOLLOWUPS = REPO / "vyuha_data" / "followups"

#: A customer who bought twice and then stopped for this long is worth a call.
DORMANT_DAYS = 45
#: Below two purchases we do not know a rhythm, so silence is not a signal.
DORMANT_MIN_PURCHASES = 2
#: How long after a quotation goes out before no answer means something.
QUOTE_DAYS = 7

OPEN, DONE, SNOOZED = "open", "done", "snoozed"


def _today() -> str:
    return date.today().isoformat()


def _days_since(iso: str) -> int:
    try:
        return (date.today() - date.fromisoformat(iso[:10])).days
    except (TypeError, ValueError):
        return 0


def _money(v: float) -> str:
    return f"₹{v:,.0f}"


@dataclass
class Followup:
    """One person worth contacting, and the reason."""

    key: str
    kind: str                      # payment | dormant | quote
    party: str
    party_phone: str = ""
    amount: float = 0.0
    days: int = 0                  # days overdue, or days silent
    reason: str = ""
    ref: str = ""                  # bill id or quote id
    severity: str = "warning"      # critical | warning | info
    status: str = OPEN
    snoozed_until: str = ""

    @property
    def actionable(self) -> bool:
        """Open, or a snooze that has run out."""
        if self.status == DONE:
            return False
        if self.status == SNOOZED and self.snoozed_until > _today():
            return False
        return True

    @property
    def has_phone(self) -> bool:
        return bool(self.party_phone)


# ------------------------------------------------------------- what was done

def _path(slug: str) -> Path:
    FOLLOWUPS.mkdir(parents=True, exist_ok=True)
    return FOLLOWUPS / f"{slug}.json"


def load_state(slug: str) -> dict:
    path = _path(slug)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_state(slug: str, state: dict) -> None:
    atomic.write_json(_path(slug), state)


def mark(slug: str, key: str, status: str, days: int = 3) -> str:
    """Record a decision against one follow-up. Returns a line for the flash."""
    state = load_state(slug)
    entry = {"status": status, "at": datetime.now().isoformat(timespec="seconds")}
    if status == SNOOZED:
        entry["until"] = (date.today() + timedelta(days=days)).isoformat()
    state[key] = entry
    save_state(slug, state)
    return {
        DONE: "Marked done — it will not come back.",
        SNOOZED: f"Snoozed for {days} day(s).",
        OPEN: "Back on the list.",
    }.get(status, "Updated.")


def _apply(items: list[Followup], state: dict) -> list[Followup]:
    for f in items:
        saved = state.get(f.key)
        if not saved:
            continue
        f.status = saved.get("status", OPEN)
        f.snoozed_until = saved.get("until", "")
    return items


# ------------------------------------------------------------ building the queue

def from_payments(book) -> list[Followup]:
    """Credit sales past their due date. The money is already earned."""
    out = []
    phones = book.customer_phones()
    for sale in book.sales:
        if sale.paid:
            continue
        due = sale.due_date or sale.date
        if not due or due >= _today():
            continue
        late = _days_since(due)
        out.append(Followup(
            key=f"payment:{sale.id}",
            kind="payment",
            party=sale.party or "Customer",
            party_phone=sale.party_phone or phones.get(sale.party.strip(), ""),
            amount=sale.amount,
            days=late,
            ref=sale.id,
            reason=f"{_money(sale.amount)} on bill {sale.id}, {late} day(s) past due.",
            severity="critical" if late >= 30 else "warning",
        ))
    return out


def from_dormant(book, dormant_days: int = DORMANT_DAYS) -> list[Followup]:
    """Repeat customers who stopped coming."""
    last_seen: dict[str, str] = {}
    counts: dict[str, int] = {}
    spend: dict[str, float] = {}
    for sale in book.sales:
        who = (sale.party or "").strip()
        if not who:
            continue
        counts[who] = counts.get(who, 0) + 1
        spend[who] = spend.get(who, 0.0) + sale.amount
        if sale.date > last_seen.get(who, ""):
            last_seen[who] = sale.date

    phones = book.customer_phones()
    out = []
    for who, when in last_seen.items():
        if counts[who] < DORMANT_MIN_PURCHASES:
            continue
        silent = _days_since(when)
        if silent < dormant_days:
            continue
        out.append(Followup(
            key=f"dormant:{who.lower()}",
            kind="dormant",
            party=who,
            party_phone=phones.get(who, ""),
            amount=spend[who],
            days=silent,
            reason=(f"Bought {counts[who]} time(s), {_money(spend[who])} in total, "
                    f"nothing for {silent} days."),
            severity="warning" if silent >= dormant_days * 2 else "info",
        ))
    return out


def from_quotes(quotes: list | None) -> list[Followup]:
    """Quotations sent with no order behind them.

    Takes the list rather than importing ``quotes.py``: that module belongs to
    the other lane and does not exist yet, and this one must not fail to import
    because of it. Anything with ``id``, ``party``, ``status``, ``amount`` and
    a date field works.
    """
    out = []
    for q in quotes or []:
        status = str(getattr(q, "status", "sent")).lower()
        if status in {"won", "lost", "ordered", "cancelled"}:
            continue
        when = getattr(q, "sent_at", "") or getattr(q, "date", "")
        waiting = _days_since(when)
        if waiting < QUOTE_DAYS:
            continue
        amount = float(getattr(q, "amount", 0) or 0)
        party = getattr(q, "party", "") or "Customer"
        out.append(Followup(
            key=f"quote:{getattr(q, 'id', when)}",
            kind="quote",
            party=party,
            party_phone=getattr(q, "party_phone", "") or "",
            amount=amount,
            days=waiting,
            ref=str(getattr(q, "id", "")),
            reason=f"Quotation for {_money(amount)} sent {waiting} days ago, no order yet.",
            severity="warning",
        ))
    return out


def queue(slug: str, book, quotes: list | None = None,
          dormant_days: int = DORMANT_DAYS, include_handled: bool = False) -> list[Followup]:
    """Everyone worth contacting today, most urgent first."""
    items = from_payments(book) + from_quotes(quotes) + from_dormant(book, dormant_days)
    items = _apply(items, load_state(slug))
    if not include_handled:
        items = [f for f in items if f.actionable]

    rank = {"critical": 0, "warning": 1, "info": 2}
    items.sort(key=lambda f: (rank.get(f.severity, 3), -f.days, -f.amount))
    return items


def counts(slug: str, book, quotes: list | None = None) -> dict:
    live = queue(slug, book, quotes)
    return {
        "total": len(live),
        "payment": sum(1 for f in live if f.kind == "payment"),
        "dormant": sum(1 for f in live if f.kind == "dormant"),
        "quote": sum(1 for f in live if f.kind == "quote"),
        "value": sum(f.amount for f in live if f.kind == "payment"),
        "no_phone": sum(1 for f in live if not f.has_phone),
    }


# ------------------------------------------------------------------- the message

def draft(f: Followup, business: str) -> str:
    """What to actually send. Polite, specific, and short enough to read.

    Written to be sent as-is by someone who would otherwise send nothing. The
    payment one names the bill and the amount because a vague reminder gets a
    vague answer; the dormant one asks a question, because a message that does
    not invite a reply does not get one.
    """
    # The whole name, not the first word. A customer is as often a firm as a
    # person -- "M/s Krishna Traders" greeted by its first word becomes
    # "Namaste M/s", and "Late Ramesh" becomes "Namaste Late". Using the name
    # exactly as it was entered can be slightly formal but is never wrong.
    who = f.party.strip() or "Sir"

    if f.kind == "payment":
        return (f"Namaste {who},\n\n"
                f"A gentle reminder about bill {f.ref} for {_money(f.amount)}, "
                f"which was due {f.days} day(s) ago.\n\n"
                f"If it is already paid, please ignore this and do let us know.\n\n"
                f"Thank you,\n{business}")

    if f.kind == "quote":
        return (f"Namaste {who},\n\n"
                f"Following up on the quotation we sent {f.days} days ago "
                f"for {_money(f.amount)}.\n\n"
                f"Happy to revise the rate or the quantity if that helps — "
                f"just tell us what works.\n\n"
                f"Thank you,\n{business}")

    return (f"Namaste {who},\n\n"
            f"It has been a while since your last order with us — we wanted to "
            f"check in and see how things are going.\n\n"
            f"If there is anything you need, or anything we can do better, "
            f"please tell us.\n\n"
            f"Thank you,\n{business}")


def facts(slug: str, book, quotes: list | None = None) -> dict:
    """Compact summary for the agent and the deck."""
    live = queue(slug, book, quotes)
    return {
        "open_followups": len(live),
        "money_to_chase": round(sum(f.amount for f in live if f.kind == "payment")),
        "customers_gone_quiet": [
            {"party": f.party, "days_silent": f.days, "past_spend": round(f.amount)}
            for f in live if f.kind == "dormant"
        ][:8],
        "overdue_payments": [
            {"party": f.party, "bill": f.ref, "amount": round(f.amount),
             "days_late": f.days}
            for f in live if f.kind == "payment"
        ][:8],
    }
