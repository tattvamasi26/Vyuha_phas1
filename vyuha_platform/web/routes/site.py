"""The business's site: /app/<slug> — Home, the sections, and the assistant.

Every route resolves the business through ``access.workspace`` first, so a tenant cannot
reach another business by editing the URL and a stranger's slug looks exactly like a typo.
The login middleware in ``app.py`` has already closed these paths to anyone signed out.
"""

from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from ... import access, agent, books, config, money, people
from .. import nav, shell
from ..templating import render
from ..views import home as home_view

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
                     page=pg.key if pg else "", title=f"{pg.label if pg else sec.label}")
    ctx.update({"sec": sec, "pg": pg})
    return render(request, "pages/section.html", ctx)


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
