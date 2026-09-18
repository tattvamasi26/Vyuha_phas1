"""Team — who works where, who came in, and who is selling.

``people.py`` owns every figure: sales per person against target, the branch comparison and
today's register. Marking the register and setting a target post to this site's own routes,
because the classic screens never had one.
"""

from __future__ import annotations

from datetime import date, timedelta

from ... import books, money, people

#: The roles the product knows. ``routines.ROLE_SECTIONS`` and ``notify.AUDIENCES`` both
#: key off these, so a typed-in role would silently hear about nothing.
ROLES = ["Owner", "Manager", "Accountant", "Salesperson", "Delivery", "Helper", "Other"]

#: How a day is marked, and what each reads as on the register.
STATES = [("present", "In"), ("half", "Half day"), ("leave", "Leave"), ("absent", "Out")]

#: The register shows a fortnight: long enough to see a pattern, short enough to fit.
REGISTER_DAYS = 14


def _short(v: float) -> str:
    from ..templating import money_short
    return money_short(v)


def _n(count: int, word: str, plural: str = "") -> str:
    return f"{count} {word if count == 1 else (plural or word + 's')}"


def staff(client, account, request) -> dict:
    org = people.load(client.slug)
    book = books.load(client.slug)
    rows = people.by_person(org, book)
    meta, per = rows[0], {r["id"]: r for r in rows[1:]}
    active = [s for s in org.staff if s.active]
    branches = [b for b in org.branches if b.active]
    no_phone = [s for s in active if not s.phone]
    return {
        "rows": [{"s": s, "sold": per.get(s.id), "branch": org.name_of(s.branch) if s.branch else ""}
                 for s in active],
        "branches": branches, "roles": ROLES, "days": meta["days"],
        "stats": [
            {"label": "People", "value": str(len(active)), "icon": "users",
             "sub": f"across {_n(len(branches) or 1, 'branch', 'branches')}"},
            {"label": "Reachable", "value": f"{len(active) - len(no_phone)}", "icon": "phone",
             "sub": ("everybody has a number" if not no_phone else
                     f"{_n(len(no_phone), 'person', 'people')} without one — they hear nothing"),
             "tone": "warn" if no_phone else ""},
            {"label": "Sold in 30 days", "value": _short(sum(r["revenue"] for r in rows[1:])),
             "icon": "trending-up", "sub": "attributed to a person"},
            {"label": "Unattributed", "value": _short(meta["unattributed"]), "icon": "circle-help",
             "sub": "sales with nobody against them",
             "tone": "warn" if meta["unattributed"] else ""},
        ],
    }


def attendance(client, account, request) -> dict:
    org = people.load(client.slug)
    today = date.today()
    days = [(today - timedelta(days=n)).isoformat() for n in range(REGISTER_DAYS)]
    marked = {(a.staff, a.day): a.state for a in org.attendance}
    register = people.today_register(org)
    counts: dict[str, int] = {}
    for r in register:
        counts[r["state"]] = counts.get(r["state"], 0) + 1
    return {
        "register": register, "states": STATES, "today_iso": today.isoformat(),
        "days": days,
        "grid": [{"person": s, "marks": [marked.get((s.id, d), "") for d in days]}
                 for s in org.staff if s.active],
        "labels": [date.fromisoformat(d).strftime("%a %d") for d in days],
        "stats": [
            {"label": "In today", "value": str(counts.get("present", 0)), "icon": "user-round",
             "sub": f"of {_n(len(register), 'person', 'people')}"},
            {"label": "Half day", "value": str(counts.get("half", 0)), "icon": "clock",
             "sub": "counted as half"},
            {"label": "Leave or out", "value": str(counts.get("leave", 0) + counts.get("absent", 0)),
             "icon": "calendar", "sub": "recorded, not assumed"},
            {"label": "Not marked", "value": str(counts.get("unmarked", 0)),
             "icon": "circle-help", "sub": "an unmarked day is a forgotten register",
             "tone": "warn" if counts.get("unmarked") else ""},
        ],
    }


def performance(client, account, request) -> dict:
    org, book = people.load(client.slug), books.load(client.slug)
    rows = people.by_person(org, book)
    meta, per = rows[0], rows[1:]
    on_track = [r for r in per if r["on_track"]]
    targeted = [r for r in per if r["target"]]
    return {
        "rows": per, "days": meta["days"], "unattributed": meta["unattributed"],
        "stats": [
            {"label": "Sold in 30 days", "value": _short(sum(r["revenue"] for r in per)),
             "icon": "trending-up", "sub": f"{_n(len(per), 'person', 'people')} selling"},
            {"label": "On target", "value": f"{len(on_track)}/{len(targeted)}" if targeted else "—",
             "icon": "target", "sub": "of those given a target",
             "tone": "ok" if targeted and len(on_track) == len(targeted) else ""},
            {"label": "Commission earned", "value": _short(sum(r["commission"] for r in per)),
             "icon": "hand-coins", "sub": "on the last 30 days"},
            {"label": "Unattributed", "value": _short(meta["unattributed"]), "icon": "circle-help",
             "sub": "not shared out — it would not be actionable",
             "tone": "warn" if meta["unattributed"] else ""},
        ],
    }


def branches(client, account, request) -> dict:
    org, book = people.load(client.slug), books.load(client.slug)
    led = money.load(client.slug)
    rows = people.performance(org, book, led)
    best = rows[0] if rows else None
    return {
        "rows": rows, "branches": [b for b in org.branches if b.active],
        "transfers": sorted(org.transfers, key=lambda t: t.date, reverse=True)[:10],
        "names": {b.id: b.name for b in org.branches},
        "stats": [
            {"label": "Branches", "value": str(len([b for b in org.branches if b.active])),
             "icon": "building-2", "sub": "open and trading"},
            {"label": "Biggest", "value": best["name"] if best else "—", "icon": "store",
             "sub": f"{int(best['share'] * 100)}% of revenue" if best else "nothing recorded"},
            {"label": "Revenue, all time", "value": _short(sum(r["revenue"] for r in rows)),
             "icon": "trending-up", "sub": "across every branch"},
            {"label": "Stock moved", "value": str(len(org.transfers)), "icon": "truck",
             "sub": "transfers between godowns"},
        ],
    }
