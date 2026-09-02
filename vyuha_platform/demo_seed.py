"""Build the demo workspace, from nothing, in one command.

``.venv/Scripts/python -m vyuha_platform seed``

Never demo off live data. Two reasons, and the second is the one that bites:
a live workspace has whatever numbers it happens to have that morning, so a
rehearsed line ("notice the ninety-four days") is wrong by the time you say it;
and two people building against different data disagree about whether something
is broken.

So this writes **Shree Agro & Hardware, Belagavi** — the business the demo
script is about — with every beat's evidence deliberately planted:

* two branches, so the People panel has something to compare
* three items below reorder and one already out, so Stock opens on a real list
* a SKU that has not moved in ~100 days, so "what is not selling" has an answer
* two customers overdue at different ages, so Follow-ups sorts by severity
* one repeat customer gone quiet, so the dormant path is visible
* expenses across five heads, so Money is a cash flow and not a receivables list

Everything is **deterministic** — a fixed seed and dates relative to today — so
the same command on two machines produces the same numbers, and re-running it
after a messy rehearsal puts it back exactly.

Idempotent: running it again wipes the workspace and rebuilds it.
"""

from __future__ import annotations

import random
import shutil
from datetime import date, timedelta

from . import auth, books, money, people, store

EMAIL = "demo@vyuha.test"
PASSWORD = "vyuha-demo"
BUSINESS = "Shree Agro & Hardware"

#: Fixed, so two machines produce identical books.
SEED = 20260830


def _ago(days: int) -> str:
    return (date.today() - timedelta(days=days)).isoformat()


def _ahead(days: int) -> str:
    return (date.today() + timedelta(days=days)).isoformat()


#: HSN code and GST rate per item. Real rates: fertiliser is 5%, most seed is
#: nil, tools and hardware are 18%. A demo invoice with one flat rate on every
#: line hides the only complication that matters — the tax summary a mixed-rate
#: bill needs.
GST: dict[str, tuple[str, float]] = {
    "Urea 50kg": ("31021000", 5), "DAP 50kg": ("31053000", 5),
    "Potash 50kg": ("31042000", 5), "Gypsum 5kg": ("25202010", 5),
    "Neem Cake 10kg": ("23064100", 5), "Vermicompost 25kg": ("31010099", 5),
    "Cattle Feed 50kg": ("23099010", 0), "Paddy Seed 5kg": ("10061010", 0),
    "Tomato Seed 100g": ("12099130", 0), "Chilli Seed 100g": ("12099130", 0),
    "Sprayer 16L": ("84242000", 18), "Pruning Shears": ("82016000", 18),
    "Spade": ("82011000", 18), "HDPE Pipe 1in 10m": ("39172390", 18),
    "Drip Emitter 100pc": ("84248200", 18), "GI Wire 5kg": ("72171090", 18),
    "Tarpaulin 12x15": ("63062200", 18), "Soil Test Kit": ("90271000", 18),
    "Mango Sapling": ("06022090", 0), "Organic Pesticide 1L": ("38089199", 18),
}

#: (name, category, unit, rate, cost, stock, reorder)
CATALOGUE = [
    ("Urea 50kg",            "Fertiliser", "bag",   320,  268,  62,  20),
    ("DAP 50kg",             "Fertiliser", "bag",   1420, 1250, 8,   15),   # below
    ("Potash 50kg",          "Fertiliser", "bag",   980,  860,  31,  12),
    ("Gypsum 5kg",           "Fertiliser", "bag",   140,  98,   0,   25),   # out
    ("Neem Cake 10kg",       "Fertiliser", "bag",   380,  305,  44,  10),
    ("Vermicompost 25kg",    "Fertiliser", "bag",   290,  215,  6,   18),   # below
    ("Cattle Feed 50kg",     "Feed",       "bag",   1180, 1040, 27,  10),
    ("Paddy Seed 5kg",       "Seed",       "pkt",   640,  520,  38,  15),
    ("Tomato Seed 100g",     "Seed",       "pkt",   210,  155,  52,  20),
    ("Chilli Seed 100g",     "Seed",       "pkt",   260,  190,  9,   20),   # below
    ("Sprayer 16L",          "Tools",      "piece", 2250, 1780, 14,  5),
    ("Pruning Shears",       "Tools",      "piece", 480,  330,  22,  8),
    ("Spade",                "Tools",      "piece", 390,  280,  18,  6),
    ("HDPE Pipe 1in 10m",    "Hardware",   "coil",  870,  690,  25,  8),
    ("Drip Emitter 100pc",   "Hardware",   "box",   540,  405,  33,  10),
    ("GI Wire 5kg",          "Hardware",   "coil",  620,  495,  16,  6),
    ("Tarpaulin 12x15",      "Hardware",   "piece", 1150, 900,  11,  4),
    # planted dead stock — bought in, never sold
    ("Soil Test Kit",        "Tools",      "piece", 3200, 2600, 7,   2),
    ("Mango Sapling",        "Plants",     "piece", 180,  110,  40,  10),
    ("Organic Pesticide 1L", "Crop Care",  "btl",   760,  610,  19,  6),
]

#: (name, phone, how often they buy, do they take credit)
CUSTOMERS = [
    ("Ramu Stores",           "919845012345", "weekly",   True),
    ("Basavaraj Agri Centre", "919886054321", "weekly",   True),
    ("M/s Krishna Traders",   "919972011122", "biweekly", True),
    ("Shetty Farms",          "919448033344", "monthly",  False),
    ("Patil Nursery",         "919035066677", "monthly",  False),
    ("Cash sale",             "",             "daily",    False),
]

#: How the running costs of a distributor split, as a share of the operating
#: expense budget. Salary dominates because six people do; the rest follow from
#: what a two-branch operation actually pays for.
OPEX_SPLIT = [
    ("Salary",    "Staff wages",             0.46, 9),
    ("Rent",      "Godown & shop rent",      0.14, 9),
    ("Transport", "Mahesh Tempo Service",    0.11, 6),
    ("Tax",       "GST — quarterly",         0.16, 3),
    ("Utilities", "HESCOM",                  0.06, 5),
    ("Repairs",   "Godown & vehicle",        0.07, 3),
]

#: Net margin the demo business should land on. Agri-input distribution is a
#: thin-margin, high-volume trade; 6% after everything is healthy and credible,
#: where 20% would invite the question of why he needs software at all.
TARGET_NET_MARGIN = 0.06

#: Purchases run slightly ahead of what was sold — a distributor restocks before
#: the shelf empties. This is why cash out can exceed cost of goods in a period.
RESTOCK_AHEAD = 1.06


def _expenses(revenue: float, cogs: float, rng) -> list[tuple]:
    """Build the expense table from the revenue that was actually generated.

    Hand-picked figures cannot hold: the first version of this seed paired a 13%
    gross margin with Rs 1.88L of running costs, producing a business that lost
    money on every statement. Deriving them means the demo is always coherent,
    whatever the sales happen to come out at.

    Returns rows of (category, party, amount, days_ago, paid, due_in_days).
    """
    gross = revenue - cogs
    opex_budget = max(gross - revenue * TARGET_NET_MARGIN, revenue * 0.04)

    rows: list[tuple] = []

    # Purchases, in lumps, across the period. Two are still owed, which is what
    # gives the payables ageing something to show.
    purchase_total = cogs * RESTOCK_AHEAD
    lumps = [0.26, 0.22, 0.19, 0.15, 0.10, 0.08]
    ages = [232, 188, 141, 96, 52, 14]
    suppliers = ["Coromandel Distributors", "Nagarjuna Agrichem",
                 "Coromandel Distributors", "Kaveri Seeds",
                 "Nagarjuna Agrichem", "Coromandel Distributors"]
    for i, (share, age) in enumerate(zip(lumps, ages)):
        owed = i >= len(lumps) - 2          # the two newest are unpaid
        rows.append(("Purchase", suppliers[i], round(purchase_total * share, -2),
                     age, not owed, (9 if i == len(lumps) - 1 else 21) if owed else ""))

    # Running costs, spread over the period so the monthly trend is not a spike.
    for category, party, share, count in OPEX_SPLIT:
        each = opex_budget * share / count
        for n in range(count):
            age = int(14 + n * (250 / max(count, 1)))
            # One tax instalment is still due, so the money panel has a bill
            # landing this week rather than a tidy all-paid ledger.
            owed = category == "Tax" and n == count - 1
            rows.append((category, party, round(each, -2), age, not owed,
                         4 if owed else ""))
    return rows


def _wipe(owner_id: str) -> None:
    for c in store.load_clients(owner_id):
        for path in (books.BOOKS / f"{c.slug}.json",
                     money.MONEY / f"{c.slug}.json",
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

    # --- the account
    account = auth.by_email(EMAIL)
    if account is None:
        account = auth.create(EMAIL, "Vyuha Demo", PASSWORD, install="operator")
        say(f"  account   {EMAIL} / {PASSWORD}")
    else:
        say(f"  account   {EMAIL} (already existed)")
    account.install, account.org_name, account.tenant_slug = "operator", "", ""
    auth.update(account)

    _wipe(account.id)

    # --- the workspace
    client = store.add_client(
        account.id, name=BUSINESS, phone="919845000111",
        contact="Vishwanath Patil", email="shreeagro@example.com",
        industry="Agri-inputs & hardware", trade="hardware",
        data_mode="books", dead_stock_days=90, low_cover_days=14,
        # Without these an invoice is only a bill of supply, and the demo cannot
        # show the thing a buyer's accountant actually wants.
        address="Plot 14, APMC Yard Road\nTilakwadi, Belagavi 590006\nKarnataka",
        gstin="29ABCDE1234F1Z5", state="KA",
        bank_name="Karnataka Bank, Belagavi Main",
        bank_account="0472500101234501", bank_ifsc="KARB0000472",
        invoice_template="classic")
    slug = client.slug
    say(f"  workspace  {BUSINESS}  ->  /c/{slug}/console")

    # --- branches and staff
    people.add_branch(slug, "Belagavi", "Main Road, Belagavi", manager="Vishwanath Patil")
    people.add_branch(slug, "Hubballi", "Market Yard, Hubballi", manager="Girish Kulkarni")
    org = people.load(slug)
    main_id, second_id = org.branches[0].id, org.branches[1].id
    # Targets only on the people who carry one. A delivery hand at 0% of a
    # target he was never given is noise on the screen, not a finding.
    for name, role, branch, target, commission in [
        ("Vishwanath Patil", "Owner", main_id, 0, 0),
        ("Girish Kulkarni", "Manager", second_id, 250000, 1.0),
        ("Sunita Desai", "Accountant", main_id, 0, 0),
        ("Mahesh Naik", "Salesperson", main_id, 320000, 2.0),
        ("Iranna Hosur", "Salesperson", second_id, 220000, 2.0),
        ("Ravi Gouda", "Delivery", second_id, 0, 0),
    ]:
        people.add_staff(slug, name, role, branch, target=target,
                         commission=commission)
    org = people.load(slug)
    sellers = {p.name: p.id for p in org.staff}
    say(f"  branches   2, staff 6")

    # --- the catalogue, with tax details
    for name, cat, unit, rate, cost, stock, reorder in CATALOGUE:
        books.add_item(slug, name, cat, unit, rate, cost, stock, reorder)
    book = books.load(slug)
    for i in book.items:
        i.hsn, i.gst_rate = GST.get(i.name, ("", 0.0))
    books.save(book)
    rates = sorted({r for _h, r in GST.values()})
    say(f"  items      {len(CATALOGUE)} across GST rates {rates}")

    # --- nine months of sales
    book = books.load(slug)
    #: The three planted dead SKUs never appear in a sale.
    dead = {"Soil Test Kit", "Mango Sapling", "Organic Pesticide 1L"}
    sellable = [i for i in book.items if i.name not in dead]
    phones = {n: p for n, p, _, _ in CUSTOMERS}

    cadence = {"daily": 2, "weekly": 8, "biweekly": 16, "monthly": 30}
    sales = 0
    for name, phone, rhythm, takes_credit in CUSTOMERS:
        step = cadence[rhythm]
        # Ramu goes quiet 70 days ago; everyone else buys up to this week.
        stop = 70 if name == "M/s Krishna Traders" else 3
        day = 270
        while day > stop:
            item = rng.choice(sellable)
            # Distributor volumes. A two-branch agri dealer moves bags by the
            # tens; the old 1-to-10 range produced a corner shop whose turnover
            # could not carry six staff, and every ratio said so.
            qty = rng.choice([10, 15, 20, 20, 25, 30, 40, 50, 60, 80, 100])
            branch = main_id if rng.random() < 0.62 else second_id
            # Whoever works that counter rang it up. A slice is left
            # unattributed on purpose: real books always have some, and the
            # screen has to show that honestly rather than share it out.
            seller = ""
            if rng.random() < 0.78:
                seller = (rng.choice([sellers["Mahesh Naik"], sellers["Vishwanath Patil"]])
                          if branch == main_id else
                          rng.choice([sellers["Iranna Hosur"], sellers["Girish Kulkarni"]]))
            # Credit older than ~45 days was settled long ago. Leaving every
            # historic credit sale open would put 17 names in the chase queue,
            # which reads as a failing business rather than a working one.
            on_credit = takes_credit and day < 45 and rng.random() < 0.30
            books.record_sale(
                slug, item.sku, name, qty, item.rate,
                when=_ago(day),
                paid=not on_credit,
                due_date=_ago(day - 30) if on_credit else "",
                party_phone=phone,
                branch=branch,
                staff=seller,
            )
            sales += 1
            day -= step + rng.randint(-1, 2)

    # --- two deliberately overdue bills, so Follow-ups has a known top row
    urea = next(i for i in books.load(slug).items if i.name == "Urea 50kg")
    dap = next(i for i in books.load(slug).items if i.name == "DAP 50kg")
    books.record_sale(slug, urea.sku, "Ramu Stores", 260, urea.rate, when=_ago(96),
                      paid=False, due_date=_ago(66), party_phone=phones["Ramu Stores"],
                      branch=main_id)
    books.record_sale(slug, dap.sku, "Basavaraj Agri Centre", 95, dap.rate, when=_ago(48),
                      paid=False, due_date=_ago(18),
                      party_phone=phones["Basavaraj Agri Centre"], branch=second_id)
    sales += 2
    say(f"  sales      {sales} bills over ~9 months")

    # --- restore the planted stock levels that the sales just ate into
    book = books.load(slug)
    for name, _, _, _, _, stock, _ in CATALOGUE:
        item = next((i for i in book.items if i.name == name), None)
        if item is not None:
            item.stock_qty = stock
    books.save(book)

    # --- the register for the last fortnight
    marked = 0
    for person in people.load(slug).staff:
        for back in range(1, 15):
            when = _ago(back)
            if date.fromisoformat(when).weekday() == 6:      # shop shuts Sunday
                continue
            roll = rng.random()
            state = ("present" if roll < 0.88 else
                     "half" if roll < 0.94 else
                     "leave" if roll < 0.97 else "absent")
            people.mark_attendance(slug, person.id, state, when)
            marked += 1
    say(f"  register   {marked} day(s) marked across 6 people")

    # --- stock moved between the two godowns
    book_now = books.load(slug)
    for item_name, qty in [("Urea 50kg", 40), ("Cattle Feed 50kg", 15),
                           ("HDPE Pipe 1in 10m", 8)]:
        item = next((i for i in book_now.items if i.name == item_name), None)
        if item is not None:
            people.transfer_stock(slug, item.sku, item.name, qty, main_id,
                                  second_id, note="Weekly top-up")
    say(f"  transfers  3 between godowns")

    # --- money out, sized from the revenue that was actually generated
    book = books.load(slug)
    by_sku = {i.sku: i for i in book.items}
    revenue = book.earned
    cogs = sum((by_sku[s.sku].cost if s.sku in by_sku else 0) * s.qty
               for s in book.sales)
    rows = _expenses(revenue, cogs, rng)
    for category, party, amount, days, paid, due in rows:
        money.add_expense(slug, category, party, amount, when=_ago(days), paid=paid,
                          due_date=_ahead(due) if due != "" else "",
                          branch=main_id if category not in {"Salary", "Tax"} else "")
    say(f"  expenses   {len(rows)} across {len({r[0] for r in rows})} heads")

    # --- run the engine over the typed-in book, so the client dashboard exists
    #
    # Without this the seed leaves a workspace whose "See the dashboard" button
    # opens nothing: the books path only writes a dashboard when somebody edits
    # an entry through the UI, and the seed writes entries directly. The demo
    # then fails on the one screen that is meant to be forwarded to the client.
    _build_dashboard(slug, client)
    say(f"  dashboard  generated from the book")

    # --- what the demo should now show
    b, ledger = books.load(slug), money.load(slug)
    from . import followup
    queue = followup.queue(slug, b)
    pos = money.position(b, ledger)
    say("")
    say(f"  earned     Rs {b.earned:,.0f}   collected Rs {b.collected:,.0f}"
        f"   owed Rs {b.owed:,.0f}")
    say(f"  cash       in Rs {pos['came_in']:,.0f}   out Rs {pos['went_out']:,.0f}"
        f"   net Rs {pos['net']:,.0f}")
    say(f"  stock      {len(b.low_stock)} below reorder, {len(b.out_of_stock)} out, "
        f"{len([i for i in b.items if i.name in dead])} never sold")
    from . import finance
    pl = finance.profit_and_loss(b, ledger)
    say(f"  P&L        gross Rs {pl['gross_profit']:,.0f} ({pl['gross_margin_pct']:.1f}%)"
        f"   net Rs {pl['net_profit']:,.0f} ({pl['net_margin_pct']:.1f}%)")
    pf = people.by_person(people.load(slug), b)
    top = pf[1] if len(pf) > 1 else None
    if top:
        say(f"  selling    {top['name']} leads on Rs {top['revenue']:,.0f} "
            f"({top['pct_of_target']}% of target)" if top["pct_of_target"] is not None
            else f"  selling    {top['name']} leads on Rs {top['revenue']:,.0f}")
    say(f"  to chase   {len(queue)} "
        f"({sum(1 for f in queue if f.kind == 'payment')} overdue, "
        f"{sum(1 for f in queue if f.kind == 'dormant')} gone quiet)")
    return EMAIL, slug


def _build_dashboard(slug: str, client) -> None:
    """Put the book through the real engine and write the client dashboard.

    Mirrors ``app._rebuild_from_book`` rather than importing it: pulling the web
    app into the seeder would drag in FastAPI and every route just to render one
    file, and the seeder has to work from a bare ``python -m`` with no server.
    """
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
        outstanding=float(ins.receivables.get("total") or 0),
    )
    fresh = store.get_client(slug, client.owner_id)
    fresh.runs = [run]
    store.update_client(fresh)


def main() -> None:
    print(f"\n  Seeding the demo workspace\n  {'-' * 46}")
    email, slug = build()
    print(f"\n  Start it:  .venv/Scripts/python -m vyuha_platform --open")
    print(f"  Log in:    {email} / {PASSWORD}")
    print(f"  Console:   http://127.0.0.1:8000/c/{slug}/console\n")


if __name__ == "__main__":
    main()
