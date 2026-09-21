# 02 — UX rewire: one website, from onboarding to the assistant

## Description

The founder asked for the product's UI/UX to be rewired end to end, and then — after seeing
the first cut — for **one website**: signing in lands on it, every section is built in the new
design, and nothing sends anybody to a classic screen. Laptop first, phone next.

Approved plan (2026-09-12): `C:\Users\HP\.claude\plans\wise-wiggling-ripple.md`.

## Acceptance criteria

### Shipped
- [x] Data bugs that would show on screen: ISO dates no longer swap day and month; an invoice
      cannot bill several customers; a second upload no longer wipes the first; a re-sent file
      no longer doubles a typed-in book's sales.
- [x] Jinja2 + HTMX + Alpine + Tailwind toolchain, assets pinned and served locally; design
      tokens, components and a style guide.
- [x] App shell: sidebar on a laptop, bottom bar with a centre "+" on a phone, Ctrl+K palette,
      assistant slide-over, dark mode. No page scrolls sideways at 360 / 768 / 1440 px.
- [x] Home on today's data: ranked "Needs you" with one action each, KPIs with sparklines,
      today, recent activity, data freshness.
- [x] **The site is the front door** — `/` sends an owner to their business and an operator to
      the Studio.
- [x] **Every section built**, 34 pages: Sales (overview, bills, customers, collections),
      Operations (record, inventory, purchases, invoices), Finance (overview, P&L, balance
      sheet, cash flow, dues, GST, reports), Team (staff, attendance, performance, branches),
      Analytics (explore, ratios, documents), Inbox (waiting, sent, brief, who gets told,
      routines), Data (add, what was read, history), Settings (business, billing, stock, access).
- [x] **Nothing links to a classic screen** — enforced by a test, as is "no page in the menu is
      still a placeholder".
- [x] Onboarding Studio: businesses by stage; profile, data map and masters working.
- [x] Documents (invoice, PDF, report pack, deck, dashboard) served under `/app/<slug>/doc/…`.
- [x] Demo profile for a bearings distributor, plus that client's own messy files, plus four
      documents in `docs/`.
- [x] `tests/test_web.py` — 34 tests over the routes, the forms, access rules and the data fixes.

### Still to do
- [ ] Data core v2 (SQLite per business) and onboarding stages 4–8: opening position, staged
      history import with review and undo, coverage and sign-off.
- [ ] The phone pass over the sections built laptop-first.
- [ ] Communication core: one Send sheet, templates, WhatsApp documents, email attachments.
- [ ] The assistant: streaming, more tools, analysis, action cards, an evaluation set.
- [ ] Continuous feeds: scheduler, email-in, watched folder, WhatsApp webhook, Tally connector.
- [ ] Cutover: retire `ui.py` / `console.py` / `modules.py`, and the operator tools that still
      use them (deployment Settings, the activity log, the staff console).

## Status: in-progress (the site is complete and is the front door; the data core is next)

## Notes / decisions

- ADR 011 — front-end stack; ADR 012 — operator-led onboarding as an eight-stage stepper.
- Site forms post to the classic handlers with `?next=/app/…`, and a middleware points the
  handler's redirect back at the site. One code path per action, and no second implementation
  to keep in step.
