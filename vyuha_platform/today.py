"""What needs a decision today, ranked by what it costs to ignore.

Every one of these numbers was already being computed — sitting one click inside
a different panel, waiting for somebody to think to go looking. Nobody does. So
the findings come to the front, and the interface finally has an opinion.

Two rules decide everything here.

**Severity gates the order; money ranks within it.** Critical means it is
costing money right now — an empty shelf turning away orders today. Those come
first however small, because "you have run out" is not something to read below a
note about customer mix. Inside each band the biggest number wins, so a stockout
worth ₹40,000 outranks one worth ₹4,000 and neither outranks the other merely
because stock is listed before receivables somewhere in the code.

**Every finding is a sentence with one button.** Not a tile, not a chart. "Ramu
Stores is 66 days late — ₹83,200" with a Send button. If it cannot be phrased as
something to *do*, it is a report and belongs on another screen.

An empty list is a real answer, not an empty state. "Nothing needs you today" is
the most valuable thing this screen can say, and it should be said in one line
so the owner can close the app and get on with his morning.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from . import books, finance, followup, money as money_mod, people


@dataclass
class Finding:
    """One thing worth a decision, and the single action that resolves it."""

    key: str
    severity: str            # critical | warning | info
    title: str               # a sentence, not a label
    detail: str              # the number, or the evidence
    action: str              # what the button says — a verb
    href: str
    #: Rupees at stake — the sort key *within* a severity band. A category with
    #: no money attached gets a nominal weight so it still ranks below anything
    #: real.
    weight: float = 0.0
    tags: list[str] = field(default_factory=list)


_RANK = {"critical": 0, "warning": 1, "info": 2}


def _fmt(v: float) -> str:
    """Short Indian money, for a sentence rather than a table."""
    v = float(v or 0)
    if v >= 10_000_000:
        return f"₹{v / 10_000_000:.2f} crore"
    if v >= 100_000:
        return f"₹{v / 100_000:.2f} lakh"
    return f"₹{v:,.0f}"


#: How the engine's alert codes read as something to do. The engine already
#: ranks and phrases these for the client dashboard; Today needs a verb and a
#: place to go, which the alert does not carry.
_ALERT_ACTIONS = {
    "out_of_stock":  ("Order these", "stock", "critical"),
    "below_reorder": ("Order these", "stock", "critical"),
    "stockout_risk": ("Order these", "stock", "warning"),
    "dead_stock":    ("See them", "stock", "warning"),
    "overdue_ar":    ("Chase them", "money", "critical"),
    "revenue_drop":  ("See the month", "money", "warning"),
    "concentration": ("See customers", "money", "info"),
}


def _from_run(client, run) -> list[Finding]:
    """Findings for a business that sends files rather than typing entries.

    Their numbers live in the last run, not in ``books`` — the manual ledger is
    empty for them and always will be. Reading only the book is why an uploaded
    file used to leave Today saying "nothing to read yet" straight after
    successfully reading it.
    """
    out: list[Finding] = []
    for i, a in enumerate(run.alerts or []):
        code = a.get("code", "generic")
        action, screen, default_sev = _ALERT_ACTIONS.get(
            code, ("See the dashboard", "data", "info"))
        severity = a.get("severity") or default_sev
        entities = a.get("entities") or []
        detail = a.get("detail") or ""
        if entities:
            detail = detail or (", ".join(str(e) for e in entities[:3]))
        out.append(Finding(
            key=f"run:{code}:{i}", severity=severity,
            title=str(a.get("title") or code.replace("_", " ").title()),
            detail=detail[:160],
            action=action, href=f"/c/{client.slug}/{screen}",
            # The engine does not attach a rupee figure to every alert, so rank
            # by its own ordering: it already sorted these worst-first.
            weight=max(len(run.alerts) - i, 1) * 1000,
            tags=["engine"]))
    return out


def findings(client, book, ledger, org, invoices=None) -> list[Finding]:
    """Everything worth surfacing, worst first."""
    out: list[Finding] = []
    slug = client.slug
    summary = books.summary(book)
    invoices = invoices or []

    # A business that sends files has an empty book by definition. Its findings
    # come from the last run, and the book-derived ones below would all be zero.
    last = client.latest
    if client.data_mode != "books" and last is not None and last.status == "ok":
        out.extend(_from_run(client, last))
        week = money_mod.due_this_week(book, ledger)
        if week["outgoing"]:
            out.append(Finding(
                key="payables", severity="info",
                title=f"{len(week['outgoing'])} supplier bill(s) due this week — "
                      f"{_fmt(week['outgoing_total'])}",
                detail="Recorded here, not in the file you sent",
                action="See them", href=f"/c/{slug}/money",
                weight=week["outgoing_total"], tags=["money"]))
        out.sort(key=lambda f: (_RANK.get(f.severity, 3), -f.weight))
        return out

    # ---- stock that is costing sales right now
    gone = summary["out_of_stock"]
    low = [i for i in summary["low_stock"] if i.stock_qty > 0]
    if gone or low:
        # What it costs is the value of what cannot be sold: an out-of-stock
        # item's own reorder quantity at its selling rate is the honest proxy.
        at_stake = sum((i.reorder_level or 1) * i.rate for i in gone + low)
        names = ", ".join(i.name for i in (gone + low)[:3])
        if gone:
            title = (f"{gone[0].name} has run out"
                     + (f", {len(gone) - 1 + len(low)} more are low"
                        if len(gone) + len(low) > 1 else ""))
        else:
            title = f"{len(low)} item(s) are about to run out"
        out.append(Finding(
            key="stock", severity="critical" if gone else "warning",
            title=title,
            detail=f"{_fmt(at_stake)} of orders you would have to turn away · {names}",
            action="Order these", href=f"/c/{slug}/stock", weight=at_stake,
            tags=["stock"]))

    # ---- money already earned and not collected
    queue = followup.queue(slug, book)
    overdue = [f for f in queue if f.kind == "payment"]
    if overdue:
        worst = overdue[0]
        total = sum(f.amount for f in overdue)
        out.append(Finding(
            key="overdue", severity=worst.severity,
            title=(f"{worst.party} is {worst.days} days late — {_fmt(worst.amount)}"
                   if len(overdue) == 1 else
                   f"{len(overdue)} customers owe you {_fmt(total)}"),
            detail=(f"Worst is {worst.party}, {worst.days} days · "
                    f"the message is already written"),
            action="Send reminders", href=f"/c/{slug}/today#chase", weight=total,
            tags=["money"]))

    # ---- cash sitting on the shelf
    never = summary["never_sold"]
    if never:
        locked = sum(i.value for i in never)
        # By value, not by date added: "since 2 September" is meaningless when
        # every item was created the same day, and the money is the point anyway.
        biggest = max(never, key=lambda i: i.value)
        out.append(Finding(
            key="dead", severity="warning",
            title=f"{_fmt(locked)} is sitting in {len(never)} item(s) that never sold",
            detail=f"Most of it is {biggest.name} — {_fmt(biggest.value)}",
            action="See them", href=f"/c/{slug}/stock?show=dead", weight=locked,
            tags=["stock"]))

    # ---- a regular who stopped coming
    for f in [x for x in queue if x.kind == "dormant"][:2]:
        out.append(Finding(
            key=f"quiet:{f.key}", severity="warning",
            title=f"{f.party} hasn't ordered in {f.days} days",
            detail=f"Used to spend {_fmt(f.amount)} with you",
            action="Message them", href=f"/c/{slug}/today#chase",
            weight=f.amount * 0.25,      # past spend is a weaker claim than money owed
            tags=["customers"]))

    # ---- bills you owe, landing this week
    week = money_mod.due_this_week(book, ledger)
    if week["outgoing"]:
        due = week["outgoing_total"]
        soonest = week["outgoing"][0]
        out.append(Finding(
            key="payables", severity="warning" if week["overdue_out"] else "info",
            title=f"{len(week['outgoing'])} supplier bill(s) due this week — {_fmt(due)}",
            detail=f"Soonest: {soonest.party or soonest.category} on {soonest.due_date}",
            action="See them", href=f"/c/{slug}/money#payables", weight=due,
            tags=["money"]))

    # ---- sales with no bill against them
    billed = {sid for inv in invoices for sid in inv.sale_ids}
    unbilled = [s for s in book.sales if s.id not in billed and not s.paid]
    if unbilled:
        value = sum(s.amount for s in unbilled)
        out.append(Finding(
            key="unbilled", severity="info",
            title=f"{len(unbilled)} credit sale(s) have no invoice — {_fmt(value)}",
            detail="A customer who has no bill has a reason not to pay",
            action="Raise bills", href=f"/c/{slug}/sell#bills", weight=value * 0.5,
            tags=["billing"]))

    # ---- too much of the business in one place
    if book.sales:
        conc = finance.concentration(book, ledger)
        # "Cash sale" is walk-in trade, not a customer. Counting it as a
        # concentration risk warns him that half his revenue depends on
        # somebody who does not exist and cannot leave.
        named = [c for c in conc["customers"]
                 if c["party"].strip().lower() not in
                 {"cash sale", "cash", "walk-in", "walkin", "counter sale"}]
        if conc["risk"] == "high" and named and named[0]["share"] >= 0.25:
            top = named[0]
            out.append(Finding(
                key="concentration", severity="info",
                title=(f"Nearly half your revenue is one customer"
                       if top["share"] >= 0.45 else
                       f"{int(top['share'] * 100)}% of revenue is one customer"),
                detail=f"{top['party']} — {int(top['share'] * 100)}%. Losing them would hurt",
                action="See customers", href=f"/c/{slug}/money#customers",
                weight=top["amount"] * 0.1, tags=["risk"]))

    # ---- the register, if this business keeps one
    register = people.today_register(org)
    unmarked = [r for r in register if r["state"] == "unmarked"]
    if register and unmarked:
        out.append(Finding(
            key="register", severity="info",
            title=f"{len(unmarked)} of {len(register)} not marked in today",
            detail="Takes ten seconds and the month adds up on its own",
            action="Mark the register", href=f"/c/{slug}/today#register",
            weight=500, tags=["people"]))

    # ---- nothing to read from at all
    if not book.items and not book.sales and not (last and last.status == "ok"):
        out.append(Finding(
            key="empty", severity="critical",
            title="Vyuha has nothing to read yet",
            detail=("Send the stock or sales file you already keep — no need to "
                    "clean it up first" if client.data_mode == "upload" else
                    "Add what you sell and start recording sales"),
            action=("Add a file" if client.data_mode == "upload" else "Set up stock"),
            href=(f"/c/{slug}/data" if client.data_mode == "upload"
                  else f"/c/{slug}/stock"),
            weight=10 ** 9, tags=["setup"]))

    # Severity first. Sorting on money alone put "48% of revenue is one
    # customer" — worth noting, not urgent — above an empty shelf that is
    # turning away orders this morning.
    out.sort(key=lambda f: (_RANK.get(f.severity, 3), -f.weight))
    return out


def greeting(client, account) -> str:
    """A name and the time of day. Small, and the difference between a tool and a screen."""
    hour = __import__("datetime").datetime.now().hour
    part = ("Good morning" if hour < 12 else
            "Good afternoon" if hour < 17 else "Good evening")
    who = (client.contact or "").split()[0] if client.contact else ""
    return f"{part}{', ' + who if who else ''}"


def minutes(items: list[Finding]) -> str:
    """Roughly how long the list will take. Sets an expectation nobody else does."""
    if not items:
        return ""
    est = sum(3 if f.severity == "critical" else 2 for f in items)
    return f"about {est} minutes" if est > 1 else "a minute"


def chase_list(client, book) -> list:
    """The people behind the "send reminders" action, message already drafted."""
    return followup.queue(client.slug, book)


def summary_line(client, book, ledger) -> str:
    """One line of context under the greeting."""
    # A business that sends files has an empty book; its totals are on the run.
    last = client.latest
    if client.data_mode != "books" and last is not None and last.status == "ok":
        bits = [f"{_fmt(last.revenue)} in sales"]
        if last.stock_value:
            bits.append(f"{_fmt(last.stock_value)} of stock")
        if last.outstanding:
            bits.append(f"{_fmt(last.outstanding)} outstanding")
        return ", ".join(bits) + f" — read from {last.filename}."

    pos = money_mod.position(book, ledger)
    if not book.sales:
        return "Nothing recorded yet."
    return (f"{_fmt(pos['came_in'])} collected, {_fmt(pos['to_collect'])} still to come in, "
            f"{_fmt(pos['to_pay'])} to go out.")
