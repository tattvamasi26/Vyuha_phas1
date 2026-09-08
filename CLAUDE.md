# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

"Vyuha" is an early-stage founder project: an AI/automation service for distributors and manufacturers who run their operations on Excel (dashboards, WhatsApp stock alerts, auto-generated reports, quotation generation, supply-chain intelligence like reorder points and dead-stock detection).

This repo now holds three separate things:

1. **`vyuha/` — the product.** A Python package (v0.1.0, shipped 2026-08-11) that turns an unmodified distributor Excel file into a self-contained HTML dashboard. This is the Phase 1 Foundation deliverable from the Platform Build roadmap. See "Architecture of the `vyuha` engine" below and [README.md](README.md).
2. **`vyuha_package/vyuha_dashboard.html`** — the "Vyuha Founder OS" dashboard: a self-contained HTML/CSS/JS planning app (no build step, no server, no dependencies) with six workspace sections (AI Learn, Platform Build, Business, Finance, Supply Chain, General) the founder uses to track the venture. Plus `vyuha_package/INSTRUCTIONS.md`, its usage notes. This is a *planning tool*, not the product.
3. **The Vyuha-1 Prime operating contract** (`vyuha-1-prime-bootstrap.md` plus the `requirements/` and `.claude/` scaffolding it generates) — see "Vyuha-1 Prime operating contract" below.

Phases 2 and 3 (WhatsApp/email alerts, quotation generation, per-client hosted dashboards) are not built yet.

## Commands

The engine is Python; the planning dashboard is a static file.

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -e .        # macOS/Linux: .venv/bin/python

.venv/Scripts/python -m vyuha demo --open       # messy sample workbook + its dashboard
.venv/Scripts/python -m vyuha run FILE.xlsx --client "Name" --open
.venv/Scripts/python -m vyuha check FILE.xlsx   # what was understood, no report written
.venv/Scripts/python -m tests.test_pipeline     # 19 engine tests, no pytest required
.venv/Scripts/python -m tests.test_platform     # 57 platform tests, same runner
.venv/Scripts/python -m tests.test_console      # 71 console tests, runs VYUHA_LLM=offline
.venv/Scripts/python -m tests.test_intake       # 23 intake tests, over the demo corpus
.venv/Scripts/python -m tests.test_invoice      # 19 invoice tests: tax, numbering, document
.venv/Scripts/python -m tests.test_library      # 22 tests over many files at once
.venv/Scripts/python -m tests.test_agents       # 47 agent-lane tests: gate, notify, routines
.venv/Scripts/python demo/make_samples.py       # the nine messy sample files
.venv/Scripts/python demo/make_samples.py --bulk 100   # 103 files over 14 months
.venv/Scripts/python -m vyuha_platform seed     # both demo businesses

.venv/Scripts/python -m vyuha_platform --open   # the web platform on :8000
.venv/Scripts/python -m vyuha_platform seed     # rebuild the demo workspace, then exit
```

`pip install -e .` also puts a `vyuha` console script on PATH. Dependencies are just `pandas` and `openpyxl`; there is no lint tooling. `out/` is gitignored — it holds generated workbooks and dashboards.

**Run `vyuha check` first on any new client file.** It prints which sheet was read as what, which row the header landed on, which columns were understood and which were ignored — the fastest way to catch a misreading before anyone sees the numbers. Each column carries **how** it was identified: `(matched)` for a close heading, `(guessed)` for a column with no usable heading that was read from its values, `(calculated)` for one the file did not contain at all. The last two are the ones worth opening the file over.

To open the founder-OS planning dashboard: open `vyuha_package/vyuha_dashboard.html` in a browser (double-click, or `start vyuha_package/vyuha_dashboard.html` on Windows). No server, nothing to install.

## Architecture of the `vyuha` engine

Five stages, one per module, wired by `pipeline.run()` → `RunResult`. Each stage hands the next a typed dataclass, so a stage can be tested or replaced on its own.

- **`ingest.py`** — opens .xlsx/.xlsm/.csv (.xls needs `xlrd`, which is not installed; the error message says so) and returns one `RawSheet` per visible sheet: a raw cell grid with **no header assumed**. Spreads merged-cell ranges across their full extent (`_spread_merged_cells`), drops all-blank rows/columns, and keeps `row_map` so the pipeline can still report "your header is on row 5" after trimming. Deliberately makes no decisions about meaning.
- **`schema.py`** — the canonical field vocabulary (`date`, `party`, `sku`, `qty`, `amount`, `stock_qty`, `reorder_level`, `outstanding`, …) as `FieldSpec` entries carrying `exact` aliases, `contains` fragments and `veto` fragments. Vetoes are what stop "Closing Stock" being read as a sales quantity. `NOISE_HEADERS` marks columns ("Remarks", "Narration") that must never be adopted. `TABLE_RULES` classifies a sheet as sales/stock/receivables from its fields. **Teaching the engine a new client's column name is usually a one-line alias addition here.**
- **`detect.py`** — three questions in order: which row is the header (`find_header_row` scores each candidate on text-vs-number ratio, vocabulary hits, uniqueness, and whether the rows *below* look like data), what each column means (`map_columns` scores every column×field pair then assigns greedily by descending score; `_infer_from_values` rescues headerless columns by reading their values), and what kind of table it is (`classify`). Returns a `DetectedTable`.
- **`clean.py`** — produces a `CleanTable` with canonical column names and real dtypes. Drops total/subtotal rows before they double every metric, parses the spreadsheet dialects of a number (`to_number`: `₹ 1,23,456.00`, `(4,500)` → negative, `5,000 Cr` → negative, `12%`), parses dd-mm-yyyy text dates, derives `amount` from qty × rate when it is missing, and collapses customer spellings into a `party_key` (strips M/s, Pvt Ltd, Traders; normalises `&` → `and`). Every fix is appended to `table.issues` and surfaced in the report.
- **`analyze.py`** — the value. Stacks tables of the same kind (clients split sales across twelve monthly sheets), then computes sales metrics, stock metrics and receivables ageing. The cross-table join in `_stock_movement` is the differentiator: stock ⋈ sales yields dead stock (90+ days idle, with the cash locked in it) and days-of-cover per SKU. Produces `Alert(severity, title, detail, value)` objects — **these are the intended Phase 2 WhatsApp/email payloads, so keep them self-contained.** A partial trailing month is flagged and excluded from trend alerts, so a half-finished month never reads as a revenue collapse.
- **`trust.py`** — how sure the engine is about each number, and why. `detect` scored every (column, field) pair to make its assignment — 10 for an exact alias, 5-6 for a fragment of the heading, nothing at all for a column rescued by reading its values — and then **threw the scores away**, along with `header_confidence` and `kind_confidence`, which reached `DetectedTable` and stopped there. So a figure read off a column labelled "Invoice Amount" and one reconstructed as qty × rate from a headerless sheet printed in the same weight of type, and a distributor could not tell them apart by looking. This module carries those signals through `CleanTable` and turns them into four verdicts — `read` / `matched` / `guessed` / `derived` — plus the sentence naming the evidence. `Basis.worst` is what a figure inherits: a total is only as trustworthy as the least certain column feeding it. `matched` is deliberately **not** in `NOTABLE` — "Qty (Nos)" is a heading a human reads without hesitating, and flagging it would put the caution panel on nearly every file, and a caption that always appears is one nobody reads by the third report.
- **`report.py`** — renders one HTML file with inline CSS and hand-rolled CSS bar/ageing charts, using Indian digit grouping (`money` → ₹12,34,567). **No `<script>`, no CDN, no remote images, no `src=`** — a test enforces this, because the file has to open on a phone with no internet after being forwarded on WhatsApp. That rules out webfonts *and inline SVG*, whose `xmlns` is a URL, so every chart is CSS boxes and every typeface is a system stack; the type does its work through role instead, with a monospace stack and tabular figures on every number so columns of rupees line up down the page. Rebuilt 2026-09-08 as **a light document rather than a dark dashboard** — it is forwarded, printed, read in daylight in a shop doorway and shown across a desk to an accountant, none of which a near-black app screen is good at; a dark palette follows the phone's own setting for anyone reading at night. Sections run in the order somebody needs them, not the order the pipeline computed them: a one-sentence verdict before any number, what needs a decision, **how to read these numbers**, the headline figures, then sales/stock/receivables, then the read-back (ADR 004). The third is the new one and is the point of the rebuild — a figure resting on a guessed or calculated column carries a one-word mark, the panel above names the column and says why in a sentence somebody can check against their own file, and a file that was labelled properly gets no marks at all.
- **`sample.py`** — generates the messy demo workbook: junk rows and a merged title above the header, blank spacers, a Grand Total row, ₹/comma/paren/Cr number formats, dates as text in one sheet and real dates in another, four spellings of one customer, three planted dead SKUs, one planted about-to-stock-out SKU, and a prose "Notes" sheet that must be skipped. It is both the test fixture and the demo file for prospects.
- **`cli.py`** — `run` / `check` / `demo`. `say()` exists because the Windows console is cp1252 and cannot encode ₹; it transliterates on the way out rather than weakening the report.

`tests/test_pipeline.py` covers value parsing, header detection under junk rows, column mapping, classification, total-row exclusion, derived amounts, a full end-to-end run against the sample, the self-contained-report guarantee, and that the report marks a guessed figure while leaving a cleanly-read one unmarked. The file is written to run under pytest *or* standalone, but **pytest is not installed in `.venv` and is not a declared dependency** — `python -m pytest` fails with "No module named pytest". Use `python -m tests.test_pipeline`.

## Architecture of `vyuha_platform/` (the web platform)

A FastAPI shell **around** the engine, added 2026-08-22. It imports `pipeline.run()` and
`report.render()` and never reimplements them, so anything true of the CLI is true here.
Deps: `fastapi`, `uvicorn`, `python-multipart` (+ `httpx` for tests) — installed in `.venv`
but **not yet declared in `pyproject.toml`**.

- **`auth.py`** — accounts and sessions, added 2026-08-23 when signup opened up.
  Accounts live in `vyuha_data/accounts.json`; a password is stored only as a stdlib
  `scrypt` hash over a per-account salt. Sessions are **stateless signed cookies**
  (HMAC-SHA256 over account id + issue time) keyed by a secret generated once into
  `vyuha_data/secret.key` — there is no session table, and deleting that file logs
  everybody out. `auth.current(request)` is the only sanctioned answer to "who is
  asking". `Account` also carries the workspace fork (`install` / `org_name` /
  `tenant_slug`), which used to live on `config.Settings`.
- **`store.py`** — client registry and run history as JSON at `vyuha_data/clients.json`
  (gitignored), with uploads under `vyuha_data/uploads/<slug>/` and generated dashboards under
  `vyuha_data/dashboards/<slug>/<runid>.html`. A file, not a database: at founder-operated scale
  it is easier to inspect and hand-edit, and swapping it means replacing this module only.
  `Client` carries per-client `dead_stock_days` / `low_cover_days`, plus the `owner_id` of
  the account that created it. **Every read here takes `owner_id` as a required argument**
  (`load_clients(owner_id)`, `get_client(slug, owner_id)`) so a route that forgets to scope
  is a `TypeError` on the first request rather than one business quietly reading another's
  numbers. **`delete_client` purges every per-slug store** (`store.PER_SLUG` — books,
  money, people, invoices, followups, outbox, notices, routines, plus uploads and
  dashboards), because slugs are freed on delete and globally unique: the next business
  onboarded under the same name gets the same slug and used to inherit the deleted one's
  book, staff and outbox with it. The list is written out by hand rather than imported,
  since `store` sits underneath all of those modules; a test asserts it stays complete.
  The activity ledger is the deliberate exception — append-only, so "this business was
  deleted on the 14th" stays answerable.
- **`channels.py`** — the Phase 2 alert renderers: pure `Insights -> str` functions
  (`as_whatsapp`, `as_email`) sitting beside `report.render()` rather than in a new pipeline.
  `as_whatsapp` respects a 1024-char cap by shedding entity lines first, then whole alerts
  lowest-severity-first, always keeping the dropped count honest. **Delivery is a `wa.me` deep
  link, not an API call** — it opens WhatsApp with the brief pre-typed and the founder taps send,
  so there is no Meta Business account, no BSP and no template pre-approval. Swapping in the
  Cloud API later means adding a sender here; the renderers do not change.
- **`ui.py`** — hand-rolled HTML strings (same choice as `report.py`). Dark styling.
  Unlike the client dashboard this **may** use a webfont CDN, since it is served over
  localhost; the embedded dashboard is still strictly self-contained and a test
  enforces that. `layout()` swaps the nav by account kind, and that nav is now
  deliberately short: an operator gets **Businesses / Settings**, a tenant gets
  **none at all**. Onboarding left the bar because it is a service Vyuha performs
  rather than a screen a client drives; Activity left because "where did this
  number come from" is a question about one business and now lives inside one.
  `client_page` — an 85KB tabbed page with sixty-six buttons — was deleted outright
  when `console.py` took over every job it did.
- **`sources.py`** — everything that is not a spreadsheet is *converted to a CSV first* and then
  handed to the unchanged pipeline: `.txt`/`.tsv` by delimiter sniffing, `.pdf` via its own text
  layer, and images plus scanned PDFs via **Claude vision** (`claude-opus-5`, base64 image /
  document blocks, structured output). Every conversion returns an `Extraction` carrying method
  and confidence, surfaced in the UI — a number transcribed from a photograph must never look
  identical to one typed into Excel. Vision needs `anthropic_key`; without it those uploads are
  rejected with the action required, never silently.
- **`books.py`** — for a business with no spreadsheet at all (the nursery/manure case). Keeps a
  small `Item`/`Sale` ledger per client in `vyuha_data/books/<slug>.json`, decrements stock on
  each sale. A `Sale` carries the **buyer's own WhatsApp number**, captured at the moment of sale
  because that is the only moment it is ever to hand; `customer_phones()` offers it back so a
  returning customer is never asked twice, and `channels.as_receipt()` turns the sale into a bill
  the buyer can keep. The entry form is one row in the order the words come out — what, how many,
  who, their number — with a running total, and price/date/due-date behind "More", and **writes the whole thing out as a workbook whose sheet names and headers
  `schema.py` already recognises** (Sales Register / Stock Statement / Outstanding). Typed-in
  entries and uploaded files therefore converge on the same engine, same dead-stock join, same
  alerts. `app._rebuild_from_book()` re-runs the pipeline after every edit.
- **`ledger.py`** — append-only JSONL at `vyuha_data/activity.jsonl`. Every onboard, file,
  conversion, run, send and export is logged, so "where did this number come from" is one screen
  away (`/activity`, filterable by client and event). One file still holds every account's
  history — it is append-only and must stay that way — so each `Entry` carries an `owner` and
  `read(owner, ...)` / `counts(owner)` demand it, same contract as `store.py`.
- **`exports.py`** — PDF (reportlab), PPTX (python-pptx) and a framed email + SMTP sender, all
  rendered from the same `Insights` as the dashboard so they cannot disagree. **The PDF uses
  `Rs.` because the Helvetica core fonts have no ₹ glyph** — precisely the split `vyuha/fmt.py`
  exists to make explicit.
- **`config.py`** — **deployment-level** settings and credentials from `vyuha_data/config.json`
  + env vars, with `whatsapp_live` / `vision_live` / `email_live` capability probes. Secrets are
  write-only in the UI (masked on render, blank means "keep"). One WhatsApp sender, one SMTP
  account, one Claude key for the machine; anything that varies per logged-in account lives on
  `auth.Account` instead. `install` / `org_name` / `tenant_slug` moved there on 2026-08-23.
- **`console.py`** — **six features on one page** (`/c/<slug>/console`), added
  2026-08-30: stock, ask, follow-ups, money, deck, people. One request renders
  all six; switching panels is a class toggle, not a round trip, which is why
  the nav can carry live counts ("3 overdue") — the whole reason somebody opens
  a panel they were not already thinking about. Mutating forms POST and redirect
  with `?panel=` so the page reopens where it was left; reads that produce
  something transient (an answer, a deck outline) render the page directly
  instead, because a redirect would throw the result away. Console-only CSS
  lives in `console.EXTRA`, not `ui.CSS`, so this file owns its own look and the
  other lane can edit `ui.py` without ever meeting a conflict here.
- **`llm.py`** — the single entry point for every Claude call outside
  `sources.py`. Buys three things: a **disk cache** (pre-warm it and a live demo
  never waits on the API), an **offline mode** (`VYUHA_LLM=offline` refuses to
  call out, so a caller with a fallback still answers), and **errors as values**
  — `ask()` never raises; a missing key, a rejected key, a rate limit and a
  refusal all return an `Answer` with `ok=False` and something a human can act
  on. Cached on the whole request (model + system + prompt + schema), so
  changing any of them is a different question.
- **`agent.py`** — the business agent. Two rules: **the model never sees the raw
  book** (`facts()` builds a compact summary of already-computed totals, so
  every number in an answer came from Python, not from a language model), and
  **there is always an answer** — `rules()` handles what an owner actually asks
  by pattern matching over the same facts, so no key and no network still
  answers. `Reply.source` says which path answered, because a rule-based answer
  and a reasoned one are different claims. A guard refuses speculation
  ("what will the monsoon do to my sales next year") *before* the keyword
  branches, since that question contains "sales" and would otherwise be answered
  with last year's revenue — which reads as a forecast.
- **`money.py`** — cash flow, which needed the half the product lacked. `Sale`
  already recorded everything coming *in*; this owns exactly one new thing, the
  `Expense`, and computes the statement by putting it beside the sales that
  already exist. Keeps two distinctions apart that an owner cares about far more
  than an accountant does: **earned vs collected** (a credit sale is revenue,
  not cash) and **committed vs paid** (an unpaid purchase is a bill, not an
  outflow). `position()` therefore reports four numbers, not two.
- **`followup.py`** — who to chase. The queue is **computed from the book every
  time, never stored**: a stored list means the day a customer pays, the
  reminder to chase him is still sitting there, and one wrong chase costs more
  than ten right ones earn. Only the *decision* persists, keyed on a stable
  `key`, so "dismissed" survives the queue being rebuilt. `from_quotes()` takes
  the list rather than importing `quotes.py` — that module is the other lane's
  item 06 and does not exist yet, and this one must not fail to import for it.
- **`people.py`** — branches and staff, deliberately **optional and additive**.
  `Sale.branch` / `Expense.branch` default to empty, so a business that never
  creates a branch sees nothing about branches anywhere and every existing row
  stays valid. Rows written before branches existed report under **Unassigned**
  rather than being attributed to whichever branch happens to be first —
  guessing there would corrupt the one number the feature exists to produce.
  `Staff` is a directory, not a login: real identity stays in `auth.py`.
- **`decks.py`** — a deck from a sentence. Separates *what to say* (an `Outline`
  Claude writes from a brief plus the same facts the agent reads) from *how it
  looks* (`to_pptx` / `to_pdf`, which know nothing about where the outline came
  from). That split is what makes the offline path honest rather than degraded:
  `_fallback()` builds a real outline with no model and renders through exactly
  the same code. Every figure is a **string already formatted by Python** — the
  model selects and arranges, never calculates.
- **`demo_seed.py`** — `python -m vyuha_platform seed` builds **Shree Agro &
  Hardware, Belagavi** from nothing: 20 items, 2 branches, 6 staff, ~200 bills
  over nine months, 16 expenses across 7 heads. Every beat's evidence is
  planted deliberately (4 below reorder, 1 out, 3 never sold, 3 overdue bills at
  different ages, 1 customer gone quiet), and a fixed `SEED` plus dates relative
  to today make it **deterministic** — the same command on two machines gives
  the same numbers, and re-running it after a messy rehearsal puts it back.
  Idempotent: it wipes the account's workspaces first. Never demo off live data.
- **`modules.py`** — **the seven modules, as data.** The founder's own structure,
  drawn on paper, and a better map than what the code had grown into: the previous
  four screens were named after *features that happened to exist*, and these are
  named after **jobs somebody has**.

      Desk · Dashboard · Financials · Operations · People · Messages · Data

  Messages carries four tabs — Send a brief, **Waiting** (drafts, and anything the
  gate is holding for approval), **Who gets told** (the Notification Agent made
  visible: who Vyuha *would* warn, before it warns them, plus who it already has)
  and Sent. Setup gained **Routine jobs**. The Messages nav badge counts what is
  waiting *on a person*, not what exists — a badge that never reaches zero is a
  badge people stop reading.

  Two rules keep it from rotting back into a feature list. **A module is a job and
  its tabs are steps within it** — a screen that cannot answer "which job is this
  part of" gets a home inside an existing module rather than a tab of its own. And
  **nothing appears in two modules**: a figure lives where the job that acts on it
  lives and every other screen links to it, which is why invoices are Operations
  and not Financials. `SETUP` is registered in `BY_KEY` but is deliberately **not**
  in `MODULES` — nothing on it is part of running the business, and putting it in
  the module row would say that it was. `MOVED` maps every old address to its new
  one and `resolve()` lands an unknown module on the Desk, so a stale bookmark
  reaches the product rather than an apology. `visible()` hides Data from a
  business that types its entries, because a screen that only ever says "nothing
  here" teaches somebody to stop looking at the nav.
- **`console.py`** — draws all of it. `render()` is a **single dispatch**: it loads
  the state every screen needs once, then looks the tab up in `_TABS`
  (`"financials.position"` → `_fin_position`). Letting each route decide what to
  load is how two screens end up disagreeing about the same number. `_TABS` is
  declared at the **foot of the file** so it can name handlers defined anywhere
  above without ordering them by hand.
  * **`shell()` renders two levels of nav** — the module row, then that module's
    tabs — and nothing else. An earlier build had a tab row *and* an in-body
    section chooser inside Financials, which is two rows of navigation for one
    module and exactly how a product starts feeling like a control panel.
  * **The Desk is the landing**, and is a *ranked list of decisions*, not tiles.
    `today.py` computes them; severity gates the order and money ranks within it,
    because sorting on money alone put customer-mix above an empty shelf.
  * **Ask is the bar in the header of every screen**, and its answer returns on the
    screen it was asked from. The agent is not a module: a panel has to be
    remembered, and a box in front of somebody does not.
  Each tab renders on its own request. The build before last put six panels in one
  141KB document and toggled them with JavaScript — instant to switch and slow at
  everything else, which is the wrong trade once a screen has content.
- **`gate.py`** — **the one way out of the system.** Every message and document
  leaves through `submit()`; `whatsapp.send` and `exports.send_email` refuse a
  caller that does not hold the key this module owns, so forgetting the gate
  fails loudly at the boundary instead of quietly putting a wrong number in front
  of a customer. That refusal is the point — a comment saying "always go through
  the gate" is a convention, and the architecture asks for a boundary. Three
  dispositions: `AUTO` (WhatsApp alerts to the business's own owner — worthless
  tomorrow morning), `DRAFT` (**every** email, whatever it contains, because
  email reaches accountants and banks where a wrong message is a document), and
  `APPROVAL` (money leaving, or a filing — it waits). **The classification is on
  the action, not the channel**: a payment reminder is money *arriving* and goes
  out like any alert, while a GST summary waits even though it travels the same
  wire. An unprovisioned channel degrades `AUTO` to `DRAFT` rather than reporting
  a failure every morning for something that is about to go out fine by hand.
- **`orchestrator.py`** — **one per client tenant, not one per platform.** Not a
  performance decision: config, schedules and the audit trail are isolated per
  client so a bespoke build can later be lifted into a shared platform without
  re-architecting. It owns four things — schedule (`tick()` is called on request;
  there is no daemon, so opening the Desk is this deployment's clock, and
  `last_fired` makes that idempotent), retry (bounded, and never in the same tick
  as the attempt), audit (into `ledger`, never a second log file), and **the gate
  key** — `approve()` is the only path to `gate.release()`, so an approval always
  carries the name of whoever granted it. `context()` is public because the
  console reuses it: a screen and a scheduled brief must never quote different
  numbers for the same morning. Each tick fires due routines *and* runs the
  Notification Agent, because a shelf that empties at eleven must not wait until
  tomorrow's brief.
- **`routines.py`** — **configuration, not code.** A routine names who it is for,
  when it fires, which `SECTIONS` go in it, and nothing else; every section reads
  from an agent that already exists. Adding "a Friday stock summary for the
  purchase head" is a row in a JSON file. If a client request means writing a new
  agent, the request was modelled wrong.
- **`agents.py`** — **the sixteen agents, as data**, and the one rule worth
  enforcing mechanically. The architecture spec (`vyuha-agent-architecture.md`,
  kept outside the repo) asks that each agent carry an explicit read/write
  contract "in code, not implicit", so each `Agent` names the stores it may touch
  and `check()` reads those declarations back. The rule it enforces is **the
  backend never surfaces**: nothing past the pipeline may read the raw or
  cleaned-but-unclassified store. A test proves the checker is not vacuous by
  putting an illegal agent in the roster and insisting it is caught. This is
  deliberately data and not a base class — fourteen of the sixteen agents already
  existed as working modules written before the spec was drawn, and what was
  missing was the *map*, not an ABC. `implemented_by` is the honest column:
  several agents share a module, because the lanes are jobs rather than files.
- **`notify.py`** — **the Notification Agent**, the one box in the flow diagram
  with nothing behind it. `Tax / Operations / Invoicing → Notification →
  Communication`: the product could already tell that a shelf was empty and could
  already send a WhatsApp, and had no answer to *whose phone this lands on*.
  Everything went to the business's own number, which meant the manager found out
  about the empty shelf when the owner told him. Four rules: **it computes
  nothing** (every event comes from `today.findings()` or `tax.events()`, so a
  notification cannot disagree with the screen it points at); **only what somebody
  can act on tonight** (`PUSHED` is critical and warning only, and `NEVER_PUSHED`
  drops "Vyuha has nothing to read yet" — as a Desk item that is the most
  important thing on an empty workspace, as a WhatsApp to a new client it is a
  complaint about our own emptiness); **nothing is said twice** (the queue is
  recomputed every tick and never stored, exactly as `followup.py` does it — only
  the *telling* persists, so a cooldown can hold its tongue); and **it never
  sends**, handing to `gate.submit()`. `AUDIENCES` maps a finding's existing tag
  to the roles that own the problem, and **the business's own number stands in for
  Owner** — almost nobody adds themselves to their own staff list.
- **`tax.py`** — **the Tax & GST agent**: liabilities *and* filing dates. The
  liability was already computed, inline, inside the Financials screen; the filing
  dates were computed nowhere, which is why the arrow into the Notification Agent
  had nothing travelling down it. A tax agent that cannot say when a return is due
  has no event to raise. `liability()` is now the single answer and `_fin_taxes`
  renders it rather than deriving it — the moment a second caller wanted those
  figures, computing them twice meant a phone and a screen that could disagree.
  Due dates are the **standard monthly cadence** (GSTR-1 on the 11th, GSTR-3B on
  the 20th, each covering the month before); `SCHEME_ASSUMED` says so out loud
  because a business on the QRMP quarterly scheme has different dates, and
  guessing silently is how somebody misses a deadline while being told they had
  nine days. **This is what finally makes the gate's `APPROVAL` disposition real**
  — it had been declared since `gate.py` was written and no caller ever produced
  one, so the rule that anything touching a filing waits for a human had never
  once fired in the running product.
- **`today.py`** — what needs a decision, ranked by what it costs to ignore. Every
  finding was already being computed and was sitting one click inside a different
  panel, which is why nobody found any of them. A business that sends files has an
  empty `Book` by definition, so its findings come from the last `Run`'s alerts
  instead — reading only the book is why an uploaded file used to leave Today
  saying "nothing to read yet" immediately after successfully reading one.
- **`finance.py`** — the statements a CA prepares: P&L, cash flow, a working
  balance sheet, both ageing schedules, eight ratios, concentration, monthly trend,
  cost heads as a share of turnover, break-even. Accrual and cash are reported
  side by side and never blended, and `balance_sheet()` **declares what it cannot
  see** rather than omitting it — the Balance sheet tab prints those assumptions
  under the statement, because a trading position taken to a bank as a filed one
  is worse than no statement at all. Financials is **one statement per tab**
  (Balance sheet · Profit & loss · Cash flow · Taxes · Analytics) with the four
  headline numbers on every one; eleven statements on a single page is a filing
  cabinet tipped onto the floor. Taxes computes output GST **from invoices
  actually raised**, never from sales — a sale with no invoice collected no tax —
  and shows input credit as a labelled *estimate*, because the expense ledger does
  not record supplier GSTINs. It refuses to be a filing document.
- **`analysis.py`** — one general `query_sales` (group by any dimension, filter on
  any combination, measure revenue/qty/margin/bills) plus stock, customer, item and
  period-comparison queries. This is what the agent calls; nothing here touches a
  model, so a wrong answer is an arithmetic bug rather than a prompt.
- **`invoice.py` / `invoice_render.py`** — real tax invoices: per-line GST,
  CGST+SGST within a state against IGST across one (frozen at issue), HSN, amount
  in words, and **numbering per financial year that is never reused**. Rendering is
  split from arithmetic so a template change cannot alter a total.
- **`deck_render.py`** — a 16:9 presentation with slide *kinds*: a figure takes the
  whole screen, a trend gets an SVG chart drawn from `finance.py`'s own series, a
  comparison gets two columns. Bullets are the fallback, not the default, which is
  what made the first version text on a rectangle. There is no Deck screen — you
  ask the agent for one.
- **`people.py`** — branches, staff, targets and commission, a daily register where
  an unmarked day is a forgotten register rather than unpaid leave, and stock
  transfers that move location without touching revenue.
- **`atomic.py`** — every JSON write goes through it. `write_text` truncates then
  writes, so a browser tab open beside a test run corrupted the client registry and
  blanked every private screen. Temp-then-`os.replace` under a lock, retried through
  the transient Windows locks OneDrive's sync client takes.
- **`app.py`** — routes: `/` (landing when signed out, portfolio when signed in),
  `GET|POST /signup`, `GET|POST /login`, `POST /logout`, `POST /install`, `/onboard`, `/setup`,
  `/settings`, `/activity`, `/c/{slug}`, and `/c/{slug}/{module}` +
  `/c/{slug}/{module}/{tab}` (declared **last**, since FastAPI matches in
  definition order and a path parameter that broad would otherwise swallow
  `/dashboard`, `/cover`, `/deck/view` and every export; the module route just
  calls the tab route with the tab blank, so there is one code path),
  `POST /c/{slug}/upload`, `POST /c/{slug}/book/item|sale`,
  `/c/{slug}/export/{pdf|pptx|html}`, `POST /c/{slug}/email|whatsapp|delete`,
  and the console block (`# ---- vishak`) at the foot of the file:
  `/c/{slug}/console`, `POST /c/{slug}/ask|followup|expense|deck|branch|staff`,
  `POST /c/{slug}/stock/{receive|count|reorder}`, `GET /c/{slug}/deck/{pptx|pdf}`,
  and the gate/schedule block: `POST /c/{slug}/outbox/{id}/{send|cancel|sent}`,
  `POST /c/{slug}/routine` (+ `/{id}/{toggle|delete}` and `/run`).
  Every console handler starts with `_console_client()`, which resolves and
  authorises in one step. `outbox/{id}/send` goes through
  `orchestrator.approve()`, never `gate.release()` — a route holds no key.
  `outbox/{id}/sent` is separate and deliberately so: with no provider
  connected the operator taps a `wa.me` link and sends from their own phone,
  and calling the release path would attempt an impossible delivery and log a
  failure for a message that actually went.
  A single `require_login` **middleware** closes everything outside `PUBLIC =
  {"/", "/login", "/signup", "/logout"}`, so a route added later is private by default —
  the safe direction to forget in. Handlers take the account via
  `Depends(_acct)` rather than re-deriving it.

- **`theme.py`** — per-trade accent colour and backdrop. As of 2026-08-24 each trade carries a
  **photograph** from `vyuha_platform/static/img/` (originals in `Project V/Images/Vyuha/`), with
  the original generated SVG kept alongside as `fallback` for any trade without one.
  `theme.HERO` is the landing page's own image, named separately so changing a trade's photo
  never silently changes the front page. `theme.guess()` infers the trade from the business name
  so nobody picks twice. A client's own uploaded cover photo (`/c/<slug>/cover`) still wins over
  both. **These are platform assets only** — the generated client dashboard never references
  them, and a test asserts `/static/` appears nowhere in it, because a dashboard forwarded on
  WhatsApp has no server to ask.

## Accounts, and the flow through the product

Signup is **open**: anyone reaches the landing page at `/`, creates an account, and gets their
own workspace that no other account can see. The whole journey, wired 2026-08-23:

```
/ (landing) --> /signup --> choose_install --> /setup or /onboard --> /c/<slug>
     \-------> /login --------------------------------------------------^
```

Isolation rests on two things and nothing else: the `require_login` middleware in `app.py`
(private by default), and the required `owner_id` argument on every `store.py` read. A URL
belonging to another account renders the same "no longer exists" page a typo would, so a slug
cannot be used to probe which businesses exist.

**But a login form is the wrong shape for the person the product is aimed at** — a shop owner
with one phone, no email habit, and no wish to remember a password for the tool their supplier
set up. So there is a second way in, added 2026-08-24: the operator mints a **private link plus a
4-digit PIN** (`POST /c/<slug>/share`) and sends it over WhatsApp. Two halves make one key — the
token nobody can guess, and the PIN that makes a forwarded message harmless. After the PIN the
device is remembered for thirty days, so the owner taps the link and is simply in.

`auth.Guest` is the principal this creates, and it is **deliberately shaped to quack like a
tenant `Account`**: its `id` returns the *operator's* account id, so every `store`/`ledger` query
written for accounts scopes correctly with no special case, and `is_tenant` is True, so the
existing operator/tenant guards already close the portfolio to it. The only place the difference
matters is deployment credentials, which ask `is_guest` — `_deny_guest()` closes `/settings`,
client deletion, and re-sharing. The PIN is stored only as a scrypt hash and shown to the
operator exactly once, when minted; a lost PIN means a new link, never a lookup. Revoking
(`POST /c/<slug>/share/revoke`) kills the remembered device immediately, because `auth.current()`
re-reads the invite on every request.

`auth.delete()` exists but has **no route** — a business does not get to delete itself
out from under its own data. It is there so the test suites can clear up
their throwaway accounts, which they previously left behind: a full run used to
add eight accounts to `accounts.json` forever, and the master console listed
every one of them as a real customer.

**Wrong PINs cost time.** After `auth.PIN_TRIES` (5) failures the link stops answering for
`auth.PIN_LOCKOUT` (15 minutes) — turning a 10,000-guess sweep into roughly a month of waiting.
The counter lives on the `Invite` record rather than in memory, so a restart does not forgive it,
and a correct PIN clears it. While locked the gate renders **no input at all**: offering a form
certain to be refused just invites more guessing. A locked link still names the business, which is
deliberate — the owner has to be able to tell the link is theirs — so tests assert the *workspace*
was not reached rather than that the name is absent.

**Cookies are `secure` when, and only when, the connection can carry it** (`app._over_https()`
reads `X-Forwarded-Proto` first, then the request scheme). Setting it unconditionally would mean
no session at all over plain `localhost`, which the same build still serves.

**Slugs are globally unique**, not per-account, because they name directories on disk
(`uploads/`, `dashboards/`) that are not partitioned by owner. Two accounts onboarding the same
business name give the second one `<slug>-2`.

## Master accounts — Vyuha's own staff

`account.role == "master"` is a third principal, added 2026-08-25. Masters sign in with a
**username** rather than an email, through a link on the ordinary login (`/login?master=1`) rather
than a section of their own — staff are not a part of the product customers should have to look at.
`auth.ensure_masters()` seeds them at import, idempotently by username, so a fresh clone always has
a way in and a password changed later survives every restart. Credentials come from
`VYUHA_MASTERS` (`user:pass,user:pass`) when set; the built-in pair is a day-one default and is
meant to be changed.

A master sees every workspace at `/master` — grouped by owning account, with a health verdict per
client (`ui._health`) answering "is anything wrong here" before "what are their numbers". They can
open any client and fix it while the owner is on the phone. Three rules make that safe:

- **`store.all_clients()` / `store.find_client()`** are the only unscoped reads, named so they
  cannot be reached for by accident while meaning `load_clients(owner_id)`.
- **Every cross-account open is logged** as `master.viewed` into *that client's own* trail, so
  support access is visible to the account it touched rather than being a silent back door. The
  workspace also renders a support banner while a master is inside it.
- **Writes are attributed to the workspace's owner, never the master** — `store.add_run`,
  `delete_client` and `create_invite` all take `client.owner_id`. A support visit must never
  silently reassign somebody's data.

## Operator vs tenant - the product boundary

`account.install` is chosen once, on the screen straight after signup, and is **not** an
editable preference, because flipping it would change who can see what:

- **`operator`** - an account that manages a portfolio: onboarding, every client's activity.
  This is Vishak's account.
- **`tenant`** - an account that *is* one business. Exactly one workspace, named by
  `account.tenant_slug`. No portfolio, no onboarding, no other business's data, and no
  awareness that any other exists. Their setup screen is about *their own operation* (business
  name, trade, how they keep records) - never about clients.

Enforcement is in `app.py`: `_deny_tenant()` closes the operator-only routes, and `client_page`
refuses any slug other than the tenant's own. `_tenant_client()` is deliberately strict - an
account with no `tenant_slug` shows setup rather than adopting whatever client happens to exist.
Tests cover the boundary in both directions: a tenant cannot reach another workspace by URL, and
one account cannot see or reach another account's client.


**Onboarding is deliberately two fields** — business name, and optionally a WhatsApp number.
Contact, email, industry and thresholds live on the client's own Details tab and may never be
filled in. The one other choice is `data_mode`: `upload` (they send files) or `books` (they keep
none, so you get entry forms instead of a drop zone).

**Known wart:** `analyze.py` holds its thresholds as module constants, so honouring a per-client
value means `app._thresholds()` swaps them for the duration of one run behind a `threading.Lock`.
That is process-global state. The clean fix is threading a `Thresholds` object through
`analyse()` — do it before this ever serves more than one operator.

## Engine changes that the platform depends on

- **`Alert.code` and `Alert.entities`** (`analyze.py`) — added 2026-08-22, both keyword fields
  with defaults so the seven positional `Alert(...)` call sites and all 13 tests were unaffected.
  `code` (`dead_stock`, `below_reorder`, `overdue_ar`, `stockout_risk`, `out_of_stock`,
  `revenue_drop`, `concentration`) is a stable machine identity so channels dispatch on it
  instead of parsing English out of `title`; `entities` is the structured SKU/party list that
  `detail`'s prose bakes in.
- **`fmt.py`** — Indian digit grouping, extracted so it is shared. `report.money()` was emitting
  the HTML entity `&#8377;`, which leaked literally into text channels. Each renderer now supplies
  its own symbol: `fmt.RUPEE_HTML` for the dashboard, `fmt.RUPEE_TEXT` for WhatsApp/email.

## Architecture of `vyuha_dashboard.html`

Everything lives in one file: inline `<style>`, inline HTML sections, inline `<script>`.

- **State**: a single global `state` object holds all data for every section (`state.ai`, `state.platform`, `state.biz`, `state.finance`, `state.supply`, `state.general`). Roadmap sections (`platform`, `biz`, `finance`, `supply`) share the same shape: `{ phases: [{ id, name, timeline, color, tasks: [{ id, text, done, note }] }], nextPhaseId, nextTaskId }`.
- **Rendering**: no framework — each section has a `render*()` function that wipes and rebuilds its DOM container from `state` (`renderWeek`, `renderVideos`, `renderNotes`, `renderGeneral`, and the generic `renderPhases()` used by platform/biz/finance/supply). `renderAll()` re-renders everything and is called after any state mutation that isn't handled locally.
- **Navigation**: `switchSection()` toggles which `.section-view` is visible, updates the accent color (`setAccent()`) and page header text (from the `PAGE_META` map), and re-renders.
- **Mutations**: task/video/day toggles and "add" functions (`addVideo`, `addNote`, `addPlatformTask`/`addBizTask`/`addFinTask`/`addSupTask` → shared `addTaskToSection()`, `addGenTask`) mutate `state` directly, then call the relevant render function. New roadmap phases are created on the fly when a task is added under a phase name that doesn't exist yet.
- **Persistence**: `saveAll()`/`loadState()` use `window.storage` (a key-value API only available when this HTML is rendered as a Claude.ai Artifact) to persist the entire `state` object under the key `vyuha_state`, with a `localStorage` fallback when `window.storage` is unavailable (i.e. when the file is opened as a plain local HTML file). The Reset button (`clearSection()`) is currently a stub — it only confirms and does not actually clear data.

## Vyuha-1 Prime operating contract

`vyuha-1-prime-bootstrap.md` is a paste-once operating prompt that turns the agent into "Vyuha-1 Prime", a plan-first orchestrator that delegates rather than writing code itself. Its first-run bootstrap was executed on 2026-08-04 and produced:

- **`requirements/` — the declared source of truth.** `00-charter.md` (filled in 2026-08-11: what Vyuha is, why, success criteria, out of scope), `01-features/` (one `NN-slug.md` per feature; `01-excel-to-dashboard.md` covers the engine, and `README.md` holds the naming conventions), `02-decisions.md` (ADR-lite, append-only; 001 = why the bootstrap landed here rather than in the parent folder, 002 = Python/pandas, 003 = rule-based detection over an LLM, 004 = show the client what we read), `03-token-log.md` (500k budget split 60/30/10 into 300k development / 150k iteration / 50k research), `99-changelog.md`.
- **`.claude/agents/`** — `planner`, `developer`, `tester`, `reviewer`. These drive the contract's 8-step loop (read → rough plan → final plan → pick one → develop → test → review → ship), where steps 2 and 3 are the only points the agent waits on the owner. Note they only resolve for sessions started **inside `Vyuha_phas1/`**; a session started from the parent `Project V` folder will not see them.
- **`.claude/skills/`** — `plan-drafting`, `requirements-update`, `test-protocol`, `token-budget-check`.
- **`.claude/hooks/`** — four Python scripts plus `hooks.json`. **These are currently inert**: Claude Code reads hook config from `.claude/settings.json`, not `.claude/hooks/hooks.json`; the event names in that file (`before_tool_use`, `after_tool_use`, `after_file_change`) are not real Claude Code events; and `pre-deploy.py` reads a `HOOK_TOOL_INPUT` environment variable, whereas real hooks receive their payload as JSON on stdin. Treat them as documentation of intent until they are rewired.

## Commands (Vyuha-1 Prime)

There is no lint tooling; tests are the standalone suite described under "Commands" above. The `.claude/hooks/` scripts are plain Python 3 (`python .claude/hooks/<name>.py`) and are no-ops or stderr nudges as written — they are unrelated to the engine's own test suite.

## Tooling notes

A Stop hook (`.claude/settings.json`) checks whether any tracked file changed since the last turn and, if so, prompts Claude to review this CLAUDE.md before finishing. `autoCompactEnabled` is on, so context compacts automatically as it fills. That Stop hook lives in the **parent** `Project V/.claude/settings.json`, not in this repo — this repo's `.claude/` currently holds only agents, skills, and the inert hooks described above.
