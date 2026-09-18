"""The business's site: /app/<slug> — Home, the sections, and the assistant.

Every route resolves the business through ``access.workspace`` first, so a tenant cannot
reach another business by editing the URL and a stranger's slug looks exactly like a typo.
The login middleware in ``app.py`` has already closed these paths to anyone signed out.
"""

from __future__ import annotations

from urllib.parse import quote_plus, urlencode

from fastapi import APIRouter, Form, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from ... import (access, agent, auth, books, config, invoice, invoice_render, ledger,
                 money, people, store)
from .. import nav, shell
from ..templating import render
from ..views import home as home_view
from ..views import pages as page_views
from ..views import settings as settings_view

router = APIRouter()


def _redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=303)


def _gone() -> RedirectResponse:
    return _redirect("/app?m=That+business+is+not+available.&k=bad")


@router.get("/app")
def app_root(request: Request):
    """Where "the site" means for this person: their business, or the Studio."""
    account = request.state.account
    if getattr(account, "is_tenant", False):
        slug = getattr(account, "tenant_slug", "")
        return _redirect(f"/app/{slug}" if slug else "/")
    return _redirect("/studio" + (f"?m={request.query_params['m']}&k=bad"
                                  if request.query_params.get("m") else ""))


@router.get("/app/{slug}", response_class=HTMLResponse)
def home(slug: str, request: Request):
    account = request.state.account
    client = access.workspace(account, slug)
    if client is None:
        return _gone()
    ctx = shell.base(request, account, area="site", client=client, section="home",
                     title="Home")
    ctx.update(home_view.build(client, account))
    return render(request, "pages/home.html", ctx)


@router.get("/app/{slug}/{section}", response_class=HTMLResponse)
def section_root(slug: str, section: str, request: Request):
    return section_page(slug, section, "", request)


@router.get("/app/{slug}/{section}/{page}", response_class=HTMLResponse)
def section_page(slug: str, section: str, page: str, request: Request):
    account = request.state.account
    client = access.workspace(account, slug)
    if client is None:
        return _gone()
    sec = nav.BY_KEY.get(section)
    if sec is None or sec.key == "home":
        return _redirect(f"/app/{slug}")
    pg = sec.page(page) or (sec.pages[0] if sec.pages else None)
    if pg is not None and page != pg.key:
        return _redirect(f"/app/{slug}/{sec.key}/{pg.key}")
    ctx = shell.base(request, account, area="site", client=client, section=sec.key,
                     page=pg.key if pg else "", title=sec.label)
    ctx.update({"sec": sec, "pg": pg, "back": _here(request)})
    build = page_views.REGISTRY.get((sec.key, pg.key)) if pg else None
    if build is None:
        return render(request, "pages/section.html", ctx)
    ctx.update(build(client, account, request))
    return render(request, f"pages/{sec.key}/{pg.key}.html", ctx)


def _here(request: Request) -> str:
    """This page's address without its flash, for a form's ``?next=`` — so a form posted
    from a filtered list comes back to the same filtered list."""
    keep = urlencode([(k, v) for k, v in request.query_params.multi_items()
                      if k not in ("m", "k")])
    return request.url.path + (f"?{keep}" if keep else "")


@router.post("/app/{slug}/assistant", response_class=HTMLResponse)
def assistant(slug: str, request: Request, question: str = Form("")):
    """Ask the business agent — the existing tool loop, with its offline fallback.

    A first version: the streamed, threaded assistant arrives in Phase 5. Numbers still
    come only from the tools, and with no key or no network ``agent.rules()`` answers.
    """
    account = request.state.account
    client = access.workspace(account, slug)
    if client is None:
        return HTMLResponse("", status_code=404)
    question = question.strip()
    reply = None
    if question:
        reply = agent.investigate(question, client, books.load(slug), config.load(),
                                  ledger=money.load(slug), org=people.load(slug))
    return render(request, "partials/assistant_answer.html",
                  {"question": question, "reply": reply, "client": client})


# --------------------------------------------------------------- team actions
# Marking the register and setting a target have no classic route to reuse: the classic
# register's buttons post to one that was never written.

def _done(request, fallback: str, note: str, kind: str = "ok") -> RedirectResponse:
    """Back where the form was, with a word about what happened."""
    target = str(request.query_params.get("next") or fallback)
    if not target.startswith("/app/") or "//" in target:
        target = fallback
    join = "&" if "?" in target else "?"
    return _redirect(f"{target}{join}m={quote_plus(note)}&k={kind}")


@router.post("/app/{slug}/team/attendance")
async def mark_attendance(slug: str, request: Request):
    form = await request.form()
    client = access.workspace(request.state.account, slug)
    if client is None:
        return _gone()
    _org, note = people.mark_attendance(slug, str(form.get("staff_id", "")),
                                        str(form.get("state", "present")),
                                        str(form.get("day", "")))
    ledger.log("people.changed", note, client=client, channel="people")
    return _done(request, f"/app/{slug}/team/attendance", note,
                 "ok" if "gone" not in note else "bad")


@router.post("/app/{slug}/team/target")
async def set_target(slug: str, request: Request):
    form = await request.form()
    client = access.workspace(request.state.account, slug)
    if client is None:
        return _gone()
    _org, note = people.set_target(slug, str(form.get("staff_id", "")),
                                   str(form.get("target", "0")),
                                   str(form.get("commission", "0")))
    ledger.log("people.changed", note, client=client, channel="people")
    return _done(request, f"/app/{slug}/team/performance", note)


# -------------------------------------------------------------- access links
# The PIN is shown exactly once, so minting renders the page rather than redirecting to it:
# a redirect would have to carry the PIN in a URL, where it would sit in history.

def _may_share(account) -> bool:
    return access.is_operator(account) and not getattr(account, "is_guest", False)


@router.post("/app/{slug}/access/share", response_class=HTMLResponse)
def access_share(slug: str, request: Request):
    account = request.state.account
    client = access.workspace(account, slug)
    if client is None:
        return _gone()
    if not _may_share(account):
        return _done(request, f"/app/{slug}/settings/access",
                     "Only the Vyuha team can issue a link.", "bad")
    _invite, pin = auth.create_invite(slug, client.owner_id, client.name)
    ledger.log("share.created", f"Workspace link issued for {client.name}", client=client)

    sec = nav.BY_KEY["settings"]
    pg = sec.page("access")
    ctx = shell.base(request, account, area="site", client=client, section="settings",
                     page="access", title=sec.label)
    ctx.update({"sec": sec, "pg": pg, "back": f"/app/{slug}/settings/access"})
    ctx.update(settings_view.access(client, account, request))
    ctx.update({"fresh_pin": pin, "flash": "Link issued. The PIN is shown once.",
                "flash_kind": "ok"})
    return render(request, "pages/settings/access.html", ctx)


@router.post("/app/{slug}/access/revoke")
def access_revoke(slug: str, request: Request):
    account = request.state.account
    client = access.workspace(account, slug)
    if client is None:
        return _gone()
    if not _may_share(account):
        return _done(request, f"/app/{slug}/settings/access",
                     "Only the Vyuha team can revoke a link.", "bad")
    auth.revoke_invite(slug)
    ledger.log("share.revoked", f"Workspace link revoked for {client.name}", client=client)
    return _done(request, f"/app/{slug}/settings/access",
                 "Link revoked. Whoever had it is locked out.")


# ------------------------------------------------------------------ documents
# The printable invoice and its PDF, from the same renderers the classic screens use.
# Five and six path segments, so they never meet /app/{slug}/{section}/{page}.

@router.get("/app/{slug}/doc/invoice/{invoice_id}", response_class=HTMLResponse)
def invoice_document(slug: str, invoice_id: str, request: Request):
    client = access.workspace(request.state.account, slug)
    if client is None:
        return _gone()
    inv = invoice.get(slug, invoice_id)
    if inv is None:
        return _redirect(f"/app/{slug}/operations/invoices?m=That+invoice+no+longer+exists.&k=bad")
    return HTMLResponse(invoice_render.render_html(inv, client))


@router.get("/app/{slug}/doc/dashboard")
@router.get("/app/{slug}/doc/dashboard/{run_id}")
def dashboard_document(slug: str, request: Request, run_id: str = ""):
    """The self-contained client dashboard — the file that gets forwarded on WhatsApp."""
    client = access.workspace(request.state.account, slug)
    if client is None:
        return _gone()
    run = (next((r for r in client.runs if r.id == run_id), None) if run_id
           else client.latest)
    back = f"/app/{slug}/data/read"
    if run is None or not run.dashboard:
        return _redirect(f"{back}?m=No+dashboard+yet.&k=bad")
    path = store.DASHBOARDS / run.dashboard
    if not path.exists():
        return _redirect(f"{back}?m=That+dashboard+file+is+missing.&k=bad")
    return FileResponse(path, media_type="text/html")


@router.get("/app/{slug}/doc/deck", response_class=HTMLResponse)
def deck_document(slug: str, request: Request):
    """The deck as a presentation. The assistant decides what it says; this renders it."""
    from ... import app as app_mod, deck_render

    client = access.workspace(request.state.account, slug)
    if client is None:
        return _gone()
    brief, kind = agent.DECK_BRIEFS.get(slug, ("", "review"))
    outline = app_mod._deck_outline(client, brief, kind, app_mod._console_state(client))
    ledger.log("export.created", f"Deck opened: {outline.title}", client=client,
               channel="deck", written_by=outline.source, slides=len(outline.slides))
    return HTMLResponse(deck_render.render_html(outline, client))


@router.get("/app/{slug}/doc/deck/{fmt}")
def deck_download(slug: str, fmt: str, request: Request):
    from ... import app as app_mod, decks

    client = access.workspace(request.state.account, slug)
    if client is None:
        return _gone()
    back = f"/app/{slug}/analytics/documents"
    if fmt not in {"pptx", "pdf"}:
        return _redirect(f"{back}?m=That+format+is+not+available.&k=bad")
    brief, kind = agent.DECK_BRIEFS.get(slug, ("", "review"))
    outline = app_mod._deck_outline(client, brief, kind, app_mod._console_state(client))
    out = store.DATA / "exports" / f"{slug}-deck.{fmt}"
    if fmt == "pptx":
        decks.to_pptx(outline, client.name, out)
        media = ("application/vnd.openxmlformats-officedocument"
                 ".presentationml.presentation")
    else:
        decks.to_pdf(outline, client.name, out)
        media = "application/pdf"
    ledger.log("export.created", f"Deck downloaded as {fmt.upper()}", client=client,
               channel=fmt)
    return FileResponse(out, media_type=media, filename=f"{slug}-{kind}.{fmt}")


@router.get("/app/{slug}/doc/export/{fmt}")
def export_document(slug: str, fmt: str, request: Request):
    """The report pack — the same builders the classic export route uses."""
    from ... import app as app_mod, exports

    client = access.workspace(request.state.account, slug)
    if client is None:
        return _gone()
    back = f"/app/{slug}/finance/reports"
    run = client.latest
    if not run or run.status != "ok":
        return _redirect(f"{back}?m=Nothing+to+export+yet.&k=bad")
    insights = app_mod._reload_insights(client, run, config.load())
    if insights is None:
        return _redirect(f"{back}?m=Could+not+rebuild+that+run.&k=bad")

    out_dir = store.dashboard_dir(slug)
    if fmt == "pdf":
        path = exports.to_pdf(insights, client.name, out_dir / f"{run.id}.pdf")
        media = "application/pdf"
    elif fmt == "pptx":
        path = exports.to_pptx(insights, client.name, out_dir / f"{run.id}.pptx")
        media = ("application/vnd.openxmlformats-officedocument"
                 ".presentationml.presentation")
    elif fmt == "html":
        path = store.DASHBOARDS / run.dashboard
        media = "text/html"
    else:
        return _redirect(f"{back}?m=Unknown+format.&k=bad")
    ledger.log("export.created", f"{fmt.upper()} generated for {client.name}",
               client=client, channel=fmt)
    return FileResponse(path, media_type=media,
                        filename=f"{store.slugify(client.name)}-brief.{fmt}")


@router.get("/app/{slug}/doc/invoice/{invoice_id}/pdf")
def invoice_document_pdf(slug: str, invoice_id: str, request: Request):
    client = access.workspace(request.state.account, slug)
    if client is None:
        return _gone()
    inv = invoice.get(slug, invoice_id)
    if inv is None:
        return _redirect(f"/app/{slug}/operations/invoices?m=That+invoice+no+longer+exists.&k=bad")
    safe = inv.number.replace("/", "-")
    out = store.DATA / "exports" / f"{slug}-{safe}.pdf"
    invoice_render.to_pdf(inv, client, out)
    ledger.log("export.created", f"{inv.number} downloaded as PDF", client=client, channel="pdf")
    return FileResponse(out, media_type="application/pdf", filename=f"{safe}.pdf")
