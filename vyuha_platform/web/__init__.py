"""The new Vyuha site — Jinja2 templates, HTMX and Alpine over the same domain modules.

Mounted beside the classic screens while the rewire lands section by section (plan: Phase 1,
"First look"). Nothing in this package computes a figure: every number comes from
``books``, ``money``, ``finance``, ``today`` and friends — the functions the classic screens
already call — so the two can never disagree about the same business.

Layout:

* ``templating`` — the Jinja2 environment, money/time filters, the icon helper.
* ``nav`` — the site map as data: sections, their pages, what each will do.
* ``shell`` — the context every page shares (who is asking, which business, the palette).
* ``views`` — view-models: plain dicts built from domain modules, one per page.
* ``routes`` — FastAPI routers: ``site`` (/app), ``studio`` (/studio), ``styleguide``.
"""

from __future__ import annotations

from fastapi import FastAPI


def mount(app: FastAPI) -> None:
    from .routes import site, studio, styleguide

    app.include_router(studio.router)
    app.include_router(styleguide.router)
    app.include_router(site.router)
