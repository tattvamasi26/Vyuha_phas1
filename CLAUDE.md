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
.venv/Scripts/python -m tests.test_pipeline     # 13 engine tests, no pytest required
.venv/Scripts/python -m tests.test_platform     # 57 platform tests, same runner
.venv/Scripts/python -m tests.test_console      # 41 console tests, runs VYUHA_LLM=offline
.venv/Scripts/python -m tests.test_intake       # 23 intake tests, over the demo corpus
.venv/Scripts/python demo/make_samples.py       # regenerate the nine messy sample files

.venv/Scripts/python -m vyuha_platform --open   # the web platform on :8000
.venv/Scripts/python -m vyuha_platform seed     # rebuild the demo workspace, then exit
```

`pip install -e .` also puts a `vyuha` console script on PATH. Dependencies are just `pandas` and `openpyxl`; there is no lint tooling. `out/` is gitignored — it holds generated workbooks and dashboards.

**Run `vyuha check` first on any new client file.** It prints which sheet was read as what, which row the header landed on, which columns were understood and which were ignored — the fastest way to catch a misreading before anyone sees the numbers.

To open the founder-OS planning dashboard: open `vyuha_package/vyuha_dashboard.html` in a browser (double-click, or `start vyuha_package/vyuha_dashboard.html` on Windows). No server, nothing to install.

## Architecture of the `vyuha` engine

Five stages, one per module, wired by `pipeline.run()` → `RunResult`. Each stage hands the next a typed dataclass, so a stage can be tested or replaced on its own.

- **`ingest.py`** — opens .xlsx/.xlsm/.csv (.xls needs `xlrd`, which is not installed; the error message says so) and returns one `RawSheet` per visible sheet: a raw cell grid with **no header assumed**. Spreads merged-cell ranges across their full extent (`_spread_merged_cells`), drops all-blank rows/columns, and keeps `row_map` so the pipeline can still report "your header is on row 5" after trimming. Deliberately makes no decisions about meaning.
- **`schema.py`** — the canonical field vocabulary (`date`, `party`, `sku`, `qty`, `amount`, `stock_qty`, `reorder_level`, `outstanding`, …) as `FieldSpec` entries carrying `exact` aliases, `contains` fragments and `veto` fragments. Vetoes are what stop "Closing Stock" being read as a sales quantity. `NOISE_HEADERS` marks columns ("Remarks", "Narration") that must never be adopted. `TABLE_RULES` classifies a sheet as sales/stock/receivables from its fields. **Teaching the engine a new client's column name is usually a one-line alias addition here.**
- **`detect.py`** — three questions in order: which row is the header (`find_header_row` scores each candidate on text-vs-number ratio, vocabulary hits, uniqueness, and whether the rows *below* look like data), what each column means (`map_columns` scores every column×field pair then assigns greedily by descending score; `_infer_from_values` rescues headerless columns by reading their values), and what kind of table it is (`classify`). Returns a `DetectedTable`.
- **`clean.py`** — produces a `CleanTable` with canonical column names and real dtypes. Drops total/subtotal rows before they double every metric, parses the spreadsheet dialects of a number (`to_number`: `₹ 1,23,456.00`, `(4,500)` → negative, `5,000 Cr` → negative, `12%`), parses dd-mm-yyyy text dates, derives `amount` from qty × rate when it is missing, and collapses customer spellings into a `party_key` (strips M/s, Pvt Ltd, Traders; normalises `&` → `and`). Every fix is appended to `table.issues` and surfaced in the report.
- **`analyze.py`** — the value. Stacks tables of the same kind (clients split sales across twelve monthly sheets), then computes sales metrics, stock metrics and receivables ageing. The cross-table join in `_stock_movement` is the differentiator: stock ⋈ sales yields dead stock (90+ days idle, with the cash locked in it) and days-of-cover per SKU. Produces `Alert(severity, title, detail, value)` objects — **these are the intended Phase 2 WhatsApp/email payloads, so keep them self-contained.** A partial trailing month is flagged and excluded from trend alerts, so a half-finished month never reads as a revenue collapse.
- **`report.py`** — renders one HTML file with inline CSS and hand-rolled CSS bar/ageing charts, using Indian digit grouping (`money` → ₹12,34,567). **No `<script>`, no CDN, no remote images, no `src=`** — a test enforces this, because the file has to open on a phone with no internet after being forwarded on WhatsApp. Ends with a "What Vyuha read from your file" panel (ADR 004) listing sheets, columns understood and fixes applied.
- **`sample.py`** — generates the messy demo workbook: junk rows and a merged title above the header, blank spacers, a Grand Total row, ₹/comma/paren/Cr number formats, dates as text in one sheet and real dates in another, four spellings of one customer, three planted dead SKUs, one planted about-to-stock-out SKU, and a prose "Notes" sheet that must be skipped. It is both the test fixture and the demo file for prospects.
- **`cli.py`** — `run` / `check` / `demo`. `say()` exists because the Windows console is cp1252 and cannot encode ₹; it transliterates on the way out rather than weakening the report.

`tests/test_pipeline.py` covers value parsing, header detection under junk rows, column mapping, classification, total-row exclusion, derived amounts, a full end-to-end run against the sample, and the self-contained-report guarantee. The file is written to run under pytest *or* standalone, but **pytest is not installed in `.venv` and is not a declared dependency** — `python -m pytest` fails with "No module named pytest". Use `python -m tests.test_pipeline`.

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
  numbers.
- **`channels.py`** — the Phase 2 alert renderers: pure `Insights -> str` functions
  (`as_whatsapp`, `as_email`) sitting beside `report.render()` rather than in a new pipeline.
  `as_whatsapp` respects a 1024-char cap by shedding entity lines first, then whole alerts
  lowest-severity-first, always keeping the dropped count honest. **Delivery is a `wa.me` deep
  link, not an API call** — it opens WhatsApp with the brief pre-typed and the founder taps send,
  so there is no Meta Business account, no BSP and no template pre-approval. Swapping in the
  Cloud API later means adding a sender here; the renderers do not change.
- **`ui.py`** — hand-rolled HTML strings (same choice as `report.py`). Dark, glass-card styling.
  Unlike the client dashboard this **may** use a webfont CDN, since it is served over localhost;
  the embedded dashboard is still strictly self-contained and a test enforces that.
  The workspace shell is `cover_hero()` + `actions()`, **not** a tab strip: a full-bleed banner
  carrying the client's own photo (or their trade backdrop) with the live numbers over a scrim,
  then every option as a large labelled card stating what it does *and its current state*
  ("Send & download — 4 alerts ready"). `?tab=` still drives which body renders; the change is
  that nothing is hidden behind an unlabelled tab. `layout()` swaps the nav and the wordmark by
  install type — a tenant sees their own business name over "powered by Vyuha".
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
- **`app.py`** — routes: `/` (landing when signed out, portfolio when signed in),
  `GET|POST /signup`, `GET|POST /login`, `POST /logout`, `POST /install`, `/onboard`, `/setup`,
  `/settings`, `/activity`, `/c/{slug}?tab=data|books|dashboard|alerts|settings`,
  `POST /c/{slug}/upload`, `POST /c/{slug}/book/item|sale`,
  `/c/{slug}/export/{pdf|pptx|html}`, `POST /c/{slug}/email|whatsapp|delete`,
  and the console block (`# ---- vishak`) at the foot of the file:
  `/c/{slug}/console`, `POST /c/{slug}/ask|followup|expense|deck|branch|staff`,
  `POST /c/{slug}/stock/{receive|count|reorder}`, `GET /c/{slug}/deck/{pptx|pdf}`.
  Every console handler starts with `_console_client()`, which resolves and
  authorises in one step.
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
