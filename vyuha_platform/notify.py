"""The Notification Agent — what needs attention, and **who to tell**.

In the architecture this sits between the domain agents and the Communication
Agent: `Tax / Operations / Invoicing -> Notification -> Communication`. That
middle box was the one thing in the whole diagram with nothing behind it. The
product could already work out that a shelf was empty, and could already send a
WhatsApp message, and had no answer at all to the question in between — *whose
phone should this land on?* Everything went to the business's own number, which
is another way of saying everything went to the owner, which is another way of
saying the manager found out about the empty shelf when the owner told him.

Three rules shape it.

**It computes nothing.** Every event it routes was already worked out by an
agent that owns that number — `today.findings()` for stock, money, customers and
billing; `tax.events()` for filing deadlines. This module reads them and decides
recipients. The moment it starts deriving a figure of its own, there are two
answers to one question and eventually they differ, and the one on somebody's
phone is the one they act on.

**Only what a person can act on tonight.** `info` findings never go out. They sit
on the Desk, where somebody looking at the business will see them. A push
notification is an interruption, and a product that interrupts you about a
customer-concentration ratio teaches you to ignore it before it ever gets to
tell you the shop is out of cement. `PUSHED` is the whole editorial policy and
it is deliberately short.

**Nothing is said twice.** The queue is recomputed from the domain agents on
every tick and never stored — the same rule `followup.py` follows, and for the
same reason: a stored notification about an empty shelf is still there the day
after it was refilled. What persists is only the *fact that somebody was told*,
keyed on the event, so a cooldown can hold its tongue. An empty shelf is worth
one message every couple of days, not one every time a screen is opened.

**It never sends.** `gate.submit()` is the only way out and this hands off to
it, which is also how a filing reminder ends up held for approval while a stock
alert goes straight out. That difference is not this module's decision — it is
the gate reading the *kind* of thing being sent — which is exactly the split the
architecture asks for.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path

from . import atomic, gate, ledger, tax, today as today_mod

REPO = Path(__file__).resolve().parent.parent
NOTICES = REPO / "vyuha_data" / "notices"

#: Severities that are worth an interruption. See the module docstring — this
#: short tuple is the entire editorial policy, and lengthening it is how a
#: notification channel dies.
PUSHED = ("critical", "warning")

#: Tags that stay on the screen however loudly they are marked. `today.py` rates
#: "Vyuha has nothing to read yet" as critical, and for the Desk that is right —
#: it is the most important thing on an empty workspace. As a message it is
#: indefensible: the first thing a new client would hear from us is a complaint
#: about our own emptiness, sent to a phone, about something they are in the
#: middle of doing. A notification is about the *business*, never about the
#: product's setup state.
NEVER_PUSHED = frozenset({"setup"})


@dataclass(frozen=True)
class Audience:
    """Who cares about a class of event, and how often they can bear hearing it.

    `roles` is in order of who owns the problem, not seniority: an empty shelf
    is the manager's job before it is the owner's, even though the owner is told
    as well. `cooldown` is in days.
    """

    roles: tuple[str, ...]
    cooldown: int
    #: The gate kind, which decides whether this can send itself. Everything
    #: here is an `alert` except a filing, which the gate holds for approval.
    kind: str = "alert"


#: Event class -> who hears about it. Keyed on the tag `today.findings()`
#: already puts on each finding, so adding a finding with an existing tag needs
#: no change here, and adding a new tag fails loudly in `_audience` rather than
#: silently telling nobody.
AUDIENCES: dict[str, Audience] = {
    # An empty shelf is turning away orders right now, and the person who can
    # fix it is whoever buys stock.
    "stock":     Audience(("Manager", "Owner"), cooldown=2),
    # Money earned and not collected. The accountant chases it; the owner wants
    # to know it is being chased.
    "money":     Audience(("Accountant", "Owner"), cooldown=3),
    "billing":   Audience(("Accountant", "Owner"), cooldown=3),
    # A regular who stopped coming is a salesperson's call to make.
    "customers": Audience(("Salesperson", "Owner"), cooldown=7),
    "people":    Audience(("Manager", "Owner"), cooldown=3),
    "risk":      Audience(("Owner",), cooldown=14),
    # No "setup" entry: `NEVER_PUSHED` drops those before routing, and an
    # audience for something that can never be routed would read as though the
    # owner gets told when they do not.
    # From the engine's own alerts, for a business that sends files.
    "engine":    Audience(("Owner",), cooldown=2),
    # A missed GST deadline costs money every day it is missed, so this is the
    # one thing that may be repeated daily — and the one thing that waits for a
    # person, because the gate holds a filing.
    "filing":    Audience(("Accountant", "Owner"), cooldown=1, kind="filing"),
}

#: Used when a finding carries a tag nothing has claimed. Telling the owner is
#: the safe failure: a notification nobody needed is a nuisance, and one nobody
#: received is the bug this module exists to fix.
FALLBACK = Audience(("Owner",), cooldown=3)


def _today() -> str:
    return date.today().isoformat()


# --- what was already said ------------------------------------------------


@dataclass
class Notice:
    """One thing, told once, to one person."""

    key: str                     # the event's stable key
    to: str                      # the phone it went to
    who: str = ""                # the name, for the screen
    role: str = ""
    sent: str = field(default_factory=_today)
    title: str = ""
    #: The outbox id, so "was this actually delivered" is answerable.
    item: str = ""


def _path(slug: str) -> Path:
    return NOTICES / f"{slug}.json"


def load(slug: str) -> list[Notice]:
    rows = atomic.read_json(_path(slug), [])
    out = []
    for r in rows:
        if not isinstance(r, dict) or not r.get("key"):
            continue
        fields = {k: v for k, v in r.items() if k in Notice.__annotations__}
        fields.setdefault("to", "")
        out.append(Notice(**fields))
    return out


def save(slug: str, items: list[Notice]) -> None:
    NOTICES.mkdir(parents=True, exist_ok=True)
    # Bounded: this is a cooldown record, not the audit trail. `ledger` holds
    # the permanent history of what went out.
    atomic.write_json(_path(slug), [asdict(n) for n in items[-500:]])


def _days_since(iso: str) -> int:
    try:
        return (date.today() - date.fromisoformat(iso)).days
    except (ValueError, TypeError):
        return 10_000


def _recently_told(notices: list[Notice], key: str, to: str, cooldown: int) -> bool:
    """Has this person already heard this, recently enough to stay quiet?"""
    for n in notices:
        if n.key == key and n.to == to and _days_since(n.sent) < cooldown:
            return True
    return False


# --- the events -----------------------------------------------------------


@dataclass(frozen=True)
class Event:
    """Something a domain agent noticed, before anybody decided who hears it."""

    key: str
    severity: str
    title: str
    detail: str
    tag: str                 # which Audience claims it
    value: float = 0.0
    source: str = ""         # the agent that raised it

    @property
    def audience(self) -> Audience:
        return AUDIENCES.get(self.tag, FALLBACK)


def collect(client, book, led, org, invoices=None, *,
            as_of: date | None = None) -> list[Event]:
    """Everything the domain agents currently think is wrong, worst first.

    Nothing here is computed. `today.findings()` is the Operations, Invoicing
    and customer view — the same list the Desk ranks — and `tax.events()` is the
    Tax agent's. Reading the Desk's own list is deliberate: a notification that
    disagreed with the screen it links to would be worse than no notification.
    """
    events: list[Event] = []

    for f in today_mod.findings(client, book, led, org, invoices):
        if f.severity not in PUSHED:
            continue
        tag = (f.tags or ["setup"])[0]
        if tag in NEVER_PUSHED:
            continue
        events.append(Event(
            key=f.key, severity=f.severity, title=f.title, detail=f.detail,
            tag=tag, value=f.weight, source="operations"))

    for e in tax.events(client, invoices or [], led, as_of):
        if e["severity"] not in PUSHED:
            continue
        events.append(Event(
            key=e["key"], severity=e["severity"], title=e["title"],
            detail=e["detail"], tag="filing", value=e["value"], source="tax"))

    return events


# --- who hears it ---------------------------------------------------------


@dataclass(frozen=True)
class Recipient:
    to: str
    who: str
    role: str


def recipients(client, org, event: Event) -> list[Recipient]:
    """Whose phone this lands on.

    Reads the staff directory at send time rather than storing numbers on the
    event, so changing somebody's phone in one place changes it everywhere.
    Anybody without a number is skipped silently — that is a setup gap, and the
    People screen is where it should be complained about, not here.

    **The business's own number is the owner.** Almost nobody adds themselves to
    their own staff list, so an audience of ("Manager", "Owner") used to reach
    the manager and stop: the one person who definitely wanted to know that a
    shelf was empty was the one person not told, because they had never filled
    in a form saying they worked there. So when a role is wanted and no active
    staff member holds it, the business's WhatsApp number stands in for Owner.

    Duplicates are collapsed by number, which also means an owner who *has*
    added themselves as staff is not messaged twice.
    """
    wanted = event.audience.roles
    out: list[Recipient] = []
    seen: set[str] = set()

    for role in wanted:
        found = False
        for p in org.staff:
            if not p.active or p.role != role or not p.phone:
                continue
            found = True
            if p.phone in seen:
                continue
            seen.add(p.phone)
            out.append(Recipient(to=p.phone, who=p.name, role=p.role))

        if role == "Owner" and not found:
            phone = getattr(client, "phone", "")
            if phone and phone not in seen:
                seen.add(phone)
                out.append(Recipient(to=phone, who=client.name, role="Owner"))

    # Nobody in any of the wanted roles, and the owner was not among them: an
    # accountant-only event at a shop with no accountant still has to land
    # somewhere, and the person who owns the business is that somewhere.
    if not out and getattr(client, "phone", ""):
        out.append(Recipient(to=client.phone, who=client.name, role="Owner"))
    return out


# --- the message ----------------------------------------------------------


def compose(client, event: Event, to: Recipient) -> str:
    """One event, to one person. Deliberately not a brief.

    A routine job is a bundle somebody asked for at a time they chose; this is
    an interruption they did not. So it says one thing, says why it matters, and
    stops. Anything longer gets read as a newsletter, which is to say not read.
    """
    mark = "‼️" if event.severity == "critical" else "⚠️"
    lines = [f"*{client.name}*", "", f"{mark} {event.title}"]
    if event.detail:
        lines.append(event.detail)
    if to.role and to.role != "Owner":
        lines.append("")
        lines.append(f"_Sent to you as {to.role.lower()}._")
    lines.append("")
    lines.append("— Vyuha")
    return "\n".join(lines)[:1024]


# --- the run --------------------------------------------------------------


@dataclass
class NotifyResult:
    """What one pass actually did.

    Four outcome lists rather than one, because they are four different claims
    and only the first is "we told them". An earlier version bucketed everything
    that was not held into `sent`, which meant a message written and parked
    because no provider is connected — and a message a provider refused —
    both reported as delivered. That is the one thing the outbound side of this
    product is most careful never to say.
    """

    #: Actually left the machine.
    sent: list = field(default_factory=list)
    #: Waiting on a named person to approve it. Never attempted.
    held: list = field(default_factory=list)
    #: Written and saved, for somebody to send by hand. Never attempted.
    drafted: list = field(default_factory=list)
    #: Attempted and refused by the provider.
    failed: list = field(default_factory=list)
    quiet: int = 0               # suppressed by a cooldown
    unaddressed: list = field(default_factory=list)
    #: Outbox ids created by this pass. The orchestrator needs them so its
    #: retry sweep does not immediately re-attempt something that failed four
    #: milliseconds ago — a retry against an unchanged condition is the same
    #: attempt, and it burns the budget before anything can clear.
    items: list = field(default_factory=list)

    @property
    def raised(self) -> list:
        """Every notification this pass created, however it ended up."""
        return self.sent + self.held + self.drafted + self.failed

    @property
    def total(self) -> int:
        return len(self.raised)

    def __str__(self) -> str:
        if not self.total:
            return "nothing to tell anybody"
        bits = []
        for label, rows in (("sent", self.sent),
                            ("held for approval", self.held),
                            ("drafted", self.drafted),
                            ("could not send", self.failed)):
            if rows:
                bits.append(f"{len(rows)} {label}")
        return ", ".join(bits)


def run(client, settings, ctx: dict, *, as_of: date | None = None) -> NotifyResult:
    """Decide who to tell, and hand each message to the gate.

    `ctx` is what the orchestrator loaded once for this tenant, so ten
    notifications read one snapshot of the book rather than triggering ten
    analyses. Never sends: `gate.submit()` decides whether a thing may send
    itself, and a filing may not.
    """
    result = NotifyResult()
    events = collect(client, ctx.get("book"), ctx.get("ledger"),
                     ctx.get("org"), ctx.get("invoices"), as_of=as_of)
    if not events:
        return result

    notices = load(client.slug)
    fresh: list[Notice] = []

    for event in events:
        audience = event.audience
        people_to_tell = recipients(client, ctx.get("org"), event)
        if not people_to_tell:
            # Nobody in the role, and no number on the business either. Worth
            # saying once on a screen rather than failing quietly every tick.
            result.unaddressed.append(event.title)
            continue

        for who in people_to_tell:
            if _recently_told(notices + fresh, event.key, who.to, audience.cooldown):
                result.quiet += 1
                continue

            item = gate.submit(
                client, settings, kind=audience.kind, channel="whatsapp",
                to=who.to, body=compose(client, event, who),
                source=f"notify:{event.source}:{event.key}")

            fresh.append(Notice(key=event.key, to=who.to, who=who.who,
                                role=who.role, title=event.title, item=item.id))
            result.items.append(item.id)
            bucket = {gate.SENT: result.sent, gate.HELD: result.held,
                      gate.DRAFTED: result.drafted}.get(item.status, result.failed)
            bucket.append(f"{event.title} → {who.who}")

    if fresh:
        save(client.slug, notices + fresh)
        ledger.log("notify.ran",
                   f"{len(fresh)} notification(s): {result}", client=client)
    return result


def preview(client, ctx: dict, *, as_of: date | None = None) -> list[dict]:
    """What would go out, and to whom, without sending any of it.

    Worth having as its own function rather than a flag on `run`: an operator
    setting a business up needs to see who Vyuha thinks it should be telling
    *before* it starts telling them, and a dry-run flag on a sending function is
    one typo away from not being a dry run.
    """
    notices = load(client.slug)
    rows = []
    for event in collect(client, ctx.get("book"), ctx.get("ledger"),
                         ctx.get("org"), ctx.get("invoices"), as_of=as_of):
        to = recipients(client, ctx.get("org"), event)
        rows.append({
            "event": event,
            "to": to,
            "held": event.audience.kind == "filing",
            "quiet": [r for r in to
                      if _recently_told(notices, event.key, r.to,
                                        event.audience.cooldown)],
        })
    return rows


def history(slug: str, limit: int = 60) -> list[Notice]:
    """Who was told what, newest first."""
    return sorted(load(slug), key=lambda n: n.sent, reverse=True)[:limit]
