"""Routine jobs — the CEO's eight o'clock brief, and everything like it.

The architecture is emphatic that these are **configuration, not code**: a
routine is a schedule that calls agents which already exist and hands the result
to the gate. If a new client request means writing a new agent, the request was
modelled wrong.

So there is no per-routine Python here. A `Routine` names:

* **who** it is for — a member of staff, by id, with their own number
* **when** it fires — a time of day and which weekdays
* **what goes in it** — a list of `SECTIONS` keys, each of which is a call into
  an agent that is already built and already tested
* **how it leaves** — always through `gate.submit()`, never directly

Adding "a Friday stock summary for the purchase head" is a row in a JSON file.
Adding a new *kind* of content is one entry in `SECTIONS` and one small function
that reads from existing analysis. That is the line, and it is the difference
between a platform and a pile of bespoke scripts.

**Why the register section exists.** An owner reading a brief wants to know the
shop opened. It is the cheapest possible signal that the day is normal, and its
absence is the signal that it is not.

**Firing is idempotent per day.** `last_fired` is a date, checked before a
routine runs again, because a process restarted four times in a morning must not
send the same brief four times. That is a property of the record rather than of
the scheduler, so it survives the scheduler being replaced.
"""

from __future__ import annotations

import secrets
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time
from pathlib import Path

from . import atomic

REPO = Path(__file__).resolve().parent.parent
ROUTINES = REPO / "vyuha_data" / "routines"

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

#: Every section a routine can carry, and the one-line promise each makes. The
#: builder for each reads from an agent that already exists — nothing here
#: computes a number of its own, which is what keeps a routine configuration.
SECTIONS = {
    "decisions": ("What needs a decision", "The ranked list from the Desk"),
    "money":     ("Money position", "In hand, owed to you, owed by you"),
    "stock":     ("Stock warnings", "Below reorder, out, and not moving"),
    "chase":     ("Who to chase", "Overdue bills and customers gone quiet"),
    "selling":   ("Who is selling", "Each person against their target"),
    "register":  ("Who is in today", "The day's attendance, or that nobody marked it"),
}

#: Sections a person in this role has any business reading. A delivery hand does
#: not get the money position. This mirrors ``people.SEES`` rather than inventing
#: a second answer to the same question.
ROLE_SECTIONS = {
    "Owner":       tuple(SECTIONS),
    "Manager":     ("decisions", "stock", "chase", "selling", "register"),
    "Accountant":  ("money", "chase"),
    "Salesperson": ("selling", "chase"),
    "Delivery":    ("stock",),
    "Helper":      ("stock",),
    "Other":       (),
}


def _today() -> str:
    return date.today().isoformat()


@dataclass
class Routine:
    id: str
    name: str
    #: ``people.Staff.id``. Blank means the business's own WhatsApp number —
    #: the owner, before anybody has been added as staff.
    staff_id: str = ""
    to: str = ""                  # resolved at send time; stored for display
    at: str = "08:00"             # HH:MM, local
    days: list = field(default_factory=lambda: list(DAYS))
    sections: list = field(default_factory=lambda: ["decisions", "money"])
    channel: str = "whatsapp"
    active: bool = True
    last_fired: str = ""          # ISO date, so a restart cannot double-send
    created: str = field(default_factory=_today)

    @property
    def when(self) -> str:
        if len(self.days) == 7:
            return f"every day at {self.at}"
        if set(self.days) == {"Mon", "Tue", "Wed", "Thu", "Fri"}:
            return f"weekdays at {self.at}"
        return f"{', '.join(self.days)} at {self.at}"

    def due(self, now: datetime) -> bool:
        """Should this fire right now?

        Late is better than never: a routine whose time has passed today and
        which has not fired today is still due. A machine that was asleep at
        eight should send the brief at nine, not skip the day.
        """
        if not self.active or not self.to:
            return False
        if DAYS[now.weekday()] not in self.days:
            return False
        if self.last_fired == now.date().isoformat():
            return False
        try:
            hh, mm = (int(x) for x in self.at.split(":", 1))
        except ValueError:
            return False
        return now.time() >= time(hh, mm)


# --- storage --------------------------------------------------------------


def _path(slug: str) -> Path:
    return ROUTINES / f"{slug}.json"


def load(slug: str) -> list[Routine]:
    rows = atomic.read_json(_path(slug), [])
    out = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        fields = {k: v for k, v in r.items() if k in Routine.__annotations__}
        fields.setdefault("id", secrets.token_hex(4))
        fields.setdefault("name", "Routine")
        out.append(Routine(**fields))
    return out


def save(slug: str, items: list[Routine]) -> None:
    ROUTINES.mkdir(parents=True, exist_ok=True)
    atomic.write_json(_path(slug), [asdict(r) for r in items])


def add(slug: str, name: str, to: str, *, staff_id: str = "", at: str = "08:00",
        days: list | None = None, sections: list | None = None) -> tuple[Routine, str]:
    name = (name or "").strip()
    if not name:
        return None, "Give the routine a name."
    picked = [s for s in (sections or []) if s in SECTIONS]
    if not picked:
        return None, "Choose at least one thing to put in it."
    r = Routine(id=secrets.token_hex(4), name=name, staff_id=staff_id,
                to=(to or "").strip(), at=at or "08:00",
                days=[d for d in (days or DAYS) if d in DAYS] or list(DAYS),
                sections=picked)
    items = load(slug)
    items.append(r)
    save(slug, items)
    return r, f"“{name}” will go out {r.when}."


def toggle(slug: str, routine_id: str) -> str:
    items = load(slug)
    for r in items:
        if r.id == routine_id:
            r.active = not r.active
            save(slug, items)
            return f"“{r.name}” {'resumed' if r.active else 'paused'}."
    return "That routine no longer exists."


def remove(slug: str, routine_id: str) -> str:
    items = load(slug)
    keep = [r for r in items if r.id != routine_id]
    if len(keep) == len(items):
        return "That routine no longer exists."
    save(slug, keep)
    return "Routine deleted."


def mark_fired(slug: str, routine_id: str, when: date | None = None) -> None:
    items = load(slug)
    for r in items:
        if r.id == routine_id:
            r.last_fired = (when or date.today()).isoformat()
    save(slug, items)


# --- composing the bundle -------------------------------------------------


def _rs(amount) -> str:
    from vyuha import fmt
    return fmt.rupees(amount, symbol=fmt.RUPEE_TEXT, dash="-")


def compose(client, routine: Routine, ctx: dict) -> str:
    """Build the message, from agents that already exist.

    ``ctx`` carries what the orchestrator loaded once for this tenant — book,
    ledger, org, findings — so a routine never triggers its own re-analysis.
    Ten routines for ten people read the same numbers rather than ten times.
    """
    lines = [f"*{client.name}*", f"_{routine.name}_", ""]
    for key in routine.sections:
        builder = _BUILDERS.get(key)
        if builder is None:
            continue
        block = builder(client, ctx)
        if block:
            lines.append(block)
            lines.append("")
    lines.append("— Vyuha")
    text = "\n".join(lines).strip()
    # WhatsApp's practical ceiling, same as `channels.as_whatsapp`.
    return text[:1024]


def _b_decisions(client, ctx) -> str:
    findings = ctx.get("findings") or []
    if not findings:
        return "✅ Nothing needs a decision today."
    out = [f"*What needs you ({len(findings)})*"]
    for f in findings[:4]:
        mark = {"critical": "‼️", "warning": "⚠️"}.get(getattr(f, "severity", ""), "•")
        out.append(f"{mark} {getattr(f, 'title', '')}")
    if len(findings) > 4:
        out.append(f"…and {len(findings) - 4} more.")
    return "\n".join(out)


def _b_money(client, ctx) -> str:
    pos = ctx.get("position") or {}
    if not pos:
        return ""
    # `money.position` reports four numbers rather than two, because
    # earned-vs-collected is a distinction an owner cares about far more than
    # an accountant does. The brief carries the cash ones.
    return ("*Money*\n"
            f"In hand: {_rs(pos.get('net'))}\n"
            f"Owed to you: {_rs(pos.get('to_collect'))}\n"
            f"You owe: {_rs(pos.get('to_pay'))}")


def _b_stock(client, ctx) -> str:
    book = ctx.get("book")
    if book is None:
        return ""
    out_of = [i for i in book.items if i.stock_qty <= 0]
    # An empty shelf is already reported as out; listing it again under "below
    # reorder" makes the same item look like two problems.
    low = [i for i in book.items if i.low and i.stock_qty > 0]
    if not low and not out_of:
        return "*Stock* — nothing below reorder."
    parts = ["*Stock*"]
    if out_of:
        parts.append(f"❌ Out: {', '.join(i.name for i in out_of[:3])}")
    if low:
        parts.append(f"⚠️ Below reorder: {', '.join(i.name for i in low[:4])}")
    return "\n".join(parts)


def _b_chase(client, ctx) -> str:
    queue = ctx.get("queue") or []
    if not queue:
        return "*To chase* — nobody, everything is current."
    out = ["*To chase*"]
    for f in queue[:4]:
        out.append(f"• {getattr(f, 'party', '')} — {_rs(getattr(f, 'amount', 0))}")
    return "\n".join(out)


def _b_selling(client, ctx) -> str:
    rows = ctx.get("selling") or []
    sellers = [r for r in rows[1:] if r.get("revenue")]
    if not sellers:
        return ""
    out = ["*Who is selling* (30 days)"]
    for r in sellers[:4]:
        out.append(f"• {r['name']} — {_rs(r['revenue'])}")
    return "\n".join(out)


def _b_register(client, ctx) -> str:
    marked = ctx.get("register_marked")
    if marked is None:
        return ""
    total = ctx.get("register_total") or 0
    if not total:
        return ""
    if marked == 0:
        return "*Register* — nobody marked in yet today."
    return f"*Register* — {marked} of {total} marked in."


_BUILDERS = {
    "decisions": _b_decisions,
    "money": _b_money,
    "stock": _b_stock,
    "chase": _b_chase,
    "selling": _b_selling,
    "register": _b_register,
}
