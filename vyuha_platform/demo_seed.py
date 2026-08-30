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

EXPENSES = [
    ("Purchase",  "Coromandel Distributors", 78000, 210, True,  ""),
    ("Purchase",  "Coromandel Distributors", 56000, 120, True,  ""),
    ("Purchase",  "Nagarjuna Agrichem",       34000,  74, True,  ""),
    ("Purchase",  "Coromandel Distributors",  42000,  35, True,  ""),
    ("Purchase",  "Nagarjuna Agrichem",       28000,   4, False, 11),   # bill owed
    ("Purchase",  "Kaveri Seeds",             19000,   2, False, 5),    # bill owed
    ("Rent",      "Shop landlord",            18000,  32, True,  ""),
    ("Rent",      "Shop landlord",            18000,   2, True,  ""),
    ("Salary",    "Staff wages",              46000,  31, True,  ""),
    ("Salary",    "Staff wages",              46000,   1, True,  ""),
    ("Transport", "Mahesh Tempo Service",      8600,  18, True,  ""),
    ("Transport", "Mahesh Tempo Service",      7200,   6, True,  ""),
    ("Utilities", "HESCOM",                    4300,  12, True,  ""),
    ("Utilities", "HESCOM",                    3950,  42, True,  ""),
    ("Repairs",   "Godown shutter",            5400,  22, True,  ""),
    ("Tax",       "GST — quarterly",          31000,   9, False, 3),    # due soon
]


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
    client = store.add_client(account.id, name=BUSINESS, phone="919845000111",
                              contact="Vishwanath Patil", email="shreeagro@example.com",
                              industry="Agri-inputs & hardware", trade="hardware",
                              data_mode="books", dead_stock_days=90, low_cover_days=14)
    slug = client.slug
    say(f"  workspace  {BUSINESS}  ->  /c/{slug}/console")

    # --- branches and staff
    people.add_branch(slug, "Belagavi", "Main Road, Belagavi", manager="Vishwanath Patil")
    people.add_branch(slug, "Hubballi", "Market Yard, Hubballi", manager="Girish Kulkarni")
    org = people.load(slug)
    main_id, second_id = org.branches[0].id, org.branches[1].id
    for name, role, branch in [
        ("Vishwanath Patil", "Owner", main_id),
        ("Girish Kulkarni", "Manager", second_id),
        ("Sunita Desai", "Accountant", main_id),
        ("Mahesh Naik", "Salesperson", main_id),
        ("Iranna Hosur", "Salesperson", second_id),
        ("Ravi Gouda", "Delivery", second_id),
    ]:
        people.add_staff(slug, name, role, branch)
    say(f"  branches   2, staff 6")

    # --- the catalogue
    for name, cat, unit, rate, cost, stock, reorder in CATALOGUE:
        books.add_item(slug, name, cat, unit, rate, cost, stock, reorder)
    say(f"  items      {len(CATALOGUE)}")

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
            qty = rng.choice([1, 2, 2, 3, 5, 5, 10])
            branch = main_id if rng.random() < 0.62 else second_id
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
            )
            sales += 1
            day -= step + rng.randint(-1, 2)

    # --- two deliberately overdue bills, so Follow-ups has a known top row
    urea = next(i for i in books.load(slug).items if i.name == "Urea 50kg")
    dap = next(i for i in books.load(slug).items if i.name == "DAP 50kg")
    books.record_sale(slug, urea.sku, "Ramu Stores", 40, urea.rate, when=_ago(96),
                      paid=False, due_date=_ago(66), party_phone=phones["Ramu Stores"],
                      branch=main_id)
    books.record_sale(slug, dap.sku, "Basavaraj Agri Centre", 12, dap.rate, when=_ago(48),
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

    # --- money out
    for category, party, amount, days, paid, due in EXPENSES:
        money.add_expense(slug, category, party, amount, when=_ago(days), paid=paid,
                          due_date=_ahead(due) if due != "" else "",
                          branch=main_id if category != "Salary" else "")
    say(f"  expenses   {len(EXPENSES)} across {len({e[0] for e in EXPENSES})} heads")

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
    say(f"  to chase   {len(queue)} "
        f"({sum(1 for f in queue if f.kind == 'payment')} overdue, "
        f"{sum(1 for f in queue if f.kind == 'dormant')} gone quiet)")
    return EMAIL, slug


def main() -> None:
    print(f"\n  Seeding the demo workspace\n  {'-' * 46}")
    email, slug = build()
    print(f"\n  Start it:  .venv/Scripts/python -m vyuha_platform --open")
    print(f"  Log in:    {email} / {PASSWORD}")
    print(f"  Console:   http://127.0.0.1:8000/c/{slug}/console\n")


if __name__ == "__main__":
    main()
