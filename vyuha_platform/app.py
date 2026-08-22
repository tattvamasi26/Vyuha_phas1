"""FastAPI application: onboarding, ingestion, dashboard, alerts.

The engine is imported and called, never reimplemented. ``pipeline.run()`` and
``report.render()`` are untouched by this package — the platform is a shell
around them, so anything that works in the CLI works here and vice versa.
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

from . import channels, store, ui

app = FastAPI(title="Vyuha Operations Platform", docs_url=None, redoc_url=None)

ACCEPTED = {".xlsx", ".xlsm", ".csv", ".xls"}

# analyze.py keeps its thresholds as module constants, so honouring a per-client
# value means swapping them for the duration of one run. That is process-global
# state, hence the lock. The clean fix is to thread a Thresholds object through
# analyse() — worth doing before this ever serves more than one operator.
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


# --------------------------------------------------------------------- clients

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    msg, kind = _flash(request)
    return ui.home(store.load_clients(), flash=msg, flash_kind=kind)


@app.get("/onboard", response_class=HTMLResponse)
def onboard_form():
    return ui.onboard()


@app.post("/onboard")
def onboard_submit(
    name: str = Form(...),
    contact: str = Form(""),
    industry: str = Form(""),
    phone: str = Form(""),
    email: str = Form(""),
    dead_stock_days: int = Form(90),
    low_cover_days: int = Form(14),
):
    client = store.add_client(
        name=name.strip(),
        contact=contact.strip(),
        industry=industry.strip(),
        phone=channels.normalise_phone(phone),
        email=email.strip(),
        dead_stock_days=max(7, min(730, dead_stock_days)),
        low_cover_days=max(1, min(120, low_cover_days)),
    )
    return _redirect(f"/c/{client.slug}?m=Workspace+created.+Drop+their+file+in.")


@app.get("/c/{slug}", response_class=HTMLResponse)
def client_page(slug: str, request: Request, tab: str = "data"):
    client = store.get_client(slug)
    if client is None:
        return _redirect("/?m=That+client+no+longer+exists.&k=bad")

    msg, kind = _flash(request)
    wa_text = wa_link = mail_link = ""

    if tab == "alerts":
        last = client.latest
        if last and last.status == "ok":
            insights = _reload_insights(client, last)
            if insights is not None:
                wa_text = channels.as_whatsapp(insights, client=client.name)
                wa_link = channels.whatsapp_link(client.phone, wa_text)
                mail_link = channels.mailto_link(
                    client.email, f"Vyuha brief — {client.name}",
                    channels.as_email(insights, client=client.name),
                )
    return ui.client_page(client, tab, flash=msg, flash_kind=kind,
                          wa_text=wa_text, wa_link=wa_link, mail_link=mail_link)


@app.post("/c/{slug}/delete")
def client_delete(slug: str):
    shutil.rmtree(store.UPLOADS / slug, ignore_errors=True)
    shutil.rmtree(store.DASHBOARDS / slug, ignore_errors=True)
    store.delete_client(slug)
    return _redirect("/?m=Client+deleted.")


# ------------------------------------------------------------------- ingestion

def _reload_insights(client: store.Client, run: store.Run):
    """Re-run the engine over the stored upload to rebuild Insights.

    Alerts are cached on the Run for display, but the WhatsApp/email renderers
    want the full object. Re-reading is a second or two and keeps exactly one
    source of truth — the file the client sent.
    """
    source = store.upload_dir(client.slug) / run.filename
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

    name = Path(file.filename or "upload").name
    if Path(name).suffix.lower() not in ACCEPTED:
        return _redirect(
            f"/c/{slug}?m=Vyuha+reads+.xlsx,+.xlsm+and+.csv.+That+file+is+{Path(name).suffix or 'unknown'}.&k=bad"
        )

    target = store.upload_dir(slug) / name
    with target.open("wb") as fh:
        shutil.copyfileobj(file.file, fh)

    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    run = store.Run(id=run_id, filename=name, uploaded_at=datetime.now().isoformat(timespec="seconds"))

    try:
        with _thresholds(client):
            result = pipeline.run(target)
            out = store.dashboard_dir(slug) / f"{run_id}.html"
            pipeline.write_report(result, out, client=client.name)

        ins = result.insights
        run.dashboard = f"{slug}/{run_id}.html"
        run.sheets_read = [f"{t.kind.title()}" for t in result.tables]
        run.sheets_skipped = [n for n, _ in result.skipped]
        run.alerts = [
            {"code": a.code, "severity": a.severity, "title": a.title,
             "detail": a.detail, "entities": list(a.entities)}
            for a in channels.ordered(ins)
        ]
        run.alert_count = len(ins.alerts)
        run.critical_count = sum(1 for a in ins.alerts if a.severity == "critical")
        run.revenue = float(ins.sales.get("revenue") or 0)
        run.stock_value = float(ins.stock.get("value") or 0)
        run.outstanding = float(ins.receivables.get("total") or 0)
        msg = f"Read {name}. {run.alert_count} alert(s) raised."
        kind = "ok"
    except Exception as exc:                       # noqa: BLE001 — surface, never crash the page
        run.status, run.error = "failed", f"{type(exc).__name__}: {exc}"
        traceback.print_exc()
        msg, kind = f"Could not read {name}. {run.error[:120]}", "bad"

    store.add_run(slug, run)
    tab = "alerts" if run.status == "ok" and run.alert_count else "data"
    return _redirect(f"/c/{slug}?tab={tab}&m={msg.replace(' ', '+')}&k={kind}")


@app.get("/c/{slug}/dashboard")
def dashboard(slug: str):
    client = store.get_client(slug)
    if client is None or not client.latest or not client.latest.dashboard:
        return _redirect(f"/c/{slug}?m=No+dashboard+yet.&k=bad")
    path = store.DASHBOARDS / client.latest.dashboard
    if not path.exists():
        return _redirect(f"/c/{slug}?m=That+dashboard+file+is+missing.&k=bad")
    return FileResponse(path, media_type="text/html")
