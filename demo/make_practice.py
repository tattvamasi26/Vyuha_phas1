"""The practice client's files — a business to onboard from scratch, start to finish.

    .venv/Scripts/python demo/make_practice.py

The two seeded demos (``seed`` and ``seed-bearings``) show Vyuha with a year of history
already in it. This pack is the opposite: nothing exists yet, and the job is to onboard
**Deshpande Electricals & Motors, Dharwad** from an empty workspace using nothing but the
pile of files they sent.

A different trade from either demo on purpose — the slug never collides with a seeded
workspace, and the starter catalogue you tick in stage 3 is one you have not seen before.

Seven files, and two of them are traps that exist to be walked into on purpose:

* ``04-purchases.csv`` is classified **Sales** by the engine — there is no purchases table
  kind yet. Upload it with the sales register and revenue roughly doubles.
* ``05-cost-list.csv`` is the one thing no importer reads. ``library.materialise`` sets
  stock, reorder level and selling rate, never cost — so margin stays zero until somebody
  types these in.

Generated, never hand-made: binaries in a repo go stale and nobody remembers what is
inside them. Dates are relative to today, so the "recent" file is always recent.
"""

from __future__ import annotations

import csv
import random
from datetime import date, timedelta
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter

HERE = Path(__file__).resolve().parent
OUT = HERE / "samples" / "practice"
SEED = 20260921

BUSINESS = "DESHPANDE ELECTRICALS & MOTORS"
GSTIN = "29DESHP7788K1Z4"
PLACE = "Station Road, Dharwad"

#: (code, name, unit, sells at, costs, on the shelf, reorder level)
ITEMS = [
    ("MOT-1HP", "1 HP Single Phase Motor", "piece", 4850, 3650, 14, 6),
    ("MOT-2HP", "2 HP Three Phase Motor", "piece", 8200, 6300, 9, 4),
    ("MOT-5HP", "5 HP Three Phase Motor", "piece", 17500, 13800, 4, 3),
    ("PMP-05HP", "0.5 HP Monoblock Pump", "piece", 3950, 2980, 22, 10),
    ("PMP-SUB1", "1 HP Submersible Pump", "piece", 9600, 7450, 7, 4),
    ("STR-DOL3", "DOL Starter 3 HP", "piece", 1850, 1320, 30, 12),
    ("STR-SD10", "Star Delta Starter 10 HP", "piece", 6400, 4900, 5, 3),
    ("CAP-36UF", "Capacitor 36 MFD", "piece", 210, 132, 180, 60),
    ("CAP-60UF", "Capacitor 60 MFD", "piece", 340, 225, 95, 40),
    ("CBL-25SQ", "2.5 sq mm Wire 90m Coil", "coil", 1980, 1560, 48, 20),
    ("CBL-40SQ", "4 sq mm Wire 90m Coil", "coil", 3150, 2480, 26, 12),
    ("CBL-ARM4", "4 Core Armoured Cable 10m", "piece", 4200, 3300, 11, 5),
    ("SWG-MCB32", "32A MCB Single Pole", "piece", 260, 168, 220, 80),
    ("SWG-RCCB63", "63A RCCB Four Pole", "piece", 2850, 2100, 14, 6),
    ("SWG-DB8", "8 Way Distribution Board", "piece", 1650, 1180, 18, 8),
    ("PNL-CTRL", "Motor Control Panel 5 HP", "piece", 14500, 11200, 3, 2),
    ("LMP-LED9", "9W LED Bulb", "piece", 95, 54, 400, 150),
    ("LMP-LED20", "20W LED Batten", "piece", 340, 205, 160, 60),
    ("FAN-CEL", "Ceiling Fan 1200mm", "piece", 1750, 1290, 36, 15),
    ("FAN-EXH", "Exhaust Fan 250mm", "piece", 1250, 890, 21, 10),
    ("ACC-GLND", "Cable Gland Set 20mm", "packet", 180, 105, 0, 24),
    ("ACC-LUG", "Copper Lug 25mm 10pc", "packet", 240, 150, 55, 20),
    ("TOL-MULT", "Digital Multimeter", "piece", 1450, 980, 6, 4),
    ("WTR-HTR", "15L Water Heater", "piece", 6800, 5200, 2, 3),
]

#: Planted so each finding on Home has evidence behind it.
NEVER_SOLD = {"ACC-LUG", "TOL-MULT", "WTR-HTR"}     # dead stock
OUT_OF_STOCK = "ACC-GLND"                            # shelf at zero
SELLABLE = [i for i in ITEMS if i[0] not in NEVER_SOLD]

#: One customer, four spellings — the thing the engine has to collapse.
PARTIES = ["Shakti Borewells", "M/s Shakti Borewells", "SHAKTI BOREWELLS",
           "Shakti Borewells.", "Gadag Cotton Mills", "Navalgund Farm Services",
           "Sri Basaveshwara Electricals", "Kittur Agro Pumps", "Cash"]

SUPPLIERS = ["Crompton Distributors", "Havells Regional Depot", "Finolex Cables Agency"]


def ago(days: int) -> date:
    return date.today() - timedelta(days=days)


def _autosize(ws) -> None:
    for col in range(1, ws.max_column + 1):
        width = max((len(str(ws.cell(r, col).value or ""))
                     for r in range(1, min(ws.max_row, 40) + 1)), default=8)
        ws.column_dimensions[get_column_letter(col)].width = min(max(width + 4, 11), 32)


def _title(ws, subtitle: str, span: str) -> None:
    """The header block every Indian trader's register carries above the table."""
    ws["A1"] = BUSINESS
    ws.merge_cells(f"A1:{span}1")
    ws["A1"].font = Font(bold=True, size=14)
    ws["A1"].alignment = Alignment(horizontal="center")
    ws["A2"] = f"GSTIN: {GSTIN}   |   {PLACE}   |   Ph: 0836-2778899"
    ws.merge_cells(f"A2:{span}2")
    ws["A3"] = subtitle
    ws.merge_cells(f"A3:{span}3")
    ws.append([])                                   # row 4 blank; header lands on 5


def sales_register(rng: random.Random) -> tuple[str, str]:
    """A year of bills, as the accountant keeps them: messy, and dated as text."""
    path = OUT / "01-sales-register.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "Sales Register"
    _title(ws, "Sales Register — last 12 months", "H")
    ws.append(["Date", "Bill No", "Party Name", "Item", "Qty", "Rate", "Amount", "Remarks"])

    total = 0.0
    for i in range(215):
        code, name, _unit, rate, _cost, _stock, _reorder = rng.choice(SELLABLE)
        qty = rng.choice([1, 2, 2, 3, 4, 5, 6, 10, 12, 20, 25])
        when = ago(rng.randint(2, 358))
        amount = qty * rate
        total += amount
        ws.append([
            when.strftime("%d-%m-%Y"),              # dates as text, day first
            f"DE/{4100 + i}",
            rng.choice(PARTIES),
            f"{name} ({code})",
            qty,
            f"₹ {rate:,.0f}",                        # rupee symbol and comma grouping
            f"₹ {amount:,.0f}",
            rng.choice(["", "", "", "urgent", "counter sale", "against PO", "site delivery"]),
        ])
        if i == 128:                                 # a Grand Total in the middle
            ws.append(["", "", "GRAND TOTAL", "", "", "", f"₹ {total:,.0f}", ""])
            ws.append([])                            # and a blank spacer after it
    ws.append(["", "", "GRAND TOTAL", "", "", "", f"₹ {total:,.0f}", ""])
    _autosize(ws)
    wb.save(path)
    return path.name, ("A year of bills: a merged title, three junk rows above the header, "
                       "dates as text, ₹ symbols, two Grand Totals, one customer spelled "
                       "four ways.")


def stock_statement() -> tuple[str, str]:
    """What is on the shelf today — a snapshot, which must not be stacked."""
    path = OUT / "02-stock-statement.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "Stock Statement"
    _title(ws, f"Stock as on {date.today().strftime('%d-%m-%Y')}", "G")
    ws.append(["Item Code", "Description", "Unit", "Closing Stock", "Reorder Level",
               "Rate", "Value"])
    for code, name, unit, rate, cost, stock, reorder in ITEMS:
        ws.append([code, name, unit, stock, reorder, rate, stock * cost])
    _autosize(ws)
    wb.save(path)
    return path.name, ("The shelf as it stands, with reorder levels and the selling rate — "
                       "a snapshot, so the newest one wins rather than adding up. This is "
                       "also the item master: upload it and you need not type items at all.")


def outstanding() -> tuple[str, str]:
    """Who owes, keyed by invoice number, with real date cells and planted ageing."""
    path = OUT / "03-outstanding.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "Outstanding"
    _title(ws, "Party-wise outstanding", "F")
    # "Outstanding Amount", not "Amount": TABLE_RULES requires the OUTSTANDING
    # field for a receivables table, and a plain "Amount" heading resolves to
    # AMOUNT — which reads the whole dues list as five more sales.
    ws.append(["Invoice No", "Party", "Invoice Date", "Due Date",
               "Outstanding Amount", "Days"])

    rows = [("DE/4188", "Gadag Cotton Mills", 118, 88, 84600),
            ("DE/4203", "Shakti Borewells", 71, 41, 47250),
            ("DE/4241", "Kittur Agro Pumps", 44, 14, 19800),
            ("DE/4266", "Sri Basaveshwara Electricals", 26, -4, 31450),
            ("DE/4288", "Navalgund Farm Services", 13, -17, 12900)]
    for number, party, age, due_age, amount in rows:
        ws.append([number, party, ago(age), ago(due_age), amount,      # real date cells
                   max((date.today() - ago(due_age)).days, 0)])
    _autosize(ws)
    wb.save(path)
    return path.name, ("Money not yet collected, keyed by invoice number and dated with "
                       "real date cells. Two are well past due, one is not due yet.")


def purchases(rng: random.Random) -> tuple[str, str]:
    """The trap. There is no purchases table kind, so this reads as a year of SALES."""
    path = OUT / "04-purchases.csv"
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["Date", "Supplier", "Bill No", "Item", "Qty", "Rate", "Amount"])
        for i in range(42):
            code, name, _unit, _rate, cost, _stock, _reorder = rng.choice(ITEMS)
            qty = rng.choice([10, 20, 25, 40, 50, 100])
            when = ago(rng.randint(5, 350))
            w.writerow([when.strftime("%Y-%m-%d"), rng.choice(SUPPLIERS),
                        f"PB-{2300 + i}", f"{name} ({code})", qty, cost, qty * cost])
    return path.name, ("A year of purchases. **Do not upload this with the others.** "
                       "`schema.TABLE_RULES` knows only sales, stock and receivables, so a "
                       "file with Date / Party / Amount is read as SALES and revenue "
                       "roughly doubles. Open it to read costs off; import it never.")


def cost_list() -> tuple[str, str]:
    """The numbers no importer reads. Typed in by hand, or margin stays zero."""
    path = OUT / "05-cost-list.csv"
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["Item Code", "Description", "Sells at", "Our Cost"])
        for code, name, _unit, rate, cost, _stock, _reorder in ITEMS:
            w.writerow([code, name, rate, cost])
    return path.name, ("What each item costs them. `library.materialise` sets stock, "
                       "reorder level and selling rate — never cost — so until these are "
                       "typed into Operations › Record › item form, gross margin reads "
                       "zero and stock is valued at the selling price.")


def whatsapp() -> tuple[str, str]:
    """An exported thread — for many distributors this IS the order book."""
    path = OUT / "06-whatsapp-orders.txt"
    d1, d2, d3 = ago(4), ago(3), ago(1)

    def stamp(when: date, time: str) -> str:
        return f"{when.strftime('%d/%m/%Y')}, {time}"

    lines = [
        f"{stamp(d1, '9:12 am')} - Messages are end-to-end encrypted.",
        f"{stamp(d1, '9:14 am')} - Shakti Borewells: Namaskara sir, 2 nos 1 HP Single Phase Motor beku",
        f"{stamp(d1, '9:15 am')} - Shakti Borewells: site ge urgent",
        f"{stamp(d1, '9:31 am')} - Deshpande Electricals: ok madtini, evening dispatch",
        f"{stamp(d1, '11:02 am')} - Kittur Agro Pumps: 10 capacitor 36 MFD and 4 DOL Starter 3 HP kalisi",
        f"{stamp(d1, '11:40 am')} - Deshpande Electricals: 👍",
        f"{stamp(d2, '10:18 am')} - Gadag Cotton Mills: sir 2 coil 4 sq mm wire beku, rate enu?",
        f"{stamp(d2, '10:26 am')} - Deshpande Electricals: 3150 per coil sir",
        f"{stamp(d2, '10:29 am')} - Gadag Cotton Mills: ok send 2",
        f"{stamp(d2, '4:52 pm')} - Navalgund Farm Services: payment madidini 12900 rs, neft",
        f"{stamp(d2, '4:58 pm')} - Deshpande Electricals: received thanks",
        f"{stamp(d3, '8:41 am')} - Sri Basaveshwara Electricals: 20 nos 32A MCB Single Pole",
        f"{stamp(d3, '8:44 am')} - Sri Basaveshwara Electricals: and 1 63A RCCB Four Pole",
        f"{stamp(d3, '9:05 am')} - Deshpande Electricals: ready madtini",
        f"{stamp(d3, '6:20 pm')} - Gadag Cotton Mills: balance 84600 next week clear madtini sir",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path.name, ("An exported WhatsApp thread: five orders, one payment and one "
                       "balance mention, in Kannada-English. Everything read out of it is a "
                       "draft a person confirms — nothing here writes to the books.")


def broken() -> tuple[str, str]:
    """A PDF renamed .xlsx — the single most common real upload accident."""
    path = OUT / "07-broken.xlsx"
    path.write_bytes(b"%PDF-1.4\n% a quotation somebody renamed instead of exporting\n"
                     b"1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n%%EOF\n")
    return path.name, ("A PDF renamed .xlsx. It must fail cleanly and say what to do — "
                       "never crash, never silently produce zeros. Finish the walkthrough "
                       "on this one: a prospect who has only seen successes believes none "
                       "of them.")


def say(text: str) -> None:
    """The Windows console is cp1252 and cannot encode ₹ — transliterate on the way out.

    Same reason ``vyuha/cli.py`` has one. Without it, piping this script's output to a
    file crashes it *after* every file has already been written.
    """
    print(text.replace("₹", "Rs "))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rng = random.Random(SEED)
    built = [sales_register(rng), stock_statement(), outstanding(), purchases(rng),
             cost_list(), whatsapp(), broken()]

    lines = [
        "# Deshpande Electricals & Motors — the practice pack", "",
        "Generated by `demo/make_practice.py` — do not hand-edit, re-run it.",
        "The business to onboard **from an empty workspace**, using nothing but these files.",
        "", "Business profile to type in stage 1:", "",
        f"- Name: **Deshpande Electricals & Motors**", "- Owner: **Anand Deshpande**",
        "- WhatsApp: **9845012345**", "- Trade: **Distribution & wholesale**",
        f"- GSTIN: **{GSTIN}**, State: **Karnataka**", f"- Address: **{PLACE}, Dharwad 580001**",
        "", "## The files", "",
    ]
    for name, what in built:
        lines.append(f"- **{name}** — {what}")
    lines += ["", "## Upload order that works", "",
              "1. `02-stock-statement.xlsx` first — it creates every item, with reorder levels.",
              "2. `01-sales-register.xlsx` — a year of history against those items.",
              "3. `03-outstanding.xlsx` — who owes what.",
              "4. Then type the costs from `05-cost-list.csv` (nothing imports them).",
              "5. `06-whatsapp-orders.txt` and `07-broken.xlsx` last, to see those two paths.",
              "", "Never `04-purchases.csv`. It reads as sales and doubles the revenue.", ""]
    (OUT / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    say(f"\n  Wrote {len(built)} files to {OUT}\n")
    for name, what in built:
        say(f"  {name:<26} {what[:70]}")
    say("")


if __name__ == "__main__":
    main()
