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

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from vyuha import analyze, pipeline

from . import (books, channels, config, exports, ledger, sources, store, theme, ui,
               whatsapp)

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


def _redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=303)


def _flash(request: Request) -> tuple[str, str]:
    return request.query_params.get("m", ""), request.query_params.get("k", "ok")


def _msg(text: str) -> str:
    return text.replace(" ", "+").replace("&", "and")


# ------------------------------------------------------------------- portfolio

def _tenant_client(settings) -> store.Client | None:
    """The single business a tenant install owns, or None if not set up yet.

    Deliberately strict: no falling back to "whatever client exists". An install
    that has not named its own business must show setup, never adopt a record
    that might belong to somebody else.
    """
    if not settings.tenant_slug:
        return None
    return store.get_client(settings.tenant_slug)


def _deny_tenant(settings) -> RedirectResponse | None:
    """Operator-only routes. A tenant must never reach portfolio machinery."""
    if settings.is_tenant:
        return _redirect("/?m=That+is+not+part+of+your+workspace.&k=bad")
    return None


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    settings = config.load()
    msg, kind = _flash(request)

    # Nothing chosen yet — the install fork happens before anything else.
    if not settings.configured:
        return ui.choose_install()

    if settings.is_tenant:
        client = _tenant_client(settings)
        if client is None:
            return ui.tenant_setup()
        return _redirect(f"/c/{client.slug}")

    clients = store.load_clients()
    return ui.home(clients, settings, ledger.read(limit=8), ledger.counts(),
                   flash=msg, flash_kind=kind)


@app.post("/install")
def install_choose(install: str = Form(...)):
    settings = config.load()
    settings.install = "tenant" if install == "tenant" else "operator"
    config.save(settings)
    ledger.log("settings.changed", f"Install configured as {settings.install}",
               channel="settings")
    return _redirect("/")


@app.get("/onboard", response_class=HTMLResponse)
def onboard_form(request: Request):
    settings = config.load()
    denied = _deny_tenant(settings)
    if denied:
        return denied
    return ui.onboard(settings, *_flash(request))


@app.post("/onboard")
def onboard_submit(name: str = Form(...), phone: str = Form(""),
                   data_mode: str = Form("upload"), trade: str = Form("")):
    """Minimal by design: a name, a number, and how their data arrives."""
    settings = config.load()
    denied = _deny_tenant(settings)
    if denied:
        return denied
    client = store.add_client(name=name.strip(), phone=channels.normalise_phone(phone),
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
def tenant_setup_form():
    settings = config.load()
    if not settings.is_tenant:
        return _redirect("/")
    return ui.tenant_setup()


@app.post("/setup")
def tenant_setup_submit(name: str = Form(...), trade: str = Form(""),
                        data_mode: str = Form("books")):
    """A tenant sets up their own operation — never a client list."""
    settings = config.load()
    if not settings.is_tenant:
        return _redirect("/")

    client = store.add_client(
        name=name.strip(), trade=trade or theme.guess(name),
        data_mode=data_mode if data_mode in ("upload", "books") else "books")
    settings.org_name = client.name
    settings.tenant_slug = client.slug
    config.save(settings)
    ledger.log("client.onboarded", f"{client.name} set up their workspace", client=client)
    return _redirect(f"/c/{client.slug}?m={_msg('Welcome. Add your first entry.')}")


# ------------------------------------------------------------------- workspace

@app.get("/c/{slug}/cover")
def cover(slug: str):
    path = store.covers_dir() / f"{slug}.img"
    if not path.exists():
        return _redirect(f"/c/{slug}")
    return FileResponse(path)


@app.post("/c/{slug}/cover")
def cover_upload(slug: str, file: UploadFile = File(...)):
    client = store.get_client(slug)
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
def client_page(slug: str, request: Request, tab: str = "data"):
    client = store.get_client(slug)
    if client is None:
        return _redirect("/?m=That+client+no+longer+exists.&k=bad")

    settings = config.load()
    # A tenant install owns exactly one workspace and cannot reach another.
    if settings.is_tenant:
        own = _tenant_client(settings)
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

    return ui.client_page(client, tab, settings, ledger.read(limit=40, client=slug),
                          flash=msg, flash_kind=kind, **extra)


# ---------------------------------------------------------------- manual books

@app.post("/c/{slug}/book/item")
def book_add_item(slug: str, name: str = Form(...), category: str = Form("Other"),
                  unit: str = Form("piece"), rate: str = Form("0"), cost: str = Form("0"),
                  stock_qty: str = Form("0"), reorder_level: str = Form("0")):
    client = store.get_client(slug)
    if client is None:
        return _redirect("/?m=That+client+no+longer+exists.&k=bad")
    _, note = books.add_item(slug, name, category, unit, rate, cost, stock_qty, reorder_level)
    ledger.log("source.received", note, client=client, channel="manual")
    _rebuild_from_book(client)
    return _redirect(f"/c/{slug}?tab=books&m={_msg(note)}")


@app.post("/c/{slug}/book/sale")
def book_add_sale(slug: str, sku: str = Form(...), party: str = Form(""),
                  qty: str = Form("1"), rate: str = Form(""), when: str = Form(""),
                  payment: str = Form("paid"), due_date: str = Form("")):
    client = store.get_client(slug)
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
def book_delete_sale(slug: str, sale_id: str):
    client = store.get_client(slug)
    if client is None:
        return _redirect("/?m=That+client+no+longer+exists.&k=bad")
    _, note = books.delete_sale(slug, sale_id)
    ledger.log("settings.changed", note, client=client, channel="manual")
    _rebuild_from_book(client)
    return _redirect(f"/c/{slug}?tab=books&m={_msg(note)}")


@app.post("/c/{slug}/book/sale/{sale_id}/paid")
def book_mark_paid(slug: str, sale_id: str):
    client = store.get_client(slug)
    if client is None:
        return _redirect("/?m=That+client+no+longer+exists.&k=bad")
    _, note = books.mark_paid(slug, sale_id)
    ledger.log("settings.changed", note, client=client, channel="manual")
    _rebuild_from_book(client)
    return _redirect(f"/c/{slug}?tab=books&m={_msg(note)}")


@app.post("/c/{slug}/book/item/{sku}/delete")
def book_delete_item(slug: str, sku: str):
    client = store.get_client(slug)
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
    client = store.get_client(client.slug)
    client.runs = [run]
    store.update_client(client)


@app.post("/c/{slug}/delete")
def client_delete(slug: str):
    client = store.get_client(slug)
    name = client.name if client else slug
    shutil.rmtree(store.UPLOADS / slug, ignore_errors=True)
    shutil.rmtree(store.DASHBOARDS / slug, ignore_errors=True)
    store.delete_client(slug)
    ledger.log("client.deleted", f"{name} was deleted", client=slug)
    return _redirect("/?m=Client+deleted.")


@app.post("/c/{slug}/contact")
def client_contact(slug: str, contact: str = Form(""), phone: str = Form(""),
                   email: str = Form(""), industry: str = Form(""),
                   dead_stock_days: int = Form(90), low_cover_days: int = Form(14)):
    """Details are optional and filled in later, never demanded at onboarding."""
    client = store.get_client(slug)
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
def upload(slug: str, file: UploadFile = File(...)):
    client = store.get_client(slug)
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

    store.add_run(slug, run)
    tab = "alerts" if run.status == "ok" and run.alert_count else "data"
    return _redirect(f"/c/{slug}?tab={tab}&m={_msg(msg)}&k={kind}")


@app.get("/c/{slug}/dashboard")
def dashboard(slug: str):
    client = store.get_client(slug)
    if client is None or not client.latest or not client.latest.dashboard:
        return _redirect(f"/c/{slug}?m=No+dashboard+yet.&k=bad")
    path = store.DASHBOARDS / client.latest.dashboard
    if not path.exists():
        return _redirect(f"/c/{slug}?m=That+dashboard+file+is+missing.&k=bad")
    return FileResponse(path, media_type="text/html")


# --------------------------------------------------------------------- exports

@app.get("/c/{slug}/export/{fmt}")
def export(slug: str, fmt: str):
    client = store.get_client(slug)
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
def email_send(slug: str, subject: str = Form(...), body: str = Form(...)):
    client = store.get_client(slug)
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
def whatsapp_send(slug: str, text: str = Form(...)):
    client = store.get_client(slug)
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
def activity(request: Request, client: str = "", kind: str = ""):
    kinds = {kind} if kind else None
    return ui.activity(ledger.read(limit=300, client=client, kinds=kinds),
                       ledger.counts(), store.load_clients(), client, kind,
                       config.load())


# -------------------------------------------------------------------- settings

@app.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request):
    return ui.settings(config.load(), *_flash(request))


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
):
    current = config.load()
    current.mode = mode if mode in ("agency", "self") else "agency"
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
    ledger.log("settings.changed", "Platform settings updated", channel="settings")
    return _redirect("/settings?m=Settings+saved.")
