"""End-to-end tests for the platform shell.

Drives the real routes against the real engine, in both data modes: the upload
path (a messy workbook) and the manual-books path (a nursery typing entries in).

Runs under pytest or standalone:  python -m tests.test_platform
"""

from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

from fastapi.testclient import TestClient

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from vyuha import sample                                      # noqa: E402
from vyuha_platform import app as app_mod                     # noqa: E402
from vyuha_platform import auth, books, channels, sources, store  # noqa: E402

client = TestClient(app_mod.app, follow_redirects=True)
_SLUGS: list[str] = []

#: Every test below runs as one signed-in operator. TestClient keeps cookies
#: across requests, so signing up once here puts the whole suite inside a real
#: session — which is also the only way any of these routes answer at all now.
ACCOUNT = auth.create(f"tests-{auth.secrets.token_hex(4)}@vyuha.test",
                      "Zeta Test Operator", "test-password-1")


def _login() -> None:
    client.post("/login", data={"email": ACCOUNT.email, "password": "test-password-1"})


def _as(install: str, org: str = "", slug: str = "") -> None:
    """Reshape the logged-in account's workspace, the way signup does."""
    account = auth.get(ACCOUNT.id)
    account.install, account.org_name, account.tenant_slug = install, org, slug
    auth.update(account)


_login()
_as("operator")


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
    matches = [c.slug for c in store.load_clients(ACCOUNT.id) if c.slug.startswith(base)]
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
    got = store.get_client(slug, ACCOUNT.id)
    assert got is not None
    assert got.phone == "919876543210", got.phone     # 10 digits -> +91 assumed
    assert got.contact == "" and got.email == ""      # nothing else demanded
    assert got.data_mode == "upload"


# ------------------------------------------------------------------- uploading

def test_upload_produces_dashboard_and_alerts():
    slug = _onboard("Zeta Upload Co")
    assert _upload(slug, _sample_workbook()).status_code == 200

    run = store.get_client(slug, ACCOUNT.id).latest
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

    run = store.get_client(slug, ACCOUNT.id).latest
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
    assert store.get_client(slug, ACCOUNT.id).runs == []
    assert "API key" in resp.text or "Settings" in resp.text


def test_unsupported_file_type_creates_no_run():
    slug = _onboard("Zeta Reject Co")
    bad = store.upload_dir(slug) / "notes.docx"
    bad.write_bytes(b"nope")
    assert _upload(slug, bad).status_code == 200
    assert store.get_client(slug, ACCOUNT.id).runs == []


# --------------------------------------------------------------- manual books

def test_manual_books_flow_end_to_end():
    """A nursery with no spreadsheet: add stock, sell it, get the same engine."""
    slug = _onboard("Zeta Nursery", mode="books", phone="")
    assert store.get_client(slug, ACCOUNT.id).data_mode == "books"

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
    run = store.get_client(slug, ACCOUNT.id).latest
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

    run = store.get_client(slug, ACCOUNT.id).latest
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
    kinds = {e.kind for e in ledger.read(ACCOUNT.id, limit=200, client=slug)}
    assert "client.onboarded" in kinds
    assert "source.received" in kinds
    assert "run.completed" in kinds
    assert client.get(f"/activity?client={slug}").status_code == 200


# ------------------------------------------------------- operator vs tenant

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
        assert not any(c.name == "Sneaky Co" for c in store.load_clients(ACCOUNT.id))

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
        a = auth.get(ACCOUNT.id)
        assert a.tenant_slug and a.org_name == "Zeta Solo Shop"
        _SLUGS.append(a.tenant_slug)
        assert store.get_client(a.tenant_slug, ACCOUNT.id).trade == "nursery"
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
    """Backdrops are photographs now, with the original SVGs kept underneath.

    A path that 404s is worse than the flat SVG it replaced, so check the file
    is actually on disk — and that the fallback survived the swap.
    """
    from vyuha_platform import theme
    static = REPO / "vyuha_platform" / "static" / "img"
    for key, t in theme.TRADES.items():
        assert t["backdrop"].startswith("/static/img/"), key
        photo = static / t["backdrop"].rsplit("/", 1)[-1]
        assert photo.exists(), f"{key} backdrop missing on disk: {photo}"
        assert photo.stat().st_size > 10_000, f"{key} backdrop looks empty"
        assert t["fallback"].startswith("data:image/svg+xml;base64,"), key
        assert len(t["fallback"]) > 400, f"{key} fallback looks empty"


def test_platform_images_are_served():
    for name in ("hero-gears.jpg", "trade-nursery.jpg", "trade-manufacturing.jpg",
                 "trade-distribution.jpg", "trade-retail.jpg"):
        resp = client.get(f"/static/img/{name}")
        assert resp.status_code == 200, name
        assert resp.headers["content-type"].startswith("image/"), name


def test_the_client_dashboard_never_reaches_for_a_platform_image():
    """The engine's self-contained guarantee must survive the platform having
    images at all. A dashboard forwarded on WhatsApp has no server to ask."""
    slug = _onboard("Zeta Selfcontained Co")
    _upload(slug, _sample_workbook())
    run = store.get_client(slug, ACCOUNT.id).latest
    html = (store.DASHBOARDS / run.dashboard).read_text(encoding="utf-8")
    assert "/static/" not in html
    assert "<script" not in html.lower()


def test_cover_photo_upload_shows_on_the_workspace():
    slug = _onboard("Zeta Cover Co", mode="books", phone="")
    assert store.get_client(slug, ACCOUNT.id).has_cover is False
    png = (b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)
    resp = client.post(f"/c/{slug}/cover",
                       files={"file": ("shop.png", png, "image/png")})
    assert resp.status_code == 200
    assert store.get_client(slug, ACCOUNT.id).has_cover is True
    assert f"/c/{slug}/cover" in client.get(f"/c/{slug}").text
    (store.covers_dir() / f"{slug}.img").unlink(missing_ok=True)


def test_workspace_shows_every_option_as_a_labelled_action():
    slug = _onboard("Zeta Actions Co", mode="books", phone="")
    body = client.get(f"/c/{slug}").text
    for label in ("Enter sales &amp; stock", "See the dashboard", "Send &amp; download", "Setup"):
        assert label in body, f"missing action: {label}"


# ---------------------------------------------------------- accounts & gate

def test_signed_out_visitor_gets_the_landing_page_not_the_app():
    anon = TestClient(app_mod.app, follow_redirects=True)
    body = anon.get("/").text
    assert "Create an account" in body
    assert "PORTFOLIO" not in body, "the portfolio leaked to a signed-out visitor"


def test_every_private_route_redirects_a_stranger_to_the_login():
    anon = TestClient(app_mod.app, follow_redirects=False)
    for path in ("/onboard", "/activity", "/settings", "/c/anything",
                 "/c/anything/dashboard", "/c/anything/export/pdf"):
        resp = anon.get(path)
        assert resp.status_code == 303, f"{path} -> {resp.status_code}"
        assert resp.headers["location"] == "/login", path


def test_signup_rejects_a_bad_email_a_short_password_and_a_duplicate():
    for data, expect in (
        ({"name": "X", "email": "not-an-email", "password": "longenough1"},
         "does not look like"),
        ({"name": "X", "email": "fresh@vyuha.test", "password": "short"},
         "at least 8 characters"),
        ({"name": "X", "email": ACCOUNT.email, "password": "test-password-1"},
         "already exists"),
    ):
        body = TestClient(app_mod.app).post("/signup", data=data).text
        assert expect in body, f"{data} -> {body[:200]}"


def test_a_password_is_never_stored_in_readable_form():
    raw = auth.ACCOUNTS.read_text(encoding="utf-8")
    assert "test-password-1" not in raw
    assert auth.get(ACCOUNT.id).password_hash != "test-password-1"


def test_a_forged_cookie_does_not_open_the_app():
    forged = TestClient(app_mod.app, follow_redirects=False)
    forged.cookies.set(auth.COOKIE, f"{ACCOUNT.id}.9999999999.deadbeef")
    resp = forged.get("/settings")
    assert resp.status_code == 303 and resp.headers["location"] == "/login"


def test_one_account_cannot_see_or_reach_another_accounts_client():
    """The whole point of open signup: two businesses, one machine, no bleed."""
    mine = _onboard("Zeta Private Co")

    other = auth.create(f"other-{auth.secrets.token_hex(4)}@vyuha.test",
                        "Someone Else", "other-password-1")
    other.install = "operator"
    auth.update(other)
    session = TestClient(app_mod.app, follow_redirects=True)
    session.post("/login", data={"email": other.email, "password": "other-password-1"})

    home = session.get("/")
    assert "Zeta Private Co" not in home.text, "a client leaked across accounts"

    reached = session.get(f"/c/{mine}")
    assert "Zeta Private Co" not in reached.text, "another account was reached by URL"
    assert session.get(f"/c/{mine}/dashboard").status_code == 200   # redirected away
    assert store.get_client(mine, other.id) is None

    # ...and the owner still sees it perfectly well.
    assert "Zeta Private Co" in client.get("/").text


def test_logging_out_closes_the_door():
    session = TestClient(app_mod.app, follow_redirects=False)
    session.post("/login", data={"email": ACCOUNT.email, "password": "test-password-1"})
    assert session.get("/settings").status_code == 200
    session.post("/logout")
    resp = session.get("/settings")
    assert resp.status_code == 303 and resp.headers["location"] == "/login"


# ------------------------------------------------ shared workspace (link+PIN)

def _share(slug: str) -> tuple[str, str]:
    """Mint a link as the operator and read the one-shot PIN back out."""
    resp = client.post(f"/c/{slug}/share")
    assert resp.status_code == 200
    invite = auth.invite_for(slug)
    assert invite is not None
    pin = re.search(r'class="pin-val">(\d{4})<', resp.text)
    assert pin, "the PIN was not shown to the operator"
    return invite.token, pin.group(1)


def test_owner_opens_their_workspace_with_a_link_and_a_pin():
    slug = _onboard("Zeta Shared Nursery", mode="books", phone="919876543210")
    token, pin = _share(slug)

    owner = TestClient(app_mod.app, follow_redirects=True)
    gate = owner.get(f"/w/{token}")
    assert "Enter your" in gate.text and "PIN" in gate.text
    assert "Zeta Shared Nursery" in gate.text

    body = owner.post(f"/w/{token}", data={"pin": pin}).text
    assert "Zeta Shared Nursery" in body, "the PIN did not open the workspace"

    # The device is remembered: the bare link now goes straight in.
    assert "Zeta Shared Nursery" in owner.get(f"/w/{token}").text


def test_the_link_alone_is_not_access():
    slug = _onboard("Zeta Forwarded Co", mode="books", phone="")
    token, pin = _share(slug)
    stranger = TestClient(app_mod.app, follow_redirects=True)

    # The gate names the business on purpose — the owner has to know the link is
    # theirs — but names nothing else, and hands over no numbers.
    opened = stranger.get(f"/w/{token}")
    assert "Enter your" in opened.text, "a forwarded link let someone straight in"
    assert "Revenue" not in opened.text and "PORTFOLIO" not in opened.text

    wrong = stranger.post(f"/w/{token}", data={"pin": f"{(int(pin) + 1) % 10000:04d}"})
    assert "not right" in wrong.text
    assert "PORTFOLIO" not in wrong.text


def test_a_guest_sees_one_workspace_and_none_of_the_operators_machinery():
    mine = _onboard("Zeta Guest Shop", mode="books", phone="")
    theirs = _onboard("Zeta Other Shop", mode="books", phone="")
    token, pin = _share(mine)

    guest = TestClient(app_mod.app, follow_redirects=True)
    guest.post(f"/w/{token}", data={"pin": pin})

    home = guest.get("/")
    assert "Zeta Guest Shop" in home.text
    assert "PORTFOLIO" not in home.text
    assert "Zeta Other Shop" not in home.text, "another client leaked to a guest"

    # Operator machinery is closed, not merely hidden.
    assert "Onboard a client" not in guest.get("/onboard").text
    assert "Zeta Other Shop" not in guest.get(f"/c/{theirs}").text

    # Deployment credentials are the operator's, never the guest's.
    creds = guest.get("/settings")
    assert "Anthropic" not in creds.text and "SMTP" not in creds.text

    # And a guest cannot re-share or delete the workspace they were lent.
    guest.post(f"/c/{mine}/share")
    guest.post(f"/c/{mine}/delete")
    assert store.get_client(mine, ACCOUNT.id) is not None, "a guest deleted the workspace"


def test_revoking_a_link_locks_the_owner_out_immediately():
    slug = _onboard("Zeta Revoked Co", mode="books", phone="")
    token, pin = _share(slug)
    owner = TestClient(app_mod.app, follow_redirects=True)
    owner.post(f"/w/{token}", data={"pin": pin})
    assert "Zeta Revoked Co" in owner.get("/").text

    client.post(f"/c/{slug}/share/revoke")

    # The remembered device is not enough once the link is off.
    assert "Zeta Revoked Co" not in owner.get(f"/w/{token}").text
    landing = owner.get("/")
    assert "Create an account" in landing.text, "a revoked guest still had a session"


def test_guessing_the_pin_locks_the_link_and_says_so():
    """Four digits is 10,000 guesses. Failures have to cost something."""
    slug = _onboard("Zeta Bruteforce Co", mode="books", phone="")
    token, pin = _share(slug)
    wrong = f"{(int(pin) + 1) % 10000:04d}"
    guesser = TestClient(app_mod.app, follow_redirects=True)

    for _ in range(auth.PIN_TRIES):
        body = guesser.post(f"/w/{token}", data={"pin": wrong}).text
    assert "Too many wrong PINs" in body, "the link never locked"

    invite = auth.invite_for(slug)
    assert invite.locked and invite.locked_for >= 1

    # Locked means locked: even the right PIN is refused while it lasts. The
    # gate still names the business — that is deliberate, so the owner knows the
    # link is theirs — so check they did not get *in*, not that the name is gone.
    refused = guesser.post(f"/w/{token}", data={"pin": pin}).text
    assert "Paused" in refused, "the right PIN opened a locked link"
    assert "Record a sale" not in refused and "WHAT IS LEFT" not in refused

    # And the form is not offered at all, rather than failing on submit.
    gate = guesser.get(f"/w/{token}").text
    assert 'name="pin"' not in gate
    assert "Paused" in gate


def test_a_correct_pin_clears_the_failure_count():
    slug = _onboard("Zeta Mistype Co", mode="books", phone="")
    token, pin = _share(slug)
    owner = TestClient(app_mod.app, follow_redirects=True)

    wrong = f"{(int(pin) + 1) % 10000:04d}"
    for _ in range(auth.PIN_TRIES - 1):          # mistyped, but stopped in time
        owner.post(f"/w/{token}", data={"pin": wrong})
    assert auth.invite_for(slug).failed == auth.PIN_TRIES - 1

    assert "Zeta Mistype Co" in owner.post(f"/w/{token}", data={"pin": pin}).text
    invite = auth.invite_for(slug)
    assert invite.failed == 0 and not invite.locked


def test_the_session_cookie_is_secure_only_when_the_connection_is():
    """Unconditional `secure` would mean no session at all over localhost."""
    plain = TestClient(app_mod.app, base_url="http://testserver",
                       follow_redirects=False)
    resp = plain.post("/login", data={"email": ACCOUNT.email,
                                      "password": "test-password-1"})
    assert "secure" not in resp.headers["set-cookie"].lower()
    assert "httponly" in resp.headers["set-cookie"].lower()
    assert "samesite=lax" in resp.headers["set-cookie"].lower()

    secure = TestClient(app_mod.app, base_url="https://testserver",
                        follow_redirects=False)
    resp = secure.post("/login", data={"email": ACCOUNT.email,
                                       "password": "test-password-1"})
    assert "secure" in resp.headers["set-cookie"].lower()

    # A reverse proxy terminating TLS says so in a header, not the scheme.
    proxied = TestClient(app_mod.app, base_url="http://testserver",
                         follow_redirects=False)
    resp = proxied.post("/login", data={"email": ACCOUNT.email,
                                        "password": "test-password-1"},
                        headers={"x-forwarded-proto": "https"})
    assert "secure" in resp.headers["set-cookie"].lower()


def test_changing_the_password_takes_effect_and_keeps_you_signed_in():
    session = TestClient(app_mod.app, follow_redirects=True)
    session.post("/login", data={"email": ACCOUNT.email, "password": "test-password-1"})

    # The current password has to be right.
    refused = session.post("/password", data={"current_password": "not-my-password",
                                              "new_password": "second-password-1"})
    assert "not your current password" in refused.text

    ok = session.post("/password", data={"current_password": "test-password-1",
                                         "new_password": "second-password-1"})
    assert "Password changed" in ok.text
    assert session.get("/settings").status_code == 200, "the change signed us out"

    assert auth.verify(ACCOUNT.email, "second-password-1") is not None
    assert auth.verify(ACCOUNT.email, "test-password-1") is None

    # Put it back so the rest of the suite's helpers still work.
    auth.change_password(auth.get(ACCOUNT.id), "second-password-1", "test-password-1")


def test_a_guest_has_no_password_to_change():
    slug = _onboard("Zeta Nopass Co", mode="books", phone="")
    token, pin = _share(slug)
    guest = TestClient(app_mod.app, follow_redirects=True)
    guest.post(f"/w/{token}", data={"pin": pin})

    body = guest.post("/password", data={"current_password": "x",
                                         "new_password": "yyyyyyyy"}).text
    assert "not part of your workspace" in body.lower() or "Zeta Nopass Co" in body
    assert auth.verify(ACCOUNT.email, "test-password-1") is not None


def test_a_pin_is_never_stored_in_readable_form():
    slug = _onboard("Zeta Pinsafe Co", mode="books", phone="")
    _, pin = _share(slug)
    assert pin not in auth.INVITES.read_text(encoding="utf-8")


def _cleanup() -> None:
    _as("operator")
    _login()
    for slug in set(_SLUGS):
        shutil.rmtree(store.UPLOADS / slug, ignore_errors=True)
        shutil.rmtree(store.DASHBOARDS / slug, ignore_errors=True)
        (books.BOOKS / f"{slug}.json").unlink(missing_ok=True)
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
