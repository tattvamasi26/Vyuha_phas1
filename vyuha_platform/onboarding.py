"""Onboarding — the stepper the Vyuha team works through with a new business.

One record per business, kept apart from the business's own numbers because it is about
*getting* the data rather than the data itself: the answers from the data-map interview
(where each kind of record lives today, how far back it goes, who keeps it, how often),
the cut-over date, and anything an operator marked by hand.

Stage status is **derived wherever it can be**. A profile with a name, an owner and a
WhatsApp number is complete whether or not anybody pressed Save on the profile screen;
a masters stage with items on the shelf is done however the items got there. Storing a
status the workspace can contradict is how a stepper ends up saying "not started" about
a business that has been trading in Vyuha for a month.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime

from . import atomic
from .store import DATA

ONBOARDING = DATA / "onboarding"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


@dataclass(frozen=True)
class Stage:
    key: str
    label: str
    blurb: str
    #: The build phase that brings this stage to life. Earlier phases show it,
    #: say what it will do, and point at whatever does the job today.
    phase: int


STAGES: tuple[Stage, ...] = (
    Stage("profile", "Business profile", "Who they are and how to reach them", 1),
    Stage("datamap", "Data map", "Where every kind of record lives today", 1),
    Stage("masters", "Items, branches & staff", "What they sell and who works there", 1),
    Stage("opening", "Opening position", "Stock, dues and cash on the cut-over date", 2),
    Stage("history", "History import", "Past records from files, photos or typing", 2),
    Stage("signoff", "Check & sign-off", "Coverage, checks and the owner's confirmation", 2),
    Stage("feeds", "Continuous feeds", "How new data keeps arriving", 6),
    Stage("golive", "People, alerts & go-live", "Access links, alerts and the welcome", 6),
)
BY_KEY = {s.key: s for s in STAGES}

#: The build phase this code ships in. A stage whose phase is later is shown as
#: "coming", never as a broken form.
LIVE_PHASE = 1

#: The kinds of record a business keeps, in the order the interview asks about them.
DOMAINS: tuple[tuple[str, str, str], ...] = (
    ("sales", "Sales", "Bills, cash sales, credit sales"),
    ("purchases", "Purchases", "Bills from suppliers, goods received"),
    ("stock", "Stock", "What is on the shelf and in the godown"),
    ("receivables", "Customers & dues", "Who owes the business, and since when"),
    ("payables", "Suppliers & payables", "Whom the business owes"),
    ("expenses", "Expenses", "Rent, salary, transport, electricity"),
    ("cash", "Cash & bank", "Cash in hand, bank balances"),
    ("staff", "Staff & attendance", "Who works where, who came in"),
)
DOMAIN_KEYS = tuple(d[0] for d in DOMAINS)

SOURCES: tuple[tuple[str, str], ...] = (
    ("tally", "Tally"),
    ("excel", "Excel / Sheets"),
    ("software", "Other software"),
    ("paper", "Paper register"),
    ("bills", "Bills only"),
    ("whatsapp", "WhatsApp"),
    ("none", "Not kept"),
)
SOURCE_LABEL = dict(SOURCES)

CADENCES: tuple[tuple[str, str], ...] = (
    ("daily", "Daily"), ("weekly", "Weekly"), ("monthly", "Monthly"), ("rarely", "Rarely"),
)

HISTORY_CHOICES: tuple[tuple[int, str], ...] = (
    (0, "None — start fresh"), (3, "3 months"), (6, "6 months"),
    (12, "12 months"), (24, "2 years"), (36, "3 years"),
)

#: What each source means for the two jobs that follow the interview: bringing the
#: past in (stage 5) and keeping new records flowing (stage 7).
_PLAN: dict[str, tuple[str, str]] = {
    "tally": ("Export the Day Book and registers from Tally, then import the files",
              "Tally sync from the office PC"),
    "excel": ("Collect the workbooks as they are and import them — no clean-up",
              "Files on a schedule: upload, email-in or a watched folder"),
    "software": ("Export from their software to Excel or CSV, then import",
                 "A scheduled export, sent as a file"),
    "paper": ("Photograph the register pages, or type them into the entry grid",
              "Typed into Vyuha on the phone as it happens"),
    "bills": ("Photograph the bills — Vyuha reads them, a person checks",
              "Bill photos forwarded on WhatsApp"),
    "whatsapp": ("Export the chat — orders and payments are read out of it",
                 "Forwarded to Vyuha's WhatsApp number"),
    "none": ("Nothing to import — the record starts at cut-over",
             "Typed into Vyuha from day one"),
}


@dataclass
class Answer:
    """One domain's answers from the interview."""

    source: str = ""
    software: str = ""        # the product's name, when source == "software"
    since: str = ""           # YYYY-MM the oldest usable record goes back to
    keeper: str = ""          # who keeps it today
    cadence: str = ""
    notes: str = ""

    @property
    def answered(self) -> bool:
        return bool(self.source)

    @property
    def source_label(self) -> str:
        if self.source == "software" and self.software:
            return self.software
        return SOURCE_LABEL.get(self.source, "")


@dataclass
class Onboarding:
    slug: str
    datamap: dict = field(default_factory=dict)       # domain -> Answer
    #: The date the opening position is taken at. Everything before it is
    #: history; everything after it is the running record.
    cutover: str = ""
    history_months: int = 12
    fy_start_month: int = 4
    #: Stages an operator marked by hand, stage -> "done" | "skipped".
    marked: dict = field(default_factory=dict)
    notes: str = ""
    started_at: str = field(default_factory=_now)
    updated_at: str = ""

    def answer(self, domain: str) -> Answer:
        raw = self.datamap.get(domain)
        if isinstance(raw, Answer):
            return raw
        if isinstance(raw, dict):
            return Answer(**{k: v for k, v in raw.items() if k in Answer.__dataclass_fields__})
        return Answer()

    @property
    def answered(self) -> int:
        return sum(1 for d in DOMAIN_KEYS if self.answer(d).answered)


# ------------------------------------------------------------------ persistence

def _path(slug: str):
    ONBOARDING.mkdir(parents=True, exist_ok=True)
    return ONBOARDING / f"{slug}.json"


def load(slug: str) -> Onboarding:
    raw = atomic.read_json(_path(slug), None)
    if not isinstance(raw, dict):
        return Onboarding(slug=slug)
    known = {k: v for k, v in raw.items() if k in Onboarding.__dataclass_fields__}
    known["slug"] = slug
    return Onboarding(**known)


def save(record: Onboarding) -> None:
    record.updated_at = _now()
    row = asdict(record)
    row["datamap"] = {d: asdict(record.answer(d)) for d in DOMAIN_KEYS
                      if record.answer(d).answered or d in record.datamap}
    atomic.write_json(_path(record.slug), row)


def default_cutover(today: date | None = None) -> str:
    """The first of this month — the natural line between history and the record."""
    today = today or date.today()
    return today.replace(day=1).isoformat()


# ------------------------------------------------------------------- status

def status(record: Onboarding, client, book, org) -> dict[str, str]:
    """Each stage as ``done`` / ``todo`` / ``later``, derived from the business itself."""
    out: dict[str, str] = {}
    for stage in STAGES:
        if record.marked.get(stage.key) in {"done", "skipped"}:
            out[stage.key] = record.marked[stage.key]
            continue
        if stage.phase > LIVE_PHASE:
            out[stage.key] = "later"
            continue
        if stage.key == "profile":
            done = bool(client.name and client.phone and client.contact)
        elif stage.key == "datamap":
            done = record.answered == len(DOMAIN_KEYS) and bool(record.cutover)
        elif stage.key == "masters":
            done = bool(book.items)
        else:
            done = False
        out[stage.key] = "done" if done else "todo"
    return out


def current(states: dict[str, str]) -> str:
    """The first stage still open — where "Continue" should land."""
    for stage in STAGES:
        if states.get(stage.key) == "todo":
            return stage.key
    for stage in STAGES:
        if states.get(stage.key) == "later":
            return stage.key
    return STAGES[-1].key


def progress(states: dict[str, str]) -> tuple[int, int]:
    done = sum(1 for s in STAGES if states.get(s.key) in {"done", "skipped"})
    return done, len(STAGES)


def plan(record: Onboarding) -> list[dict]:
    """What the interview means in practice, one line per domain."""
    rows = []
    for key, label, _hint in DOMAINS:
        a = record.answer(key)
        if not a.answered:
            rows.append({"key": key, "label": label, "source": "", "history": "",
                         "ongoing": "", "since": ""})
            continue
        history, ongoing = _PLAN.get(a.source, ("", ""))
        if a.source == "software" and a.software:
            history = history.replace("their software", a.software)
        rows.append({"key": key, "label": label, "source": a.source_label,
                     "history": history, "ongoing": ongoing, "since": a.since})
    return rows
