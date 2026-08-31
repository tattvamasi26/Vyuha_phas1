"""Tests for tax invoices — arithmetic, numbering, and the document.

Runs under pytest or standalone:  python -m tests.test_invoice

An invoice is a legal document, so the tests here are less about "does it
render" and more about the three ways it can be quietly wrong: tax computed on
the wrong base, a number reused, and a total that disagrees with the buyer's
own books by a rupee.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

os.environ["VYUHA_LLM"] = "offline"

from fastapi.testclient import TestClient                  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from vyuha_platform import (app as app_mod, auth, books, invoice,   # noqa: E402
                            invoice_render, store)

client = TestClient(app_mod.app, follow_redirects=True)
_SLUGS: list[str] = []

ACCOUNT = auth.create(f"inv-{auth.secrets.token_hex(4)}@vyuha.test",
                      "Invoice Test Operator", "test-password-1")


def _login() -> None:
    client.post("/login", data={"email": ACCOUNT.email, "password": "test-password-1"})


def _as_operator() -> None:
    a = auth.get(ACCOUNT.id)
    a.install, a.org_name, a.tenant_slug = "operator", "", ""
    auth.update(a)


_login()
_as_operator()


def _shop(name: str, gstin: str = "29ABCDE1234F1Z5", state: str = "KA"):
    """A billing business with three GST rates on the shelf."""
    client.post("/onboard", data={"name": name, "phone": "9876543210",
                                  "data_mode": "books"})
    slug = next(c.slug for c in store.load_clients(ACCOUNT.id)
                if c.slug.startswith(store.slugify(name)))
    _SLUGS.append(slug)

    for item, cat, rate, cost, hsn, gst in [
        ("Urea 50kg", "Fertiliser", 320, 268, "31021000", 5),
        ("Paddy Seed 5kg", "Seed", 640, 520, "10061010", 0),
        ("Sprayer 16L", "Tools", 2250, 1780, "84242000", 18),
    ]:
        client.post(f"/c/{slug}/book/item", data={
            "name": item, "category": cat, "unit": "piece",
            "rate": str(rate), "cost": str(cost), "stock_qty": "500",
            "reorder_level": "10"})

    book = books.load(slug)
    for i in book.items:
        i.hsn, i.gst_rate = {
            "Urea 50kg": ("31021000", 5.0),
            "Paddy Seed 5kg": ("10061010", 0.0),
            "Sprayer 16L": ("84242000", 18.0)}[i.name]
    books.save(book)

    c = store.get_client(slug, ACCOUNT.id)
    c.gstin, c.state = gstin, state
    c.address = "Test Yard, Belagavi"
    store.update_client(c)
    return slug, store.get_client(slug, ACCOUNT.id)


def _sell(slug: str, item: str, qty: float, rate: float) -> str:
    book = books.load(slug)
    sku = next(i.sku for i in book.items if item.lower() in i.name.lower())
    book, _note, _ok = books.record_sale(slug, sku, "Test Buyer", qty, rate)
    return book.sales[-1].id


def _raise(slug: str, sale_ids: list[str], **extra):
    data = {"sale_ids": sale_ids}
    data.update(extra)
    client.post(f"/c/{slug}/invoice", data=data)
    return invoice.load_all(slug)[0]


# ===================================================== the tax arithmetic

def test_tax_is_computed_per_line_not_on_the_total():
    """A mixed-rate bill taxed at the bottom disagrees with the buyer's books."""
    slug, c = _shop("Per Line Traders")
    ids = [_sell(slug, "urea", 10, 320),        # 3200 @ 5%  = 160
           _sell(slug, "paddy", 10, 640),       # 6400 @ 0%  = 0
           _sell(slug, "sprayer", 2, 2250)]     # 4500 @ 18% = 810
    inv = _raise(slug, ids)

    assert inv.taxable == 14100
    assert inv.tax == 970, inv.tax
    assert inv.total == 15070
    # Taxing the whole base at any single rate gives a different answer.
    assert inv.tax != round(inv.taxable * 0.05, 2)
    assert inv.tax != round(inv.taxable * 0.18, 2)


def test_within_the_state_splits_into_cgst_and_sgst():
    slug, c = _shop("Local Traders", state="KA")
    inv = _raise(slug, [_sell(slug, "sprayer", 2, 2250)], party_state="KA")
    assert inv.intra_state
    assert inv.cgst == inv.sgst == 405.0
    assert inv.igst == 0
    assert inv.cgst + inv.sgst == inv.tax


def test_across_a_state_border_it_becomes_igst():
    """The one field that changes the arithmetic."""
    slug, c = _shop("Export Traders", state="KA")
    inv = _raise(slug, [_sell(slug, "sprayer", 2, 2250)], party_state="MH")
    assert not inv.intra_state
    assert inv.igst == 810.0
    assert inv.cgst == inv.sgst == 0


def test_an_unknown_buyer_state_is_treated_as_local():
    """A shop assumes local when nobody says otherwise, and so does this."""
    slug, c = _shop("Assume Local Traders", state="KA")
    inv = _raise(slug, [_sell(slug, "urea", 10, 320)])
    assert inv.intra_state


def test_a_business_with_no_gstin_prints_a_bill_of_supply():
    """Never an invoice with a blank tax field — that is a document nobody can use."""
    slug, c = _shop("No GST Traders", gstin="", state="")
    assert "your GSTIN" in " ".join(invoice.missing(c))
    inv = _raise(slug, [_sell(slug, "urea", 10, 320)])
    page = invoice_render.render_html(inv, store.get_client(slug, ACCOUNT.id))
    assert "BILL OF SUPPLY" in page
    assert "TAX INVOICE" not in page


def test_the_rate_summary_groups_by_rate_when_they_differ():
    slug, c = _shop("Summary Traders")
    ids = [_sell(slug, "urea", 10, 320), _sell(slug, "sprayer", 2, 2250)]
    inv = _raise(slug, ids)
    groups = {g["gst_rate"]: g for g in inv.by_rate()}
    assert set(groups) == {5.0, 18.0}
    assert groups[18.0]["tax"] == 810.0
    assert groups[18.0]["half"] == 405.0


def test_the_rounded_total_and_its_round_off_agree():
    slug, c = _shop("Rounding Traders")
    inv = _raise(slug, [_sell(slug, "urea", 3, 333.33)])
    assert abs(inv.total + inv.round_off - inv.rounded) < 0.005


# ========================================================== the numbering

def test_numbers_are_sequential_and_never_repeat():
    slug, c = _shop("Series Traders")
    numbers = [_raise(slug, [_sell(slug, "urea", 1, 320)]).number for _ in range(4)]
    assert len(set(numbers)) == 4
    assert numbers == sorted(numbers)


def test_a_cancelled_invoice_does_not_give_its_number_back():
    """Two documents sharing one number is far worse than a gap in the series."""
    slug, c = _shop("Cancel Traders")
    first = _raise(slug, [_sell(slug, "urea", 1, 320)])
    second = _raise(slug, [_sell(slug, "urea", 1, 320)])
    client.post(f"/c/{slug}/invoice/{second.id}/delete")
    third = _raise(slug, [_sell(slug, "urea", 1, 320)])

    assert third.number != second.number
    live = {i.number for i in invoice.load_all(slug)}
    assert second.number not in live
    assert first.number in live


def test_the_number_carries_the_financial_year():
    slug, c = _shop("FY Traders")
    inv = _raise(slug, [_sell(slug, "urea", 1, 320)])
    assert inv.number.startswith("INV/")
    fy = inv.number.split("/")[1]
    assert len(fy) == 7 and "-" in fy, fy


def test_a_failed_raise_does_not_consume_a_number():
    """A gap from a render that crashed is a question from the tax office."""
    slug, c = _shop("No Burn Traders")
    before = invoice.next_number(store.get_client(slug, ACCOUNT.id))[0]
    client.post(f"/c/{slug}/invoice", data={"sale_ids": []})     # nothing ticked
    after = invoice.next_number(store.get_client(slug, ACCOUNT.id))[0]
    assert before == after


def test_one_invoice_can_cover_several_sales():
    """A customer who bought three things gets one bill, not three."""
    slug, c = _shop("Consolidated Traders")
    ids = [_sell(slug, "urea", 5, 320), _sell(slug, "paddy", 2, 640),
           _sell(slug, "sprayer", 1, 2250)]
    inv = _raise(slug, ids)
    assert len(inv.lines) == 3
    assert set(inv.sale_ids) == set(ids)


# ============================================================ the document

def test_the_printed_invoice_is_self_contained():
    """It gets forwarded, saved and printed in a shop with no internet."""
    slug, c = _shop("Offline Doc Traders")
    inv = _raise(slug, [_sell(slug, "sprayer", 2, 2250)])
    page = invoice_render.render_html(inv, store.get_client(slug, ACCOUNT.id))
    assert "<script" not in page.lower() or "window.print" in page
    assert "src=" not in page
    assert "http://" not in page and "https://" not in page
    assert "@page" in page, "it has to be laid out for paper"


def test_the_document_carries_what_makes_it_a_tax_invoice():
    slug, c = _shop("Complete Doc Traders")
    inv = _raise(slug, [_sell(slug, "sprayer", 2, 2250)], party_gstin="29XYZAB5678K1Z2")
    page = invoice_render.render_html(inv, store.get_client(slug, ACCOUNT.id))
    for probe in ("TAX INVOICE", "29ABCDE1234F1Z5", "29XYZAB5678K1Z2",
                  "Place of supply", "CGST", "SGST", "HSN",
                  "Rupees Only", "Authorised signatory"):
        assert probe in page, probe


def test_the_total_prints_in_words_in_the_indian_system():
    """A buyer's clerk checks the words against the figure."""
    assert (invoice_render.in_words(126840)
            == "One Lakh Twenty Six Thousand Eight Hundred Forty Rupees Only")
    assert invoice_render.in_words(0) == "Zero Rupees Only"
    assert "Crore" in invoice_render.in_words(12_500_000)
    assert "Lakh" in invoice_render.in_words(250000)


def test_the_pdf_renders_and_carries_no_rupee_glyph():
    """Helvetica has no ₹ and prints a black box in a total field."""
    slug, c = _shop("PDF Traders")
    inv = _raise(slug, [_sell(slug, "sprayer", 2, 2250)])
    out = REPO / "out" / "invoice-test"
    path = invoice_render.to_pdf(inv, store.get_client(slug, ACCOUNT.id),
                                 out / "inv.pdf")
    blob = path.read_bytes()
    assert blob[:4] == b"%PDF"
    assert "₹".encode() not in blob
    assert len(blob) > 1500
    shutil.rmtree(out, ignore_errors=True)


def test_the_route_serves_the_document_and_the_pdf():
    slug, c = _shop("Route Doc Traders")
    inv = _raise(slug, [_sell(slug, "urea", 4, 320)])
    page = client.get(f"/c/{slug}/invoice/{inv.id}")
    assert page.status_code == 200 and inv.number in page.text
    pdf = client.get(f"/c/{slug}/invoice/{inv.id}/pdf")
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"


def test_saving_the_identity_does_not_change_invoices_already_sent():
    """A document somebody already has must not change under them."""
    slug, c = _shop("Frozen Traders", state="KA")
    inv = _raise(slug, [_sell(slug, "sprayer", 2, 2250)], party_state="KA")
    assert inv.intra_state

    client.post(f"/c/{slug}/invoice/identity",
                data={"gstin": "27NEWAB1234C1Z9", "state": "MH",
                      "address": "Moved to Maharashtra"})

    again = invoice.get(slug, inv.id)
    assert again.intra_state, "the issued invoice keeps the split it was raised with"


def test_the_bills_panel_renders():
    slug, c = _shop("Panel Traders")
    _raise(slug, [_sell(slug, "urea", 4, 320)])
    _sell(slug, "paddy", 2, 640)     # leave one unbilled, or the form is hidden
    page = client.get(f"/c/{slug}/console?panel=bills").text
    for probe in ('data-panel="bills"', "Raise an invoice", "Invoices raised",
                  "What prints at the top"):
        assert probe in page, probe


def _cleanup() -> None:
    _login()
    _as_operator()
    for slug in set(_SLUGS):
        shutil.rmtree(store.UPLOADS / slug, ignore_errors=True)
        shutil.rmtree(store.DASHBOARDS / slug, ignore_errors=True)
        for path in (books.BOOKS / f"{slug}.json",
                     invoice.INVOICES / f"{slug}.json"):
            path.unlink(missing_ok=True)
        store.delete_client(slug, ACCOUNT.id)


def main() -> int:
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    passed = failed = 0
    try:
        for name, fn in tests:
            try:
                fn()
                print(f"ok   {name}")
                passed += 1
            except Exception as exc:                       # noqa: BLE001
                print(f"FAIL {name}: {type(exc).__name__}: {exc}")
                failed += 1
    finally:
        _cleanup()
    print(f"\n{passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
