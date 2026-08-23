"""End-to-end tests for the platform shell.

Drives the real routes against the real engine, in both data modes: the upload
path (a messy workbook) and the manual-books path (a nursery typing entries in).

Runs under pytest or standalone:  python -m tests.test_platform
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from fastapi.testclient import TestClient

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from vyuha import sample                                      # noqa: E402
from vyuha_platform import app as app_mod                     # noqa: E402
from vyuha_platform import books, channels, config, sources, store  # noqa: E402

client = TestClient(app_mod.app, follow_redirects=True)
_SLUGS: list[str] = []


def _sample_workbook() -> Path:
    path = REPO / "out" / "sample-distributor.xlsx"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        sample.build(path)
    return path


def _onboard(name: str, mode: str = "upload", phone: str = "98765 43210") -> str:
    resp = client.post("/onboard", data={"name": name, "phone": phone, "data_mode": mode})
    assert resp.status_code == 200, resp.status_code
    base = store.slugify(name)
    matches = [c.slug for c in store.load_clients() if c.slug.startswith(base)]
    assert matches, f"{name} was not persisted"
    _SLUGS.extend(matches)
    return matches[0]


def _upload(slug: str, path: Path, mime: str = "application/octet-stream"):
    with path.open("rb") as fh:
        return client.post(f"/c/{slug}/upload", files={"file": (path.name, fh, mime)})


# ------------------------------------------------------------- platform pages

def test_all_platform_pages_render():
    for path in ("/", "/onboard", "/activity", "/settings"):
        resp = client.get(path)
        assert resp.status_code == 200, f"{path} -> {resp.status_code}"
        assert "VYUHA" in resp.text


def test_onboarding_asks_for_only_a_name_and_number():
    slug = _onboard("Zeta Minimal Co")
    got = store.get_client(slug)
    assert got is not None
    assert got.phone == "919876543210", got.phone     # 10 digits -> +91 assumed
    assert got.contact == "" and got.email == ""      # nothing else demanded
    assert got.data_mode == "upload"


# ------------------------------------------------------------------- uploading

def test_upload_produces_dashboard_and_alerts():
    slug = _onboard("Zeta Upload Co")
    assert _upload(slug, _sample_workbook()).status_code == 200

    run = store.get_client(slug).latest
    assert run is not None and run.status == "ok", getattr(run, "error", "no run")
    assert run.alert_count >= 3
    assert {"Sales", "Stock", "Receivables"} <= set(run.sheets_read), run.sheets_read
    assert all(a["code"] != "generic" for a in run.alerts)
    assert run.source_kind == "native"

    assert client.get(f"/c/{slug}/dashboard").status_code == 200


def test_text_file_is_converted_and_read():
    slug = _onboard("Zeta Text Co")
    tmp = store.upload_dir(slug) / "stock.txt"
    tmp.write_text(
        "SKU\tItem\tClosing Stock\tReorder Level\tRate\n"
        "BRG-1\tBall Bearing\t24\t120\t340\n"
        "SEAL-2\tOil Seal\t180\t50\t95\n"
        "CPL-3\tCoupling\t8\t40\t1250\n",
        encoding="utf-8")
    assert _upload(slug, tmp, "text/plain").status_code == 200

    run = store.get_client(slug).latest
    assert run is not None and run.status == "ok", getattr(run, "error", "")
    assert run.source_kind == "text", run.source_kind
    assert run.source_method, "conversion method was not recorded"


def test_image_without_a_key_is_rejected_with_an_action():
    slug = _onboard("Zeta Image Co")
    img = store.upload_dir(slug) / "page.png"
    img.write_bytes(b"not really a png")
    resp = _upload(slug, img, "image/png")
    assert resp.status_code == 200
    # No run is recorded, and the operator is told what to do about it.
    assert store.get_client(slug).runs == []
    assert "API key" in resp.text or "Settings" in resp.text


def test_unsupported_file_type_creates_no_run():
    slug = _onboard("Zeta Reject Co")
    bad = store.upload_dir(slug) / "notes.docx"
    bad.write_bytes(b"nope")
    assert _upload(slug, bad).status_code == 200
    assert store.get_client(slug).runs == []


# --------------------------------------------------------------- manual books

def test_manual_books_flow_end_to_end():
    """A nursery with no spreadsheet: add stock, sell it, get the same engine."""
    slug = _onboard("Zeta Nursery", mode="books", phone="")
    assert store.get_client(slug).data_mode == "books"

    client.post(f"/c/{slug}/book/item", data={
        "name": "Areca Palm 4ft", "category": "Plants", "unit": "piece",
        "rate": "450", "cost": "260", "stock_qty": "40", "reorder_level": "10"})
    client.post(f"/c/{slug}/book/item", data={
        "name": "Vermicompost 5kg", "category": "Manure & Fertiliser", "unit": "bag",
        "rate": "180", "cost": "110", "stock_qty": "25", "reorder_level": "8"})

    book = books.load(slug)
    assert len(book.items) == 2
    palm = next(i for i in book.items if i.name.startswith("Areca"))

    client.post(f"/c/{slug}/book/sale", data={
        "sku": palm.sku, "party": "Green Valley Resort", "qty": "12",
        "rate": "", "payment": "paid"})
    client.post(f"/c/{slug}/book/sale", data={
        "sku": palm.sku, "party": "Lakeview Villas", "qty": "8",
        "rate": "", "payment": "credit", "due_date": "2026-09-20"})

    book = books.load(slug)
    palm = next(i for i in book.items if i.name.startswith("Areca"))
    assert palm.stock_qty == 20, palm.stock_qty        # stock came down
    assert book.earned == 20 * 450
    assert book.owed == 8 * 450                        # the credit sale
    assert book.collected == 12 * 450
    assert book.margin == 20 * (450 - 260)             # profit on what sold

    # The typed-in ledger went through the real engine.
    run = store.get_client(slug).latest
    assert run is not None and run.status == "ok", getattr(run, "error", "")
    assert run.source_kind == "manual"
    assert run.revenue == 20 * 450
    assert "Sales" in run.sheets_read and "Stock" in run.sheets_read

    page = client.get(f"/c/{slug}?tab=books")
    assert page.status_code == 200
    assert "Record a sale" in page.text and "WHAT IS LEFT" in page.text


def test_deleting_a_sale_puts_the_stock_back():
    slug = _onboard("Zeta Restock", mode="books", phone="")
    client.post(f"/c/{slug}/book/item", data={
        "name": "Money Plant", "category": "Plants", "unit": "piece",
        "rate": "120", "cost": "55", "stock_qty": "30", "reorder_level": "5"})
    sku = books.load(slug).items[0].sku
    client.post(f"/c/{slug}/book/sale", data={"sku": sku, "party": "Walk-in",
                                              "qty": "10", "payment": "paid"})
    assert books.load(slug).items[0].stock_qty == 20

    sale_id = books.load(slug).sales[0].id
    client.post(f"/c/{slug}/book/sale/{sale_id}/delete")
    assert books.load(slug).items[0].stock_qty == 30
    assert books.load(slug).sales == []


def test_adding_a_known_item_restocks_instead_of_duplicating():
    slug = _onboard("Zeta Topup", mode="books", phone="")
    for qty in ("10", "15"):
        client.post(f"/c/{slug}/book/item", data={
            "name": "Neem Cake 10kg", "category": "Manure & Fertiliser", "unit": "bag",
            "rate": "320", "cost": "210", "stock_qty": qty, "reorder_level": "5"})
    book = books.load(slug)
    assert len(book.items) == 1, "restock created a duplicate item"
    assert book.items[0].stock_qty == 25


def test_credit_sale_becomes_a_receivable_the_engine_sees():
    slug = _onboard("Zeta Credit", mode="books", phone="")
    client.post(f"/c/{slug}/book/item", data={
        "name": "Terracotta Pot", "category": "Pots & Planters", "unit": "piece",
        "rate": "260", "cost": "150", "stock_qty": "20", "reorder_level": "4"})
    sku = books.load(slug).items[0].sku
    client.post(f"/c/{slug}/book/sale", data={
        "sku": sku, "party": "Anil Farms", "qty": "5",
        "payment": "credit", "due_date": "2026-09-30"})

    run = store.get_client(slug).latest
    assert run.outstanding == 5 * 260, run.outstanding
    assert "Receivables" in run.sheets_read

    sale_id = books.load(slug).sales[0].id
    client.post(f"/c/{slug}/book/sale/{sale_id}/paid")
    assert books.load(slug).owed == 0


# -------------------------------------------------------------- send & export

def test_alerts_tab_offers_whatsapp_email_and_exports():
    slug = _onboard("Zeta Brief Co")
    _upload(slug, _sample_workbook())
    resp = client.get(f"/c/{slug}?tab=alerts")
    assert resp.status_code == 200
    assert "wa.me/919876543210" in resp.text, "WhatsApp deep link missing"
    assert f"/c/{slug}/export/pdf" in resp.text
    assert f"/c/{slug}/export/pptx" in resp.text


def test_pdf_and_pptx_exports_download():
    slug = _onboard("Zeta Export Co")
    _upload(slug, _sample_workbook())
    pdf = client.get(f"/c/{slug}/export/pdf")
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF", pdf.status_code
    deck = client.get(f"/c/{slug}/export/pptx")
    assert deck.status_code == 200 and deck.content[:2] == b"PK", deck.status_code


def test_whatsapp_brief_respects_the_character_cap():
    from vyuha import pipeline
    insights = pipeline.run(_sample_workbook()).insights
    for cap in (1024, 400, 220):
        text = channels.as_whatsapp(insights, client="Cap Test", limit=cap)
        assert len(text) <= cap, f"cap {cap}: got {len(text)}"


def test_phone_normalisation():
    assert channels.normalise_phone("98765 43210") == "919876543210"
    assert channels.normalise_phone("+91 98765-43210") == "919876543210"
    assert channels.normalise_phone("0091 9876543210") == "919876543210"
    assert channels.normalise_phone("") == ""


def test_source_classification():
    assert sources.classify("a.xlsx") == "native"
    assert sources.classify("a.csv") == "native"
    assert sources.classify("a.txt") == "text"
    assert sources.classify("a.JPG") == "image"
    assert sources.classify("a.pdf") == "pdf"
    assert sources.classify("a.docx") == "unsupported"


# ------------------------------------------------------------------ activity

def test_every_action_lands_in_the_activity_trail():
    from vyuha_platform import ledger
    slug = _onboard("Zeta Trail Co")
    _upload(slug, _sample_workbook())
    kinds = {e.kind for e in ledger.read(limit=200, client=slug)}
    assert "client.onboarded" in kinds
    assert "source.received" in kinds
    assert "run.completed" in kinds
    assert client.get(f"/activity?client={slug}").status_code == 200


# ------------------------------------------------------- operator vs tenant

def _as(install: str, org: str = "", slug: str = "") -> None:
    s = config.load()
    s.install, s.org_name, s.tenant_slug = install, org, slug
    config.save(s)


def test_first_run_asks_who_the_install_is_for():
    _as("")
    body = client.get("/").text
    assert "I run Vyuha" in body
    assert "This is my own business" in body
    _as("operator")


def test_operator_sees_the_portfolio_and_can_onboard():
    _as("operator")
    home = client.get("/")
    assert "PORTFOLIO" in home.text
    assert "Onboard" in home.text
    assert client.get("/onboard").status_code == 200
    assert "Operator" in home.text


def test_tenant_never_sees_the_portfolio_or_onboarding():
    """The product boundary: a tenant install must not reveal that other
    businesses exist, let alone let them onboard one."""
    mine = _onboard("Zeta Tenant Nursery", mode="books", phone="")
    theirs = _onboard("Zeta Someone Else")
    _as("tenant", "Zeta Tenant Nursery", mine)
    try:
        home = client.get("/")
        assert "PORTFOLIO" not in home.text
        assert "Zeta Someone Else" not in home.text, "another client leaked into a tenant install"
        assert "Onboard" not in home.text

        # The onboarding route itself is closed, not merely hidden.
        assert "Onboard a client" not in client.get("/onboard").text
        blocked = client.post("/onboard", data={"name": "Sneaky Co", "phone": ""})
        assert not any(c.name == "Sneaky Co" for c in store.load_clients())

        # And another workspace cannot be reached by guessing the URL.
        other = client.get(f"/c/{theirs}")
        assert "Zeta Someone Else" not in other.text, "tenant reached another workspace"
        assert blocked.status_code == 200
    finally:
        _as("operator")


def test_tenant_setup_creates_exactly_one_business():
    _as("tenant", "", "")
    try:
        page = client.get("/")
        assert "Set up your" in page.text and "kind of business" in page.text
        resp = client.post("/setup", data={"name": "Zeta Solo Shop", "trade": "nursery",
                                           "data_mode": "books"})
        assert resp.status_code == 200
        s = config.load()
        assert s.tenant_slug and s.org_name == "Zeta Solo Shop"
        _SLUGS.append(s.tenant_slug)
        assert store.get_client(s.tenant_slug).trade == "nursery"
    finally:
        _as("operator")


def test_trade_is_guessed_from_the_name():
    from vyuha_platform import theme
    assert theme.guess("Krishna Nursery and Manure") == "nursery"
    assert theme.guess("Shree Engineering Spares") == "manufacturing"
    assert theme.guess("Anand Hardware Store") == "retail"
    assert theme.guess("Patel Wholesale Agency") == "distribution"
    assert theme.guess("Something Vague Ltd") == "general"


def test_every_trade_has_a_usable_backdrop():
    from vyuha_platform import theme
    for key, t in theme.TRADES.items():
        assert t["backdrop"].startswith("data:image/svg+xml;base64,"), key
        assert len(t["backdrop"]) > 400, f"{key} backdrop looks empty"


def test_cover_photo_upload_shows_on_the_workspace():
    slug = _onboard("Zeta Cover Co", mode="books", phone="")
    assert store.get_client(slug).has_cover is False
    png = (b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)
    resp = client.post(f"/c/{slug}/cover",
                       files={"file": ("shop.png", png, "image/png")})
    assert resp.status_code == 200
    assert store.get_client(slug).has_cover is True
    assert f"/c/{slug}/cover" in client.get(f"/c/{slug}").text
    (store.covers_dir() / f"{slug}.img").unlink(missing_ok=True)


def test_workspace_shows_every_option_as_a_labelled_action():
    slug = _onboard("Zeta Actions Co", mode="books", phone="")
    body = client.get(f"/c/{slug}").text
    for label in ("Enter sales &amp; stock", "See the dashboard", "Send &amp; download", "Setup"):
        assert label in body, f"missing action: {label}"


def _cleanup() -> None:
    _as("operator")
    for slug in set(_SLUGS):
        shutil.rmtree(store.UPLOADS / slug, ignore_errors=True)
        shutil.rmtree(store.DASHBOARDS / slug, ignore_errors=True)
        (books.BOOKS / f"{slug}.json").unlink(missing_ok=True)
        store.delete_client(slug)


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
