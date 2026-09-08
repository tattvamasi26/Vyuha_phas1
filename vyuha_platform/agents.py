"""The agent roster, as data — sixteen agents in five lanes.

The architecture spec is a document; this is the same thing in a form the code
can be held to. Its first implementation note asks that every agent carry an
explicit input and output contract "in code (schemas/types), not implicit", and
a contract nothing can check is a comment. So each `Agent` below names the
stores it may read and the stores it may write, `check()` reads those
declarations back against the rule the architecture cares most about, and a test
fails if a lane boundary is crossed.

    Onboarding -> Data Pipeline -> Domain -> Communication & Documents -> Routine Jobs

**The one rule worth enforcing mechanically.** "The backend never surfaces": no
domain agent may read from the raw store, or from cleaned records that have not
been classified yet. Everything else in the spec is a design principle a
reviewer can weigh; this one is a boundary, and the difference between a
boundary and a principle is whether something breaks when you cross it.

**Why this is data and not a base class.** Every agent here already exists as a
working module, written before the spec was drawn, and most of them are pure
functions over a book. Rewriting fourteen working modules to inherit from an
`Agent` ABC would buy a uniform `run()` nobody calls and lose the plainness that
makes them readable. What was actually missing was the *map* — which module is
which agent, and what each is allowed to touch — and a map is data.

`implemented_by` is therefore the honest column: it says where the agent lives
today. Two agents share `finance.py` and three share the engine, because the
spec's lanes are jobs rather than files, and splitting working modules to match
the diagram would be the diagram driving the code.
"""

from __future__ import annotations

from dataclasses import dataclass

# --- lanes ----------------------------------------------------------------

ONBOARDING = "onboarding"
PIPELINE = "pipeline"
DOMAIN = "domain"
COMMS = "comms"
ROUTINE = "routine"
ORCHESTRATION = "orchestration"

#: In flow order, which is also the order data moves. The blurb says what the
#: lane is *for*, in the words somebody would use asking about it.
LANES: tuple[tuple[str, str, str], ...] = (
    (ONBOARDING, "Onboarding",
     "Runs once per client: who they are, and everything that happened before us."),
    (PIPELINE, "Data pipeline",
     "Continuous, and never shown to anybody. Messy input becomes trusted records."),
    (DOMAIN, "Domain agents",
     "One product slice each. Everything a client reads comes from here."),
    (COMMS, "Communication & documents",
     "What needs attention, who is told, and what leaves the system."),
    (ROUTINE, "Routine jobs",
     "A schedule over agents that already exist. Configuration, not code."),
    (ORCHESTRATION, "Orchestration",
     "One per client. Schedules, retries, audits, and holds the only key."),
)

LANE_LABEL = {key: label for key, label, _ in LANES}

# --- stores ---------------------------------------------------------------
#
# The nouns the contracts are written in. Each is a real place on disk or a real
# in-flight structure, not a category invented to make the table look tidy.

#: Untouched client input. Exactly as it arrived, mess and all.
RAW = "raw"
#: Parsed and normalised, but nothing yet knows what it *means*.
CLEANED = "cleaned"
#: Tagged and routed. Everything below is domain-specific and safe to read.
LEDGER_STORE = "ledger"          # sales, expenses, cash
STOCK_STORE = "stock"            # items, levels, movement
INVOICE_STORE = "invoice"        # raised bills and their tax
TAX_STORE = "tax"                # liabilities and filing dates
TENANT_CONFIG = "tenant_config"  # branches, staff, thresholds, preferences
STATEMENTS = "statements"        # computed P&L, balance sheet, cash flow
DASHBOARD = "dashboard"          # the assembled client-facing view
EVENTS = "events"                # what a domain agent noticed
OUTBOX = "outbox"                # things trying to leave
FILES = "files"                  # generated PDFs, decks, invoices
AUDIT = "audit"                  # the append-only trail

#: Stores a domain agent may never read. This is "the backend never surfaces",
#: expressed as a set rather than a sentence in a docstring.
BACKEND_ONLY = frozenset({RAW, CLEANED})


@dataclass(frozen=True)
class Agent:
    """One agent, and the contract it is held to."""

    key: str
    name: str
    lane: str
    #: What it is responsible for, in one line.
    does: str
    reads: tuple[str, ...] = ()
    writes: tuple[str, ...] = ()
    #: Where this lives in the codebase today. The honest column — several
    #: agents share a module, and some live in the engine rather than here.
    implemented_by: str = ""

    @property
    def lane_label(self) -> str:
        return LANE_LABEL.get(self.lane, self.lane)


ROSTER: tuple[Agent, ...] = (
    # -- L0 onboarding, once per client
    Agent("client_setup", "Client Setup Agent", ONBOARDING,
          "Branches, people, roles and notification preferences.",
          reads=(TENANT_CONFIG,), writes=(TENANT_CONFIG,),
          implemented_by="people.py, app.onboard"),
    Agent("backfill", "Historical Backfill Agent", ONBOARDING,
          "Loads past years of statements and transactions so nothing starts empty.",
          reads=(RAW,), writes=(LEDGER_STORE, STOCK_STORE),
          implemented_by="library.py"),

    # -- L1 pipeline, continuous, never client-visible
    Agent("ingestion", "Ingestion Agent", PIPELINE,
          "Watches the drop-folder and every connected source, continuously.",
          reads=(RAW,), writes=(RAW,),
          implemented_by="sources.py, library.scan"),
    Agent("cleaning", "Cleaning & Normalization Agent", PIPELINE,
          "Dedupes, fixes formats, flags exceptions.",
          reads=(RAW,), writes=(CLEANED,),
          implemented_by="vyuha/clean.py"),
    Agent("classification", "Classification Router Agent", PIPELINE,
          "Tags each record and routes it to the store that owns it.",
          reads=(CLEANED,),
          writes=(LEDGER_STORE, STOCK_STORE, INVOICE_STORE, TAX_STORE),
          implemented_by="vyuha/detect.py, vyuha/schema.py"),

    # -- L2 domain, one product slice each
    Agent("dashboard", "Dashboard Aggregation Agent", DOMAIN,
          "Assembles the single branded view the client opens.",
          reads=(STATEMENTS, LEDGER_STORE, STOCK_STORE, INVOICE_STORE, TAX_STORE),
          writes=(DASHBOARD,),
          implemented_by="vyuha/report.py, console.py"),
    Agent("statements", "Financial Statements Agent", DOMAIN,
          "Balance sheet, P&L and cash flow, for every year held.",
          reads=(LEDGER_STORE,), writes=(STATEMENTS,),
          implemented_by="finance.py"),
    Agent("tax", "Tax & GST Agent", DOMAIN,
          "Liabilities, filing dates and returns.",
          reads=(LEDGER_STORE, INVOICE_STORE, TAX_STORE),
          writes=(TAX_STORE, EVENTS),
          implemented_by="finance.py, tax.py"),
    Agent("invoicing", "Invoicing & Billing Agent", DOMAIN,
          "Generates and reconciles invoices and bills.",
          reads=(INVOICE_STORE, LEDGER_STORE), writes=(INVOICE_STORE, EVENTS),
          implemented_by="invoice.py"),
    Agent("operations", "Operations Agent", DOMAIN,
          "What was bought and sold, and what is on the shelf.",
          reads=(STOCK_STORE, LEDGER_STORE), writes=(STOCK_STORE, EVENTS),
          implemented_by="books.py, today.py"),
    Agent("analytics", "Financial Analytics Agent", DOMAIN,
          "On-demand analysis, driven by a question somebody asked.",
          reads=(LEDGER_STORE, STOCK_STORE, INVOICE_STORE, STATEMENTS),
          writes=(FILES,),
          implemented_by="analysis.py, agent.py"),

    # -- L3 communication & documents, shared
    Agent("notification", "Notification Agent", COMMS,
          "Decides what needs attention, and who to tell.",
          reads=(EVENTS, TENANT_CONFIG), writes=(OUTBOX,),
          implemented_by="notify.py"),
    Agent("communication", "Communication Agent", COMMS,
          "The only way out. WhatsApp sends; email is always a draft.",
          reads=(OUTBOX,), writes=(OUTBOX, AUDIT),
          implemented_by="gate.py"),
    Agent("documents", "Document Generation Agent", COMMS,
          "PDFs, decks and formatted invoices.",
          reads=(STATEMENTS, INVOICE_STORE), writes=(FILES,),
          implemented_by="exports.py, deck_render.py, invoice_render.py"),

    # -- L4 routine jobs
    Agent("routine", "Routine Job Agent", ROUTINE,
          "One scheduled, personalised bundle per person.",
          reads=(DASHBOARD, STATEMENTS, STOCK_STORE, TENANT_CONFIG),
          writes=(OUTBOX,),
          implemented_by="routines.py"),

    # -- orchestration
    Agent("orchestrator", "Orchestrator", ORCHESTRATION,
          "Schedules, retries, audits, and gates anything leaving the system.",
          reads=(TENANT_CONFIG, OUTBOX), writes=(OUTBOX, AUDIT),
          implemented_by="orchestrator.py"),
)

BY_KEY = {a.key: a for a in ROSTER}


def lane(key: str) -> tuple[Agent, ...]:
    return tuple(a for a in ROSTER if a.lane == key)


def by_lane() -> list[tuple[str, str, str, tuple[Agent, ...]]]:
    """The roster grouped for display, in flow order."""
    return [(k, label, blurb, lane(k)) for k, label, blurb in LANES]


# --- the boundary ---------------------------------------------------------


def check() -> list[str]:
    """Every way the declared contracts break the architecture's own rules.

    Returns a list of sentences rather than raising: a caller wants all of them
    at once, and a check that reports only the first violation makes the second
    one somebody else's problem.
    """
    problems: list[str] = []
    valid_lanes = {k for k, _, _ in LANES}

    for a in ROSTER:
        if a.lane not in valid_lanes:
            problems.append(f"{a.name} is in lane '{a.lane}', which does not exist.")

        # The rule the spec calls a hard boundary: the backend never surfaces.
        if a.lane in (DOMAIN, ROUTINE):
            leaked = sorted(set(a.reads) & BACKEND_ONLY)
            if leaked:
                problems.append(
                    f"{a.name} reads {', '.join(leaked)}. Nothing past the "
                    f"pipeline may read raw or unclassified records — a domain "
                    f"agent sees only what the Classification Router has tagged.")

        # An agent that reads nothing and writes nothing is a name on a diagram.
        if not a.reads and not a.writes:
            problems.append(f"{a.name} declares no contract at all.")
        if not a.implemented_by:
            problems.append(f"{a.name} says nowhere in the code that it exists.")

    # Every store an agent reads has to be written by somebody, or the flow
    # diagram has an arrow coming from nothing.
    written = {s for a in ROSTER for s in a.writes}
    for a in ROSTER:
        for store_name in a.reads:
            if store_name not in written:
                problems.append(
                    f"{a.name} reads '{store_name}', which no agent writes.")

    return problems
