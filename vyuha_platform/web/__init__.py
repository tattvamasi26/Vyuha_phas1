"""The Vyuha site — Jinja2 templates, HTMX and Alpine over the same domain modules.

The front door since the UX rewire: signing in lands here, and nothing here links to the
classic screens. Nothing in this package computes a figure: every number comes from
``books``, ``money``, ``finance``, ``today`` and friends — the functions the classic screens
also call — so the two can never disagree about the same business.

Layout:

* ``templating`` — the Jinja2 environment, money/time filters, the icon helper.
* ``nav`` — the site map as data: sections and their pages.
* ``shell`` — the context every page shares (who is asking, which business, the palette).
* ``views`` — view-models: plain dicts built from domain modules, one per page, and
  ``views.pages.REGISTRY``, which says which builds which.
* ``routes`` — FastAPI routers: ``site`` (/app), ``studio`` (/studio), ``styleguide``.
"""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit

from fastapi import FastAPI


def mount(app: FastAPI) -> None:
    from .routes import demo, site, studio, styleguide

    app.include_router(studio.router)
    app.include_router(styleguide.router)
    app.include_router(demo.router)
    app.include_router(site.router)
    app.middleware("http")(_back_to_the_page)


async def _back_to_the_page(request, call_next):
    """Send a form posted from the site back to the page it was posted from.

    Site pages post to the handlers the classic screens use — one code path for recording
    a sale, marking it paid, sending a receipt — adding ``?next=/app/...``. Those handlers
    redirect to a classic screen; this points the redirect at ``next`` instead and keeps
    the handler's message (``m``/``k``), so the person never leaves the site. Only a path on
    the site is accepted, so ``next`` cannot be used to send anyone somewhere else.
    """
    response = await call_next(request)
    target = request.query_params.get("next", "")
    if (request.method != "POST" or not 300 <= response.status_code < 400
            or not target.startswith("/app/") or "//" in target or "\\" in target):
        return response
    location = response.headers.get("location", "")
    if location.startswith("/app/"):
        return response
    carry = [(k, v) for k, v in parse_qsl(urlsplit(location).query) if k in ("m", "k")]
    base = urlsplit(target)
    kept = [(k, v) for k, v in parse_qsl(base.query) if k not in ("m", "k")]
    query = urlencode(kept + carry)
    response.headers["location"] = base.path + (f"?{query}" if query else "")
    return response
