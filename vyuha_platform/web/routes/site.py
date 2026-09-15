"""The business's site: /app/<slug> — Home, the sections, and the assistant.

Every route resolves the business through ``access.workspace`` first, so a tenant cannot
reach another business by editing the URL and a stranger's slug looks exactly like a typo.
The login middleware in ``app.py`` has already closed these paths to anyone signed out.
"""

from __future__ import annotations

from urllib.parse import urlencode

from fastapi import APIRouter, Form, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from ... import (access, agent, books, config, invoice, invoice_render, ledger, money,
                 people, store)
from .. import nav, shell
from ..templating import render
from ..views import home as home_view
from ..views import pages as page_views

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
