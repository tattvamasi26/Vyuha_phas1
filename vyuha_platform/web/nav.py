"""The site map, as data: sections, their pages, and what each page is for.

The navigation, the section placeholders, the command palette and the routes all read
from here, so a page is added in one place. ``classic`` names the screen in the classic
workspace (``/c/<slug>/<classic>``) that does the job today, so every page of the new site
is useful from the first build — an unbuilt page says what is coming and opens the screen
that works now.
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
    #: The build phase that brings this section to life.
    phase: int = 1
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
         Page("bills", "Bills & orders", "Every bill, searchable, with its receipt and invoice",
              "dashboard/transactions"),
         Page("customers", "Customers", "Each customer's history, dues and statement",
              "dashboard/sales"),
         Page("collections", "Collections", "Who owes what, since when — message already written",
              "desk/chase"),
         Page("quotes", "Quotations", "Quote, send, follow up, turn into a bill")),
        phase=3),
    Section(
        "operations", "Operations", "package",
        "The daily work: record, stock, purchases and bills.",
        (Page("record", "Record", "A sale, a purchase, a payment, an expense, stock in or out",
              "operations/record"),
         Page("inventory", "Inventory", "What is on the shelf, what to order, counts and transfers",
              "operations/alerts"),
         Page("purchases", "Purchases", "Supplier bills, purchase orders and what you owe",
              "operations/record"),
         Page("invoices", "Invoices", "Raise GST invoices and send them",
              "operations/invoices")),
        phase=3),
    Section(
        "finance", "Finance", "wallet",
        "Cash, profit, dues and tax — the numbers a bank or CA asks for.",
        (Page("overview", "Overview", "Cash in hand, profit, and what lands this week",
              "financials/position"),
         Page("pnl", "Profit & loss", "What was earned, what it cost, what is left",
              "financials/profit"),
         Page("balance", "Balance sheet", "What you own, what you owe", "financials/position"),
         Page("cashflow", "Cash flow", "What actually moved, and what comes next",
              "financials/cashflow"),
         Page("dues", "Receivables & payables", "Money to come in and money to go out, by age",
              "financials/position"),
         Page("expenses", "Expenses", "Rent, salary, transport and every other head",
              "operations/record"),
         Page("gst", "GST & filings", "Tax collected, tax paid, what is due and when",
              "financials/taxes"),
         Page("reports", "Reports", "Statements to download or send to your CA")),
        phase=4),
    Section(
        "team", "Team", "users",
        "Who works where, who came in, and who is selling.",
        (Page("staff", "Staff & access", "People, roles and their own access links",
              "people/team"),
         Page("attendance", "Attendance", "Today's register and the month so far", "desk/register"),
         Page("performance", "Performance", "Sales per person against target, and commission",
              "people/performance"),
         Page("branches", "Branches", "Branch against branch", "people/branches")),
        phase=4),
    Section(
        "analytics", "Analytics", "chart-column",
        "Any question of your numbers, and documents made from them.",
        (Page("explore", "Explore", "Group, filter and chart any of your numbers",
              "dashboard/sales"),
         Page("reports", "Reports", "Ratios, margins, stock ageing, customer mix",
              "financials/analytics"),
         Page("insights", "Insights", "What changed, what is unusual, what to watch", "desk/today"),
         Page("documents", "Documents", "Decks and PDFs made from your numbers"),
         Page("quality", "Data quality", "What was read from each source, and how sure it is",
              "data/readback")),
        phase=4),
    Section(
        "inbox", "Inbox", "inbox",
        "Messages waiting to go, what went, and what came in.",
        (Page("waiting", "Waiting", "Drafts to send and anything held for approval",
              "messages/approvals"),
         Page("sent", "Sent", "Everything that left, and to whom", "messages/outbox"),
         Page("received", "Received", "WhatsApp and email that came in, ready to review"),
         Page("rules", "Who gets told", "Which alert reaches which person", "messages/notices"),
         Page("routines", "Routines", "Scheduled briefs — who gets what, and when",
              "setup/routines")),
        phase=4, group="utility"),
    Section(
        "data", "Data", "database",
        "Where the numbers come from, and how fresh they are.",
        (Page("add", "Add data", "Send files or point at a folder", "data/sources"),
         Page("feeds", "Feeds & health", "Every source, when it last sent, when it is due"),
         Page("imports", "Imports", "Every batch that came in — and undo", "data/history"),
         Page("review", "Review queue", "Rows read from photos and chats, waiting for a check"),
         Page("coverage", "Coverage", "Which months of which records are in", "data/readback")),
        phase=2, group="utility"),
    Section(
        "settings", "Settings", "settings",
        "The business, billing, stock levels, channels and access.",
        (Page("business", "Business", "Contact details and when to warn you", "setup/business"),
         Page("billing", "Billing & tax", "What prints on your invoices", "setup/billing"),
         Page("stock", "Stock levels", "When Vyuha should warn you about an item", "setup/levels"),
         Page("access", "Access", "The private link and PIN for the owner", "setup/access")),
        phase=4, group="utility"),
)

BY_KEY = {s.key: s for s in SECTIONS}
MAIN = tuple(s for s in SECTIONS if s.group == "main")
UTILITY = tuple(s for s in SECTIONS if s.group == "utility")

#: The phone's bottom bar: Home, Sales, the + in the middle, Operations, More.
PHONE_TABS = ("home", "sales", "operations")
