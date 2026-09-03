"""FastAPI application: onboarding, ingestion, dashboard, alerts, exports.

The engine is imported and called, never reimplemented. ``pipeline.run()`` and
``report.render()`` are untouched by this package — the platform is a shell
around them, so anything that works in the CLI works here and vice versa.

Two deployment modes, one codebase (``settings.mode``):

* ``agency`` — the founder runs it and manages a portfolio of clients.
* ``self``   — a client installed it for their own company. First run asks for
  the company name once, then every screen is about that one business.

Every state change is written to the activity ledger, so the answer to "where
did this number come from" is always one screen away.
"""

from __future__ import annotations

import shutil
import threading
import traceback
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from vyuha import analyze, pipeline, report

from . import (agent, auth, books, channels, config, console, deck_render, decks,
               exports, finance, followup, invoice, invoice_render, ledger, library,
               money, people, sources, store, theme, ui, whatsapp)

app = FastAPI(title="Vyuha Operations Platform", docs_url=None, redoc_url=None)

# Vyuha's own staff logins exist from the first boot, so a fresh clone is never
# locked out of its own support console. Idempotent — see auth.ensure_masters.
auth.ensure_masters()

# analyze.py keeps its thresholds as module constants, so honouring a per-client
# value means swapping them for the duration of one run. That is process-global
# state, hence the lock. The clean fix is to thread a Thresholds object through
# analyse() — do it before this ever serves more than one operator.
_RUN_LOCK = threading.Lock()


@contextmanager
def _thresholds(client: store.Client):
    with _RUN_LOCK:
        dead, cover = analyze.DEAD_STOCK_DAYS, analyze.LOW_COVER_DAYS
        analyze.DEAD_STOCK_DAYS = client.dead_stock_days
        analyze.LOW_COVER_DAYS = client.low_cover_days
        try:
            yield
        finally:
            analyze.DEAD_STOCK_DAYS, analyze.LOW_COVER_DAYS = dead, cover


#: Platform images (trade backdrops, the landing hero). Served from disk rather
#: than inlined: the browser caches them, and the *client* dashboard still never
#: references them — that file stays self-contained, and a test enforces it.
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"),
          name="static")

#: Reachable without a session. Everything else is closed by the middleware
#: below, so a new route is private by default — the safe direction to forget in.
PUBLIC = {"/", "/login", "/signup", "/logout"}

#: Prefixes open to anyone holding the URL. ``/w/`` is a shared workspace link,
#: which carries its own PIN check; ``/static/`` is decoration.
PUBLIC_PREFIXES = ("/static/", "/w/")


@app.middleware("http")
async def require_login(request: Request, call_next):
    """One gate for the whole app.

    Guarding each route by hand means a route added later is public until
    somebody remembers. Here the default is the other way round: unknown path,
    no session, no entry.
    """
    path = request.url.path
    request.state.principal = principal = auth.current(request)
    # Kept for the many handlers that only ever deal with a logged-in account.
    request.state.account = principal
    if principal is None and path not in PUBLIC \
            and not path.startswith(PUBLIC_PREFIXES):
        return RedirectResponse("/login", status_code=303)
    return await call_next(request)


def _acct(request: Request) -> auth.Account:
    """The logged-in account. Only ever called on a route the middleware closed,
    so it cannot be None by the time a handler runs."""
    return request.state.account


def _redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=303)


def _flash(request: Request) -> tuple[str, str]:
    return request.query_params.get("m", ""), request.query_params.get("k", "ok")


def _msg(text: str) -> str:
    return text.replace(" ", "+").replace("&", "and")


# ------------------------------------------------------------------- portfolio

def _tenant_client(account) -> store.Client | None:
    """The single business a tenant account owns, or None if not set up yet.

    Deliberately strict: no falling back to "whatever client exists". An account
    that has not named its own business must show setup, never adopt a record
    that might belong to somebody else.
    """
    if not account.tenant_slug:
        return None
    return store.get_client(account.tenant_slug, account.id)


def _deny_not_master(account) -> RedirectResponse | None:
    """The support console is Vyuha staff only."""
    if not getattr(account, "is_master", False):
        return _redirect("/?m=That+is+not+part+of+your+workspace.&k=bad")
    return None


def _client_for(account, slug: str) -> store.Client | None:
    """Resolve a client for whoever is asking.

    Everybody sees only what they own. A master sees any workspace, because the
    whole point of the role is fixing a client's dashboard while they are on the
    phone — and **every one of those reads is written to that client's own
    activity trail**, so support access is visible to the account it touched
    rather than being a silent back door.
    """
    if getattr(account, "is_master", False):
        client = store.find_client(slug)
        if client is not None and client.owner_id != account.id:
            ledger.log("master.viewed", f"Vyuha support opened {client.name}",
                       client=client, channel="settings", master=account.username)
        return client
    return store.get_client(slug, account.id)


def _deny_guest(account) -> RedirectResponse | None:
    """Deployment credentials are the operator's, not the guest's.

    A shared-link guest is the owner of *their* business, not of this install,
    so the WhatsApp/SMTP/Claude keys are none of their business — and letting
    them overwrite the keys would break every other client's sends.
    """
    if getattr(account, "is_guest", False):
        return _redirect("/?m=That+is+not+part+of+your+workspace.&k=bad")
    return None


def _deny_tenant(account) -> RedirectResponse | None:
    """Operator-only routes. A tenant must never reach portfolio machinery."""
    if account.is_tenant:
        return _redirect("/?m=That+is+not+part+of+your+workspace.&k=bad")
    return None


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    """The front door, which is two different doors.

    Signed out it is the public landing page — the thing you send a prospect.
    Signed in it is the workspace, in whichever of its two shapes this account
    chose.
    """
    account = request.state.account
    if account is None:
        return ui.landing()
    if account.is_master:
        return _redirect("/master")

    msg, kind = _flash(request)

    # Nothing chosen yet — the workspace fork happens before anything else.
    if not account.configured:
        return ui.choose_install(account)

    if account.is_tenant:
        client = _tenant_client(account)
        if client is None:
            return ui.tenant_setup(account)
        return _redirect(f"/c/{client.slug}")

    clients = store.load_clients(account.id)
    return ui.home(clients, account, ledger.read(account.id, limit=8),
                   ledger.counts(account.id), flash=msg, flash_kind=kind)


# -------------------------------------------------------------- master console

@app.get("/master", response_class=HTMLResponse)
def master_console(request: Request, q: str = "", account: auth.Account = Depends(_acct)):
    denied = _deny_not_master(account)
    if denied:
        return denied

    clients = store.all_clients()
    if q:
        needle = q.lower()
        clients = [c for c in clients
                   if needle in c.name.lower() or needle in c.slug.lower()]

    # Group by the account that owns them, so the console reads as "who is on
    # this install and how are they doing" rather than one flat list.
    accounts = {a.id: a for a in auth._load_all()}
    invites = {i.slug: i for i in auth._load_invites() if not i.revoked}
    return ui.master(clients, accounts, invites, account,
                     ledger.read_all(limit=40), q, *_flash(request))


# ------------------------------------------------------------------------ auth

@app.get("/signup", response_class=HTMLResponse)
def signup_form(request: Request):
    if request.state.account is not None:
        return _redirect("/")
    return ui.signup()


@app.post("/signup")
def signup_submit(request: Request, name: str = Form(""), email: str = Form(...),
                  password: str = Form(...)):
    try:
        account = auth.create(email, name, password)
    except auth.SignupError as exc:
        return HTMLResponse(ui.signup(flash=str(exc), email=email, name=name))

    ledger.log("account.created", f"{account.email} signed up", owner=account.id,
               channel="settings")
    resp = _redirect("/")
    _set_session(resp, request, account)
    return resp


@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request, master: str = ""):
    if request.state.account is not None:
        return _redirect("/")
    return ui.login(master=bool(master))


@app.post("/login")
def login_submit(request: Request, email: str = Form(...),
                 password: str = Form(...), master: str = Form("")):
    is_master_form = bool(master)
    account = auth.verify(email, password)
    if account is None:
        # One message for both causes: which half was wrong is not the visitor's
        # business to learn, and saying so enumerates who has an account.
        note = ("That username and password do not match." if is_master_form
                else "That email and password do not match.")
        return HTMLResponse(ui.login(flash=note, email=email, master=is_master_form))

    # A customer account cannot be smuggled in through the staff door, and staff
    # are sent to their own console rather than a portfolio they do not have.
    if is_master_form and not account.is_master:
        return HTMLResponse(ui.login(flash="That is not a master account.",
                                     email=email, master=True))

    ledger.log("account.login",
               f"{account.username or account.email} signed in"
               + (" (master)" if account.is_master else ""),
               owner=account.id, channel="settings")
    resp = _redirect("/master" if account.is_master else "/")
    _set_session(resp, request, account)
    return resp


@app.post("/logout")
def logout():
    resp = _redirect("/")
    resp.delete_cookie(auth.COOKIE, path="/")
    return resp


# ------------------------------------------------- shared workspace (link+PIN)

@app.get("/w/{token}", response_class=HTMLResponse)
def shared_open(token: str, request: Request):
    """A workspace link, as sent over WhatsApp.

    Two halves make one key: the token, which nobody can guess, and a four-digit
    PIN, which makes a forwarded message harmless. Once both are given the device
    is remembered, so the owner taps the link and is simply *in* from then on.
    """
    invite = auth.get_invite(token)
    if invite is None:
        return HTMLResponse(ui.link_dead())

    principal = request.state.principal
    if getattr(principal, "is_guest", False) and principal.token == token:
        return _redirect(f"/c/{invite.slug}")
    if invite.locked:
        return HTMLResponse(ui.pin_gate(
            invite, flash=f"Too many wrong PINs. Try again in "
                          f"{invite.locked_for} minutes."))
    return HTMLResponse(ui.pin_gate(invite))


@app.post("/w/{token}")
def shared_unlock(token: str, request: Request, pin: str = Form(...)):
    invite = auth.get_invite(token)
    if invite is None:
        return HTMLResponse(ui.link_dead())

    if not auth.check_pin(invite, pin):
        # Say which it was. Somebody who mistyped deserves to know they must
        # wait, rather than keep guessing at a PIN that is now refused anyway.
        if invite.locked:
            ledger.log("share.locked",
                       f"{invite.org_name}: too many wrong PINs, link paused",
                       client=invite.slug, owner=invite.owner_id, channel="whatsapp")
            note = (f"Too many wrong PINs. Try again in {invite.locked_for} minutes, "
                    "or ask for a new link.")
        else:
            note = "That PIN is not right."
        return HTMLResponse(ui.pin_gate(invite, flash=note))

    ledger.log("share.opened", f"{invite.org_name} opened their workspace",
               client=invite.slug, owner=invite.owner_id, channel="whatsapp")
    resp = _redirect(f"/c/{invite.slug}")
    _set_cookie(resp, request, auth.issue_guest(invite))
    return resp


@app.post("/c/{slug}/share")
def share_create(slug: str, request: Request,
                 account: auth.Account = Depends(_acct)):
    """Mint the link and PIN for a client. Operator-only, by definition."""
    denied = _deny_tenant(account)
    if denied:
        return denied
    client = _client_for(account, slug)
    if client is None:
        return _redirect("/?m=That+client+no+longer+exists.&k=bad")

    invite, pin = auth.create_invite(slug, client.owner_id, client.name)
    ledger.log("share.created", f"Workspace link issued for {client.name}",
               client=client, channel="whatsapp")
    # The PIN is shown exactly once, here, because it is not stored in clear.
    return _redirect(f"/c/{slug}/setup?pin={pin}&m={_msg('Link ready. Send it with the PIN.')}")


@app.post("/c/{slug}/share/revoke")
def share_revoke(slug: str, account: auth.Account = Depends(_acct)):
    denied = _deny_tenant(account)
    if denied:
        return denied
    client = _client_for(account, slug)
    if client is None:
        return _redirect("/?m=That+client+no+longer+exists.&k=bad")
    auth.revoke_invite(slug)
    ledger.log("share.revoked", f"Workspace link revoked for {client.name}",
               client=client)
    return _redirect(f"/c/{slug}/setup?m=Link+revoked.")


def _over_https(request: Request) -> bool:
    """Whether this request actually arrived over TLS.

    Checked per request rather than configured, because the same build serves
    plain localhost during development and HTTPS in front of a proxy. The
    forwarded header is what a reverse proxy sets; the scheme covers the case
    where uvicorn terminates TLS itself.
    """
    forwarded = request.headers.get("x-forwarded-proto", "").split(",")[0].strip()
    return (forwarded or request.url.scheme) == "https"


def _set_cookie(resp, request: Request, value: str) -> None:
    """httponly so script cannot read it; samesite=lax so a form post from
    another site cannot ride along; secure whenever the connection can carry it.

    ``secure`` is deliberately conditional: setting it unconditionally would
    mean the cookie is never stored over plain localhost, and a session that
    never persists is worse than one that does.
    """
    resp.set_cookie(auth.COOKIE, value, max_age=auth.MAX_AGE, httponly=True,
                    samesite="lax", secure=_over_https(request), path="/")


def _set_session(resp, request: Request, account) -> None:
    _set_cookie(resp, request, auth.issue(account))


@app.post("/install")
def install_choose(request: Request, install: str = Form(...)):
    account = request.state.account
    account.install = "tenant" if install == "tenant" else "operator"
    auth.update(account)
    ledger.log("settings.changed", f"Workspace set up as {account.install}",
               owner=account.id, channel="settings")
    return _redirect("/")


@app.get("/onboard", response_class=HTMLResponse)
def onboard_form(request: Request, account: auth.Account = Depends(_acct)):
    denied = _deny_tenant(account)
    if denied:
        return denied
    return ui.onboard(config.load(), account, *_flash(request))


@app.post("/onboard")
def onboard_submit(name: str = Form(...), phone: str = Form(""),
                   data_mode: str = Form("upload"), trade: str = Form(""),
                   account: auth.Account = Depends(_acct)):
    """Minimal by design: a name, a number, and how their data arrives."""
    settings = config.load()
    denied = _deny_tenant(account)
    if denied:
        return denied
    client = store.add_client(account.id,
                              name=name.strip(), phone=channels.normalise_phone(phone),
                              data_mode=data_mode if data_mode in ("upload", "books") else "upload",
                              trade=trade or theme.guess(name))
    ledger.log("client.onboarded", f"{client.name} onboarded", client=client,
               channel="whatsapp" if client.phone else "")

    if client.phone:
        result = whatsapp.send_test(settings, client.phone)
        if result.ok:
            ledger.log("alert.sent", f"Connection test delivered to {client.name}",
                       client=client, channel="whatsapp", provider=result.provider)
            return _redirect(f"/c/{client.slug}?m={_msg('Workspace created and a test message was sent.')}")
        ledger.log("alert.send_failed", f"Connection test not sent: {result.detail}",
                   client=client, channel="whatsapp")
        return _redirect(f"/c/{client.slug}/today?m={_msg('Workspace created. ' + result.needs_action)}&k=bad")

    return _redirect(f"/c/{client.slug}?m={_msg('Workspace created. Drop their data in.')}")


@app.get("/setup", response_class=HTMLResponse)
def tenant_setup_form(account: auth.Account = Depends(_acct)):
    if not account.is_tenant:
        return _redirect("/")
    return ui.tenant_setup(account)


@app.post("/setup")
def tenant_setup_submit(name: str = Form(...), trade: str = Form(""),
                        data_mode: str = Form("books"), account: auth.Account = Depends(_acct)):
    """A tenant sets up their own operation — never a client list."""
    if not account.is_tenant:
        return _redirect("/")

    client = store.add_client(
        account.id,
        name=name.strip(), trade=trade or theme.guess(name),
        data_mode=data_mode if data_mode in ("upload", "books") else "books")
    account.org_name = client.name
    account.tenant_slug = client.slug
    auth.update(account)
    ledger.log("client.onboarded", f"{client.name} set up their workspace", client=client)
    return _redirect(f"/c/{client.slug}?m={_msg('Welcome. Add your first entry.')}")


# ------------------------------------------------------------------- workspace

@app.get("/c/{slug}/cover")
def cover(slug: str, account: auth.Account = Depends(_acct)):
    path = store.covers_dir() / f"{slug}.img"
    if not path.exists():
        return _redirect(f"/c/{slug}")
    return FileResponse(path)


@app.post("/c/{slug}/cover")
def cover_upload(slug: str, file: UploadFile = File(...), account: auth.Account = Depends(_acct)):
    client = _client_for(account, slug)
    if client is None:
        return _redirect("/?m=That+client+no+longer+exists.&k=bad")
    if not (file.content_type or "").startswith("image/"):
        return _redirect(f"/c/{slug}?m=That+is+not+an+image.&k=bad")

    target = store.covers_dir() / f"{slug}.img"
    with target.open("wb") as fh:
        shutil.copyfileobj(file.file, fh)
    client.has_cover = True
    store.update_client(client)
    ledger.log("settings.changed", f"Cover photo set for {client.name}", client=client)
    return _redirect(f"/c/{slug}?m=Photo+updated.")


@app.get("/c/{slug}", response_class=HTMLResponse)
def client_page(slug: str, request: Request, account: auth.Account = Depends(_acct)):
    """The workspace root.

    This used to render an 85KB page with five sections, sixty-six buttons and
    the entry form, most of which the console already did better. It is now the
    front door and nothing else — every screen has its own URL.
    """
    client, bail = _console_client(account, slug)
    if bail is not None:
        return bail
    if account.is_master and client.owner_id != account.id:
        ledger.log("master.viewed", f"Vyuha staff opened {client.name}",
                   client=client, channel="support")
    msg, kind = _flash(request)
    return _render(client, account, "today", flash=msg, flash_kind=kind)


# ---------------------------------------------------------------- manual books

@app.post("/c/{slug}/book/item")
def book_add_item(slug: str, name: str = Form(...), category: str = Form("Other"),
                  unit: str = Form("piece"), rate: str = Form("0"), cost: str = Form("0"),
                  stock_qty: str = Form("0"), reorder_level: str = Form("0"),
                  account: auth.Account = Depends(_acct)):
    client = _client_for(account, slug)
    if client is None:
        return _redirect("/?m=That+client+no+longer+exists.&k=bad")
    _, note = books.add_item(slug, name, category, unit, rate, cost, stock_qty, reorder_level)
    ledger.log("source.received", note, client=client, channel="manual")
    _rebuild_from_book(client)
    return _redirect(f"/c/{slug}/sell?m={_msg(note)}")


@app.post("/c/{slug}/book/sale")
def book_add_sale(slug: str, sku: str = Form(...), party: str = Form(""),
                  qty: str = Form("1"), rate: str = Form(""), when: str = Form(""),
                  payment: str = Form("paid"), due_date: str = Form(""),
                  party_phone: str = Form(""), send_receipt: str = Form(""),
                  account: auth.Account = Depends(_acct)):
    client = _client_for(account, slug)
    if client is None:
        return _redirect("/?m=That+client+no+longer+exists.&k=bad")
    phone = channels.normalise_phone(party_phone)
    book, note, ok = books.record_sale(slug, sku, party, qty, rate, when,
                                       paid=(payment == "paid"), due_date=due_date,
                                       party_phone=phone)
    if not ok:
        return _redirect(f"/c/{slug}/sell?m={_msg(note)}&k=bad")
    ledger.log("source.received", note, client=client, channel="manual")
    _rebuild_from_book(client)

    # The buyer's number is only ever to hand at this moment, so the receipt
    # goes out now or realistically never.
    if phone and send_receipt and book.sales:
        note += " " + _send_receipt(client, book.sales[-1])
    return _redirect(f"/c/{slug}/sell?m={_msg(note)}")


def _send_receipt(client: store.Client, sale) -> str:
    """Deliver a bill to the buyer, and say plainly whether it left the machine."""
    settings = config.load()
    text = channels.as_receipt(client.name, sale)
    result = whatsapp.send(settings, sale.party_phone, text)

    ledger.log("receipt.sent" if result.ok else "receipt.failed",
               f"Receipt for {sale.id} to {sale.party}: {result.detail}",
               client=client, channel="whatsapp", provider=result.provider,
               bill=sale.id)
    if result.ok:
        books.mark_receipt_sent(client.slug, sale.id)
        return f"Receipt sent to {sale.party}."
    return result.needs_action or result.detail


@app.post("/c/{slug}/book/sale/{sale_id}/receipt")
def book_send_receipt(slug: str, sale_id: str,
                      account: auth.Account = Depends(_acct)):
    client = _client_for(account, slug)
    if client is None:
        return _redirect("/?m=That+client+no+longer+exists.&k=bad")
    sale = books.load(slug).sale(sale_id)
    if sale is None:
        return _redirect(f"/c/{slug}/sell?m=That+bill+is+gone.&k=bad")
    if not sale.party_phone:
        return _redirect(f"/c/{slug}/sell?m="
                         f"{_msg('No number was taken for ' + sale.party + '.')}&k=bad")
    return _redirect(f"/c/{slug}/sell?m={_msg(_send_receipt(client, sale))}")


@app.post("/c/{slug}/book/sale/{sale_id}/delete")
def book_delete_sale(slug: str, sale_id: str, account: auth.Account = Depends(_acct)):
    client = _client_for(account, slug)
    if client is None:
        return _redirect("/?m=That+client+no+longer+exists.&k=bad")
    _, note = books.delete_sale(slug, sale_id)
    ledger.log("settings.changed", note, client=client, channel="manual")
    _rebuild_from_book(client)
    return _redirect(f"/c/{slug}/sell?m={_msg(note)}")


@app.post("/c/{slug}/book/sale/{sale_id}/paid")
def book_mark_paid(slug: str, sale_id: str, account: auth.Account = Depends(_acct)):
    client = _client_for(account, slug)
    if client is None:
        return _redirect("/?m=That+client+no+longer+exists.&k=bad")
    _, note = books.mark_paid(slug, sale_id)
    ledger.log("settings.changed", note, client=client, channel="manual")
    _rebuild_from_book(client)
    return _redirect(f"/c/{slug}/sell?m={_msg(note)}")


@app.post("/c/{slug}/book/item/{sku}/delete")
def book_delete_item(slug: str, sku: str, account: auth.Account = Depends(_acct)):
    client = _client_for(account, slug)
    if client is None:
        return _redirect("/?m=That+client+no+longer+exists.&k=bad")
    _, note = books.delete_item(slug, sku)
    ledger.log("settings.changed", note, client=client, channel="manual")
    _rebuild_from_book(client)
    return _redirect(f"/c/{slug}/sell?m={_msg(note)}")


def _rebuild_from_book(client: store.Client) -> None:
    """Re-run the engine over the typed-in ledger after every edit.

    A manual entry is worth nothing to the owner until the dashboard reflects
    it, and the ledger is small enough that a full re-run is instant. Failures
    are logged, never raised — a bad entry must not break the entry screen.
    """
    book = books.load(client.slug)
    if not book.sales and not book.items:
        return
    try:
        workbook = books.to_workbook(book, store.upload_dir(client.slug) / "books.xlsx")
        run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
        with _thresholds(client):
            result = pipeline.run(workbook)
            out = store.dashboard_dir(client.slug) / f"{run_id}.html"
            pipeline.write_report(result, out, client=client.name)
    except Exception as exc:                       # noqa: BLE001
        ledger.log("run.failed", f"Books rebuild failed: {exc}", client=client,
                   channel="manual")
        return

    ins = result.insights
    run = store.Run(
        id=run_id, filename="books.xlsx",
        uploaded_at=datetime.now().isoformat(timespec="seconds"),
        source_kind="manual", source_method="Typed in directly", confidence="high",
        dashboard=f"{client.slug}/{run_id}.html",
        sheets_read=[t.kind.title() for t in result.tables],
        alerts=[{"code": a.code, "severity": a.severity, "title": a.title,
                 "detail": a.detail, "entities": list(a.entities)}
                for a in channels.ordered(ins)],
        alert_count=len(ins.alerts),
        critical_count=sum(1 for a in ins.alerts if a.severity == "critical"),
        revenue=float(ins.sales.get("revenue") or 0),
        stock_value=float(ins.stock.get("value") or 0),
        outstanding=float(ins.receivables.get("total") or 0),
    )
    # One rolling run for a manual book — the ledger is the history, not the runs.
    client = store.get_client(client.slug, client.owner_id)
    client.runs = [run]
    store.update_client(client)


@app.post("/c/{slug}/delete")
def client_delete(slug: str, account: auth.Account = Depends(_acct)):
    denied = _deny_guest(account)
    if denied:
        return denied
    client = _client_for(account, slug)
    name = client.name if client else slug
    shutil.rmtree(store.UPLOADS / slug, ignore_errors=True)
    shutil.rmtree(store.DASHBOARDS / slug, ignore_errors=True)
    store.delete_client(slug, client.owner_id)
    ledger.log("client.deleted", f"{name} was deleted", client=slug,
               owner=account.id)
    return _redirect("/?m=Client+deleted.")


@app.post("/c/{slug}/contact")
def client_contact(slug: str, contact: str = Form(""), phone: str = Form(""),
                   email: str = Form(""), industry: str = Form(""),
                   dead_stock_days: int = Form(90), low_cover_days: int = Form(14),
                   account: auth.Account = Depends(_acct)):
    """Details are optional and filled in later, never demanded at onboarding."""
    client = _client_for(account, slug)
    if client is None:
        return _redirect("/?m=That+client+no+longer+exists.&k=bad")
    client.contact = contact.strip()
    client.phone = channels.normalise_phone(phone)
    client.email = email.strip()
    client.industry = industry.strip()
    client.dead_stock_days = max(7, min(730, dead_stock_days))
    client.low_cover_days = max(1, min(120, low_cover_days))
    store.update_client(client)
    ledger.log("settings.changed", f"Details updated for {client.name}", client=client)
    return _redirect(f"/c/{slug}/setup?m=Saved.")


# ------------------------------------------------------------------- ingestion

def _reload_insights(client: store.Client, run: store.Run, settings):
    """Rebuild Insights from the stored upload.

    Alerts are cached on the Run for display, but the WhatsApp/email/export
    renderers want the whole object. Re-reading keeps exactly one source of
    truth — the file the client sent — at the cost of a second or two.
    """
    source = store.upload_dir(client.slug) / (run.converted or run.filename)
    if not source.exists():
        return None
    try:
        with _thresholds(client):
            return pipeline.run(source).insights
    except Exception:
        return None


def _ingest(client: store.Client, paths: list[Path], label: str) -> tuple[store.Run, str]:
    """Read a pile of files as one dataset and write one run.

    Everything goes through ``library.batch``, which reconciles them: sales
    accumulate, stock is a snapshot where the newest wins, duplicates are
    dropped before anything is summed. Reading them one at a time and keeping
    the last — which is what this route used to do — reported whichever file
    happened to be dropped last as though it were the whole business.
    """
    settings = config.load()
    catalogue = books.load(client.slug).items
    workdir = store.upload_dir(client.slug)

    with _thresholds(client):
        result = library.batch(
            paths, workdir, settings,
            item_names=[i.name for i in catalogue],
            rates={i.name: i.rate for i in catalogue},
            label=label)

    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    ins = result.insights
    first_ok = next((f for f in result.files if f.ok), None)

    run = store.Run(
        id=run_id,
        filename=(label if len(paths) != 1 else paths[0].name),
        uploaded_at=datetime.now().isoformat(timespec="seconds"),
        source_kind=(first_ok.kind if first_ok else "native"),
        source_method=(first_ok.method if first_ok else ""),
        confidence=("high" if result.rejected == 0 else "medium"),
        source_notes=list(result.notes) + [
            f"{f.name}: {f.error}" for f in result.files if not f.ok][:12],
        sheets_read=sorted({t.kind.title() for t in result.tables}),
        sheets_skipped=[f.name for f in result.files if not f.ok][:12],
    )

    if not result.tables:
        # No run. A run is a record of data, and nothing was read — leaving a
        # failed run behind would put an empty dashboard at the top of the
        # history and make the workspace look like it holds numbers it does not.
        # The rejection reaches the operator through the flash and the ledger.
        why = ("Nothing readable in "
               + ("that file." if len(paths) == 1 else f"any of {len(paths)} files."))
        detail = next((f"{f.name}: {f.error}"
                       + (f" {f.needs_action}" if f.needs_action else "")
                       for f in result.files if not f.ok), "")
        ledger.log("source.rejected", detail or why, client=client, channel="upload")
        run.status = "failed"
        run.error = why
        return run, (detail or why)

    out = store.dashboard_dir(client.slug) / f"{run_id}.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report.render(ins, client=client.name), encoding="utf-8")

    run.dashboard = f"{client.slug}/{run_id}.html"
    run.alerts = [{"code": a.code, "severity": a.severity, "title": a.title,
                   "detail": a.detail, "entities": list(a.entities)}
                  for a in channels.ordered(ins)]
    run.alert_count = len(ins.alerts)
    run.critical_count = sum(1 for a in ins.alerts if a.severity == "critical")
    run.revenue = float(ins.sales.get("revenue") or 0)
    run.stock_value = float(ins.stock.get("value") or 0)
    run.outstanding = float(ins.receivables.get("total") or 0)
    store.add_run(client.slug, client.owner_id, run)

    ledger.log("run.completed",
               f"{result.read} of {len(result.files)} file(s) read — "
               f"{result.rows:,} row(s)", client=client, channel="upload",
               duplicates=result.duplicates_dropped, alerts=run.alert_count)

    note = (f"Read {result.read} of {len(result.files)} file(s), "
            f"{result.rows:,} row(s).")
    if result.duplicates_dropped:
        note += f" {result.duplicates_dropped} duplicate row(s) counted once."
    if result.rejected:
        note += f" {result.rejected} could not be read — see below."
    return run, note


@app.post("/c/{slug}/upload")
async def upload(slug: str, request: Request, account: auth.Account = Depends(_acct)):
    """Take as many files as somebody selected, and read them together.

    Declared with the raw form rather than ``List[UploadFile]`` so a browser
    that posts a single file and one that posts ninety both arrive the same way.
    """
    client, bail = _console_client(account, slug)
    if bail is not None:
        return bail

    form = await request.form()
    uploads = [u for u in form.getlist("file") if getattr(u, "filename", "")]
    if not uploads:
        return _console_back(slug, "data", "Pick at least one file.")

    folder = store.upload_dir(slug)
    folder.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []
    for upload_file in uploads:
        name = Path(upload_file.filename or "upload").name
        target = folder / name
        with target.open("wb") as fh:
            shutil.copyfileobj(upload_file.file, fh)
        saved.append(target)

    ledger.log("source.received", f"{len(saved)} file(s) received", client=client,
               channel="upload", files=[p.name for p in saved][:20])
    _run, note = _ingest(client, saved,
                         label=(saved[0].name if len(saved) == 1
                                else f"{len(saved)} files"))
    return _console_back(slug, "data", note)


@app.post("/c/{slug}/folder")
def read_folder(slug: str, path: str = Form(""), recursive: str = Form("1"),
                account: auth.Account = Depends(_acct)):
    """Read a folder already on this machine.

    The honest answer to "the data is already on my computer" — nobody wants to
    select ninety files in a dialog. Only reachable by a signed-in operator, and
    it reads rather than copies, so nothing is moved out from under them.
    """
    client, bail = _console_client(account, slug)
    if bail is not None:
        return bail
    if account.is_guest:
        return _console_back(slug, "data", "Shared links cannot read folders.")

    found, notes = library.scan(Path(path.strip()), recursive=bool(recursive))
    if not found:
        return _console_back(slug, "data", " ".join(notes) or "Nothing readable there.")

    ledger.log("source.received", f"Folder read: {len(found)} file(s) from {path}",
               client=client, channel="folder")
    _run, note = _ingest(client, found, label=f"{len(found)} files from {Path(path).name}")
    return _console_back(slug, "data", " ".join(notes + [note]))


@app.get("/c/{slug}/dashboard")
def dashboard(slug: str, account: auth.Account = Depends(_acct)):
    client = _client_for(account, slug)
    if client is None or not client.latest or not client.latest.dashboard:
        return _redirect(f"/c/{slug}?m=No+dashboard+yet.&k=bad")
    path = store.DASHBOARDS / client.latest.dashboard
    if not path.exists():
        return _redirect(f"/c/{slug}?m=That+dashboard+file+is+missing.&k=bad")
    return FileResponse(path, media_type="text/html")


# --------------------------------------------------------------------- exports

@app.get("/c/{slug}/export/{fmt}")
def export(slug: str, fmt: str, account: auth.Account = Depends(_acct)):
    client = _client_for(account, slug)
    if client is None or not client.latest or client.latest.status != "ok":
        return _redirect(f"/c/{slug}?m=Nothing+to+export+yet.&k=bad")

    settings = config.load()
    insights = _reload_insights(client, client.latest, settings)
    if insights is None:
        return _redirect(f"/c/{slug}?m=Could+not+rebuild+that+run.&k=bad")

    out_dir = store.dashboard_dir(slug)
    stamp = client.latest.id
    try:
        if fmt == "pdf":
            path = exports.to_pdf(insights, client.name, out_dir / f"{stamp}.pdf")
            media = "application/pdf"
        elif fmt == "pptx":
            path = exports.to_pptx(insights, client.name, out_dir / f"{stamp}.pptx")
            media = ("application/vnd.openxmlformats-officedocument"
                     ".presentationml.presentation")
        elif fmt == "html":
            path = store.DASHBOARDS / client.latest.dashboard
            media = "text/html"
        else:
            return _redirect(f"/c/{slug}?m=Unknown+export+format.&k=bad")
    except Exception as exc:                       # noqa: BLE001
        traceback.print_exc()
        return _redirect(f"/c/{slug}?m={_msg(f'Export failed: {exc}')}&k=bad")

    ledger.log("export.created", f"{fmt.upper()} generated for {client.name}",
               client=client, channel=fmt)
    filename = f"{store.slugify(client.name)}-brief.{fmt if fmt != 'html' else 'html'}"
    return FileResponse(path, media_type=media, filename=filename)


@app.post("/c/{slug}/email")
def email_send(slug: str, subject: str = Form(...), body: str = Form(...),
               account: auth.Account = Depends(_acct)):
    client = _client_for(account, slug)
    if client is None:
        return _redirect("/?m=That+client+no+longer+exists.&k=bad")

    settings = config.load()
    attachments = []
    if client.latest and client.latest.dashboard:
        attachments.append(store.DASHBOARDS / client.latest.dashboard)

    ok, detail = exports.send_email(settings, client.email, subject, body, attachments)
    ledger.log("alert.sent" if ok else "alert.send_failed",
               f"Email to {client.name}: {detail}", client=client, channel="email")
    return _redirect(f"/c/{slug}/today?m={_msg(detail)}&k={'ok' if ok else 'bad'}")


@app.post("/c/{slug}/whatsapp")
def whatsapp_send(slug: str, text: str = Form(...), account: auth.Account = Depends(_acct)):
    client = _client_for(account, slug)
    if client is None:
        return _redirect("/?m=That+client+no+longer+exists.&k=bad")

    settings = config.load()
    result = whatsapp.send(settings, client.phone, text)
    ledger.log("alert.sent" if result.ok else "alert.send_failed",
               f"WhatsApp to {client.name}: {result.detail}", client=client,
               channel="whatsapp", provider=result.provider)
    note = result.detail + (" " + result.needs_action if result.needs_action else "")
    return _redirect(f"/c/{slug}/today?m={_msg(note)}&k={'ok' if result.ok else 'bad'}")


# -------------------------------------------------------------------- activity

@app.get("/activity", response_class=HTMLResponse)
def activity(request: Request, client: str = "", kind: str = "",
             account: auth.Account = Depends(_acct)):
    kinds = {kind} if kind else None
    return ui.activity(ledger.read(account.id, limit=300, client=client, kinds=kinds),
                       ledger.counts(account.id), store.load_clients(account.id),
                       client, kind, account)


# -------------------------------------------------------------------- settings

@app.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request, account: auth.Account = Depends(_acct)):
    denied = _deny_guest(account)
    if denied:
        return denied
    return ui.settings(config.load(), account, *_flash(request))


@app.post("/settings/test-whatsapp")
def settings_test_whatsapp(to: str = Form(...),
                           account: auth.Account = Depends(_acct)):
    """Prove the credentials work, against a real number, before a client sees it.

    Reports whatever the provider actually said. A test that quietly succeeds
    when nothing was delivered is worse than no test, so a link-only fallback is
    reported as *not sent* even though a usable link comes back with it.
    """
    denied = _deny_guest(account)
    if denied:
        return denied

    settings = config.load()
    result = whatsapp.send_test(settings, to)
    ledger.log("alert.sent" if result.ok else "alert.send_failed",
               f"Connection test via {result.provider}: {result.detail}",
               owner=account.id, channel="whatsapp", provider=result.provider)

    note = result.detail + (" " + result.needs_action if result.needs_action else "")
    return _redirect(f"/settings?m={_msg(note)}&k={'ok' if result.ok else 'bad'}")


@app.post("/password")
def password_change(request: Request, current_password: str = Form(...),
                    new_password: str = Form(...),
                    account: auth.Account = Depends(_acct)):
    """A guest has no password to change — their key is the link and the PIN."""
    denied = _deny_guest(account)
    if denied:
        return denied
    try:
        auth.change_password(account, current_password, new_password)
    except auth.SignupError as exc:
        return _redirect(f"/settings?m={_msg(str(exc))}&k=bad")

    ledger.log("account.password", "Password changed", owner=account.id,
               channel="settings")
    # Changing the salt invalidates nothing on its own — the session is signed
    # over the account id — so re-issue deliberately, which is also what makes
    # "change my password" a usable answer to "I think somebody has my laptop".
    resp = _redirect("/settings?m=Password+changed.")
    _set_session(resp, request, account)
    return resp


@app.post("/settings")
def settings_save(
    mode: str = Form("agency"),
    whatsapp_provider: str = Form("link"),
    meta_token: str = Form(""), meta_phone_number_id: str = Form(""),
    meta_template: str = Form(""),
    twilio_sid: str = Form(""), twilio_token: str = Form(""), twilio_from: str = Form(""),
    anthropic_key: str = Form(""),
    smtp_host: str = Form(""), smtp_port: int = Form(587),
    smtp_user: str = Form(""), smtp_password: str = Form(""), smtp_from: str = Form(""),
    account: auth.Account = Depends(_acct),
):
    denied = _deny_guest(account)
    if denied:
        return denied
    current = config.load()
    current.whatsapp_provider = whatsapp_provider
    current.meta_phone_number_id = meta_phone_number_id.strip()
    current.meta_template = meta_template.strip()
    current.twilio_sid = twilio_sid.strip()
    current.twilio_from = twilio_from.strip() or current.twilio_from
    current.smtp_host = smtp_host.strip()
    current.smtp_port = smtp_port
    current.smtp_user = smtp_user.strip()
    current.smtp_from = smtp_from.strip()

    # A blank secret means "leave it alone" — the form only ever shows a mask.
    for field_name, value in (("meta_token", meta_token), ("twilio_token", twilio_token),
                              ("anthropic_key", anthropic_key),
                              ("smtp_password", smtp_password)):
        if value.strip():
            setattr(current, field_name, value.strip())

    config.save(current)
    ledger.log("settings.changed", "Platform settings updated", owner=account.id,
               channel="settings")
    return _redirect("/settings?m=Settings+saved.")


# =====================================================================
# ---- vishak · the console: stock, ask, follow-ups, money, deck, people
#
# Six features, one page (see console.py for why). Routes only — every one of
# these is a thin shell over a module that holds the actual logic, so this
# block stays readable no matter how much the console grows.
#
# Two conventions worth keeping:
#   * Mutations redirect back with ?panel= so the page reopens where it was.
#   * Reads that produce something transient (an answer, a deck outline) render
#     the page directly instead, because a redirect would throw the result away.
# =====================================================================

def _console_state(client: store.Client) -> dict:
    """Everything the console page needs, loaded once.

    ``purse``, not ``ledger``: this module already imports the *activity*
    ledger under that name, and shadowing it here would silently break event
    logging in whichever handler did it.
    """
    book = books.load(client.slug)
    purse = money.load(client.slug)
    org = people.load(client.slug)
    return {
        "book": book,
        "ledger": purse,
        "org": org,
        "queue": followup.queue(client.slug, book),
        "invoices": invoice.load_all(client.slug),
        "settings": config.load(),
    }


#: Where each kind of action lands afterwards. The old console had one URL and
#: a ?panel= query; now every screen has its own address, so a form has to say
#: which one it belongs to rather than which tab to reopen.
_AFTER = {
    "stock": "stock", "money": "money", "bills": "sell", "sell": "sell",
    "followups": "today", "people": "setup", "setup": "setup",
    "deck": "today", "ask": "today", "data": "data", "today": "today",
}


def _console_back(slug: str, panel: str, note: str = "") -> RedirectResponse:
    """Back to the screen this action belongs to, with a word about what happened."""
    view = _AFTER.get(panel, "today")
    tail = f"?m={_msg(note)}" if note else ""
    return _redirect(f"/c/{slug}/{view}{tail}")


def _console_client(account, slug: str):
    """Resolve and authorise in one step — every handler below starts with it.

    Returns the client, or the redirect to send instead. A tenant reaching for
    somebody else's slug gets the same answer a typo gets, so a URL cannot be
    used to discover which workspaces exist.
    """
    client = _client_for(account, slug)
    if client is None:
        return None, _redirect("/?m=That+client+no+longer+exists.&k=bad")
    if account.is_tenant:
        own = _tenant_client(account)
        if own is None or own.slug != slug:
            return None, _redirect("/?m=That+is+not+your+workspace.&k=bad")
    return client, None


#: The workspace is four screens plus setup, each on its own URL. The previous
#: build rendered all six panels into one 141KB document and toggled them with
#: JavaScript: instant to switch, slow at everything else, and the wrong trade
#: once a screen carries real content.
_VIEWS = {"today", "sell", "data", "stock", "money", "setup"}


def _render(client, account, view: str, *, flash: str = "", flash_kind: str = "ok",
            reply=None, question: str = "", period: str = "all",
            show: str = "summary", fresh_pin: str = "") -> HTMLResponse:
    """Load what one view needs and render it.

    Every route goes through here so none of them can drift into loading a
    different set of state than the others.
    """
    state = _console_state(client)
    book, ledger_, org = state["book"], state["ledger"], state["org"]
    settings, invoices = state["settings"], state["invoices"]
    common = dict(reply=reply, question=question, flash=flash, flash_kind=flash_kind)

    if view == "sell":
        return HTMLResponse(console.sell_view(client, account, book, org, invoices,
                                              settings, **common))
    if view == "data":
        entries = ledger.read(client.owner_id, limit=20, client=client.slug)
        return HTMLResponse(console.data_view(client, account, settings, entries,
                                              **common))
    if view == "stock":
        return HTMLResponse(console.stock_view(client, account, book, org, settings,
                                               **common))
    if view == "money":
        return HTMLResponse(console.money_view(client, account, book, ledger_, org,
                                               settings, period=period, show=show,
                                               **common))
    if view == "setup":
        invite = auth.invite_for(client.slug) if not account.is_guest else None
        return HTMLResponse(console.setup_view(client, account, book, org, settings,
                                               invoices, invite=invite,
                                               fresh_pin=fresh_pin, **common))
    return HTMLResponse(console.today_view(client, account, book, ledger_, org,
                                           invoices, settings, **common))


# ---------------------------------------------------------------- 02 · stock

@app.post("/c/{slug}/stock/receive")
def stock_receive(slug: str, sku: str = Form(...), qty: str = Form("0"),
                  cost: str = Form(""), account: auth.Account = Depends(_acct)):
    client, bail = _console_client(account, slug)
    if bail is not None:
        return bail
    _, note, ok = books.receive_stock(slug, sku, qty, cost)
    if ok:
        ledger.log("source.received", note, client=client, channel="manual")
        _rebuild_from_book(client)
    return _console_back(slug, "stock", note)


@app.post("/c/{slug}/stock/count")
def stock_count(slug: str, sku: str = Form(...), counted: str = Form(""),
                branch: str = Form(""), account: auth.Account = Depends(_acct)):
    client, bail = _console_client(account, slug)
    if bail is not None:
        return bail
    _, note, ok = books.adjust_stock(slug, sku, counted)
    if ok:
        if branch:
            books.set_branch(slug, sku, branch)
        ledger.log("source.received", note, client=client, channel="manual")
        _rebuild_from_book(client)
    return _console_back(slug, "stock", note)


@app.post("/c/{slug}/stock/reorder")
async def stock_reorder(slug: str, request: Request,
                        account: auth.Account = Depends(_acct)):
    """Bulk reorder-level save.

    The field names are dynamic — one per SKU — so this reads the raw form
    rather than declaring parameters it cannot know in advance.
    """
    client, bail = _console_client(account, slug)
    if bail is not None:
        return bail
    form = await request.form()
    levels = {k[4:]: str(v) for k, v in form.items() if k.startswith("lvl_")}
    _, note = books.set_reorder(slug, levels)
    if "updated" in note:
        ledger.log("source.received", note, client=client, channel="manual")
        _rebuild_from_book(client)
    return _console_back(slug, "stock", note)


# ------------------------------------------------------------------ 03 · ask

@app.post("/c/{slug}/ask", response_class=HTMLResponse)
async def console_ask(slug: str, request: Request,
                      account: auth.Account = Depends(_acct)):
    """Answer, and stay where you were.

    The question box is in the header of every screen, so the answer has to come
    back on that screen — bouncing somebody to a different view because they
    asked a question is how a feature stops being used. The originating view
    arrives as a hidden `from` field, which cannot be a declared parameter
    because `from` is a Python keyword.
    """
    client, bail = _console_client(account, slug)
    if bail is not None:
        return bail

    form = await request.form()
    question = str(form.get("question", "")).strip()
    view = str(form.get("from", "today"))
    if view not in _VIEWS:
        view = "today"
    if client.data_mode == "books" and view == "data":
        view = "sell"
    if client.data_mode != "books" and view == "sell":
        view = "data"

    state = _console_state(client)
    # investigate() lets the model query the books itself rather than reading a
    # fixed summary, and falls back to the pattern answers when Claude is not
    # reachable — so the offline path is still the same call.
    reply = agent.investigate(question, client, state["book"], state["settings"],
                              ledger=state["ledger"], org=state["org"])
    ledger.log("agent.asked", f"Asked: {question[:90]}", client=client,
               channel="agent", answered_by=reply.source, ok=reply.ok)
    return _render(client, account, view, reply=reply, question=question)


# ----------------------------------------------------------- 07 · follow-ups

@app.post("/c/{slug}/followup")
def console_followup(slug: str, key: str = Form(...), status: str = Form("done"),
                     days: int = Form(7), account: auth.Account = Depends(_acct)):
    client, bail = _console_client(account, slug)
    if bail is not None:
        return bail
    note = followup.mark(slug, key, status, days)
    ledger.log("followup.handled", f"{status}: {key}", client=client, channel="followup")
    return _console_back(slug, "followups", note)


# ---------------------------------------------------------------- 08 · money

@app.post("/c/{slug}/expense")
def console_expense(slug: str, category: str = Form("Other"), party: str = Form(""),
                    amount: str = Form("0"), when: str = Form(""),
                    due_date: str = Form(""), branch: str = Form(""),
                    unpaid: str = Form(""), account: auth.Account = Depends(_acct)):
    client, bail = _console_client(account, slug)
    if bail is not None:
        return bail
    _, note = money.add_expense(slug, category, party, amount, when=when,
                                paid=not bool(unpaid), due_date=due_date, branch=branch)
    ledger.log("money.recorded", note, client=client, channel="money")
    return _console_back(slug, "money", note)


@app.post("/c/{slug}/expense/{expense_id}/paid")
def console_expense_paid(slug: str, expense_id: str,
                         account: auth.Account = Depends(_acct)):
    client, bail = _console_client(account, slug)
    if bail is not None:
        return bail
    _, note = money.mark_paid(slug, expense_id)
    ledger.log("money.recorded", note, client=client, channel="money")
    return _console_back(slug, "money", note)


@app.post("/c/{slug}/expense/{expense_id}/delete")
def console_expense_delete(slug: str, expense_id: str,
                           account: auth.Account = Depends(_acct)):
    client, bail = _console_client(account, slug)
    if bail is not None:
        return bail
    _, note = money.delete_expense(slug, expense_id)
    return _console_back(slug, "money", note)


# ----------------------------------------------------------------- 09 · deck

def _deck_outline(client: store.Client, brief: str, kind: str, state: dict):
    # Both fact sets. agent.facts carries the operating picture — stock, best
    # sellers, who owes what — and finance.facts carries the series a chart is
    # drawn from: the monthly trend, the customer split, the ratios. A deck
    # needs both, and reading only one is why the charts came out empty.
    facts = {**agent.facts(client, state["book"], state["ledger"], state["org"]),
             **finance.facts(state["book"], state["ledger"])}
    return decks.outline(brief, kind, client, facts, state["settings"])


@app.get("/c/{slug}/deck/view", response_class=HTMLResponse)
def console_deck_view(slug: str, account: auth.Account = Depends(_acct)):
    """The deck itself — a real presentation, not a preview pane.

    Its own page rather than a panel: a deck wants the whole screen, arrow keys
    and a print stylesheet, none of which fit inside a dashboard tab.
    """
    client, bail = _console_client(account, slug)
    if bail is not None:
        return bail
    brief, kind = agent.DECK_BRIEFS.get(slug, ("", "review"))
    outline = _deck_outline(client, brief, kind, _console_state(client))
    ledger.log("export.created", f"Deck opened: {outline.title}", client=client,
               channel="deck", written_by=outline.source, slides=len(outline.slides))
    return HTMLResponse(deck_render.render_html(outline, client))


@app.get("/c/{slug}/deck/{fmt}")
def console_deck_download(slug: str, fmt: str, account: auth.Account = Depends(_acct)):
    client, bail = _console_client(account, slug)
    if bail is not None:
        return bail
    if fmt not in {"pptx", "pdf"}:
        return _console_back(slug, "deck", "That format is not available.")

    brief, kind = agent.DECK_BRIEFS.get(slug, ("", "review"))
    state = _console_state(client)
    outline = _deck_outline(client, brief, kind, state)

    out = store.DATA / "exports" / f"{slug}-deck.{fmt}"
    if fmt == "pptx":
        decks.to_pptx(outline, client.name, out)
        media = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    else:
        decks.to_pdf(outline, client.name, out)
        media = "application/pdf"

    ledger.log("export.created", f"Deck downloaded as {fmt.upper()}", client=client,
               channel=fmt)
    return FileResponse(out, media_type=media, filename=f"{slug}-{kind}.{fmt}")


# ---------------------------------------------------------------- 10 · people

@app.post("/c/{slug}/branch")
def console_branch(slug: str, name: str = Form(...), place: str = Form(""),
                   manager: str = Form(""), account: auth.Account = Depends(_acct)):
    client, bail = _console_client(account, slug)
    if bail is not None:
        return bail
    _, note = people.add_branch(slug, name, place, manager=manager)
    ledger.log("people.changed", note, client=client, channel="people")
    return _console_back(slug, "people", note)


@app.post("/c/{slug}/branch/{branch_id}/delete")
def console_branch_delete(slug: str, branch_id: str,
                          account: auth.Account = Depends(_acct)):
    client, bail = _console_client(account, slug)
    if bail is not None:
        return bail
    _, note = people.delete_branch(slug, branch_id)
    ledger.log("people.changed", note, client=client, channel="people")
    return _console_back(slug, "people", note)


@app.post("/c/{slug}/staff")
def console_staff(slug: str, name: str = Form(...), role: str = Form("Salesperson"),
                  branch: str = Form(""), phone: str = Form(""),
                  account: auth.Account = Depends(_acct)):
    client, bail = _console_client(account, slug)
    if bail is not None:
        return bail
    _, note = people.add_staff(slug, name, role, branch, phone)
    ledger.log("people.changed", note, client=client, channel="people")
    return _console_back(slug, "people", note)


@app.post("/c/{slug}/staff/{staff_id}/delete")
def console_staff_delete(slug: str, staff_id: str,
                         account: auth.Account = Depends(_acct)):
    client, bail = _console_client(account, slug)
    if bail is not None:
        return bail
    _, note = people.delete_staff(slug, staff_id)
    return _console_back(slug, "people", note)


# ---------------------------------------------------------------- 03b · bills

@app.post("/c/{slug}/invoice")
async def invoice_raise(slug: str, request: Request,
                        account: auth.Account = Depends(_acct)):
    """Raise one invoice over the ticked sales.

    Reads the raw form because `sale_ids` is a repeated checkbox field, and a
    declared parameter would collapse it to the last value — silently billing
    one line of a five-line order.
    """
    client, bail = _console_client(account, slug)
    if bail is not None:
        return bail

    form = await request.form()
    sale_ids = [str(v) for v in form.getlist("sale_ids")]
    if not sale_ids:
        return _console_back(slug, "bills", "Tick at least one sale to bill.")

    try:
        inv, note = invoice.issue(
            client, books.load(slug), sale_ids,
            party_gstin=str(form.get("party_gstin", "")).strip(),
            party_state=str(form.get("party_state", "")).strip(),
            party_address=str(form.get("party_address", "")).strip())
    except ValueError as exc:
        return _console_back(slug, "bills", str(exc))

    ledger.log("invoice.raised", note, client=client, channel="invoice",
               number=inv.number, total=inv.rounded, lines=len(inv.lines))
    return _console_back(slug, "bills", note)


@app.get("/c/{slug}/invoice/{invoice_id}", response_class=HTMLResponse)
def invoice_view(slug: str, invoice_id: str, account: auth.Account = Depends(_acct)):
    """The printable document. Self-contained, so it works with no internet."""
    client, bail = _console_client(account, slug)
    if bail is not None:
        return bail
    inv = invoice.get(slug, invoice_id)
    if inv is None:
        return _console_back(slug, "bills", "That invoice no longer exists.")
    return HTMLResponse(invoice_render.render_html(inv, client))


@app.get("/c/{slug}/invoice/{invoice_id}/pdf")
def invoice_pdf(slug: str, invoice_id: str, account: auth.Account = Depends(_acct)):
    client, bail = _console_client(account, slug)
    if bail is not None:
        return bail
    inv = invoice.get(slug, invoice_id)
    if inv is None:
        return _console_back(slug, "bills", "That invoice no longer exists.")

    safe = inv.number.replace("/", "-")
    out = store.DATA / "exports" / f"{slug}-{safe}.pdf"
    invoice_render.to_pdf(inv, client, out)
    ledger.log("export.created", f"{inv.number} downloaded as PDF", client=client,
               channel="pdf")
    return FileResponse(out, media_type="application/pdf", filename=f"{safe}.pdf")


@app.post("/c/{slug}/invoice/{invoice_id}/delete")
def invoice_cancel(slug: str, invoice_id: str, account: auth.Account = Depends(_acct)):
    client, bail = _console_client(account, slug)
    if bail is not None:
        return bail
    note = invoice.delete(slug, invoice_id)
    ledger.log("invoice.cancelled", note, client=client, channel="invoice")
    return _console_back(slug, "bills", note)


@app.post("/c/{slug}/invoice/identity")
def invoice_identity(slug: str, gstin: str = Form(""), state: str = Form(""),
                     address: str = Form(""), bank_name: str = Form(""),
                     bank_account: str = Form(""), bank_ifsc: str = Form(""),
                     invoice_terms: str = Form(""),
                     invoice_template: str = Form("classic"),
                     account: auth.Account = Depends(_acct)):
    """What prints at the top of every bill from now on.

    Deliberately does not touch invoices already raised — a document that has
    been sent to somebody must not change afterwards.
    """
    client, bail = _console_client(account, slug)
    if bail is not None:
        return bail

    client.gstin = gstin.strip()
    client.state = state.strip().upper()
    client.address = address.strip()
    client.bank_name = bank_name.strip()
    client.bank_account = bank_account.strip()
    client.bank_ifsc = bank_ifsc.strip()
    if invoice_terms.strip():
        client.invoice_terms = invoice_terms.strip()
    if invoice_template in invoice.TEMPLATES:
        client.invoice_template = invoice_template
    store.update_client(client)

    gaps = invoice.missing(client)
    note = ("Saved. Invoices now print as tax invoices." if not gaps
            else "Saved. Still missing: " + ", ".join(gaps) + ".")
    ledger.log("settings.changed", "Invoice details updated", client=client,
               channel="invoice")
    return _console_back(slug, "bills", note)


# ---------------------------------------------------------------- the workspace
#
# Declared last on purpose. FastAPI matches routes in definition order, so a
# path parameter this broad placed earlier would swallow /dashboard, /cover,
# /deck/view and every export.

@app.get("/c/{slug}/{view}", response_class=HTMLResponse)
def workspace(slug: str, view: str, request: Request, period: str = "all",
              show: str = "summary", account: auth.Account = Depends(_acct)):
    if view not in _VIEWS:
        return _redirect(f"/c/{slug}/today")
    client, bail = _console_client(account, slug)
    if bail is not None:
        return bail

    # A business that types entries has no Data screen, and one that sends files
    # has no Sell screen. Asking for the wrong one lands on its own daily job.
    if view == "sell" and client.data_mode != "books":
        return _redirect(f"/c/{slug}/data")
    if view == "data" and client.data_mode == "books":
        return _redirect(f"/c/{slug}/sell")

    msg, kind = _flash(request)
    return _render(client, account, view, flash=msg, flash_kind=kind, period=period,
                   show=show, fresh_pin=request.query_params.get("pin", ""))
