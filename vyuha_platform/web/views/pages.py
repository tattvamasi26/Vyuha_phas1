"""Which view builds which page.

Each builder takes ``(client, account, request)`` and returns the page's own context; its
template is ``pages/<section>/<page>.html``. A page listed in ``nav.py`` with no entry here
shows the "being built" card, so the menu and the pages can land in either order.
"""

from __future__ import annotations

from . import analytics, data, finance, inbox, operations, sales, settings, team

REGISTRY = {
    ("sales", "overview"): sales.overview,
    ("sales", "bills"): sales.bills,
    ("sales", "customers"): sales.customers,
    ("sales", "collections"): sales.collections,
    ("operations", "record"): operations.record,
    ("operations", "inventory"): operations.inventory,
    ("operations", "purchases"): operations.purchases,
    ("operations", "invoices"): operations.invoices,
    ("finance", "overview"): finance.overview,
    ("finance", "pnl"): finance.pnl,
    ("finance", "balance"): finance.balance,
    ("finance", "cashflow"): finance.cashflow,
    ("finance", "dues"): finance.dues,
    ("finance", "gst"): finance.gst,
    ("finance", "reports"): finance.reports,
    ("team", "staff"): team.staff,
    ("team", "attendance"): team.attendance,
    ("team", "performance"): team.performance,
    ("team", "branches"): team.branches,
    ("analytics", "explore"): analytics.explore,
    ("analytics", "ratios"): analytics.ratios,
    ("analytics", "documents"): analytics.documents,
    ("inbox", "waiting"): inbox.waiting,
    ("inbox", "sent"): inbox.sent,
    ("inbox", "brief"): inbox.brief,
    ("inbox", "rules"): inbox.rules,
    ("inbox", "routines"): inbox.routines,
    ("data", "add"): data.add,
    ("data", "read"): data.read,
    ("data", "history"): data.history,
    ("settings", "business"): settings.business,
    ("settings", "billing"): settings.billing,
    ("settings", "stock"): settings.stock,
    ("settings", "access"): settings.access,
}
