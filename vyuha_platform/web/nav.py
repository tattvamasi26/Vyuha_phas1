"""The site map, as data: sections, their pages, and what each page is for.

The navigation, the section headers, the command palette and the routes all read from
here, so a page is added in one place. A page is listed only once it exists — a menu that
offers "coming soon" teaches somebody to stop opening it.

``classic`` names the classic workspace screen (``/c/<slug>/<classic>``) that did the same
job. Nothing links there any more; it is kept so the classic addresses can be pointed at
their new pages when the classic screens are retired.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Page:
    key: str
    label: str
    blurb: str
    classic: str = ""


@dataclass(frozen=True)
class Section:
    key: str
    label: str
    icon: str
    blurb: str
    pages: tuple[Page, ...] = ()
    #: "main" sits in the primary nav; "utility" below it.
    group: str = "main"

    def page(self, key: str) -> Page | None:
        return next((p for p in self.pages if p.key == key), None)


SECTIONS: tuple[Section, ...] = (
    Section("home", "Home", "house", "What needs you today, and how the business is doing."),
    Section(
        "sales", "Sales", "trending-up",
        "What is selling, who is buying, and who still has to pay.",
        (Page("overview", "Overview", "What is selling, to whom, and how that is moving",
              "dashboard/sales"),
         Page("bills", "Bills", "Every bill, searchable — mark paid, send the receipt",
              "dashboard/transactions"),
         Page("customers", "Customers", "Each customer's history and what they owe",
              "dashboard/sales"),
         Page("collections", "Collections", "Who owes what, since when — message already written",
              "desk/chase"))),
    Section(
        "operations", "Operations", "package",
        "The daily work: record, stock, purchases and bills.",
        (Page("record", "Record", "A sale, or a new item for the shelf", "operations/record"),
         Page("inventory", "Inventory", "What is on the shelf, what to order, counts",
              "operations/alerts"),
         Page("purchases", "Purchases & expenses", "Supplier bills and every other payment",
              "operations/record"),
         Page("invoices", "Invoices", "Raise GST invoices and send them",
              "operations/invoices"))),
    Section(
        "finance", "Finance", "wallet",
        "Cash, profit, dues and tax — the numbers a bank or CA asks for.",
        (Page("overview", "Overview", "Cash in hand, profit, and what lands this week",
              "financials/position"),
         Page("pnl", "Profit & loss", "What was earned, what it cost, what is left",
              "financials/profit"),
         Page("balance", "Balance sheet", "What you own, what you owe", "financials/position"),
         Page("cashflow", "Cash flow", "What actually moved, month by month",
              "financials/cashflow"),
         Page("dues", "Receivables & payables", "Money to come in and money to go out, by age",
              "financials/position"),
         Page("gst", "GST", "Tax collected, tax paid, what is due and when",
              "financials/taxes"),
         Page("reports", "Reports", "Statements to download or send to your CA"))),
    Section(
        "team", "Team", "users",
        "Who works where, who came in, and who is selling.",
        (Page("staff", "Staff", "People, roles and branches", "people/team"),
         Page("attendance", "Attendance", "Today's register", "desk/register"),
         Page("performance", "Performance", "Sales per person against target, and commission",
              "people/performance"),
         Page("branches", "Branches", "Branch against branch", "people/branches"))),
    Section(
        "analytics", "Analytics", "chart-column",
        "Any question of your numbers, and documents made from them.",
        (Page("explore", "Explore", "Group, filter and chart your sales", "dashboard/sales"),
         Page("ratios", "Ratios", "Margins, concentration, break-even", "financials/analytics"),
         Page("documents", "Documents", "Decks and PDFs made from your numbers"))),
    Section(
        "inbox", "Inbox", "inbox",
        "Messages waiting to go, what went, and who hears about what.",
        (Page("waiting", "Waiting", "Drafts to send and anything held for approval",
              "messages/approvals"),
         Page("sent", "Sent", "Everything that left, and to whom", "messages/outbox"),
         Page("brief", "Send a brief", "Today's alerts, as WhatsApp or email", "messages/brief"),
         Page("rules", "Who gets told", "Which alert reaches which person", "messages/notices"),
         Page("routines", "Routines", "Scheduled briefs — who gets what, and when",
              "setup/routines")),
        group="utility"),
    Section(
        "data", "Data", "database",
        "Where the numbers come from, and what was read from each file.",
        (Page("add", "Add data", "Send files or point at a folder", "data/sources"),
         Page("read", "What was read", "Per file: understood, ignored, fixed", "data/readback"),
         Page("history", "History", "Every file and every run", "data/history")),
        group="utility"),
    Section(
        "settings", "Settings", "settings",
        "The business, billing, stock levels and access.",
        (Page("business", "Business", "Contact details and when to warn you", "setup/business"),
         Page("billing", "Billing", "What prints on your invoices", "setup/billing"),
         Page("stock", "Stock levels", "When Vyuha should warn you about an item", "setup/levels"),
         Page("access", "Access", "The private link and PIN for the owner", "setup/access")),
        group="utility"),
)

BY_KEY = {s.key: s for s in SECTIONS}
MAIN = tuple(s for s in SECTIONS if s.group == "main")
UTILITY = tuple(s for s in SECTIONS if s.group == "utility")

#: Classic addresses that are not any page's ``classic`` above, and where each job lives
#: now. An empty target is Home.
_CLASSIC_ALSO = {
    "": "", "desk": "", "desk/today": "",
    "desk/chase": "sales/collections",
    "desk/register": "team/attendance",
    "dashboard": "sales/overview",
    "data": "data/add",
    "financials/analytics": "analytics/ratios",
}


def site_path(slug: str, href: str) -> str:
    """The site's page for a classic address — for links domain code still writes in
    classic form (``today.findings`` builds ``/c/<slug>/desk/chase``). Anything else is
    returned unchanged; an unknown classic screen lands on Home rather than on a 404."""
    prefix = f"/c/{slug}"
    if not (href == prefix or href.startswith(prefix + "/") or href.startswith(prefix + "?")):
        return href
    rest, _, query = href[len(prefix):].lstrip("/").partition("?")
    target = _CLASSIC_ALSO.get(rest)
    if target is None:
        target = next((f"{s.key}/{p.key}" for s in SECTIONS for p in s.pages
                       if p.classic == rest), "")
    return f"/app/{slug}" + (f"/{target}" if target else "") + (f"?{query}" if query else "")

#: The phone's bottom bar: Home, Sales, the + in the middle, Operations, More.
PHONE_TABS = ("home", "sales", "operations")
