"""End-to-end and unit checks.

Run with: .venv/Scripts/python.exe -m pytest -q
(or `python -m tests.test_pipeline` for a dependency-free run)
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from vyuha import clean, detect, ingest, pipeline, report, sample, schema, trust
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



# --- how sure the engine is, and whether it says so -----------------------


def _messy_sales(path: Path) -> Path:
    """A sheet a real client sends: no Amount column, one heading missing."""
    pd.DataFrame(
        {
            "Bill Dt": ["01-04-2026", "02-04-2026", "03-04-2026", "05-04-2026"],
            "Party Name": ["Ramesh Traders", "M/s Ramesh Traders",
                           "Kumar & Co", "Kumar and Co"],
            "Unnamed: 2": ["Cement 50kg", "Cement 50kg",
                           "TMT Bar 12mm", "TMT Bar 12mm"],
            "Qty (Nos)": [10, 5, 8, 3],
            "Rate": [380, 380, 720, 720],
        }
    ).to_excel(path, sheet_name="Sales", index=False)
    return path


def test_mapping_confidence_survives_detection_and_cleaning():
    """These were computed and thrown away, which is why every figure used to
    print at the same weight whatever it rested on."""
    frame = pd.DataFrame(
        {"Invoice Date": ["01-04-2026"], "Qty (Nos)": [5], "Rate": [100]}
    )
    mapping, _unmapped = detect.map_columns(frame)
    scores = detect.score_mapping(frame, mapping)

    assert scores[schema.DATE] == 10.0, "an exact alias is certain"
    assert 5.0 <= scores[schema.QTY] < 10.0, "a fragment match is not"


def test_a_derived_column_is_reported_as_calculated(tmp_path: Path):
    workbook = _messy_sales(tmp_path / "messy.xlsx")
    table = pipeline.run(workbook, as_of=AS_OF).insights.tables[0]

    assert schema.AMOUNT in table.derived, "Amount was manufactured from qty x rate"
    basis = trust.basis([table], "Revenue", schema.AMOUNT)
    assert basis.worst == trust.DERIVED
    assert "calculated" in basis.note


def test_a_headerless_column_is_reported_as_guessed(tmp_path: Path):
    workbook = _messy_sales(tmp_path / "messy.xlsx")
    table = pipeline.run(workbook, as_of=AS_OF).insights.tables[0]

    # "Unnamed: 2" says nothing; the column was identified by its values.
    assert trust.verdict(table.field_confidence.get(schema.ITEM, 0.0)) == trust.GUESSED
    assert any("no usable heading" in c for c in trust.concerns([table]))


def test_a_recognisable_heading_does_not_raise_an_alarm(tmp_path: Path):
    """A caption that appears on every report is one nobody reads.

    "Qty (Nos)" is a heading a human reads without hesitating, so it stays
    visible in the read-back and never triggers the caution panel.
    """
    workbook = sample.build(tmp_path / "demo.xlsx", as_of=AS_OF)
    insights = pipeline.run(workbook, as_of=AS_OF).insights
    sales = next(t for t in insights.tables if t.kind == schema.SALES)

    assert trust.verdict(sales.field_confidence[schema.QTY]) == trust.MATCHED
    assert not [c for c in trust.concerns([sales]) if "matched" in c]


def test_the_report_marks_a_guessed_figure_and_not_a_clean_one(tmp_path: Path):
    """The whole point: a number Vyuha worked out must not look identical to
    one read off a labelled column."""
    messy = pipeline.run(_messy_sales(tmp_path / "messy.xlsx"), as_of=AS_OF)
    html = report.render(messy.insights, client="Messy Traders")
    assert "How to read these numbers" in html
    assert "calculated" in html
    assert "Amount was not in the file" in html

    clean_run = pipeline.run(sample.build(tmp_path / "demo.xlsx", as_of=AS_OF),
                             as_of=AS_OF)
    clean_html = report.render(clean_run.insights, client="Clean Traders")
    assert 'class="chip' not in clean_html, "nothing here was guessed"


def test_the_report_leads_with_a_verdict_before_any_number(tmp_path: Path):
    """Somebody who reads nothing else should still know whether it needed
    them."""
    workbook = sample.build(tmp_path / "demo.xlsx", as_of=AS_OF)
    html = report.render(pipeline.run(workbook, as_of=AS_OF).insights)

    verdict_at = html.index('class="verdict"')
    assert verdict_at < html.index('class="figures"'), "the verdict comes first"
    assert "need a decision" in html or "needs a decision" in html

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
