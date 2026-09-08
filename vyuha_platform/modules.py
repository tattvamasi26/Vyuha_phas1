"""The seven modules, and what lives in each.

This is the founder's own structure, drawn on paper, and it is a better map than
what the code had grown into. The difference is not cosmetic: the previous four
screens were named after *features* that happened to exist, and this is named
after **jobs somebody has**. A person opening Vyuha wants to run the day, look
at the business, do the books, move stock, manage people, or talk to customers —
and each of those is now one place instead of a thing you assemble from three.

    Vyuha — reads data from different sources and keeps it updated
    │
    ├── Desk ─────────── routine jobs · what needs a decision today
    ├── Dashboard ────── sales · inventory · transactions
    ├── Financials ───── balance sheet · cash flow · taxes · analytics
    ├── Operations ───── bought & sold · stock alerts · invoices
    ├── People ───────── branches · team · who is selling
    ├── Messages ─────── WhatsApp · email · what was sent
    └── Data ─────────── the sources, and what was read from each

The AI agent is not a module. It is the question box in the header of every one
of them, because a panel has to be remembered and a box in front of somebody
does not.

Two rules keep this from rotting back into a feature list:

**A module is a job, and its tabs are steps within that job.** If a new screen
does not answer "which job is this part of", it does not get a tab — it gets a
home inside one that exists.

**Nothing appears in two modules.** A figure lives where the job that acts on it
lives; every other screen links to it. Invoices are Operations, not Financials,
because raising one is an operation and reading the tax on it is not.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Tab:
    key: str
    label: str
    #: One line, shown under the module heading. Says what this tab answers, in
    #: the words somebody would use asking for it.
    blurb: str = ""


@dataclass(frozen=True)
class Module:
    key: str
    label: str
    #: What this module is for, in one sentence. Shown on the module's own
    #: landing and nowhere else, so the nav stays a nav.
    purpose: str
    tabs: tuple[Tab, ...] = ()
    #: Modules an operator sees but a shop floor never should.
    operator_only: bool = False

    @property
    def default(self) -> str:
        return self.tabs[0].key if self.tabs else ""

    def tab(self, key: str) -> Tab | None:
        return next((t for t in self.tabs if t.key == key), None)


MODULES: tuple[Module, ...] = (
    Module(
        "desk", "Desk",
        "What needs you today, and the routine that clears it.",
        (Tab("today", "Today", "Decisions waiting on you, worst first"),
         Tab("chase", "Follow-ups", "Who to contact, message already written"),
         Tab("register", "Register", "Who is in today")),
    ),
    Module(
        "dashboard", "Dashboard",
        "How the business is doing, right now and over time.",
        (Tab("sales", "Sales", "What is selling, to whom, and how that is moving"),
         Tab("inventory", "Inventory", "What is on the shelf and what it is worth"),
         Tab("transactions", "Transactions", "Every movement, in and out, in one list")),
    ),
    Module(
        "financials", "Financials",
        "The books, and what a bank or an accountant would ask for.",
        (Tab("position", "Balance sheet", "What you own, what you owe, what is left"),
         Tab("profit", "Profit & loss", "What was earned, what it cost, what is left"),
         Tab("cashflow", "Cash flow", "What actually moved, and what lands next"),
         Tab("taxes", "Taxes", "GST collected, GST paid, what is due"),
         Tab("analytics", "Analytics", "Ratios, concentration, break-even")),
    ),
    Module(
        "operations", "Operations",
        "The daily work: what was bought, what was sold, what to order, what to bill.",
        (Tab("record", "Record", "Enter a sale, a purchase, or stock that arrived"),
         Tab("alerts", "Stock alerts", "Below reorder, out of stock, and not moving"),
         Tab("invoices", "Invoices", "Raise a bill and send it")),
    ),
    Module(
        "people", "People",
        "Who works where, who is selling, and how the branches compare.",
        (Tab("team", "Team", "Branches and the people in them"),
         Tab("performance", "Performance", "Sales per person against target"),
         Tab("branches", "Branches", "Branch against branch")),
    ),
    Module(
        "messages", "Messages",
        "What goes out to customers, and what already has.",
        (Tab("brief", "Send a brief", "Today's alerts, as WhatsApp or email"),
         Tab("outbox", "Sent", "Everything that has left, and to whom")),
    ),
    Module(
        "data", "Data",
        "Where the numbers come from, and what Vyuha made of each file.",
        (Tab("sources", "Add data", "Send files, or point at a folder"),
         Tab("readback", "What was read", "Per file: understood, ignored, fixed"),
         Tab("history", "History", "Every file, every run")),
    ),
)

#: Setup is reachable but is **not** a module. Nothing on it is part of running
#: the business, and putting it in the module row would say that it was.
SETUP = Module(
    "setup", "Setup",
    "Done once. Nothing here needs looking at again.",
    (Tab("checklist", "Checklist", "What is still to be filled in"),
     Tab("business", "Business", "Contact, alerts and when to warn you"),
     Tab("billing", "Billing", "What prints at the top of your invoices"),
     Tab("levels", "Stock levels", "When Vyuha should warn you about an item"),
     Tab("access", "Access", "The private link and PIN for the owner")),
)

BY_KEY = {m.key: m for m in MODULES}
BY_KEY["setup"] = SETUP

#: The old addresses, and where each now lives. Every one of them is somewhere
#: in a bookmark, a flash redirect or a link inside a page, and a dead link is a
#: worse outcome than a redirect nobody notices.
MOVED = {
    "today": ("desk", "today"),
    "followups": ("desk", "chase"),
    "sell": ("operations", "record"),
    "stock": ("operations", "alerts"),
    "bills": ("operations", "invoices"),
    "money": ("financials", "position"),
    "setup": ("people", "team"),
}


def resolve(module: str, tab: str = "") -> tuple[Module, Tab]:
    """Land somewhere sensible whatever was asked for.

    An unknown module is the Desk rather than a 404: somebody following a stale
    link wants the product, not an apology.
    """
    m = BY_KEY.get(module)
    if m is None:
        moved = MOVED.get(module)
        m = BY_KEY[moved[0]] if moved else BY_KEY["desk"]
        tab = moved[1] if moved else ""
    t = m.tab(tab) or m.tabs[0]
    return m, t


def visible(client, account) -> list[Module]:
    """The modules this person, at this business, should be offered.

    Data hides for a business that types its entries — they have no files to
    send, and a screen that only ever says "nothing here" teaches somebody to
    stop looking at the nav.
    """
    out = []
    for m in MODULES:
        if m.key == "data" and getattr(client, "data_mode", "") == "books":
            continue
        if m.operator_only and getattr(account, "is_guest", False):
            continue
        out.append(m)
    return out
