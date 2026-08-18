# Vyuha

Send us the Excel file you already use. Get back a dashboard.

`vyuha` reads an unmodified distributor or manufacturer spreadsheet — junk rows,
merged cells, ₹ symbols, "Grand Total" lines and all — works out what every sheet
and column means on its own, and writes a single self-contained HTML dashboard
covering sales, stock and receivables, plus a short list of what needs attention.

No template. No column mapping. No upload. Nothing for the client to change.

## Try it in 30 seconds

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -e .        # macOS/Linux: .venv/bin/python
.venv/Scripts/python -m vyuha demo --open
```

`demo` writes a deliberately messy sample workbook to `out/sample-distributor.xlsx`,
analyses it, and opens `out/sample-dashboard.html`. That sample file is the demo to
open a prospect conversation with when they have not sent their data yet.

## On a real file

```bash
python -m vyuha run "Sales Register FY26.xlsx" --client "Sharma Traders" --open
python -m vyuha check "Sales Register FY26.xlsx"   # what did it understand? no report
```

| Flag | Does |
| --- | --- |
| `-o, --output` | where to write the .html (default `out/<name>-dashboard.html`) |
| `--client` | name shown on the dashboard |
| `--as-of` | treat this date as today, `YYYY-MM-DD` (ageing, days of cover) |
| `--open` | open the dashboard when it is done |

Run `check` first on any new client file. It prints which sheet was read as what,
which row the header was found on, which columns were understood and which were
ignored — the fastest way to spot a misreading before showing anyone the numbers.

## What it works out

**Sales** — revenue, orders, average order value, month-by-month trend, top
customers, top products, top categories, and a warning when too much of the
revenue sits with too few customers.

**Stock** — stock value, everything at or below its reorder level, days of cover
per SKU at the current run rate, and dead stock: items sitting in the stock sheet
that have not sold in 90+ days, with the cash locked in them. That last one comes
from joining the stock sheet against the sales sheet, which is the join nobody
does by hand.

**Receivables** — total outstanding, ageing buckets (not due / 0–30 / 31–60 /
61–90 / 90+), overdue total, biggest debtors and who to chase first.

Everything urgent is also collected as a structured alert — severity, headline,
one line of detail. Those objects are what Phase 2 will push over WhatsApp.

## The mess it handles

Company name, address and a report title above the header · a blank row between
the title and the header · merged cells · blank spacer rows in the middle of the
data · "Grand Total" and "Sub Total" rows · `₹ 1,23,456.00` · `(4,500)` for
negatives · `5,000 Cr` for credits · dates stored as `dd-mm-yyyy` text · the same
customer as "M/s Sharma Traders", "Sharma traders", "SHARMA TRADERS" and
"M/s. Sharma Traders Pvt Ltd" · no amount column, only qty and rate · a sheet of
handwritten notes that is not data at all · duplicate pasted rows.

Every fix applied is listed at the bottom of the dashboard, so the owner can see
what was done to their numbers rather than having to trust them blind.

## How it fits together

| Module | Job |
| --- | --- |
| `vyuha/ingest.py` | open .xlsx/.xls/.csv, spread merged cells, trim blanks → raw grids |
| `vyuha/schema.py` | the canonical field vocabulary and its real-world aliases |
| `vyuha/detect.py` | find the header row, map columns to fields, classify the sheet |
| `vyuha/clean.py` | coerce types, drop total rows, normalise customer names |
| `vyuha/analyze.py` | sales / stock / receivables intelligence and alerts |
| `vyuha/report.py` | render one self-contained HTML file |
| `vyuha/pipeline.py` | `run()` — the five stages, end to end |
| `vyuha/sample.py` | generate the messy demo workbook |

The report has no `<script>`, no CDN link and no remote image. It opens on a phone
with no internet, and it survives being forwarded on WhatsApp.

To teach it a column it did not recognise, add the alias to the right `FieldSpec`
in `vyuha/schema.py` — that is usually the whole fix.

## Tests

```bash
.venv/Scripts/python -m tests.test_pipeline     # no pytest needed
.venv/Scripts/python -m pytest -q               # if you have pytest
```

## Status

v0.1.0. Works end to end on the generated sample. **Not yet validated against a
real client file** — that is the next gate before using it in a prospect demo.
See [requirements/01-features/01-excel-to-dashboard.md](requirements/01-features/01-excel-to-dashboard.md).
