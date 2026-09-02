"""Branches, and the people who run them.

A distributor with two godowns does not have two businesses — he has one set of
customers, one price list and one bank account, split across two places whose
numbers he can never see side by side. That comparison is the whole feature.

The design keeps branches **optional and additive**, which matters because most
clients have exactly one:

* A ``Branch`` is a record here; ``Sale`` and ``Expense`` carry a ``branch`` id
  that defaults to empty. A business that never creates a branch sees nothing
  about branches anywhere, and every existing row stays valid.
* Rows written before a branch existed keep an empty id and are reported under
  **Unassigned** rather than being silently attributed to whichever branch
  happens to be first. Guessing here would corrupt the one number the feature
  exists to produce.

``Staff`` is a directory, not a login. Real per-person accounts belong on
``auth.Account``, and inventing a second identity system beside it would be a
mistake — so a staff record names who works where, and ``auth`` stays the only
answer to "who is asking".
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path

from . import atomic

REPO = Path(__file__).resolve().parent.parent
PEOPLE = REPO / "vyuha_data" / "people"

ROLES = ["Owner", "Manager", "Salesperson", "Accountant", "Delivery", "Helper", "Other"]

#: The bucket for rows that predate branches, or were entered without one.
UNASSIGNED = "unassigned"


def _today() -> str:
    return date.today().isoformat()


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:20] or "branch"


@dataclass
class Branch:
    id: str
    name: str
    place: str = ""
    phone: str = ""
    manager: str = ""
    opened: str = field(default_factory=_today)
    active: bool = True


#: What each role is allowed to see. Not enforced here — ``auth.py`` is the only
#: answer to "who is asking" and inventing a second identity system beside it
#: would be a mistake. This is what a staff login *would* be granted, and the
#: screen shows it, so the owner can reason about access before it exists.
SEES = {
    "Owner": ("everything", "Every branch, every figure, including margins."),
    "Manager": ("their branch", "Their own branch's sales, stock and customers. "
                                "No margins, no other branch."),
    "Accountant": ("the money", "Every financial statement. No stock operations."),
    "Salesperson": ("their own sales", "What they sold and to whom. No margins, "
                                       "no other person's numbers."),
    "Delivery": ("today's orders", "What has to go out today. Nothing else."),
    "Helper": ("stock only", "What is on the shelf. No money at all."),
    "Other": ("nothing yet", "Set a role to decide what they would see."),
}


@dataclass
class Staff:
    id: str
    name: str
    role: str = "Salesperson"
    branch: str = ""              # Branch.id
    phone: str = ""
    joined: str = field(default_factory=_today)
    active: bool = True
    #: Monthly sales target. Zero means untargeted — a helper or an accountant
    #: has no number to hit, and showing them at 0% of nothing is noise.
    target: float = 0.0
    #: Percentage of what they sell. Zero for salaried staff.
    commission_pct: float = 0.0

    @property
    def sees(self) -> tuple[str, str]:
        return SEES.get(self.role, SEES["Other"])


@dataclass
class Attendance:
    """One person, one day. Absence is recorded, not inferred from silence.

    A missing row means nobody marked the register that day — which is a
    different thing from being absent, and conflating them turns a forgotten
    Tuesday into somebody's unpaid leave.
    """
    staff: str
    day: str
    state: str = "present"        # present | absent | half | leave
    note: str = ""


@dataclass
class Transfer:
    """Stock moved between godowns.

    Not a sale and not a purchase: the business still owns it, so total stock is
    unchanged and only its location moves. Recording it as a sale out of one
    branch and a purchase into the other would inflate both revenue and costs.
    """
    id: str
    date: str
    sku: str
    item: str
    qty: float
    from_branch: str
    to_branch: str
    note: str = ""
    by: str = ""                  # Staff.id who moved it


@dataclass
class Org:
    slug: str
    branches: list[Branch] = field(default_factory=list)
    staff: list[Staff] = field(default_factory=list)
    attendance: list[Attendance] = field(default_factory=list)
    transfers: list[Transfer] = field(default_factory=list)

    @property
    def has_branches(self) -> bool:
        """One branch is not a multi-branch business — do not show the feature."""
        return len([b for b in self.branches if b.active]) > 1

    def branch(self, branch_id: str) -> Branch | None:
        return next((b for b in self.branches if b.id == branch_id), None)

    def name_of(self, branch_id: str) -> str:
        b = self.branch(branch_id)
        return b.name if b else "Unassigned"

    def staff_at(self, branch_id: str) -> list[Staff]:
        return [s for s in self.staff if s.branch == branch_id and s.active]

    def person(self, staff_id: str) -> Staff | None:
        return next((s for s in self.staff if s.id == staff_id), None)


# ------------------------------------------------------------------ persistence

def _path(slug: str) -> Path:
    PEOPLE.mkdir(parents=True, exist_ok=True)
    return PEOPLE / f"{slug}.json"


def load(slug: str) -> Org:
    path = _path(slug)
    if not path.exists():
        return Org(slug=slug)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return Org(slug=slug)

    def build(cls, rows):
        out = []
        for r in rows:
            known = {k: v for k, v in r.items() if k in cls.__dataclass_fields__}
            out.append(cls(**known))
        return out

    return Org(slug=slug,
               branches=build(Branch, raw.get("branches", [])),
               staff=build(Staff, raw.get("staff", [])),
               attendance=build(Attendance, raw.get("attendance", [])),
               transfers=build(Transfer, raw.get("transfers", [])))


def save(org: Org) -> None:
    atomic.write_json(_path(org.slug), {
        "branches": [asdict(b) for b in org.branches],
        "staff": [asdict(s) for s in org.staff],
        "attendance": [asdict(a) for a in org.attendance],
        "transfers": [asdict(t) for t in org.transfers],
    })


# --------------------------------------------------------------------- editing

def add_branch(slug: str, name: str, place: str = "", phone: str = "",
               manager: str = "") -> tuple[Org, str]:
    org = load(slug)
    name = name.strip()
    if not name:
        return org, "A branch needs a name."
    if any(b.name.lower() == name.lower() for b in org.branches):
        return org, f"{name} is already on the list."

    base = _slug(name)
    taken = {b.id for b in org.branches}
    bid = base if base not in taken else f"{base}-{uuid.uuid4().hex[:4]}"
    org.branches.append(Branch(id=bid, name=name, place=place.strip(),
                               phone=phone.strip(), manager=manager.strip()))
    save(org)
    return org, f"Added {name}."


def delete_branch(slug: str, branch_id: str) -> tuple[Org, str]:
    """Deactivate rather than delete — sales already point at this id."""
    org = load(slug)
    b = org.branch(branch_id)
    if b is None:
        return org, "That branch is already gone."
    b.active = False
    for s in org.staff:
        if s.branch == branch_id:
            s.branch = ""
    save(org)
    return org, f"Closed {b.name}. Its past sales stay on the books."


def add_staff(slug: str, name: str, role: str = "Salesperson", branch: str = "",
              phone: str = "", target=0, commission=0) -> tuple[Org, str]:
    org = load(slug)
    name = name.strip()
    if not name:
        return org, "A person needs a name."
    org.staff.append(Staff(id=uuid.uuid4().hex[:8], name=name,
                           role=(role or "Salesperson"), branch=branch,
                           phone=phone.strip(), target=_num(target),
                           commission_pct=_num(commission)))
    save(org)
    where = f" at {org.name_of(branch)}" if branch else ""
    return org, f"Added {name}{where}."


def _num(value, default: float = 0.0) -> float:
    try:
        return float(str(value).replace(",", "").strip() or default)
    except (TypeError, ValueError):
        return default


def set_target(slug: str, staff_id: str, target, commission) -> tuple[Org, str]:
    org = load(slug)
    person = org.person(staff_id)
    if person is None:
        return org, "That person is gone."
    person.target = _num(target)
    person.commission_pct = _num(commission)
    save(org)
    return org, f"{person.name}'s target is now {person.target:,.0f} a month."


def mark_attendance(slug: str, staff_id: str, state: str = "present",
                    day: str = "") -> tuple[Org, str]:
    """One row per person per day; marking again corrects it rather than adding."""
    org = load(slug)
    person = org.person(staff_id)
    if person is None:
        return org, "That person is gone."
    day = (day or _today())[:10]
    org.attendance = [a for a in org.attendance
                      if not (a.staff == staff_id and a.day == day)]
    org.attendance.append(Attendance(staff=staff_id, day=day, state=state))
    save(org)
    return org, f"{person.name} marked {state} for {day}."


def transfer_stock(slug: str, sku: str, item: str, qty, from_branch: str,
                   to_branch: str, note: str = "") -> tuple[Org, str]:
    """Move stock between godowns. Total stock is unchanged by design."""
    org = load(slug)
    amount = _num(qty)
    if amount <= 0:
        return org, "How many are moving?"
    if from_branch == to_branch:
        return org, "Those are the same branch."
    org.transfers.append(Transfer(
        id=uuid.uuid4().hex[:8], date=_today(), sku=sku, item=item, qty=amount,
        from_branch=from_branch, to_branch=to_branch, note=note.strip()))
    save(org)
    return org, (f"{amount:g} × {item} moved from {org.name_of(from_branch)} "
                 f"to {org.name_of(to_branch)}.")


def today_register(org: Org, day: str = "") -> list[dict]:
    """Who is in today, and who has not been marked at all."""
    day = (day or _today())[:10]
    marked = {a.staff: a.state for a in org.attendance if a.day == day}
    return [{"id": s.id, "name": s.name, "role": s.role,
             "branch": org.name_of(s.branch) if s.branch else "",
             "state": marked.get(s.id, "unmarked")}
            for s in org.staff if s.active]


def by_person(org: Org, book, days: int = 30) -> list[dict]:
    """Sales per person against their target — "who is actually selling".

    Sales with no ``staff`` are reported as unattributed rather than shared out.
    A number split evenly across a team is a number nobody can act on.
    """
    from datetime import timedelta
    since = (date.today() - timedelta(days=days)).isoformat()

    sold: dict[str, dict] = {}
    unattributed = 0.0
    for sale in book.sales:
        if sale.date < since:
            continue
        if not sale.staff:
            unattributed += sale.amount
            continue
        row = sold.setdefault(sale.staff, {"revenue": 0.0, "bills": 0,
                                           "parties": set()})
        row["revenue"] += sale.amount
        row["bills"] += 1
        if sale.party:
            row["parties"].add(sale.party.strip().lower())

    rows = []
    for person in org.staff:
        if not person.active:
            continue
        got = sold.get(person.id, {"revenue": 0.0, "bills": 0, "parties": set()})
        pct = (got["revenue"] / person.target * 100) if person.target else None
        rows.append({
            "id": person.id, "name": person.name, "role": person.role,
            "branch": org.name_of(person.branch) if person.branch else "—",
            "revenue": round(got["revenue"]), "bills": got["bills"],
            "customers": len(got["parties"]),
            "target": round(person.target),
            "pct_of_target": round(pct, 1) if pct is not None else None,
            "on_track": (pct is not None and pct >= 100),
            "commission": round(got["revenue"] * person.commission_pct / 100)
                          if person.commission_pct else 0,
        })
    rows.sort(key=lambda r: r["revenue"], reverse=True)
    return [{"days": days, "unattributed": round(unattributed)}] + rows


def delete_staff(slug: str, staff_id: str) -> tuple[Org, str]:
    org = load(slug)
    person = org.person(staff_id)
    if person is None:
        return org, "That person is already gone."
    org.staff = [s for s in org.staff if s.id != staff_id]
    save(org)
    return org, f"Removed {person.name}."


# ------------------------------------------------------------------ comparison

def performance(org: Org, book, ledger=None) -> list[dict]:
    """One row per branch, plus Unassigned when anything lands there.

    Unassigned is included **only if it holds something** — a business that has
    always tagged its rows should not see a permanent empty row implying it
    forgot to.
    """
    rows: dict[str, dict] = {}

    def row(bid: str) -> dict:
        return rows.setdefault(bid, {
            "id": bid,
            "name": org.name_of(bid) if bid != UNASSIGNED else "Unassigned",
            "place": (org.branch(bid).place if org.branch(bid) else ""),
            "revenue": 0.0, "collected": 0.0, "owed": 0.0,
            "bills": 0, "spend": 0.0, "customers": set(), "staff": 0,
        })

    for b in org.branches:
        if b.active:
            row(b.id)

    for sale in book.sales:
        r = row(sale.branch or UNASSIGNED)
        r["revenue"] += sale.amount
        r["bills"] += 1
        if sale.paid:
            r["collected"] += sale.amount
        else:
            r["owed"] += sale.amount
        if sale.party:
            r["customers"].add(sale.party.strip().lower())

    for expense in getattr(ledger, "expenses", []):
        row(expense.branch or UNASSIGNED)["spend"] += expense.amount

    if UNASSIGNED in rows and not rows[UNASSIGNED]["bills"] and not rows[UNASSIGNED]["spend"]:
        rows.pop(UNASSIGNED)

    out = []
    for r in rows.values():
        r["customers"] = len(r["customers"])
        r["staff"] = len(org.staff_at(r["id"])) if r["id"] != UNASSIGNED else 0
        r["net"] = r["revenue"] - r["spend"]
        out.append(r)

    out.sort(key=lambda r: r["revenue"], reverse=True)
    total = sum(r["revenue"] for r in out) or 1.0
    for r in out:
        r["share"] = r["revenue"] / total
    return out


def facts(org: Org, book, ledger=None) -> dict:
    """Compact summary for the agent and the deck."""
    rows = performance(org, book, ledger)
    people_rows = by_person(org, book)[1:] if book is not None else []
    register = today_register(org)
    return {
        "branch_count": len([b for b in org.branches if b.active]),
        "staff_count": len([s for s in org.staff if s.active]),
        "present_today": len([r for r in register if r["state"] == "present"]),
        "unmarked_today": len([r for r in register if r["state"] == "unmarked"]),
        "by_person": [{"name": r["name"], "role": r["role"], "branch": r["branch"],
                       "revenue_30d": r["revenue"], "target": r["target"],
                       "pct_of_target": r["pct_of_target"]}
                      for r in people_rows[:10]],
        "transfers_recorded": len(org.transfers),
        "branches": [
            {"name": r["name"], "revenue": round(r["revenue"]),
             "bills": r["bills"], "customers": r["customers"],
             "spend": round(r["spend"]), "share_of_revenue": round(r["share"], 3)}
            for r in rows
        ],
    }
