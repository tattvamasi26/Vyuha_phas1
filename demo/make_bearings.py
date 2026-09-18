"""The bearings client's own files — the pile they would actually send.

    .venv/Scripts/python demo/make_bearings.py

The seeded workspace (``python -m vyuha_platform seed-bearings``) shows Vyuha with a year
of history already in it. These files show the other half of the story: what onboarding
starts from when a distributor says "everything is in Excel".

Four files, each carrying a different piece of the mess a real one has — a merged title and
three junk rows above the header, dates as text in one sheet and real dates in another, a
Grand Total row in the middle, four spellings of one customer, ₹ symbols and comma
grouping, and an outstanding list keyed by invoice number.

Generated, never hand-made: binaries in a repo go stale and nobody remembers what is inside
them. Dates are relative to today, so the "recent" file is always recent.
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
OUT = HERE / "samples" / "bearings"
SEED = 20260916

BUSINESS = "SHAKTI BEARINGS & POWER TRANSMISSION"
GSTIN = "29SHAKT4321B1Z9"

#: (code, name, unit, sells at, costs, on the shelf, reorder level)
ITEMS = [
    ("BRG-6204", "6204 ZZ Ball Bearing", "piece", 190, 132, 180, 60),
    ("BRG-6205", "6205 2RS Ball Bearing", "piece", 240, 168, 145, 60),
    ("BRG-6206", "6206 ZZ Ball Bearing", "piece", 310, 222, 96, 40),
    ("BRG-6305", "6305 2RS Ball Bearing", "piece", 420, 300, 62, 30),
    ("BRG-6308", "6308 ZZ Ball Bearing", "piece", 780, 560, 28, 15),
    ("BRG-30205", "30205 Taper Roller Bearing", "piece", 520, 372, 40, 20),
    ("BRG-32210", "32210 Taper Roller Bearing", "piece", 980, 700, 12, 15),
    ("BRG-22210", "22210 Spherical Bearing", "piece", 2450, 1790, 6, 8),
    ("HSG-UCP205", "UCP 205 Pillow Block", "piece", 690, 480, 34, 15),
    ("HSG-UCF206", "UCF 206 Flange Unit", "piece", 820, 590, 18, 10),
    ("HSG-SN510", "SN 510 Plummer Block", "piece", 3250, 2400, 4, 6),
    ("BLT-B56", "V-Belt B-56", "piece", 410, 290, 85, 40),
    ("BLT-C90", "V-Belt C-90", "piece", 980, 700, 22, 20),
    ("CHN-08B1", "Chain 08B-1 10ft", "piece", 1180, 860, 26, 12),
    ("SPR-08B18", "Sprocket 08B-1 Z18", "piece", 640, 450, 31, 12),
    ("CPL-L095", "Flexible Coupling L-095", "piece", 1350, 980, 14, 8),
    ("SEL-3552", "Oil Seal 35x52x7", "piece", 95, 58, 240, 80),
    ("SEL-5072", "Oil Seal 50x72x10", "piece", 145, 92, 130, 60),
    ("CON-GRS500", "Bearing Grease 500g", "piece", 280, 195, 0, 24),
    ("CON-CLP52", "Circlip 52mm 10pc", "packet", 130, 82, 60, 25),
    ("BRG-LM25UU", "Linear Bearing LM25UU", "piece", 780, 560, 18, 6),
    ("TRN-BS1605", "Ball Screw 1605 500mm", "piece", 4200, 3100, 5, 2),
]

#: One customer, four spellings — the thing the engine has to collapse.
PARTIES = ["Sanjeevani Motors", "M/s Sanjeevani Motors", "SANJEEVANI MOTORS",
           "Sanjeevani Motors.", "Hubballi Foundry Works", "Nandi Sugars Ltd",
           "Vishwa Engineering Works", "Raj Auto Spares", "Sri Datta Pump Works", "Cash"]


def ago(days: int) -> date:
    return date.today() - timedelta(days=days)


def _autosize(ws) -> None:
    for col in range(1, ws.max_column + 1):
        width = max((len(str(ws.cell(r, col).value or ""))
                     for r in range(1, min(ws.max_row, 40) + 1)), default=8)
        ws.column_dimensions[get_column_letter(col)].width = min(max(width + 4, 11), 32)


def _title(ws, subtitle: str, span: str) -> None:
    """The header block every Indian trader's register carries above the actual table."""
    ws["A1"] = BUSINESS
    ws.merge_cells(f"A1:{span}1")
    ws["A1"].font = Font(bold=True, size=14)
    ws["A1"].alignment = Alignment(horizontal="center")
    ws["A2"] = f"GSTIN: {GSTIN}   |   Gokul Road, Hubballi   |   Ph: 0836-2345678"
    ws.merge_cells(f"A2:{span}2")
    ws["A3"] = subtitle
    ws.merge_cells(f"A3:{span}3")
    ws.append([])                                   # row 4 blank; the header lands on 5


def sales_register(rng: random.Random) -> tuple[str, str]:
    """A year of bills, as the accountant keeps them: messy, and dated as text."""
    path = OUT / "01-sales-register.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "Sales Register"
    _title(ws, "Sales Register — last 12 months", "H")
    ws.append(["Date", "Bill No", "Party Name", "Item", "Qty", "Rate", "Amount", "Remarks"])

    total = 0.0
    for i in range(260):
        code, name, _unit, rate, _cost, _stock, _reorder = rng.choice(ITEMS)
        qty = rng.choice([2, 4, 5, 6, 10, 12, 20, 25, 40, 50])
        when = ago(rng.randint(2, 360))
        amount = qty * rate
        total += amount
        ws.append([
            when.strftime("%d-%m-%Y"),              # dates as text, day first
            f"SB/{2600 + i}",
            rng.choice(PARTIES),
            f"{name} ({code})",
            qty,
            f"₹ {rate:,.0f}",                        # rupee symbol and comma grouping
            f"₹ {amount:,.0f}",
            rng.choice(["", "", "", "urgent", "counter sale", "against PO"]),
        ])
        if i == 150:                                 # a Grand Total in the middle
            ws.append(["", "", "GRAND TOTAL", "", "", "", f"₹ {total:,.0f}", ""])
            ws.append([])
    ws.append(["", "", "GRAND TOTAL", "", "", "", f"₹ {total:,.0f}", ""])
    _autosize(ws)
    wb.save(path)
    return path.name, "A year of bills: junk rows, a merged title, text dates, ₹ symbols, two Grand Totals, one customer spelled four ways."


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
    return path.name, "The shelf as it stands, with reorder levels — a snapshot, so the newest file wins rather than adding up."


def outstanding(rng: random.Random) -> tuple[str, str]:
    """Who owes, keyed by invoice number, with a couple of long-overdue lines."""
    path = OUT / "03-outstanding.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "Outstanding"
    _title(ws, "Party-wise outstanding", "F")
    ws.append(["Invoice No", "Party", "Invoice Date", "Due Date", "Amount", "Days"])

    rows = [("SB/2711", "Nandi Sugars Ltd", 104, 74, 58800),
            ("SB/2744", "Hubballi Foundry Works", 66, 36, 39000),
            ("SB/2769", "Sanjeevani Motors", 41, 11, 14400),
            ("SB/2781", "Raj Auto Spares", 24, -6, 21300),
            ("SB/2788", "Vishwa Engineering Works", 12, -18, 46500)]
    for number, party, age, due_age, amount in rows:
        ws.append([number, party, ago(age), ago(due_age), amount,      # real date cells
                   max((date.today() - ago(due_age)).days, 0)])
    _autosize(ws)
    wb.save(path)
    return path.name, "Money not yet collected, keyed by invoice number and dated with real date cells — the other half of the same period."


def purchases(rng: random.Random) -> tuple[str, str]:
    """What was bought in, as a plain CSV — the file the supplier's portal exports."""
    path = OUT / "04-purchases.csv"
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["Date", "Supplier", "Bill No", "Item", "Qty", "Rate", "Amount"])
        for i in range(48):
            code, name, _unit, _rate, cost, _stock, _reorder = rng.choice(ITEMS)
            qty = rng.choice([25, 50, 100, 150, 200])
            when = ago(rng.randint(5, 350))
            w.writerow([when.strftime("%Y-%m-%d"),
                        rng.choice(["Bharat Bearing Agencies", "Deccan Seals & Spares",
                                    "Shree Transmission Supplies"]),
                        f"P-{1200 + i}", f"{name} ({code})", qty, cost, qty * cost])
    return path.name, "A year of purchases as a clean CSV — the control, and what the cost side of the margin comes from."


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rng = random.Random(SEED)
    built = [sales_register(rng), stock_statement(), outstanding(rng), purchases(rng)]

    lines = ["# The bearings client's files", "",
             "Generated by `demo/make_bearings.py`. What a distributor sends when they say",
             "everything is in Excel. Send them together — Vyuha reads them as one picture.",
             ""]
    for name, what in built:
        lines.append(f"- **{name}** — {what}")
    (OUT / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"\n  Wrote {len(built)} files to {OUT}\n")
    for name, what in built:
        print(f"  {name:<26} {what[:72]}")
    print()


if __name__ == "__main__":
    main()
