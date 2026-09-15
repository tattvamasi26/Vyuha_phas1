"""Which view builds which page.

Each builder takes ``(client, account, request)`` and returns the page's own context; its
template is ``pages/<section>/<page>.html``. A page listed in ``nav.py`` with no entry here
shows the "being built" card, so the menu and the pages can land in either order.
"""

from __future__ import annotations

from . import operations, sales

REGISTRY = {
    ("sales", "overview"): sales.overview,
    ("sales", "bills"): sales.bills,
    ("sales", "customers"): sales.customers,
    ("sales", "collections"): sales.collections,
    ("operations", "record"): operations.record,
    ("operations", "inventory"): operations.inventory,
    ("operations", "purchases"): operations.purchases,
    ("operations", "invoices"): operations.invoices,
}
