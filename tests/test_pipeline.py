"""End-to-end and unit checks.

Run with: .venv/Scripts/python.exe -m pytest -q
(or `python -m tests.test_pipeline` for a dependency-free run)
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from vyuha import clean, detect, ingest, pipeline, report, sample, schema
from vyuha.analyze import CRITICAL

AS_OF = datetime(2026, 8, 11)


# --- value parsing --------------------------------------------------------


def test_to_number_handles_spreadsheet_dialects():
    assert clean.to_number("₹ 1,23,456.00") == 123456.0
    assert clean.to_number("(4,500)") == -4500.0
    assert clean.to_number("5,000 Cr") == -5000.0
    assert clean.to_number("5,000 Dr") == 5000.0
    assert clean.to_number("12%") == 12.0
    assert clean.to_number("  ") is None
    assert clean.to_number("-") is None
    assert clean.to_number("abc") is None
    assert clean.to_number(1500) == 1500.0
    assert clean.to_number(None) is None


def test_party_key_collapses_spellings():
    keys = {
        clean.party_key("M/s Sharma Traders"),
        clean.party_key("Sharma traders"),
        clean.party_key("SHARMA TRADERS  "),
        clean.party_key("M/s. Sharma Traders Pvt Ltd"),
    }
    assert len(keys) == 1
    assert clean.party_key("Patel Pumps & Motors") == clean.party_key(
        "patel pumps and motors"
    )
    assert clean.party_key("Sharma Traders") != clean.party_key("Gupta Engineering")


# --- header + column detection -------------------------------------------


def test_finds_header_below_junk_rows():
    grid = pd.DataFrame(
        [
            ["Shree Balaji Distributors", None, None, None],
            ["SALES REGISTER", None, None, None],
            ["Bill Date", "Party Name", "Qty (Nos)", "Amount"],
            [datetime(2026, 1, 4), "Sharma Traders", 5, 1200],
            [datetime(2026, 1, 5), "Anand Hardware", 2, 900],
        ]
    )
    row, confidence = detect.find_header_row(grid)
    assert row == 2
    assert confidence > 0


def test_maps_messy_headers_to_canonical_fields():
    frame = pd.DataFrame(
        columns=["Bill Date", "Invoice No.", "Party Name", "Item Code",
                 "Item Description", "Qty (Nos)", "Rate", "Amount", "Remarks"]
    )
    mapping, unmapped = detect.map_columns(frame)
    assert mapping[schema.DATE] == "Bill Date"
    assert mapping[schema.PARTY] == "Party Name"
    assert mapping[schema.SKU] == "Item Code"
    assert mapping[schema.ITEM] == "Item Description"
    assert mapping[schema.QTY] == "Qty (Nos)"
    assert mapping[schema.AMOUNT] == "Amount"
    assert "Remarks" in unmapped


def test_stock_columns_do_not_steal_sales_fields():
    frame = pd.DataFrame(columns=["Item Code", "Closing Stock", "Reorder Level",
                                  "Purchase Rate", "Stock Value"])
    mapping, _ = detect.map_columns(frame)
    assert mapping[schema.STOCK_QTY] == "Closing Stock"
    assert mapping[schema.REORDER_LEVEL] == "Reorder Level"
    assert schema.QTY not in mapping  # "Closing Stock" is not a sales quantity


def test_classify_prefers_receivables_over_sales():
    kind, _ = detect.classify({schema.OUTSTANDING, schema.PARTY, schema.DUE_DATE,
                               schema.AMOUNT})
    assert kind == schema.RECEIVABLES
    kind, _ = detect.classify({schema.AMOUNT, schema.DATE, schema.PARTY, schema.QTY})
    assert kind == schema.SALES
    kind, _ = detect.classify({schema.STOCK_QTY, schema.SKU, schema.REORDER_LEVEL})
    assert kind == schema.STOCK
    kind, _ = detect.classify({schema.LOCATION})
    assert kind == schema.UNKNOWN


# --- cleaning -------------------------------------------------------------


def test_total_rows_are_excluded_from_revenue(tmp_path: Path):
    csv = tmp_path / "sales.csv"
    csv.write_text(
        "Bill Date,Party Name,Qty,Amount\n"
        "01-04-2026,Sharma Traders,2,1000\n"
        "02-04-2026,Anand Hardware,3,1500\n"
        ",Grand Total,5,2500\n",
        encoding="utf-8",
    )
    result = pipeline.run(csv, as_of=AS_OF)
    assert result.insights.sales["revenue"] == 2500.0  # not 5000
    assert result.tables[0].rows_out == 2


def test_amount_derived_from_qty_times_rate(tmp_path: Path):
    csv = tmp_path / "sales.csv"
    csv.write_text(
        "Date,Party,Item,Qty,Rate\n"
        "01-04-2026,Sharma Traders,Bearing 6205,4,150\n"
        "02-04-2026,Anand Hardware,V-Belt A45,2,300\n",
        encoding="utf-8",
    )
    result = pipeline.run(csv, as_of=AS_OF)
    assert result.insights.sales["revenue"] == 1200.0
    assert any("Qty × Rate" in issue for issue in result.tables[0].issues)


# --- full run on the messy sample ----------------------------------------


def test_sample_workbook_runs_end_to_end(tmp_path: Path):
    workbook = sample.build(tmp_path / "demo.xlsx", as_of=AS_OF)
    result = pipeline.run(workbook, as_of=AS_OF)

    kinds = {t.kind for t in result.tables}
    assert kinds == {schema.SALES, schema.STOCK, schema.RECEIVABLES}

    sales = next(t for t in result.tables if t.kind == schema.SALES)
    # Header sits on row 5 of the file, under three junk rows and a blank one.
    assert sales.header_row == 5
    assert sales.has(schema.DATE, schema.PARTY, schema.SKU, schema.QTY, schema.AMOUNT)
    assert any("total" in issue.lower() for issue in sales.issues)

    # The Notes sheet is prose; it must not be mistaken for data.
    assert any(name == "Notes" for name, _ in result.skipped)

    insights = result.insights
    assert insights.sales["revenue"] > 0
    assert insights.receivables["total"] > 0
    assert insights.stock["skus"] == len(sample.PRODUCTS)

    # The three planted dead SKUs are found, and no others.
    dead_labels = {row["label"] for row in insights.stock["dead_stock"]}
    expected = {name for sku, name, _c, _r in sample.PRODUCTS if sku in sample.DEAD_SKUS}
    assert expected <= dead_labels

    # The planted fast mover is flagged as about to run out.
    cover = {row["label"]: row["days_cover"] for row in insights.stock["cover"]}
    fast_name = next(n for s, n, _c, _r in sample.PRODUCTS if s == sample.FAST_MOVER)
    assert cover[fast_name] <= 14

    assert any(a.severity == CRITICAL for a in insights.alerts)


def test_partial_month_does_not_trigger_a_revenue_alert(tmp_path: Path):
    workbook = sample.build(tmp_path / "demo.xlsx", as_of=AS_OF)
    insights = pipeline.run(workbook, as_of=AS_OF).insights
    assert insights.sales["monthly"][-1]["partial"] is True
    assert not any("Revenue fell" in a.title for a in insights.alerts)


def test_report_is_self_contained(tmp_path: Path):
    workbook = sample.build(tmp_path / "demo.xlsx", as_of=AS_OF)
    result = pipeline.run(workbook, as_of=AS_OF)
    path = pipeline.write_report(result, tmp_path / "dash.html", client="Test Client")
    html = path.read_text(encoding="utf-8")

    assert "Test Client" in html
    for forbidden in ("http://", "https://", "<script", "src="):
        assert forbidden not in html, f"report should not contain {forbidden!r}"
    assert html.startswith("<!DOCTYPE html>")


def test_unreadable_input_fails_cleanly(tmp_path: Path):
    missing = tmp_path / "nope.xlsx"
    try:
        pipeline.run(missing)
    except ingest.IngestError as exc:
        assert "not found" in str(exc).lower()
    else:  # pragma: no cover
        raise AssertionError("expected IngestError")


def test_money_uses_indian_digit_grouping():
    assert report.money(1234567) == "&#8377;12,34,567"
    assert report.money(999) == "&#8377;999"
    assert report.money(-4500) == "-&#8377;4,500"
    assert report.money_short(12500000) == "&#8377;1.25 Cr"
    assert report.money_short(250000) == "&#8377;2.50 L"


# --- dependency-free runner ----------------------------------------------

if __name__ == "__main__":
    import tempfile
    import traceback

    passed, failed = 0, 0
    for name, func in sorted(globals().items()):
        if not name.startswith("test_") or not callable(func):
            continue
        try:
            if "tmp_path" in func.__code__.co_varnames[: func.__code__.co_argcount]:
                with tempfile.TemporaryDirectory() as tmp:
                    func(Path(tmp))
            else:
                func()
        except Exception:
            failed += 1
            print(f"FAIL {name}")
            traceback.print_exc()
        else:
            passed += 1
            print(f"ok   {name}")
    print(f"\n{passed} passed, {failed} failed")
    raise SystemExit(1 if failed else 0)
