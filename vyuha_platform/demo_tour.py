"""The guided demo — the whole product, in order, with the words to say.

A prospect does not want a slide deck and cannot be shown a dead screenshot: they want to
watch their own kind of business be set up from nothing and then be walked through what
they would use on a Tuesday. This module is that walk, and it is **data, not a recording**
— the same choice `agents.py`, `modules.py` and `routines.py` make. A step names a page, a
thing on it to point at, what to say, and optionally an action that does the typing.

Three rules it is built on:

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


@dataclass(frozen=True)
class Step:
    key: str
    chapter: str
    title: str
    #: What to say out loud. Written to be read aloud, not summarised.
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
    Chapter("open", "Why we are here", "One sentence, before any screen"),
    Chapter("onboard", "Set the business up", "From nothing to a workspace, live"),
    Chapter("data", "Their own files", "The mess goes in; the read-back comes out"),
    Chapter("day", "An ordinary day", "What needs doing, what sold, what is on the shelf"),
    Chapter("money", "The money", "Profit, position, tax — and what we cannot see"),
    Chapter("tell", "Telling the right person", "The part nobody else does"),
    Chapter("close", "What happens next", "Honest about what is not built"),
)

STEPS: tuple[Step, ...] = (
    # ------------------------------------------------------------------ open
    Step("open.why", "open", "What we are about to do",
         "Vyuha takes the Excel a distributor already keeps and turns it into a business "
         "that tells them what needs doing today. In the next twenty minutes I am going to "
         "set up a business from nothing, put a year of their own messy files through it, "
         "and then walk you through what they would open on a Tuesday morning. Nothing here "
         "is a mock-up — every screen you see is the live product.",
         path="/studio",
         note="If they ask about price, park it to the end. Let the product do the work."),
    Step("open.portfolio", "open", "Our side of it",
         "This is the Onboarding Studio, and it is ours, not theirs. Every business we look "
         "after sits here with the stage it has reached, so nothing gets half-set-up and "
         "forgotten. The client never sees this screen.",
         target='[data-testid="studio"]'),

    # -------------------------------------------------------------- onboard
    Step("onboard.new", "onboard", "Four fields, not forty",
         "Onboarding asks four things: the business name, the owner's name, the owner's "
         "WhatsApp number, and what kind of trade it is. That is the whole form. Everything "
         "else gets gathered as we go, because a form nobody finishes is a business nobody "
         "onboards.",
         path="/studio/new", target='[data-testid="studio-new"]',
         action="create", action_label="Create the business",
         note="Type it yourself if the room would rather watch you type."),
    Step("onboard.map", "onboard", "Where does each record live today?",
         "This is the interview that decides everything. Eight kinds of record — sales, "
         "purchases, stock, who owes them, whom they owe, expenses, cash, staff — and for "
         "each one: where does it live today? Tally, Excel, other software, a paper "
         "register, only the bills, WhatsApp, or not kept at all. Every honest answer is on "
         "that list, including 'not kept'.",
         path="/studio/{slug}/datamap", target='[data-testid="datamap-form"]',
         action="datamap", action_label="Answer it the way this client would"),
    Step("onboard.freeze", "onboard", "The answer that decides the rest",
         "How they keep sales is the one that matters. Tally, Excel or other software and "
         "the business runs on files — they send them and the files are the truth. Paper, "
         "bills or WhatsApp, and it runs on typed entries instead, where a file sent later "
         "merges rather than replacing. We decide that once, here, while the workspace is "
         "still empty.",
         target='[data-testid="domain-sales"]'),
    Step("onboard.plan", "onboard", "Read this back to them",
         "And here is what those answers mean in practice — how we bring the past in, and "
         "how new records keep arriving afterwards. This is the moment the owner "
         "understands what he is buying, so read it to him line by line.",
         target='[data-testid="import-plan"]'),
    Step("onboard.profile", "onboard", "What has to print on a bill",
         "Now the details that make a document a document. The GSTIN and the state are the "
         "two that matter: without them a bill prints as a bill of supply rather than a tax "
         "invoice, and the state decides whether a sale carries CGST plus SGST or IGST — "
         "which is frozen onto the invoice the moment it is raised.",
         path="/studio/{slug}/profile", target='[data-testid="profile-form"]',
         action="profile", action_label="Fill in their details"),
    Step("onboard.masters", "onboard", "Who works there",
         "Items, branches and people. The part worth slowing down on is the phone numbers: "
         "a role decides who hears what — stock to the manager, money to the accountant, a "
         "customer gone quiet to the salesman, everything to the owner. A person with no "
         "number gets skipped, and then the owner is the one told about everything, which "
         "is exactly what he is paying us to stop.",
         path="/studio/{slug}/masters", target='[data-testid="masters"]',
         action="people", action_label="Add their staff"),
    Step("onboard.later", "onboard", "What we still do by hand",
         "I will be straight with you about the rest of the stepper. The opening stock "
         "position, the staged history import and the sign-off are described here but we do "
         "them by hand today — and that is the next thing being built. I would rather you "
         "hear that from me now than find it in week three.",
         path="/studio/{slug}/opening", target='[data-testid="stage-later"]',
         note="Do not skip this step. It is the one that buys trust for everything else."),

    # ----------------------------------------------------------------- data
    Step("data.stock", "data", "Send it exactly as it is",
         "Here is where their files land, and the instruction we give every client is: do "
         "not clean anything up. Send it exactly as it is. Handling the mess is the product "
         "— a client who tidies a file first usually deletes the columns we need. I will "
         "start with their stock list, because it creates every item on the shelf.",
         path="/app/{slug}/data/add", target='[data-testid="send-files"]',
         action="import_stock", action_label="Send the stock statement"),
    Step("data.sales", "data", "A year of bills, as the accountant keeps them",
         "Now the sales register — and this is a deliberately horrible file. A merged title "
         "across the top, three junk rows above the real header, dates written as text, "
         "rupee symbols inside the numbers, a Grand Total sitting in the middle of the "
         "data, and one customer spelled four different ways. No configuration, no mapping "
         "screen. Watch.",
         action="import_sales", action_label="Send the sales register"),
    Step("data.dues", "data", "And who still owes them",
         "Last one — the outstanding list, so the money side is complete.",
         action="import_dues", action_label="Send the outstanding list"),
    Step("data.read", "data", "What we understood, and how sure we are",
         "This screen is the one I would ask you to judge us on. For every file it names "
         "the sheet it read, the row the header turned out to be on, which columns it "
         "understood and which it ignored, and every fix it applied. A figure read off a "
         "properly labelled column and one we reconstructed from quantity times rate do not "
         "look the same here. If we are ever wrong, this is where you catch us.",
         path="/app/{slug}/data/read", target='[data-testid="readback"]'),

    # ------------------------------------------------------------------ day
    Step("day.home", "day", "What needs you today",
         "This is the screen the owner opens in the morning, and it is not a dashboard — it "
         "is a ranked list of decisions. An empty shelf, money that is late, a customer who "
         "has gone quiet. Each one has the action next to it, so nobody has to go looking "
         "for the screen where that gets dealt with.",
         path="/app/{slug}", target='[data-testid="needs-you"]'),
    Step("day.kpis", "day", "The four numbers",
         "Above it, the four figures he would ask for anyway — what has sold, what is "
         "owed, what is on the shelf, what is in hand — with the direction of travel.",
         target='[data-testid="kpis"]'),
    Step("day.sales", "day", "What is actually selling",
         "Sales, month by month, by item and by customer. All of it read out of that one "
         "messy register, with no one typing anything.",
         path="/app/{slug}/sales/overview", target='[data-testid="sales-chart"]'),
    Step("day.customers", "day", "The four spellings, as one customer",
         "Remember the customer spelled four ways in the register — with M/s, without, in "
         "capitals, with a full stop. Here he is once, with everything he has bought and "
         "everything he owes. That collapsing is not clever formatting; it is the "
         "difference between knowing who your biggest customer is and not.",
         path="/app/{slug}/sales/customers", target='[data-testid="customers"]'),
    Step("day.collect", "day", "Chasing money, without the awkwardness",
         "Who owes what, and for how long. The message is already written — he reads it, "
         "changes a word if he wants, and sends it from his own WhatsApp. Chasing money is "
         "the job every owner puts off, so we take the writing of it away.",
         path="/app/{slug}/sales/collections"),
    Step("day.stock", "day", "The shelf",
         "What is on the shelf, what is below its reorder mark, what has not moved in "
         "ninety days and how much cash is asleep in it. The dead-stock number is usually "
         "the one that makes an owner sit up — it is money he already spent.",
         path="/app/{slug}/operations/inventory", target='[data-testid="inventory"]'),
    Step("day.record", "day", "For the day that has not been filed yet",
         "And when something sells at the counter before any file exists, it gets typed "
         "here — what, how many, who, their number — in the order the words come out of "
         "somebody's mouth. Typed entries and uploaded files end up in exactly the same "
         "place.",
         path="/app/{slug}/operations/record", target='[data-testid="record-sale"]'),

    # ---------------------------------------------------------------- money
    Step("money.costs", "money", "Watch the margin appear",
         "Now something honest. Gross margin here is zero — and it should be, because no "
         "file a distributor sends contains what things cost him. Their sale prices came "
         "out of the stock list; the costs are in a purchase file that nothing imports. So "
         "we put them in once, and the whole of Finance wakes up. I will do it now.",
         path="/app/{slug}/finance/pnl", target='[data-testid="pnl"]',
         action="costs", action_label="Type their costs in",
         note="Reload the page after the action — the figure changes in front of them."),
    Step("money.balance", "money", "What we can see, and what we cannot",
         "The balance sheet, and underneath it the list of what it does not know — no "
         "opening balances, no fixed assets, no loans. We print that every time. A trading "
         "position handed to a bank as though it were a filed one is worse than no "
         "statement at all.",
         path="/app/{slug}/finance/balance", target='[data-testid="assumptions"]'),
    Step("money.gst", "money", "Tax, and when it is due",
         "Tax collected on the invoices actually raised — never on sales, because a sale "
         "with no invoice collected no tax — and the filing dates beside it. Anything that "
         "touches a filing waits for a named person to approve it. It never just goes.",
         path="/app/{slug}/finance/gst", target='[data-testid="filings"]'),
    Step("money.ratios", "money", "The question he cannot ask Excel",
         "And the analysis he would have to pay somebody for: margins, break-even, and how "
         "much of his turnover is sitting with three customers.",
         path="/app/{slug}/analytics/ratios", target='[data-testid="concentration"]'),

    # ----------------------------------------------------------------- tell
    Step("tell.rules", "tell", "Who gets told, before anybody is told",
         "This is the part I have not seen anyone else do. Vyuha works out who owns each "
         "problem and tells that person — not the owner, every time. And before a single "
         "message goes anywhere, you can read exactly who would be told what. We show the "
         "owner this screen and get his blessing before we switch anything on.",
         path="/app/{slug}/inbox/rules", target='[data-testid="rules"]'),
    Step("tell.brief", "tell", "The morning brief",
         "Everything that needs him, as one WhatsApp he can read at a traffic light.",
         path="/app/{slug}/inbox/brief", target='[data-testid="brief"]'),
    Step("tell.routines", "tell", "And it keeps happening",
         "Eight in the morning, every day, to whoever should get it. A Friday stock summary "
         "for the purchase head is a line in a file, not a new feature.",
         path="/app/{slug}/inbox/routines", target='[data-testid="routines"]'),
    Step("tell.access", "tell", "How the owner gets in",
         "No password. We send him a private link and a four-digit PIN, on WhatsApp, as two "
         "separate messages — the link nobody can guess, and the PIN that makes a forwarded "
         "message harmless. He taps it and he is in, on the phone he already has.",
         path="/app/{slug}/settings/access", target='[data-testid="settings-access"]'),

    # ---------------------------------------------------------------- close
    Step("close.ask", "close", "Or he can just ask",
         "And when he wants something none of these screens show, he asks in his own words. "
         "Every number in the answer is computed by us — the model chooses what to say, "
         "never what the figure is.",
         path="/app/{slug}", target='[data-testid="open-assistant"]'),
    Step("close.end", "close", "Where we would start with you",
         "That is the product. We would start exactly the way you just watched: you send us "
         "what you already keep, we set it up, and you see your own numbers in it before "
         "you decide anything. Everything I showed you is running today — what is still "
         "being built is the automatic collection of new files, and the history import that "
         "we do by hand for now.",
         note="Now ask for their files. That is the only close that matters."),
)

BY_KEY = {s.key: s for s in STEPS}
CHAPTER_BY_KEY = {c.key: c for c in CHAPTERS}


def steps_for(slug: str) -> list[dict]:
    """The script with the demo business's slug filled in, ready for the browser."""
    out = []
    for i, s in enumerate(STEPS):
        out.append({
            "i": i, "key": s.key, "chapter": s.chapter,
            "chapter_label": CHAPTER_BY_KEY[s.chapter].label,
            "title": s.title, "say": s.say, "note": s.note,
            "path": s.path.replace("{slug}", slug) if s.path and slug else "",
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
    return Outcome(True, f"{NAME} created.", client.slug,
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
    return Outcome(True, "Eight records answered, cut-over set — and because sales live in "
                         "Excel, this is now a business we read from files.",
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
    return Outcome(True, "GSTIN, state and address in — invoices will print as tax "
                         "invoices, with CGST and SGST inside Karnataka.",
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
    return Outcome(True, f"Cost typed in for {priced} item(s) — reload and the margin is "
                         "there.", client.slug, go=f"/app/{client.slug}/finance/pnl")


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
