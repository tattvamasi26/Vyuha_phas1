"""The bearings demo: a distributor with a year of history, built in one command.

    .venv/Scripts/python -m vyuha_platform seed-bearings

**Shakti Bearings & Power Transmission, Hubballi** — a spares distributor selling to
garages, foundries, a sugar factory and dealers. It exists because the agri demo
(``demo_seed.py``) shows a shop, and the trade Vyuha is being sold into next is industrial
distribution: higher value per line, slower stock, longer credit, and a buyer whose
accountant wants a tax invoice.

Every beat of the demo has its evidence planted, and all of it is deterministic — a fixed
seed and dates relative to today — so the same command on two machines gives the same
numbers and a rehearsed line is still true tomorrow:

* 24 items across bearings, housings, belts, chains, seals and consumables
* grease **out of stock**, three items **below reorder**, three that **never sold**
* two branches and six people, so "who is selling" and "branch against branch" have data
* a year of sales, ~25% gross margin, running costs that leave a credible net
* three customers overdue at different ages, one regular gone quiet
* invoices raised inside the state and outside it, so CGST+SGST and IGST both appear
* an 8 am routine, so the scheduled brief can be shown firing

Idempotent: running it again wipes this account's workspaces and rebuilds them.
"""

from __future__ import annotations

import random
import shutil
from datetime import date, timedelta

from . import auth, books, invoice, money, onboarding, people, routines, store

EMAIL = "bearings@vyuha.test"
PASSWORD = "vyuha-bearings"
BUSINESS = "Shakti Bearings & Power Transmission"

#: Fixed, so two machines produce identical books.
SEED = 20260916

#: Twelve months, which is what makes a year-on-year line and a full GST story possible.
HISTORY_DAYS = 365


def _ago(days: int) -> str:
    return (date.today() - timedelta(days=days)).isoformat()


def _ahead(days: int) -> str:
    return (date.today() + timedelta(days=days)).isoformat()


#: (name, category, unit, sells at, costs, stock, reorder level, HSN, GST %)
#:
#: Bearings, housings and transmission parts are 8482/8483/8484 at 18%; grease is 3403.
#: One flat rate on every line would hide the only complication a real bill has.
CATALOGUE = [
    ("6204 ZZ Ball Bearing",        "Bearings",    "piece", 190,  132,  180, 60, "84821011", 18),
    ("6205 2RS Ball Bearing",       "Bearings",    "piece", 240,  168,  145, 60, "84821011", 18),
    ("6206 ZZ Ball Bearing",        "Bearings",    "piece", 310,  222,  96,  40, "84821011", 18),
    ("6305 2RS Ball Bearing",       "Bearings",    "piece", 420,  300,  62,  30, "84821011", 18),
    ("6308 ZZ Ball Bearing",        "Bearings",    "piece", 780,  560,  28,  15, "84821011", 18),
    ("30205 Taper Roller Bearing",  "Bearings",    "piece", 520,  372,  40,  20, "84822000", 18),
    ("32210 Taper Roller Bearing",  "Bearings",    "piece", 980,  700,  12,  15, "84822000", 18),  # below
    ("22210 Spherical Bearing",     "Bearings",    "piece", 2450, 1790, 6,   8,  "84823000", 18),  # below
    ("UCP 205 Pillow Block",        "Housings",    "piece", 690,  480,  34,  15, "84833000", 18),
    ("UCF 206 Flange Unit",         "Housings",    "piece", 820,  590,  18,  10, "84833000", 18),
    ("SN 510 Plummer Block",        "Housings",    "piece", 3250, 2400, 4,   6,  "84833000", 18),  # below
    ("V-Belt B-56",                 "Belts",       "piece", 410,  290,  85,  40, "40103990", 18),
    ("V-Belt C-90",                 "Belts",       "piece", 980,  700,  22,  20, "40103990", 18),
    ("Timing Belt 1200-8M",         "Belts",       "piece", 1450, 1050, 9,   8,  "40103990", 18),
    ("Chain 08B-1 10ft",            "Chains",      "piece", 1180, 860,  26,  12, "73151200", 18),
    ("Sprocket 08B-1 Z18",          "Chains",      "piece", 640,  450,  31,  12, "84836090", 18),
    ("Flexible Coupling L-095",     "Couplings",   "piece", 1350, 980,  14,  8,  "84836090", 18),
    ("Oil Seal 35x52x7",            "Seals",       "piece", 95,   58,   240, 80, "84842000", 18),
    ("Oil Seal 50x72x10",           "Seals",       "piece", 145,  92,   130, 60, "84842000", 18),
    ("Bearing Grease 500g",         "Consumables", "piece", 280,  195,  0,   24, "34031900", 18),  # out
    ("Circlip 52mm 10pc",           "Consumables", "packet", 130, 82,   60,  25, "73182900", 18),
    # planted dead stock — bought in, never sold
    ("Linear Bearing LM25UU",       "Bearings",    "piece", 780,  560,  18,  6,  "84821012", 18),
    ("Ball Screw 1605 500mm",       "Transmission", "piece", 4200, 3100, 5,  2,  "84834000", 18),
    ("Pneumatic Cylinder 32x100",   "Pneumatics",  "piece", 2350, 1700, 7,   3,  "84123110", 18),
]

DEAD = {"Linear Bearing LM25UU", "Ball Screw 1605 500mm", "Pneumatic Cylinder 32x100"}

#: (name, phone, how often they buy, do they take credit, typical order size)
#:
#: A sugar factory buys seldom and heavily; a garage buys constantly and small. That spread
#: is what makes customer concentration and the ageing schedule worth looking at.
CUSTOMERS = [
    ("Sanjeevani Motors",        "919845101010", "weekly",   True,  "small"),
    ("Hubballi Foundry Works",   "919886202020", "weekly",   True,  "medium"),
    ("Nandi Sugars Ltd",         "919972303030", "monthly",  True,  "large"),
    ("Vishwa Engineering Works", "919448404040", "biweekly", True,  "medium"),
    ("Raj Auto Spares",          "919035505050", "weekly",   False, "small"),
    ("Sri Datta Pump Works",     "919611606060", "monthly",  False, "medium"),
    ("Cash sale",                "",             "daily",    False, "small"),
]

SIZES = {"small": [2, 2, 4, 5, 6, 10], "medium": [5, 10, 12, 20, 25],
         "large": [20, 25, 40, 50, 60]}

#: How a spares distributor's running costs split. Salary dominates; rent on an industrial
#: estate is real money; transport is what it costs to get a bearing to a mill at night.
OPEX_SPLIT = [
    ("Salary",    "Staff wages",              0.44, 12),
    ("Rent",      "Godown & shop rent",       0.16, 12),
    ("Transport", "Sharma Transport",         0.12, 8),
    ("Tax",       "GST — monthly",            0.14, 4),
    ("Utilities", "HESCOM & phones",          0.06, 6),
    ("Repairs",   "Racking, vehicle & tools", 0.08, 4),
]

SUPPLIERS = ["Bharat Bearing Agencies", "Deccan Seals & Spares",
             "Shree Transmission Supplies"]

#: Spares distribution carries a better gross margin than agri inputs and a worse one than
#: retail. 8% net after everything is a healthy, credible distributor.
TARGET_NET_MARGIN = 0.08
RESTOCK_AHEAD = 1.05


def _expenses(revenue: float, cogs: float) -> list[tuple]:
    """Running costs derived from the revenue actually generated.

    Hand-picked figures cannot hold: change the sales and a fixed expense table turns the
    demo into a business that loses money. Returns rows of
    (category, party, amount, days_ago, paid, due_in_days).
    """
    gross = revenue - cogs
    opex_budget = max(gross - revenue * TARGET_NET_MARGIN, revenue * 0.05)
    rows: list[tuple] = []

    purchase_total = cogs * RESTOCK_AHEAD
    lumps = [0.20, 0.18, 0.16, 0.15, 0.13, 0.10, 0.08]
    ages = [330, 280, 232, 181, 124, 63, 18]
    for i, (share, age) in enumerate(zip(lumps, ages)):
        owed = i >= len(lumps) - 2                      # the two newest are still owed
        rows.append(("Purchase", SUPPLIERS[i % len(SUPPLIERS)],
                     round(purchase_total * share, -2), age, not owed,
                     (6 if i == len(lumps) - 1 else 19) if owed else ""))

    for category, party, share, count in OPEX_SPLIT:
        each = opex_budget * share / count
        for n in range(count):
            age = int(10 + n * (HISTORY_DAYS - 20) / max(count, 1))
            owed = category == "Tax" and n == count - 1     # one instalment still due
            rows.append((category, party, round(each, -2), age, not owed, 5 if owed else ""))
    return rows


def _wipe(owner_id: str) -> None:
    for c in store.load_clients(owner_id):
        for path in (books.BOOKS / f"{c.slug}.json", money.MONEY / f"{c.slug}.json",
                     people.PEOPLE / f"{c.slug}.json"):
            path.unlink(missing_ok=True)
        shutil.rmtree(store.UPLOADS / c.slug, ignore_errors=True)
        shutil.rmtree(store.DASHBOARDS / c.slug, ignore_errors=True)
        store.delete_client(c.slug, owner_id)


def build(quiet: bool = False) -> tuple[str, str]:
    """Create the account and the workspace. Returns (email, slug)."""
    rng = random.Random(SEED)

    def say(line: str) -> None:
        if not quiet:
            print(line)

    account = auth.by_email(EMAIL)
    if account is None:
        account = auth.create(EMAIL, "Vyuha Demo (bearings)", PASSWORD, install="operator")
        say(f"  account    {EMAIL} / {PASSWORD}")
    else:
        say(f"  account    {EMAIL} (already existed)")
    account.install, account.org_name, account.tenant_slug = "operator", "", ""
    auth.update(account)
    _wipe(account.id)

    client = store.add_client(
        account.id, name=BUSINESS, phone="919845000333",
        contact="Prakash Shetty", email="shakti.bearings@example.com",
        industry="Bearings & power transmission", trade="manufacturing",
        data_mode="books", dead_stock_days=90, low_cover_days=21,
        address="Shed 22, Chitaguppi Industrial Estate\nGokul Road, Hubballi 580030\n"
                "Karnataka",
        gstin="29SHAKT4321B1Z9", state="KA",
        bank_name="Canara Bank, Gokul Road", bank_account="0891201004567",
        bank_ifsc="CNRB0000891", invoice_template="classic",
        invoice_terms="Payment within 30 days. Goods once sold are not taken back.")
    slug = client.slug
    say(f"  workspace  {BUSINESS}  ->  /app/{slug}")

    # --- branches and the people in them
    people.add_branch(slug, "Gokul Road", "Chitaguppi Industrial Estate, Hubballi",
                      manager="Prakash Shetty")
    people.add_branch(slug, "Gadag Road", "Opp. APMC, Gadag", manager="Santosh Patil")
    org = people.load(slug)
    main_id, second_id = org.branches[0].id, org.branches[1].id
    for name, role, branch, phone, target, commission in [
        ("Prakash Shetty", "Owner", main_id, "9999100001", 0, 0),
        ("Santosh Patil", "Manager", second_id, "9999100002", 900000, 1.0),
        ("Rekha Kulkarni", "Accountant", main_id, "9999100003", 0, 0),
        ("Imtiaz Ahmed", "Salesperson", main_id, "9999100004", 1200000, 1.5),
        ("Vinay Hegde", "Salesperson", second_id, "9999100005", 800000, 1.5),
        ("Basavaraj Kamble", "Delivery", main_id, "9999100006", 0, 0),
    ]:
        people.add_staff(slug, name, role, branch, phone=phone, target=target,
                         commission=commission)
    org = people.load(slug)
    sellers = {p.name: p.id for p in org.staff}
    say("  branches   2, staff 6")

    # --- the catalogue, with the tax details a real invoice needs
    for name, cat, unit, rate, cost, stock, reorder, _hsn, _gst in CATALOGUE:
        books.add_item(slug, name, cat, unit, rate, cost, stock, reorder)
    book = books.load(slug)
    tax_by_name = {row[0]: (row[7], row[8]) for row in CATALOGUE}
    for i in book.items:
        i.hsn, i.gst_rate = tax_by_name.get(i.name, ("", 0.0))
    books.save(book)
    say(f"  items      {len(CATALOGUE)}, all at 18% GST with HSN codes")

    # --- a year of sales
    book = books.load(slug)
    sellable = [i for i in book.items if i.name not in DEAD]
    cadence = {"daily": 2, "weekly": 7, "biweekly": 15, "monthly": 30}
    sales = 0
    for name, phone, rhythm, takes_credit, size in CUSTOMERS:
        step = cadence[rhythm]
        # Vishwa Engineering goes quiet 80 days ago; everyone else buys up to this week.
        stop = 80 if name == "Vishwa Engineering Works" else 3
        day = HISTORY_DAYS
        while day > stop:
            item = rng.choice(sellable)
            qty = rng.choice(SIZES[size])
            branch = main_id if rng.random() < 0.65 else second_id
            seller = ""
            if rng.random() < 0.8:
                seller = (rng.choice([sellers["Imtiaz Ahmed"], sellers["Prakash Shetty"]])
                          if branch == main_id else
                          rng.choice([sellers["Vinay Hegde"], sellers["Santosh Patil"]]))
            # Older credit was settled long ago; leaving it open would read as a failing
            # business rather than a working one.
            on_credit = takes_credit and day < 50 and rng.random() < 0.35
            books.record_sale(slug, item.sku, name, qty, item.rate, when=_ago(day),
                              paid=not on_credit,
                              due_date=_ago(day - 30) if on_credit else "",
                              party_phone=phone, branch=branch, staff=seller)
            sales += 1
            day -= step + rng.randint(-1, 2)

    # --- counter trade through the last six weeks
    #
    # Without it the current month reads as a collapse against the last, and a demo that
    # opens on "-59%" invites a question about the data rather than about the product.
    for day in range(45, 2, -1):
        if rng.random() < 0.8:
            item = rng.choice(sellable)
            books.record_sale(slug, item.sku, "Cash sale", rng.choice([2, 4, 5, 6, 10, 12]),
                              item.rate, when=_ago(day), paid=True, branch=main_id,
                              staff=sellers["Imtiaz Ahmed"] if rng.random() < 0.6 else "")
            sales += 1

    # --- three deliberately overdue bills, at three ages
    fresh = books.load(slug)
    def item_of(name: str):
        return next(i for i in fresh.items if i.name == name)

    for party, phone, item_name, qty, age, due_age, branch in [
        ("Nandi Sugars Ltd", "919972303030", "22210 Spherical Bearing", 24, 104, 74, main_id),
        ("Hubballi Foundry Works", "919886202020", "SN 510 Plummer Block", 12, 66, 36, main_id),
        ("Sanjeevani Motors", "919845101010", "6205 2RS Ball Bearing", 60, 41, 11, second_id),
    ]:
        it = item_of(item_name)
        books.record_sale(slug, it.sku, party, qty, it.rate, when=_ago(age), paid=False,
                          due_date=_ago(due_age), party_phone=phone, branch=branch,
                          staff=sellers["Imtiaz Ahmed"])
        sales += 1
    say(f"  sales      {sales} bills over twelve months")

    # --- put the planted stock levels back where the sales ate into them
    book = books.load(slug)
    for name, _c, _u, _r, _co, stock, *_rest in CATALOGUE:
        item = next((i for i in book.items if i.name == name), None)
        if item is not None:
            item.stock_qty = stock
    books.save(book)

    # --- the register for the last fortnight
    marked = 0
    for person in people.load(slug).staff:
        for back in range(1, 15):
            when = _ago(back)
            if date.fromisoformat(when).weekday() == 6:        # shut on Sunday
                continue
            roll = rng.random()
            state = ("present" if roll < 0.9 else "half" if roll < 0.95
                     else "leave" if roll < 0.98 else "absent")
            people.mark_attendance(slug, person.id, state, when)
            marked += 1
    say(f"  register   {marked} days marked across 6 people")

    # --- stock moved between the two godowns
    now = books.load(slug)
    for item_name, qty in [("6205 2RS Ball Bearing", 40), ("V-Belt B-56", 20),
                           ("Oil Seal 35x52x7", 60)]:
        it = next((i for i in now.items if i.name == item_name), None)
        if it is not None:
            people.transfer_stock(slug, it.sku, it.name, qty, main_id, second_id,
                                  note="Weekly top-up")
    say("  transfers  3 between godowns")

    # --- money out, sized from the revenue that was actually generated
    book = books.load(slug)
    by_sku = {i.sku: i for i in book.items}
    revenue = book.earned
    cogs = sum((by_sku[s.sku].cost if s.sku in by_sku else 0) * s.qty for s in book.sales)
    rows = _expenses(revenue, cogs)
    for category, party, amount, days, paid, due in rows:
        money.add_expense(slug, category, party, amount, when=_ago(days), paid=paid,
                          due_date=_ahead(due) if due != "" else "",
                          branch=main_id if category not in {"Salary", "Tax"} else "")
    say(f"  expenses   {len(rows)} across {len({r[0] for r in rows})} heads")

    # --- invoices: one inside the state, one outside it, so both tax shapes appear
    raised = _invoices(client, say)

    # --- a scheduled brief, so the routine can be shown firing
    owner = next((s for s in people.load(slug).staff if s.role == "Owner"), None)
    routines.add(slug, "Owner's 8am brief", client.phone,
                 staff_id=owner.id if owner else "", at="08:00",
                 days=["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"],
                 sections=["decisions", "money", "stock", "chase"])
    say("  routine    Owner's 8am brief, Mon–Sat")

    _onboarding(slug, say)

    _build_dashboard(slug, client)
    say("  dashboard  generated from the book")

    _report(slug, raised, say)
    return EMAIL, slug


#: Who gets a proper tax invoice, and where they are. Three in Karnataka and one outside
#: it, so CGST+SGST and IGST both appear — and enough of them that the tax collected is a
#: real figure rather than two bills against a year of purchases.
BILLED = [
    ("Nandi Sugars Ltd", "29NANDI7788K1Z2", "KA", 5),
    ("Hubballi Foundry Works", "29HUBLI3344F1Z6", "KA", 5),
    ("Sanjeevani Motors", "29SANJE9911M1Z3", "KA", 4),
    ("Vishwa Engineering Works", "27VISHW4455E1Z8", "MH", 4),
]


def _invoices(client, say) -> int:
    """Bill the named customers properly. One invoice is for one customer, so this bills
    each of them in turn, four lines at a time, newest first."""
    slug = client.slug
    raised = last = 0
    for party, gstin, state, count in BILLED:
        for _ in range(count):
            book = books.load(slug)
            billed = {sid for inv in invoice.load_all(slug) for sid in inv.sale_ids}
            ids = [s.id for s in book.sales
                   if s.party == party and s.id not in billed][-4:]
            if not ids:
                break
            try:
                inv, _note = invoice.issue(client, book, ids, party_gstin=gstin,
                                           party_state=state)
            except ValueError:
                break
            raised += 1
            last = inv.rounded
            client = store.get_client(slug, client.owner_id)   # the number was consumed
        say(f"  invoices   {party}: billed ({'CGST+SGST' if state == 'KA' else 'IGST'})")
    if raised:
        say(f"  invoices   {raised} raised, the last for Rs {last:,.0f}")
    return raised


#: The data-map interview as this business answered it: the office keeps sales, purchases,
#: stock and dues in Excel; the counter keeps expenses and the register on paper; supplier
#: bills arrive as bills. It is the spread that makes the import plan worth reading.
ANSWERS = {
    "sales":       ("excel", "", "daily", "Rekha, in the office"),
    "purchases":   ("excel", "", "weekly", "Rekha, in the office"),
    "stock":       ("excel", "", "monthly", "Santosh, at the godown"),
    "receivables": ("excel", "", "weekly", "Rekha, in the office"),
    "payables":    ("bills", "", "weekly", "Prakash keeps the file"),
    "expenses":    ("paper", "", "daily", "the counter book"),
    "cash":        ("paper", "", "daily", "the counter book"),
    "staff":       ("paper", "", "daily", "Santosh marks the register"),
}


def _onboarding(slug: str, say) -> None:
    """The Studio record: the interview answered and a cut-over a year back.

    Stage status is derived from the business itself, so this does not mark anything done
    by hand — profile, data map and masters come out done because the workspace really has
    those things.
    """
    first_of_this_month = date.today().replace(day=1)
    cutover = (first_of_this_month - timedelta(days=HISTORY_DAYS)).replace(day=1)
    record = onboarding.load(slug)
    record.datamap = {
        domain: onboarding.Answer(source=source, software=software, cadence=cadence,
                                  keeper=keeper, since=cutover.strftime("%Y-%m"))
        for domain, (source, software, cadence, keeper) in ANSWERS.items()
    }
    record.cutover = cutover.isoformat()
    record.history_months = 12
    record.fy_start_month = 4
    onboarding.save(record)
    say(f"  onboarding data map answered for all {len(ANSWERS)} records, "
        f"cut-over {cutover.isoformat()}")


def _build_dashboard(slug: str, client) -> None:
    """Put the book through the real engine, so the client dashboard exists."""
    from datetime import datetime

    from vyuha import pipeline

    from . import channels

    book = books.load(slug)
    if not book.sales and not book.items:
        return
    workbook = books.to_workbook(book, store.upload_dir(slug) / "books.xlsx")
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    result = pipeline.run(workbook)
    out = store.dashboard_dir(slug) / f"{run_id}.html"
    pipeline.write_report(result, out, client=client.name)

    ins = result.insights
    run = store.Run(
        id=run_id, filename="books.xlsx",
        uploaded_at=datetime.now().isoformat(timespec="seconds"),
        source_kind="manual", source_method="Typed in directly", confidence="high",
        dashboard=f"{slug}/{run_id}.html",
        sheets_read=[t.kind.title() for t in result.tables],
        alerts=[{"code": a.code, "severity": a.severity, "title": a.title,
                 "detail": a.detail, "entities": list(a.entities)}
                for a in channels.ordered(ins)],
        alert_count=len(ins.alerts),
        critical_count=sum(1 for a in ins.alerts if a.severity == "critical"),
        revenue=float(ins.sales.get("revenue") or 0),
        stock_value=float(ins.stock.get("value") or 0),
        outstanding=float(ins.receivables.get("total") or 0))
    fresh = store.get_client(slug, client.owner_id)
    fresh.runs = [run]
    store.update_client(fresh)


def _report(slug: str, raised: int, say) -> None:
    """What the demo should now show — the numbers to rehearse against."""
    from . import finance, followup

    book, led = books.load(slug), money.load(slug)
    pos = money.position(book, led)
    pl = finance.profit_and_loss(book, led)
    queue = followup.queue(slug, book)
    say("")
    say(f"  earned     Rs {book.earned:,.0f}   collected Rs {book.collected:,.0f}"
        f"   owed Rs {book.owed:,.0f}")
    say(f"  cash       in Rs {pos['came_in']:,.0f}   out Rs {pos['went_out']:,.0f}"
        f"   net Rs {pos['net']:,.0f}")
    say(f"  P&L        gross Rs {pl['gross_profit']:,.0f} ({pl['gross_margin_pct']:.1f}%)"
        f"   net Rs {pl['net_profit']:,.0f} ({pl['net_margin_pct']:.1f}%)")
    say(f"  stock      {len(book.low_stock)} below reorder, {len(book.out_of_stock)} out, "
        f"{len(DEAD)} never sold, Rs {book.stock_value:,.0f} on the shelf")
    say(f"  to chase   {len(queue)} "
        f"({sum(1 for f in queue if f.kind == 'payment')} overdue, "
        f"{sum(1 for f in queue if f.kind == 'dormant')} gone quiet)")
    say(f"  invoices   {raised} raised")


def main() -> None:
    print(f"\n  Seeding the bearings demo\n  {'-' * 46}")
    email, slug = build()
    print(f"\n  Start it:  .venv/Scripts/python -m vyuha_platform --open")
    print(f"  Log in:    {email} / {PASSWORD}")
    print(f"  The site:  http://127.0.0.1:8000/app/{slug}")
    print(f"  Studio:    http://127.0.0.1:8000/studio\n")


if __name__ == "__main__":
    main()
