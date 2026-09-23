# Changelog

## 2026-08-04
- shipped: Vyuha-1 Prime first-run bootstrap — `requirements/` scaffold, 4 sub-agents, 4 skills, 4 hooks
- tests: n/a (scaffold only, no executable product code)
- reviewer notes: pending — charter not yet defined, so nothing substantive to review

## 2026-08-11
- shipped: `vyuha/` v0.1.0 — the Excel → dashboard engine (feature 01). Five stages
  (ingest / detect / clean / analyze / report), a CLI (`run`, `check`, `demo`), and a
  messy sample-workbook generator used as both the test fixture and the demo file.
- shipped: charter filled in; feature 01 written up; ADRs 002–004 recorded.
- tests: 13 tests in `tests/test_pipeline.py`, all passing — value parsing, header
  detection under junk rows, column mapping, sheet classification, total-row exclusion,
  derived amounts, a full run over the messy sample, and a check that the report makes
  no external requests.
- verified by hand: `python -m vyuha demo` reads a 4-sheet messy workbook, finds the
  header on row 5 under three junk rows and a blank, classifies all three data sheets
  correctly, skips the prose sheet, and raises 4 alerts (dead stock, below reorder,
  overdue receivables, days-of-cover).
- reviewer notes: not yet validated against a real client file — that is the next gate
  before this can be used in a prospect demo.

## 2026-09-14
- shipped: UX rewire Phase 1, "First look" (feature 02), on branch `feature/ux-rewire`, running
  beside the classic screens: a Jinja2 + HTMX + Alpine + Tailwind site at `/app/<slug>` (sidebar,
  phone bottom bar, Ctrl+K palette, assistant slide-over, dark mode, and Home on today's data),
  the Onboarding Studio at `/studio` (stages 1–3 working, 4–8 described) and `/styleguide`.
  ADRs 011–012.
- fixed: ISO dates no longer swap day and month (`vyuha/clean.py`, `books.to_workbook`); an
  invoice refuses sales from different customers; a second upload no longer wipes the first; a
  re-sent file no longer doubles a typed-in book's sales.
- tests: 282 passing across 8 suites — new `tests/test_web.py` (22); pipeline 19, platform 57,
  invoice 19, library 22, intake 23, agents 49 and console 71 all green.
- verified: Home, Studio, data map, assistant panel, phone "More" sheet and dark mode captured
  with Playwright against the running app on `127.0.0.1:8000` at 360, 768 and 1440 px, and all
  16 new pages checked for sideways scroll at each width (the check caught the Studio's
  Previous/Next footer overflowing a phone; fixed).
- reviewer notes: waiting on the owner's Phase 1 review; nothing committed yet.

## 2026-09-18
- shipped: **the site is the product's front door**. Signing in lands on it, all 34 pages are
  built — Home, Sales, Operations, Finance, Team, Analytics, Inbox, Data, Settings, plus the
  Studio and the style guide — and nothing on it links to a classic screen. Two tests enforce
  exactly that: no page in the menu may still be a placeholder, and no page may contain
  `href="/c/`.
- shipped: site forms reuse the classic handlers with `?next=/app/…` (a middleware points the
  redirect back), documents are served under `/app/<slug>/doc/…`, and marking the register and
  setting a target got the routes the classic app never had.
- shipped: the bearings demo — `python -m vyuha_platform seed-bearings` builds Shakti Bearings
  & Power Transmission (361 bills, ₹24.3 lakh, 27.9% gross, 17 GST invoices across both tax
  shapes), and `demo/make_bearings.py` writes that client's own messy files.
- shipped: `docs/` — what Vyuha does, using it fully, the onboarding runbook, and a demo script
  whose figures are the ones the seed produces.
- tests: **294 passing** across eight suites — web 34, platform 57, console 71, agents 49,
  invoice 19, library 22, intake 23, pipeline 19.
- verified: every page captured at 1440 px; Home, the data map and the section pages also at
  360 and 768 px with a sideways-scroll check.
- reviewer notes: the phone pass over the new sections, and the data core, are next. Nothing is
  committed — the work sits on `feature/ux-rewire`.

## 2026-09-22
- shipped: `docs/runbooks/onboard-from-scratch.md` and the **Onboarding Workbook** artifact —
  every Studio field and option, the order imports have to go in, and a practice business to
  rehearse the whole thing on.
- shipped: `demo/make_practice.py` -> `demo/samples/practice/` — Deshpande Electricals &
  Motors, Dharwad: a business to onboard from an empty workspace, in a trade neither demo
  uses so nothing collides. Seven files, two of them traps on purpose.
- fixed: **the dues file in both demo packs was read as sales, not receivables.**
  `TABLE_RULES` requires an `OUTSTANDING` field and the column was headed "Amount", so the
  whole file landed as extra sales with no ageing and no collections queue. Renamed to
  "Outstanding Amount"; `vyuha check` now reports `[Receivables]` with Rs 1.12 L (bearings)
  and Rs 1.52 L (practice) overdue where it previously reported none at all.
- fixed: `demo/make_bearings.py` crashed on the rupee sign when its output was piped
  (cp1252) — after every file had already been written. Both generators now transliterate
  through a local `say()`, the same reason `vyuha/cli.py` has one.
- found, documented, not fixed: a purchase register imports as **revenue** (there is no
  purchases table kind — measured at +102% over the bearings sales register), and no importer
  ever sets item cost (`library.materialise`), so a file-only onboarding reports zero gross
  margin and values stock at the selling price. Both are written up as traps in the runbook
  and both belong to the data core.
- tests: intake 23 and library 22 — the two suites that read `demo/samples/` — both green.

## 2026-09-23
- shipped: **the guided demo** (feature 03) on branch `feature/guided-demo` — one button that
  walks a room through the whole product, live. It creates a business from nothing, answers the
  eight-record data map, fills the profile and the staff list, puts the practice pack's stock,
  sales and outstanding files through the **real ingest path**, types the costs in — the beat
  where gross margin stops being zero — and then walks 30 steps across Home, Sales, Operations,
  Finance, Team, Analytics, Inbox and Settings, carrying the words to say at each one.
- `demo_tour.py` holds the script as data (30 steps, 7 chapters, 8 actions), the way `agents.py`
  and `routines.py` do; `web/routes/demo.py` serves `/demo`, the script as JSON, the actions and
  the reset; `static/app/js/tour.js` and `tour.css` are the overlay, with no new dependency.
- There is **no demo mode inside the product**: every action calls the function the real screen
  calls, so what a prospect watches is what they would get. The demo business is resolved by name
  under the presenter's own account, so nothing can touch a business somebody trades on.
- The presenter is never trapped: Pause (or Escape) restores the app exactly as it was and leaves
  a Resume button, every action is optional so you can type it yourself, stepping off the script
  is allowed and offers the way back, and `POST /demo/reset` deletes the demo business so a
  rehearsal that went sideways is one click from clean.
- fixed: the practice pack's sales register folded the item code into the description, so every
  sold line became a *different* item from the stock statement's and the shelf read 45 items
  where there are 24. The code now travels in its own column.
- tests: **51 green** — new `tests/test_demo.py` (17), including one that fails the build if any
  step points at a page that does not exist, and `tests/test_web.py` (34) after the shell changes.
- verified by driving all 30 steps over HTTP against the running app: every action succeeded,
  every page returned 200, every spotlight target was present, and reset left no trace.
