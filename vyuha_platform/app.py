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

from vyuha import analyze, pipeline

from . import (auth, books, channels, config, exports, ledger, sources, store, theme,
               ui, whatsapp)

app = FastAPI(title="Vyuha Operations Platform", docs_url=None, redoc_url=None)

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
def login_form(request: Request):
    if request.state.account is not None:
        return _redirect("/")
    return ui.login()


@app.post("/login")
def login_submit(request: Request, email: str = Form(...),
                 password: str = Form(...)):
    account = auth.verify(email, password)
    if account is None:
        # One message for both causes: which half was wrong is not the visitor's
        # business to learn, and saying so enumerates who has an account.
        return HTMLResponse(ui.login(flash="That email and password do not match.",
                                     email=email))
    resp = _redirect("/")
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
    client = store.get_client(slug, account.id)
    if client is None:
        return _redirect("/?m=That+client+no+longer+exists.&k=bad")

    invite, pin = auth.create_invite(slug, account.id, client.name)
    ledger.log("share.created", f"Workspace link issued for {client.name}",
               client=client, channel="whatsapp")
    # The PIN is shown exactly once, here, because it is not stored in clear.
    return _redirect(f"/c/{slug}?tab=settings&pin={pin}&m={_msg('Link ready. Send it with the PIN.')}")


@app.post("/c/{slug}/share/revoke")
def share_revoke(slug: str, account: auth.Account = Depends(_acct)):
    denied = _deny_tenant(account)
    if denied:
        return denied
    client = store.get_client(slug, account.id)
    if client is None:
        return _redirect("/?m=That+client+no+longer+exists.&k=bad")
    auth.revoke_invite(slug)
    ledger.log("share.revoked", f"Workspace link revoked for {client.name}",
               client=client)
    return _redirect(f"/c/{slug}?tab=settings&m=Link+revoked.")


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
        return _redirect(f"/c/{client.slug}?tab=alerts&m={_msg('Workspace created. ' + result.needs_action)}&k=bad")

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
    client = store.get_client(slug, account.id)
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
def client_page(slug: str, request: Request, tab: str = "data",
                account: auth.Account = Depends(_acct)):
    client = store.get_client(slug, account.id)
    if client is None:
        return _redirect("/?m=That+client+no+longer+exists.&k=bad")

    settings = config.load()
    # A tenant account owns exactly one workspace and cannot reach another.
    if account.is_tenant:
        own = _tenant_client(account)
        if own is None or own.slug != slug:
            return _redirect("/?m=That+is+not+your+workspace.&k=bad")
    msg, kind = _flash(request)
    extra: dict = {}

    if tab == "alerts":
        last = client.latest
        if last and last.status == "ok":
            insights = _reload_insights(client, last, settings)
            if insights is not None:
                wa_text = channels.as_whatsapp(insights, client=client.name)
                subject, email_body = exports.draft_email(insights, client.name, client.contact)
                extra = {
                    "wa_text": wa_text,
                    "wa_link": channels.whatsapp_link(client.phone, wa_text),
                    "mail_link": channels.mailto_link(client.email, subject, email_body),
                    "email_subject": subject,
                    "email_body": email_body,
                }

    if client.data_mode == "books" or tab == "books":
        extra["book"] = books.load(slug)

    if tab == "settings" and not account.is_guest:
        extra["invite"] = auth.invite_for(slug)
        extra["fresh_pin"] = request.query_params.get("pin", "")

    return ui.client_page(client, tab, settings, account,
                          ledger.read(account.id, limit=40, client=slug),
                          flash=msg, flash_kind=kind, **extra)


# ---------------------------------------------------------------- manual books

@app.post("/c/{slug}/book/item")
def book_add_item(slug: str, name: str = Form(...), category: str = Form("Other"),
                  unit: str = Form("piece"), rate: str = Form("0"), cost: str = Form("0"),
                  stock_qty: str = Form("0"), reorder_level: str = Form("0"),
                  account: auth.Account = Depends(_acct)):
    client = store.get_client(slug, account.id)
    if client is None:
        return _redirect("/?m=That+client+no+longer+exists.&k=bad")
    _, note = books.add_item(slug, name, category, unit, rate, cost, stock_qty, reorder_level)
    ledger.log("source.received", note, client=client, channel="manual")
    _rebuild_from_book(client)
    return _redirect(f"/c/{slug}?tab=books&m={_msg(note)}")


@app.post("/c/{slug}/book/sale")
def book_add_sale(slug: str, sku: str = Form(...), party: str = Form(""),
                  qty: str = Form("1"), rate: str = Form(""), when: str = Form(""),
                  payment: str = Form("paid"), due_date: str = Form(""),
                  account: auth.Account = Depends(_acct)):
    client = store.get_client(slug, account.id)
    if client is None:
        return _redirect("/?m=That+client+no+longer+exists.&k=bad")
    _, note, ok = books.record_sale(slug, sku, party, qty, rate, when,
                                    paid=(payment == "paid"), due_date=due_date)
    if not ok:
        return _redirect(f"/c/{slug}?tab=books&m={_msg(note)}&k=bad")
    ledger.log("source.received", note, client=client, channel="manual")
    _rebuild_from_book(client)
    return _redirect(f"/c/{slug}?tab=books&m={_msg(note)}")


@app.post("/c/{slug}/book/sale/{sale_id}/delete")
def book_delete_sale(slug: str, sale_id: str, account: auth.Account = Depends(_acct)):
    client = store.get_client(slug, account.id)
    if client is None:
        return _redirect("/?m=That+client+no+longer+exists.&k=bad")
    _, note = books.delete_sale(slug, sale_id)
    ledger.log("settings.changed", note, client=client, channel="manual")
    _rebuild_from_book(client)
    return _redirect(f"/c/{slug}?tab=books&m={_msg(note)}")


@app.post("/c/{slug}/book/sale/{sale_id}/paid")
def book_mark_paid(slug: str, sale_id: str, account: auth.Account = Depends(_acct)):
    client = store.get_client(slug, account.id)
    if client is None:
        return _redirect("/?m=That+client+no+longer+exists.&k=bad")
    _, note = books.mark_paid(slug, sale_id)
    ledger.log("settings.changed", note, client=client, channel="manual")
    _rebuild_from_book(client)
    return _redirect(f"/c/{slug}?tab=books&m={_msg(note)}")


@app.post("/c/{slug}/book/item/{sku}/delete")
def book_delete_item(slug: str, sku: str, account: auth.Account = Depends(_acct)):
    client = store.get_client(slug, account.id)
    if client is None:
        return _redirect("/?m=That+client+no+longer+exists.&k=bad")
    _, note = books.delete_item(slug, sku)
    ledger.log("settings.changed", note, client=client, channel="manual")
    _rebuild_from_book(client)
    return _redirect(f"/c/{slug}?tab=books&m={_msg(note)}")


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
    client = store.get_client(slug, account.id)
    name = client.name if client else slug
    shutil.rmtree(store.UPLOADS / slug, ignore_errors=True)
    shutil.rmtree(store.DASHBOARDS / slug, ignore_errors=True)
    store.delete_client(slug, account.id)
    ledger.log("client.deleted", f"{name} was deleted", client=slug,
               owner=account.id)
    return _redirect("/?m=Client+deleted.")


@app.post("/c/{slug}/contact")
def client_contact(slug: str, contact: str = Form(""), phone: str = Form(""),
                   email: str = Form(""), industry: str = Form(""),
                   dead_stock_days: int = Form(90), low_cover_days: int = Form(14),
                   account: auth.Account = Depends(_acct)):
    """Details are optional and filled in later, never demanded at onboarding."""
    client = store.get_client(slug, account.id)
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
    return _redirect(f"/c/{slug}?tab=settings&m=Saved.")


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


@app.post("/c/{slug}/upload")
def upload(slug: str, file: UploadFile = File(...), account: auth.Account = Depends(_acct)):
    client = store.get_client(slug, account.id)
    if client is None:
        return _redirect("/?m=That+client+no+longer+exists.&k=bad")

    settings = config.load()
    name = Path(file.filename or "upload").name
    target = store.upload_dir(slug) / name
    with target.open("wb") as fh:
        shutil.copyfileobj(file.file, fh)

    size = target.stat().st_size
    ledger.log("source.received", f"{name} received", client=client,
               channel="upload", bytes=size, file_kind=sources.classify(name))

    # Anything that is not a spreadsheet is converted to one first.
    extraction = sources.prepare(target, store.upload_dir(slug), settings)
    if not extraction.ok:
        ledger.log("source.rejected", f"{name}: {extraction.error}", client=client,
                   channel="upload", needs_action=extraction.needs_action)
        detail = extraction.error + (" " + extraction.needs_action if extraction.needs_action else "")
        return _redirect(f"/c/{slug}?m={_msg(detail)}&k=bad")

    if extraction.kind != "native":
        ledger.log("source.converted", f"{name} — {extraction.method}", client=client,
                   channel=extraction.kind, confidence=extraction.confidence,
                   notes=extraction.notes)

    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    run = store.Run(id=run_id, filename=name,
                    uploaded_at=datetime.now().isoformat(timespec="seconds"),
                    source_kind=extraction.kind, source_method=extraction.method,
                    confidence=extraction.confidence, source_notes=list(extraction.notes),
                    converted=extraction.path.name if extraction.path else "")

    try:
        with _thresholds(client):
            result = pipeline.run(extraction.path)
            out = store.dashboard_dir(slug) / f"{run_id}.html"
            pipeline.write_report(result, out, client=client.name)

        ins = result.insights
        run.dashboard = f"{slug}/{run_id}.html"
        run.sheets_read = [t.kind.title() for t in result.tables]
        run.sheets_skipped = [n for n, _ in result.skipped]
        run.alerts = [{"code": a.code, "severity": a.severity, "title": a.title,
                       "detail": a.detail, "entities": list(a.entities)}
                      for a in channels.ordered(ins)]
        run.alert_count = len(ins.alerts)
        run.critical_count = sum(1 for a in ins.alerts if a.severity == "critical")
        run.revenue = float(ins.sales.get("revenue") or 0)
        run.stock_value = float(ins.stock.get("value") or 0)
        run.outstanding = float(ins.receivables.get("total") or 0)

        ledger.log("run.completed",
                   f"{name}: understood {', '.join(run.sheets_read) or 'no sheets'}",
                   client=client, channel=extraction.kind, alerts=run.alert_count)
        if run.alert_count:
            ledger.log("alert.raised", f"{run.alert_count} alert(s) from {name}",
                       client=client, critical=run.critical_count)
        msg, kind = f"Read {name}. {run.alert_count} alert(s) raised.", "ok"
    except Exception as exc:                       # noqa: BLE001 — surface, never crash the page
        run.status, run.error = "failed", f"{type(exc).__name__}: {exc}"
        traceback.print_exc()
        ledger.log("run.failed", f"{name}: {run.error}", client=client)
        msg, kind = f"Could not read {name}. {run.error[:110]}", "bad"

    store.add_run(slug, account.id, run)
    tab = "alerts" if run.status == "ok" and run.alert_count else "data"
    return _redirect(f"/c/{slug}?tab={tab}&m={_msg(msg)}&k={kind}")


@app.get("/c/{slug}/dashboard")
def dashboard(slug: str, account: auth.Account = Depends(_acct)):
    client = store.get_client(slug, account.id)
    if client is None or not client.latest or not client.latest.dashboard:
        return _redirect(f"/c/{slug}?m=No+dashboard+yet.&k=bad")
    path = store.DASHBOARDS / client.latest.dashboard
    if not path.exists():
        return _redirect(f"/c/{slug}?m=That+dashboard+file+is+missing.&k=bad")
    return FileResponse(path, media_type="text/html")


# --------------------------------------------------------------------- exports

@app.get("/c/{slug}/export/{fmt}")
def export(slug: str, fmt: str, account: auth.Account = Depends(_acct)):
    client = store.get_client(slug, account.id)
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
    client = store.get_client(slug, account.id)
    if client is None:
        return _redirect("/?m=That+client+no+longer+exists.&k=bad")

    settings = config.load()
    attachments = []
    if client.latest and client.latest.dashboard:
        attachments.append(store.DASHBOARDS / client.latest.dashboard)

    ok, detail = exports.send_email(settings, client.email, subject, body, attachments)
    ledger.log("alert.sent" if ok else "alert.send_failed",
               f"Email to {client.name}: {detail}", client=client, channel="email")
    return _redirect(f"/c/{slug}?tab=alerts&m={_msg(detail)}&k={'ok' if ok else 'bad'}")


@app.post("/c/{slug}/whatsapp")
def whatsapp_send(slug: str, text: str = Form(...), account: auth.Account = Depends(_acct)):
    client = store.get_client(slug, account.id)
    if client is None:
        return _redirect("/?m=That+client+no+longer+exists.&k=bad")

    settings = config.load()
    result = whatsapp.send(settings, client.phone, text)
    ledger.log("alert.sent" if result.ok else "alert.send_failed",
               f"WhatsApp to {client.name}: {result.detail}", client=client,
               channel="whatsapp", provider=result.provider)
    note = result.detail + (" " + result.needs_action if result.needs_action else "")
    return _redirect(f"/c/{slug}?tab=alerts&m={_msg(note)}&k={'ok' if result.ok else 'bad'}")


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
