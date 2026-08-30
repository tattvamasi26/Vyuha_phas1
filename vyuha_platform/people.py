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


@dataclass
class Staff:
    id: str
    name: str
    role: str = "Salesperson"
    branch: str = ""              # Branch.id
    phone: str = ""
    joined: str = field(default_factory=_today)
    active: bool = True


@dataclass
class Org:
    slug: str
    branches: list[Branch] = field(default_factory=list)
    staff: list[Staff] = field(default_factory=list)

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
               staff=build(Staff, raw.get("staff", [])))


def save(org: Org) -> None:
    _path(org.slug).write_text(json.dumps({
        "branches": [asdict(b) for b in org.branches],
        "staff": [asdict(s) for s in org.staff],
    }, indent=2), encoding="utf-8")


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
              phone: str = "") -> tuple[Org, str]:
    org = load(slug)
    name = name.strip()
    if not name:
        return org, "A person needs a name."
    org.staff.append(Staff(id=uuid.uuid4().hex[:8], name=name,
                           role=(role or "Salesperson"), branch=branch,
                           phone=phone.strip()))
    save(org)
    where = f" at {org.name_of(branch)}" if branch else ""
    return org, f"Added {name}{where}."


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
    return {
        "branch_count": len([b for b in org.branches if b.active]),
        "staff_count": len([s for s in org.staff if s.active]),
        "branches": [
            {"name": r["name"], "revenue": round(r["revenue"]),
             "bills": r["bills"], "customers": r["customers"],
             "spend": round(r["spend"]), "share_of_revenue": round(r["share"], 3)}
            for r in rows
        ],
    }
