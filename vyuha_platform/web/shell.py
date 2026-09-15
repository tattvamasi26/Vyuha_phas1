"""The context every page shares: who is asking, which business, the nav, the palette."""

from __future__ import annotations

from .. import access, gate, theme
from . import nav


def trade_key(client) -> str:
    """The business's trade, as a key ``theme.TRADES`` and ``catalog`` both know.

    Older records can carry a trade that is not in the list (the demo seed writes
    "hardware"), which would show as "Something else" and offer a generic starter
    list; for those the trade is worked out from the name, as onboarding does.
    """
    if client.trade in theme.TRADES:
        return client.trade
    return theme.guess(client.name, getattr(client, "industry", ""))


def trade_for(client) -> dict:
    return theme.trade(trade_key(client))


def base(request, account, *, area: str, client=None, section: str = "", page: str = "",
         title: str = "") -> dict:
    """What the shell needs on every page. ``area`` is "site" or "studio"."""
    operator = access.is_operator(account)
    ctx = {
        "account": account,
        "area": area,
        "client": client,
        "section": section,
        "page": page,
        "title": title,
        "flash": request.query_params.get("m", ""),
        "flash_kind": request.query_params.get("k", "ok"),
        "is_operator": operator,
        "is_master": access.is_master(account),
        "is_guest": bool(getattr(account, "is_guest", False)),
        "user_name": getattr(account, "name", "") or getattr(account, "email", ""),
        "user_initials": getattr(account, "initials", "V"),
        "nav_main": nav.MAIN,
        "nav_utility": nav.UTILITY,
        "phone_tabs": [nav.BY_KEY[k] for k in nav.PHONE_TABS],
        "businesses": access.businesses(account) if operator else [],
        "waiting": 0,
    }
    if client is not None:
        ctx["waiting"] = len(gate.waiting(client.slug))
        ctx["trade"] = trade_for(client)
    ctx["palette"] = palette(account, client, ctx["businesses"])
    return ctx


def palette(account, client, businesses) -> list[dict]:
    """Everything the command palette can jump to or do, in the order it lists them."""
    items: list[dict] = []
    if client is not None:
        root = f"/app/{client.slug}"
        items.append({"label": "Home", "hint": client.name, "href": root,
                      "group": "Go to", "icon": "house"})
        for sec in nav.SECTIONS[1:]:
            for pg in sec.pages:
                items.append({"label": f"{sec.label} · {pg.label}", "hint": pg.blurb,
                              "href": f"{root}/{sec.key}/{pg.key}", "group": "Go to",
                              "icon": sec.icon})
        items += [
            {"label": "Record a sale", "hint": "Operations · Record",
             "href": f"{root}/operations/record", "group": "Do", "icon": "receipt"},
            {"label": "Record an expense or purchase", "hint": "Operations · Purchases",
             "href": f"{root}/operations/purchases", "group": "Do", "icon": "wallet"},
            {"label": "Raise an invoice", "hint": "Operations · Invoices",
             "href": f"{root}/operations/invoices", "group": "Do", "icon": "file-text"},
            {"label": "Chase payments", "hint": "Sales · Collections",
             "href": f"{root}/sales/collections", "group": "Do", "icon": "hand-coins"},
        ]
    if access.is_operator(account):
        items += [
            {"label": "Onboarding Studio", "hint": "Every business being set up",
             "href": "/studio", "group": "Go to", "icon": "rocket"},
            {"label": "Onboard a business", "hint": "Start a new stepper",
             "href": "/studio/new", "group": "Do", "icon": "plus"},
        ]
        for b in businesses[:40]:
            items.append({"label": b.name, "hint": "Open this business",
                          "href": f"/app/{b.slug}", "group": "Businesses",
                          "icon": "building-2"})
    return items
