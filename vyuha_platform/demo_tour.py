"""The guided demo — the whole product, in order, with the words to say.

A prospect does not want a slide deck and cannot be shown a dead screenshot: they want to
watch their own kind of business be set up from nothing and then be walked through what
they would use on a Tuesday. This module is that walk, and it is **data, not a recording**
— the same choice `agents.py`, `modules.py` and `routines.py` make.

Every step carries two different pieces of writing, because a demo has two audiences:

* ``point`` — one plain sentence, in large type, that **the room reads off the screen**.
  It is the claim being made, and it has to survive being read at three metres by somebody
  who has never seen the product.
* ``say`` — the fuller line for the **presenter** to speak over it, in small type.

Keeping them apart is what stops the demo becoming a paragraph nobody reads aloud and
nobody in the room can follow either. ``note`` is for the presenter alone and is never said
unless asked.

Three rules the whole thing is built on:

* **It drives the real product.** Every action calls the same function the screens call —
  ``store.add_client``, ``onboarding.save``, ``people.add_staff``, and the very ingest
  path an upload uses. There is no demo mode inside the product and no fake data: what the
  prospect sees is what they get, because it *is* what they get.
* **The presenter is never trapped.** Pause leaves the app fully usable, every action is
  optional (type it yourself if the room wants to see you type), and wandering off the
  step is allowed — the tour notices and offers the way back rather than snatching the
  page away.
* **It can always be run again.** ``reset`` deletes the demo business outright, so a
  rehearsal that went sideways is one click from clean. Nothing here ever touches a
  business somebody actually trades on: every action resolves the demo business by name,
  under the presenter's own account, and refuses to work on anything else.

The files it imports are the practice pack from ``demo/samples/practice/`` — the same pile
the onboarding runbook uses, generated if it is missing.
"""

from __future__ import annotations

import csv
import importlib.util
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from . import access, books, channels, ledger, onboarding, people, store

ROOT = Path(__file__).resolve().parent.parent
PRACTICE = ROOT / "demo" / "samples" / "practice"
MAKER = ROOT / "demo" / "make_practice.py"

#: The business the demo builds. Named so nobody mistakes it for a real client, and
#: matched by this exact name when an action needs to find it again.
NAME = "Deshpande Electricals & Motors (Demo)"
OWNER = "Anand Deshpande"
PHONE = "9845012345"          # fiction: the 98450 block, never a real subscriber here
TRADE = "distribution"
GSTIN = "29DESHP7788K1Z4"
STATE = "KA"
ADDRESS = "Station Road, Dharwad 580001"
INDUSTRY = "Motors, pumps, starters, switchgear and cable"


# --------------------------------------------------------------------- the script

@dataclass(frozen=True)
class Chapter:
    key: str
    label: str
    blurb: str
    #: Roughly how long this chapter should take, so a presenter can keep to twenty
    #: minutes without watching a clock.
    minutes: int
    #: The one thing the room should take away from it. Shown on the chapter card.
    proves: str


@dataclass(frozen=True)
class Step:
    key: str
    chapter: str
    title: str
    #: **The room reads this.** One plain sentence, large. Keep it short enough to take
    #: in at a glance — if it needs a comma-spliced second clause, it is two steps.
    point: str
    #: What the presenter says over it.
    say: str
    #: Where the step happens. ``{slug}`` is the demo business. Empty means "stay here".
    path: str = ""
    #: What to put the spotlight on. Empty centres the card instead.
    target: str = ""
    #: An action key from ``ACTIONS`` — the demo does the typing, if the presenter wants.
    action: str = ""
    action_label: str = ""
    #: An aside for the presenter only; never said unless asked.
    note: str = ""


CHAPTERS: tuple[Chapter, ...] = (
    Chapter("open", "Why we are here", "One sentence, before any screen", 1,
            "This is a live product, not a slideshow."),
    Chapter("onboard", "Set the business up", "From nothing to a workspace, live", 5,
            "Getting set up is our job, not theirs."),
    Chapter("data", "Their own files", "The mess goes in; the read-back comes out", 4,
            "No cleaning up, and we show our working."),
    Chapter("day", "An ordinary day", "What needs doing, what sold, what is on the shelf", 4,
            "One screen says what to do today."),
    Chapter("money", "The money", "Profit, position, tax — and what we cannot see", 3,
            "The statements a bank or a CA asks for."),
    Chapter("tell", "Telling the right person", "The part nobody else does", 2,
            "The person who owns the problem hears about it."),
    Chapter("close", "What happens next", "Honest about what is not built", 1,
            "You would start exactly the way you just watched."),
)

STEPS: tuple[Step, ...] = (
    # ------------------------------------------------------------------ open
    Step("open.why", "open", "What we are about to do",
         point="In twenty minutes, a real business — built from nothing, in front of you.",
         say="I am going to set a business up from scratch, put a year of their own messy "
             "Excel through it, and then walk you through what they would open on a Tuesday "
             "morning. Every screen you see is the live product.",
         path="/studio",
         note="If they ask about price, park it to the end. Let the product do the work."),
    Step("open.portfolio", "open", "Our side of it",
         point="Every business we look after, and how far along each one is.",
         say="This is the Studio, and it is ours, not theirs — the client never sees this "
             "screen. Nothing gets half-set-up and forgotten.",
         target='[data-testid="studio"]'),

    # -------------------------------------------------------------- onboard
    Step("onboard.new", "onboard", "Four fields, not forty",
         point="Setting a business up takes four fields.",
         say="Name, owner, the owner's WhatsApp number, and the kind of trade. That is the "
             "whole form — everything else we gather as we go, because a form nobody "
             "finishes is a business nobody onboards.",
         path="/studio/new", target='[data-testid="studio-new"]',
         action="create", action_label="Create the business",
         note="Type it yourself if the room would rather watch you type."),
    Step("onboard.map", "onboard", "Where does each record live today?",
         point="We ask where each of their eight kinds of record lives today.",
         say="Sales, purchases, stock, who owes them, whom they owe, expenses, cash, staff. "
             "Tally, Excel, other software, a paper register, only the bills, WhatsApp — or "
             "not kept at all. Every honest answer is on that list.",
         path="/studio/{slug}/datamap", target='[data-testid="datamap-form"]',
         action="datamap", action_label="Answer it the way this client would"),
    Step("onboard.freeze", "onboard", "The answer that decides the rest",
         point="How they keep sales decides how everything else works.",
         say="Excel or Tally, and the business runs on files they send us — the files are "
             "the truth. Paper or WhatsApp, and it runs on typed entries instead. We decide "
             "that once, here, while the workspace is still empty.",
         target='[data-testid="domain-sales"]'),
    Step("onboard.plan", "onboard", "Read this back to them",
         point="What those answers mean, in plain words, before we touch anything.",
         say="How we bring the past in, and how new records keep arriving afterwards. This "
             "is the moment the owner understands what he is buying — so read it to him "
             "line by line.",
         target='[data-testid="import-plan"]'),
    Step("onboard.profile", "onboard", "What has to print on a bill",
         point="The two details that turn a bill into a tax invoice.",
         say="The GSTIN, and the state. Without them a bill prints as a bill of supply and "
             "the buyer's accountant sends it back. The state decides CGST plus SGST or "
             "IGST, and that is frozen onto the invoice the moment it is raised.",
         path="/studio/{slug}/profile", target='[data-testid="profile-form"]',
         action="profile", action_label="Fill in their details"),
    Step("onboard.masters", "onboard", "Who works there",
         point="A role decides who gets told — so every person needs a number.",
         say="Stock to the manager, money to the accountant, a customer gone quiet to the "
             "salesman, everything to the owner. A person with no number gets skipped, and "
             "then the owner is told about everything — which is what he is paying us to "
             "stop.",
         path="/studio/{slug}/masters", target='[data-testid="masters"]',
         action="people", action_label="Add their staff"),
    Step("onboard.later", "onboard", "What we still do by hand",
         point="Some of this we still do by hand. I would rather tell you now.",
         say="The opening stock position, the staged history import and the sign-off are "
             "described here, but we do them by hand today — and that is the next thing "
             "being built.",
         path="/studio/{slug}/opening", target='[data-testid="stage-later"]',
         note="Do not skip this step. It is the one that buys trust for everything else."),

    # ----------------------------------------------------------------- data
    Step("data.stock", "data", "Send it exactly as it is",
         point="They send the file exactly as it is. No cleaning up.",
         say="That is the instruction we give every client, and we mean it — handling the "
             "mess is the product. A client who tidies a file first usually deletes the "
             "columns we need. I will start with their stock list.",
         path="/app/{slug}/data/add", target='[data-testid="send-files"]',
         action="import_stock", action_label="Send the stock statement"),
    Step("data.sales", "data", "A year of bills, as the accountant keeps them",
         point="A merged title, junk rows, dates as text, one customer spelled four ways.",
         say="This is a deliberately horrible file — there is even a Grand Total sitting in "
             "the middle of the data. No configuration, no mapping screen, no one telling "
             "it which column is which. Watch.",
         action="import_sales", action_label="Send the sales register"),
    Step("data.dues", "data", "And who still owes them",
         point="And the list of who still owes them money.",
         say="Last one, so the money side is complete.",
         action="import_dues", action_label="Send the outstanding list"),
    Step("data.read", "data", "What we understood, and how sure we are",
         point="Everything we understood from each file — and how sure we are of it.",
         say="The sheet it read, the row the header turned out to be on, which columns it "
             "understood, which it ignored, and every fix it applied. A figure read off a "
             "labelled column and one we reconstructed do not look the same here. If we are "
             "ever wrong, this is where you catch us.",
         path="/app/{slug}/data/read", target='[data-testid="readback"]'),

    # ------------------------------------------------------------------ day
    Step("day.home", "day", "What needs you today",
         point="The morning screen is a list of decisions, not a wall of charts.",
         say="An empty shelf, money that is late, a customer who has gone quiet — ranked by "
             "what it costs to ignore, each with the action sitting next to it.",
         path="/app/{slug}", target='[data-testid="needs-you"]'),
    Step("day.kpis", "day", "The four numbers",
         point="The four numbers he would ask for anyway.",
         say="What has sold, what is owed, what is on the shelf, what is in hand — with the "
             "direction of travel.",
         target='[data-testid="kpis"]'),
    Step("day.sales", "day", "What is actually selling",
         point="All of this came out of that one messy register.",
         say="Month by month, by item, by customer. Nobody typed any of it.",
         path="/app/{slug}/sales/overview", target='[data-testid="sales-chart"]'),
    Step("day.customers", "day", "The four spellings, as one customer",
         point="Four spellings in the file. One customer here.",
         say="With M/s, without, in capitals, with a full stop. That collapsing is the "
             "difference between knowing who your biggest customer is and not.",
         path="/app/{slug}/sales/customers", target='[data-testid="customers"]'),
    Step("day.collect", "day", "Chasing money, without the awkwardness",
         point="The chasing message is already written.",
         say="Who owes what and for how long. He reads it, changes a word if he wants, and "
             "sends it from his own WhatsApp. Chasing money is the job every owner puts "
             "off, so we take the writing of it away.",
         path="/app/{slug}/sales/collections"),
    Step("day.stock", "day", "The shelf",
         point="What is low, what is dead, and the cash asleep on the shelf.",
         say="Below the reorder mark, out entirely, or not moved in ninety days. The "
             "dead-stock figure is usually the one that makes an owner sit up — it is money "
             "he has already spent.",
         path="/app/{slug}/operations/inventory", target='[data-testid="inventory"]'),
    Step("day.record", "day", "For the day that has not been filed yet",
         point="For the sale that happened before any file existed.",
         say="What, how many, who, their number — in the order the words come out of "
             "somebody's mouth. Typed entries and uploaded files end up in the same place.",
         path="/app/{slug}/operations/record", target='[data-testid="record-sale"]'),

    # ---------------------------------------------------------------- money
    Step("money.costs", "money", "Watch the margin appear",
         point="Margin reads zero — because no file they send says what things cost.",
         say="Their sale prices came out of the stock list. The costs are in a purchase file "
             "that nothing imports. So we put them in once, and the whole of Finance wakes "
             "up. I will do it now — watch this number.",
         path="/app/{slug}/finance/pnl", target='[data-testid="pnl"]',
         action="costs", action_label="Type their costs in",
         note="Let the page reload and pause for a second. This is the beat of the demo."),
    Step("money.balance", "money", "What we can see, and what we cannot",
         point="Underneath the statement: what it does not know.",
         say="No opening balances, no fixed assets, no loans. We print that every time — a "
             "trading position handed to a bank as though it were a filed one is worse than "
             "no statement at all.",
         path="/app/{slug}/finance/balance", target='[data-testid="assumptions"]'),
    Step("money.gst", "money", "Tax, and when it is due",
         point="Tax on the invoices actually raised — and the date it is due.",
         say="Never on sales, because a sale with no invoice collected no tax. And anything "
             "that touches a filing waits for a named person to approve it. It never just "
             "goes.",
         path="/app/{slug}/finance/gst", target='[data-testid="filings"]'),
    Step("money.ratios", "money", "The question he cannot ask Excel",
         point="The analysis he would otherwise pay somebody for.",
         say="Margins, break-even, and how much of his turnover is sitting with three "
             "customers.",
         path="/app/{slug}/analytics/ratios", target='[data-testid="concentration"]'),

    # ----------------------------------------------------------------- tell
    Step("tell.rules", "tell", "Who gets told, before anybody is told",
         point="You can read who would be told what — before anyone is told anything.",
         say="Vyuha works out who owns each problem and tells that person, not the owner "
             "every time. We show the owner this screen and get his blessing before we "
             "switch anything on.",
         path="/app/{slug}/inbox/rules", target='[data-testid="rules"]'),
    Step("tell.brief", "tell", "The morning brief",
         point="One WhatsApp he can read at a traffic light.",
         say="Everything that needs him, in one message.",
         path="/app/{slug}/inbox/brief", target='[data-testid="brief"]'),
    Step("tell.routines", "tell", "And it keeps happening",
         point="Eight in the morning, every day, without anyone asking.",
         say="A Friday stock summary for the purchase head is a line in a file, not a new "
             "feature.",
         path="/app/{slug}/inbox/routines", target='[data-testid="routines"]'),
    Step("tell.access", "tell", "How the owner gets in",
         point="No password. A link and a PIN, on the phone he already has.",
         say="Two separate WhatsApp messages — the link nobody can guess, and the PIN that "
             "makes a forwarded message harmless. He taps it and he is in.",
         path="/app/{slug}/settings/access", target='[data-testid="settings-access"]'),

    # ---------------------------------------------------------------- close
    Step("close.ask", "close", "Or he can just ask",
         point="Or he asks, in his own words.",
         say="Every number in the answer is computed by us. The model chooses what to say, "
             "never what the figure is.",
         path="/app/{slug}", target='[data-testid="open-assistant"]'),
    Step("close.end", "close", "Where we would start with you",
         point="We would start with you exactly the way you just watched.",
         say="You send us what you already keep, we set it up, and you see your own numbers "
             "in it before you decide anything. Everything I showed you runs today — what "
             "is still being built is the automatic collection of new files.",
         note="Now ask for their files. That is the only close that matters."),
)

BY_KEY = {s.key: s for s in STEPS}
CHAPTER_BY_KEY = {c.key: c for c in CHAPTERS}


def steps_for(slug: str) -> list[dict]:
    """The script with the demo business's slug filled in, ready for the browser.

    Two things are resolved here rather than in the browser, because getting either wrong
    strands a presenter mid-demo:

    * **A path that needs no business still works before there is one.** The first steps
      live on ``/studio`` and ``/studio/new``, which exist whether or not the demo business
      has been created — blanking them because the slug was not known yet left the opening
      of every demo sitting on the wrong page.
    * **Every step knows the page it belongs on** (``page``), inherited from the last step
      that named one. Half the script deliberately says nothing about the address because
      it carries on where the step before it left off, and without this those steps could
      not be jumped to from the control page at all.
    """
    order = [c.key for c in CHAPTERS]
    seen: set[str] = set()
    page = ""
    out = []
    for i, s in enumerate(STEPS):
        path = s.path
        if "{slug}" in path:
            # Needs the business. Unresolvable until it exists, and inheriting the page
            # before it would send somebody to the wrong screen confidently.
            path = path.replace("{slug}", slug) if slug else ""
            page = path
        elif path:
            page = path
        chapter = CHAPTER_BY_KEY[s.chapter]
        first = s.chapter not in seen
        seen.add(s.chapter)
        in_chapter = [x for x in STEPS if x.chapter == s.chapter]
        out.append({
            "i": i, "key": s.key, "title": s.title, "point": s.point, "say": s.say,
            "note": s.note,
            "chapter": s.chapter,
            "chapter_label": chapter.label,
            "chapter_blurb": chapter.blurb,
            "chapter_proves": chapter.proves,
            "chapter_minutes": chapter.minutes,
            "chapter_index": order.index(s.chapter) + 1,
            "chapter_total": len(CHAPTERS),
            "first_in_chapter": first,
            "step_in_chapter": in_chapter.index(s) + 1,
            "steps_in_chapter": len(in_chapter),
            #: What this step itself names — empty means "carry on where we are".
            "path": path,
            #: The page it belongs on, inherited. This is what the overlay navigates to.
            "page": page,
            "target": s.target, "action": s.action, "action_label": s.action_label,
        })
    return out


# ------------------------------------------------------------------ the business

@dataclass
class Outcome:
    ok: bool
    message: str
    slug: str = ""
    #: Where the browser should be after this — usually the same page, reloaded.
    go: str = ""
    extra: dict = field(default_factory=dict)


def find(account) -> store.Client | None:
    """The demo business under this account, by name. Never anybody else's."""
    if account is None:
        return None
    return next((c for c in access.businesses(account)
                 if c.name == NAME and c.owner_id == account.id), None)


def status(account) -> dict:
    """What the presenter needs to know before starting: is it built, how far."""
    client = find(account)
    if client is None:
        return {"exists": False, "slug": "", "items": 0, "sales": 0, "runs": 0,
                "files": PRACTICE.exists()}
    book = books.load(client.slug)
    return {"exists": True, "slug": client.slug, "name": client.name,
            "items": len(book.items), "sales": len(book.sales),
            "runs": len(client.runs), "mode": client.data_mode,
            "files": PRACTICE.exists()}


def _ensure_files() -> bool:
    """The practice pack, generated if this clone has never made it."""
    wanted = PRACTICE / "02-stock-statement.xlsx"
    if wanted.exists():
        return True
    if not MAKER.exists():
        return False
    try:
        spec = importlib.util.spec_from_file_location("make_practice", MAKER)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)      # type: ignore[union-attr]
        module.main()
    except Exception:                        # noqa: BLE001 — a demo must not crash here
        return False
    return wanted.exists()


def _need(account) -> tuple[store.Client | None, Outcome | None]:
    client = find(account)
    if client is None:
        return None, Outcome(False, "Start with “Create the business” — there is nothing "
                                    "to act on yet.")
    return client, None


# --------------------------------------------------------------------- actions

def act_create(account) -> Outcome:
    """Stage 1. The same call the Studio's own form makes."""
    existing = find(account)
    if existing is not None:
        return Outcome(True, f"{NAME} is already here.", existing.slug,
                       go=f"/studio/{existing.slug}/datamap")
    client = store.add_client(
        account.id, name=NAME, contact=OWNER, phone=channels.normalise_phone(PHONE),
        trade=TRADE,
        # Typed-in until the data map says otherwise — exactly as studio.py does it.
        data_mode="books")
    record = onboarding.Onboarding(slug=client.slug,
                                   cutover=onboarding.default_cutover())
    onboarding.save(record)
    ledger.log("client.onboarded", f"{client.name} created for a demo", client=client,
               channel="studio")
    return Outcome(True, "Business created — that is the whole of stage one.", client.slug,
                   go=f"/studio/{client.slug}/datamap")


#: How this client keeps each kind of record. Excel for the four that drive the
#: product, and honest gaps elsewhere — a demo where everything is perfect is a
#: demo nobody believes.
ANSWERS: dict[str, tuple[str, str, str]] = {
    "sales":       ("excel", "Sales register, one workbook a year", "daily"),
    "purchases":   ("excel", "Purchase register from their accountant", "monthly"),
    "stock":       ("excel", "Stock statement, printed every Monday", "weekly"),
    "receivables": ("excel", "Outstanding list, kept by the owner himself", "weekly"),
    "payables":    ("bills", "A spike file of supplier bills", "monthly"),
    "expenses":    ("paper", "A cash book in the drawer", "daily"),
    "cash":        ("paper", "Bank passbook and the cash box", "weekly"),
    "staff":       ("none", "", ""),
}


def act_datamap(account) -> Outcome:
    """Stage 2, answered the way this client would — and the mode it decides."""
    client, bail = _need(account)
    if bail:
        return bail
    record = onboarding.load(client.slug)
    for key in onboarding.DOMAIN_KEYS:
        source, keeper, cadence = ANSWERS.get(key, ("none", "", ""))
        record.datamap[key] = onboarding.Answer(
            source=source, keeper=keeper, cadence=cadence,
            since="" if source == "none" else "2025-10",
            notes="")
    record.cutover = onboarding.default_cutover()
    record.history_months = 12
    onboarding.save(record)

    # The same rule the Studio applies: sales in a spreadsheet makes this a business
    # whose files are the truth, and only while nothing has been read yet.
    book = books.load(client.slug)
    if not book.items and not book.sales and not client.runs:
        client.data_mode = "upload"
        store.update_client(client)
    ledger.log("settings.changed", "Data map answered (demo)", client=client,
               channel="studio")
    return Outcome(True, "Eight records answered. Sales live in Excel, so this is now a "
                         "business we read from files.",
                   client.slug, go=f"/studio/{client.slug}/datamap")


def act_profile(account) -> Outcome:
    client, bail = _need(account)
    if bail:
        return bail
    client.gstin, client.state = GSTIN, STATE
    client.address, client.industry = ADDRESS, INDUSTRY
    client.email = "anand@deshpande-electricals.example"
    store.update_client(client)
    record = onboarding.load(client.slug)
    record.fy_start_month = 4
    onboarding.save(record)
    ledger.log("settings.changed", "Profile filled in (demo)", client=client,
               channel="studio")
    return Outcome(True, "GSTIN and state in — bills will print as tax invoices, with CGST "
                         "and SGST inside Karnataka.",
                   client.slug, go=f"/studio/{client.slug}/profile")


#: Roles chosen so the Notification Agent has somebody real to tell. Numbers are the
#: reserved-for-fiction 9999 block, so a rehearsal can never ring a stranger.
STAFF = (
    ("Anand Deshpande", "Owner", "9999000101"),
    ("Ravi Kulkarni", "Manager", "9999000102"),
    ("Shalini Pai", "Accountant", "9999000103"),
    ("Mahesh Naik", "Salesperson", "9999000104"),
)


def act_people(account) -> Outcome:
    client, bail = _need(account)
    if bail:
        return bail
    org = people.load(client.slug)
    have = {p.name.strip().lower() for p in org.staff}
    added = 0
    for name, role, phone in STAFF:
        if name.strip().lower() in have:
            continue
        people.add_staff(client.slug, name, role, "", channels.normalise_phone(phone))
        added += 1
    if added:
        ledger.log("people.changed", f"{added} people added (demo)", client=client,
                   channel="studio")
    return Outcome(True, f"{added or 'No new'} people added — an owner, a manager, an "
                         "accountant and a salesman, each with a number.",
                   client.slug, go=f"/studio/{client.slug}/masters")


def _import(account, filename: str, said: str) -> Outcome:
    """Put one of their files through the very path a real upload takes."""
    client, bail = _need(account)
    if bail:
        return bail
    if not _ensure_files():
        return Outcome(False, "The practice files are missing. Run "
                              "`python demo/make_practice.py` and try again.")
    source = PRACTICE / filename
    if not source.exists():
        return Outcome(False, f"{filename} is not in demo/samples/practice/.")

    # Imported here, not at module scope: `app` mounts this package's routes near the
    # top of its own import, long before `_ingest` exists.
    from . import app as platform_app

    folder = store.upload_dir(client.slug)
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / source.name
    shutil.copyfile(source, target)
    ledger.log("source.received", f"{source.name} received (demo)", client=client,
               channel="upload", files=[source.name])

    # Same rule as the upload route: a file-driven business is rebuilt from everything
    # it has ever sent, so the batch is the whole folder.
    batch = ([target] if client.data_mode == "books"
             else platform_app._source_files(folder))
    _run, note = platform_app._ingest(
        client, batch, label=(target.name if len(batch) == 1 else f"{len(batch)} files"))
    return Outcome(True, f"{said} {note}", client.slug,
                   go=f"/app/{client.slug}/data/add")


def act_import_stock(account) -> Outcome:
    return _import(account, "02-stock-statement.xlsx", "Stock list read.")


def act_import_sales(account) -> Outcome:
    return _import(account, "01-sales-register.xlsx", "Sales register read.")


def act_import_dues(account) -> Outcome:
    return _import(account, "03-outstanding.xlsx", "Outstanding list read.")


def act_costs(account) -> Outcome:
    """The beat where margin appears: costs are the one thing no file carries."""
    client, bail = _need(account)
    if bail:
        return bail
    if not _ensure_files():
        return Outcome(False, "The practice files are missing — run "
                              "`python demo/make_practice.py`.")
    path = PRACTICE / "05-cost-list.csv"
    if not path.exists():
        return Outcome(False, "05-cost-list.csv is not in demo/samples/practice/.")

    costs: dict[str, float] = {}
    with path.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            name = (row.get("Description") or "").strip().lower()
            try:
                costs[name] = float(row.get("Our Cost") or 0)
            except ValueError:
                continue

    book = books.load(client.slug)
    if not book.items:
        return Outcome(False, "There are no items yet — send the stock statement first.")
    priced = 0
    for item in book.items:
        want = costs.get(item.name.strip().lower())
        if want and not item.cost:
            item.cost = want
            priced += 1
    books.save(book)
    ledger.log("settings.changed", f"Cost set on {priced} item(s) (demo)", client=client,
               channel="manual")
    return Outcome(True, f"Cost typed in for {priced} items — and there is the margin.",
                   client.slug, go=f"/app/{client.slug}/finance/pnl")


ACTIONS = {
    "create": act_create,
    "datamap": act_datamap,
    "profile": act_profile,
    "people": act_people,
    "import_stock": act_import_stock,
    "import_sales": act_import_sales,
    "import_dues": act_import_dues,
    "costs": act_costs,
}


def run(key: str, account) -> Outcome:
    fn = ACTIONS.get(key)
    if fn is None:
        return Outcome(False, "That is not something the demo can do.")
    try:
        return fn(account)
    except Exception as exc:                 # noqa: BLE001
        # A demo in front of a prospect must fail in words, never in a stack trace.
        return Outcome(False, f"That did not work: {exc}")


def reset(account) -> Outcome:
    """Delete the demo business outright, so the next run starts from nothing."""
    client = find(account)
    if client is None:
        return Outcome(True, "Nothing to clear — the demo business does not exist yet.")
    slug = client.slug
    store.delete_client(slug, account.id)
    return Outcome(True, "Cleared. The next run starts from an empty workspace.", "",
                   go="/demo")
