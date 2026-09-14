"""/styleguide — every component of the design system on one page.

For the people building Vyuha, not the businesses using it: operators and masters only.
If a component looks wrong here it looks wrong everywhere, which is the point of having it.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from ... import access
from .. import charts, shell
from ..templating import render

router = APIRouter()


@router.get("/styleguide", response_class=HTMLResponse)
def styleguide(request: Request):
    account = request.state.account
    if not access.is_operator(account):
        return RedirectResponse("/app", status_code=303)
    ctx = shell.base(request, account, area="studio", section="styleguide",
                     title="Style guide")
    ctx.update({
        "spark": charts.sparkline([3, 5, 4, 8, 6, 9, 7, 12, 10, 14, 11, 16]),
        "bars": charts.bars([4, 7, 5, 9, 6, 11]),
        "swatches": ["bg", "surface", "surface-2", "sunken", "line", "ink", "ink-2", "ink-3",
                     "brand", "brand-soft", "ok", "ok-soft", "warn", "warn-soft", "bad",
                     "bad-soft", "info", "info-soft"],
    })
    return render(request, "pages/styleguide.html", ctx)
