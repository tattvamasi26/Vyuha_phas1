"""Tests for data intake — the demo corpus, and reading a WhatsApp thread.

Runs under pytest or standalone:  python -m tests.test_intake

Everything here runs with ``VYUHA_LLM=offline``. That is the point, not a
shortcut: the pattern path is what a demo laptop with no signal uses, so it is
the path most likely to be exercised in front of somebody, and it has to work.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ["VYUHA_LLM"] = "offline"

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from vyuha import ingest, pipeline                          # noqa: E402
from vyuha_platform import config, intake, sources          # noqa: E402

SAMPLES = REPO / "demo" / "samples"
SETTINGS = config.load()

CATALOGUE = ["Urea 50kg", "DAP 50kg", "Potash 50kg", "Gypsum 5kg",
             "Neem Cake 10kg", "Cattle Feed 50kg", "Paddy Seed 5kg",
             "Sprayer 16L", "HDPE Pipe 1in 10m", "Tarpaulin 12x15"]
RATES = {"Urea 50kg": 320, "DAP 50kg": 1420, "Gypsum 5kg": 140,
         "Sprayer 16L": 2250, "Paddy Seed 5kg": 640, "Neem Cake 10kg": 380,
         "Cattle Feed 50kg": 1180}


def _ensure_corpus() -> None:
    if not (SAMPLES / "08-whatsapp-orders.txt").exists():
        sys.path.insert(0, str(REPO / "demo"))
        import make_samples
        make_samples.build()


_ensure_corpus()


def _chat() -> str:
    return (SAMPLES / "08-whatsapp-orders.txt").read_text(encoding="utf-8")


def _extract():
    return intake.parse_chat(_chat(), CATALOGUE, SETTINGS)


# ===================================================== the corpus reads

def test_every_readable_sample_goes_through_the_engine():
    """Seven of the nine are tables the engine must survive unaided."""
    readable = ["01-clean-sales.csv", "02-filthy-multisheet.xlsx",
                "03-month-jun-2026.xlsx", "04-month-jul-2026.xlsx",
                "05-month-aug-2026.xlsx", "06-tally-export.txt",
                "07-price-list-merged-header.xlsx"]
    for name in readable:
        path = SAMPLES / name
        assert path.exists(), f"{name} missing — run demo/make_samples.py"
        result = pipeline.run(path)
        assert result.insights.tables, f"{name} produced no usable table"


def test_the_filthy_workbook_finds_the_header_under_the_junk():
    """Junk rows, a merged title and a blank line sit above the real header."""
    result = pipeline.run(SAMPLES / "02-filthy-multisheet.xlsx")
    sales = next(t for t in result.insights.tables if t.kind == "sales")
    assert sales.header_row == 5, sales.header_row


def test_the_grand_total_row_is_excluded():
    """Counting it would inflate every figure by roughly double."""
    result = pipeline.run(SAMPLES / "02-filthy-multisheet.xlsx")
    sales = next(t for t in result.insights.tables if t.kind == "sales")
    assert any("total" in issue.lower() for issue in sales.issues), sales.issues


def test_the_prose_sheet_is_skipped_not_guessed_at():
    result = pipeline.run(SAMPLES / "02-filthy-multisheet.xlsx")
    assert any(name == "Notes" for name, _ in result.skipped)


def test_the_month_with_no_amount_column_still_reports_revenue():
    """Its Amount column is missing entirely — it has to come from qty x rate."""
    result = pipeline.run(SAMPLES / "05-month-aug-2026.xlsx")
    assert (result.insights.sales.get("revenue") or 0) > 0


def test_all_three_monthly_files_classify_the_same_despite_drifting_columns():
    """Same report, exported by a different person each month."""
    kinds = []
    for name in ("03-month-jun-2026.xlsx", "04-month-jul-2026.xlsx",
                 "05-month-aug-2026.xlsx"):
        result = pipeline.run(SAMPLES / name)
        kinds.append({t.kind for t in result.insights.tables})
    assert kinds[0] == kinds[1] == kinds[2] == {"sales"}, kinds


def test_the_accounting_export_reads_particulars_as_a_party_not_a_product():
    """Otherwise the dashboard reports the best-selling item as "Ramu Stores"."""
    result = pipeline.run(SAMPLES / "06-tally-export.txt")
    sales = next(t for t in result.insights.tables if t.kind == "sales")
    assert "party" in sales.frame.columns, list(sales.frame.columns)
    assert "item" not in sales.frame.columns


def test_the_price_list_finds_its_header_under_the_merged_group_row():
    result = pipeline.run(SAMPLES / "07-price-list-merged-header.xlsx")
    stock = next(t for t in result.insights.tables if t.kind == "stock")
    assert stock.header_row == 3, stock.header_row
    assert "stock_qty" in stock.frame.columns


def test_a_renamed_file_says_what_it_actually_is():
    """The most common upload accident there is. The message has to be usable."""
    try:
        pipeline.run(SAMPLES / "09-broken.xlsx")
    except ingest.IngestError as exc:
        message = str(exc)
    else:
        raise AssertionError("a PDF named .xlsx must not read as a workbook")
    assert "PDF" in message, message
    assert "zip" not in message.lower(), "that is openpyxl's voice, not ours"
    assert "upload it as .pdf" in message.lower(), message


# ================================================== the WhatsApp thread

def test_a_chat_is_recognised_and_a_spreadsheet_is_not():
    assert intake.looks_like_chat(_chat())
    csv_text = (SAMPLES / "01-clean-sales.csv").read_text(encoding="utf-8")
    assert not intake.looks_like_chat(csv_text), "a CSV must never route to the chat parser"


def test_every_message_is_read_including_the_wrapped_ones():
    lines = intake.read_lines(_chat())
    assert len(lines) >= 15
    assert all(line.sender for line in lines)


def test_orders_are_pulled_out_of_the_conversation():
    extract = _extract()
    assert extract.ok, extract.error
    orders = {(d.party, d.item, d.qty) for d in extract.orders}
    assert ("Ramu Stores", "Urea 50kg", 20.0) in orders
    assert ("Ramu Stores", "Gypsum 5kg", 5.0) in orders
    assert ("Patil Nursery", "Paddy Seed 5kg", 30.0) in orders
    assert ("Hanumanth & Sons", "Cattle Feed 50kg", 40.0) in orders


def test_a_short_item_name_is_still_matched():
    """Half the fertiliser trade is DAP, MOP, NPK and SSP."""
    extract = _extract()
    assert any(d.item == "DAP 50kg" and d.qty == 10 for d in extract.orders), \
        [(d.party, d.item, d.qty) for d in extract.orders]


def test_a_short_name_does_not_match_inside_another_word():
    """"dap" inside "adaptor" must not book an order for fertiliser."""
    assert intake._match_item("2 adaptor needed", ["DAP 50kg"]) is None


def test_asking_the_rate_is_not_an_order():
    """The expensive mistake in this direction: inventing demand."""
    lines = intake.read_lines(
        "28/08/2026, 9:03 am - Ramu Stores: 20 bags urea rate enu?")
    drafts = intake.by_patterns(lines, CATALOGUE, {"You"})
    assert not drafts, drafts


def test_asking_whether_stock_exists_is_not_an_order():
    extract = _extract()
    assert not any(d.party == "Krishna Traders Pvt Ltd" and d.kind == "order"
                   for d in extract.drafts), "'potash stock ideya?' is a question"


def test_the_same_order_restated_is_counted_once():
    """The thread says "20 bags urea beku", then "ok send 20 bags urea"."""
    extract = _extract()
    urea = [d for d in extract.orders
            if d.party == "Ramu Stores" and d.item == "Urea 50kg"]
    assert len(urea) == 1, urea


def test_the_shops_own_replies_are_never_read_as_orders():
    extract = _extract()
    assert not any(d.party.lower() == "you" for d in extract.drafts)


def test_a_payment_and_an_unpaid_balance_are_told_apart():
    extract = _extract()
    payments = {(d.party, d.amount) for d in extract.payments}
    assert ("Shetty Farms", 45000.0) in payments
    balances = {(d.party, d.amount) for d in extract.drafts if d.kind == "balance"}
    assert ("Ramu Stores", 12800.0) in balances, \
        "money the customer still owes is not money received"


def test_every_draft_carries_the_message_it_came_from():
    """A number lifted from a conversation must be checkable against the thread."""
    for draft in _extract().drafts:
        assert draft.evidence, f"{draft.kind} for {draft.party} has no evidence"


def test_the_chat_reaches_the_engine_as_priced_sales():
    extract = sources.prepare(SAMPLES / "08-whatsapp-orders.txt", REPO / "out" / "t-chat",
                              SETTINGS, CATALOGUE, RATES)
    assert extract.ok, extract.error
    assert extract.kind == "whatsapp"
    result = pipeline.run(extract.path)
    assert (result.insights.sales.get("revenue") or 0) > 50000


def test_the_conversion_says_the_orders_are_drafts():
    """They came out of a conversation; the screen must not present them as facts."""
    extract = sources.prepare(SAMPLES / "08-whatsapp-orders.txt", REPO / "out" / "t-chat",
                              SETTINGS, CATALOGUE, RATES)
    assert any("draft" in note.lower() for note in extract.notes), extract.notes
    assert extract.confidence != "high"


def test_a_plain_text_table_still_takes_the_delimited_path():
    """The chat check must not swallow ordinary text exports."""
    extract = sources.prepare(SAMPLES / "06-tally-export.txt", REPO / "out" / "t-chat",
                              SETTINGS, CATALOGUE, RATES)
    assert extract.ok, extract.error
    assert extract.kind != "whatsapp", "a tab-separated export is not a chat"


def main() -> int:
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    passed = failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"ok   {name}")
            passed += 1
        except Exception as exc:                           # noqa: BLE001
            print(f"FAIL {name}: {type(exc).__name__}: {exc}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
