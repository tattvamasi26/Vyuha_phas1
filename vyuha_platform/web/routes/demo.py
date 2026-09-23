"""/demo — the guided demo: a control page for the presenter, and the script as JSON.

The overlay itself lives in the browser (``static/app/js/tour.js``) because the demo walks
across real page loads: every step names a real address, so the prospect is always looking
at the live product rather than at a slideshow of it. The server's part is small — hand
over the script, run an action when the presenter asks for one, and clear up afterwards.

Operators and masters only, like the Studio. A guest on a shared link has no business
running a sales demo of their own workspace, and ``_deny`` says so rather than half-working.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from ... import access, demo_tour
from .. import shell
from ..templating import render

router = APIRouter()


def _presenter(request: Request):
    """The account, if it may run a demo; otherwise None."""
    account = request.state.account
    if account is None or getattr(account, "is_guest", False):
        return None
    return account if access.is_operator(account) else None


@router.get("/demo", response_class=HTMLResponse)
def demo_home(request: Request):
    account = _presenter(request)
    if account is None:
        return RedirectResponse("/app", status_code=303)
    state = demo_tour.status(account)
    ctx = shell.base(request, account, area="studio", section="demo",
                     title="Guided demo")
    ctx.update({
        "state": state,
        "chapters": demo_tour.CHAPTERS,
        "steps": demo_tour.STEPS,
        "by_chapter": {c.key: [s for s in demo_tour.STEPS if s.chapter == c.key]
                       for c in demo_tour.CHAPTERS},
        "business": demo_tour.NAME,
    })
    return render(request, "pages/demo.html", ctx)


@router.get("/demo/steps.json")
def steps(request: Request):
    """The script, with the demo business's slug already in every address."""
    account = _presenter(request)
    if account is None:
        return JSONResponse({"ok": False, "steps": [], "status": {}}, status_code=403)
    state = demo_tour.status(account)
    return JSONResponse({
        "ok": True,
        "status": state,
        "chapters": [{"key": c.key, "label": c.label, "blurb": c.blurb}
                     for c in demo_tour.CHAPTERS],
        "steps": demo_tour.steps_for(state.get("slug", "")),
    })


@router.post("/demo/act/{key}")
def act(key: str, request: Request):
    """Do the typing for one step — the same calls the real screens make."""
    account = _presenter(request)
    if account is None:
        return JSONResponse({"ok": False, "message": "Not allowed."}, status_code=403)
    outcome = demo_tour.run(key, account)
    return JSONResponse({"ok": outcome.ok, "message": outcome.message,
                         "slug": outcome.slug, "go": outcome.go})


@router.post("/demo/reset")
def reset(request: Request):
    account = _presenter(request)
    if account is None:
        return JSONResponse({"ok": False, "message": "Not allowed."}, status_code=403)
    outcome = demo_tour.reset(account)
    return JSONResponse({"ok": outcome.ok, "message": outcome.message, "go": outcome.go})
