"""Settings — the business, what prints on a bill, stock levels, and who may open it.

Done once. Every form here posts to the handler the classic screens use, so a change made
on either is the same change.
"""

from __future__ import annotations

from ... import auth, books, invoice
# The function below is called access() too, and a module import would be shadowed by it.
from ...access import is_operator


def business(client, account, request) -> dict:
    return {"client": client}


def billing(client, account, request) -> dict:
    return {
        "gaps": invoice.missing(client),
        "states": sorted(invoice.STATES.items(), key=lambda kv: kv[1]),
        "templates": invoice.TEMPLATES,
        "chosen": client.invoice_template or "classic",
        "next_number": invoice.next_number(client)[0],
    }


def stock(client, account, request) -> dict:
    book = books.load(client.slug)
    items = sorted(book.items, key=lambda i: i.name.lower())
    return {
        "items": items,
        "unset": [i for i in items if not i.reorder_level],
    }


def access(client, account, request) -> dict:
    """The private link and its PIN. Operators only — a guest cannot re-share a workspace."""
    invite = auth.invite_for(client.slug)
    base = str(request.base_url).rstrip("/")
    return {
        "invite": invite,
        "link": f"{base}/w/{invite.token}" if invite else "",
        # A guest is on a shared link themselves, so they may not mint another.
        "may_share": is_operator(account) and not getattr(account, "is_guest", False),
        "fresh_pin": "",
    }
