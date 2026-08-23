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
.venv/Scripts/python -m tests.test_platform     # 24 platform tests, same runner

.venv/Scripts/python -m vyuha_platform --open   # the web platform on :8000
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

- **`store.py`** — client registry and run history as JSON at `vyuha_data/clients.json`
  (gitignored), with uploads under `vyuha_data/uploads/<slug>/` and generated dashboards under
  `vyuha_data/dashboards/<slug>/<runid>.html`. A file, not a database: at founder-operated scale
  it is easier to inspect and hand-edit, and swapping it means replacing this module only.
  `Client` carries per-client `dead_stock_days` / `low_cover_days`.
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
  each sale, and **writes the whole thing out as a workbook whose sheet names and headers
  `schema.py` already recognises** (Sales Register / Stock Statement / Outstanding). Typed-in
  entries and uploaded files therefore converge on the same engine, same dead-stock join, same
  alerts. `app._rebuild_from_book()` re-runs the pipeline after every edit.
- **`ledger.py`** — append-only JSONL at `vyuha_data/activity.jsonl`. Every onboard, file,
  conversion, run, send and export is logged, so "where did this number come from" is one screen
  away (`/activity`, filterable by client and event).
- **`exports.py`** — PDF (reportlab), PPTX (python-pptx) and a framed email + SMTP sender, all
  rendered from the same `Insights` as the dashboard so they cannot disagree. **The PDF uses
  `Rs.` because the Helvetica core fonts have no ₹ glyph** — precisely the split `vyuha/fmt.py`
  exists to make explicit.
- **`config.py`** — settings and credentials from `vyuha_data/config.json` + env vars, with
  `whatsapp_live` / `vision_live` / `email_live` capability probes. Secrets are write-only in the
  UI (masked on render, blank means "keep"). `install` is `operator` or `tenant` — see the
  section below; it is set at first run and intentionally not editable from the UI.
- **`app.py`** — routes: `/` portfolio, `/onboard`, `/setup`, `/settings`, `/activity`,
  `/c/{slug}?tab=data|books|dashboard|alerts|settings`, `POST /c/{slug}/upload`,
  `POST /c/{slug}/book/item|sale`, `/c/{slug}/export/{pdf|pptx|html}`,
  `POST /c/{slug}/email|whatsapp|delete`.

- **`theme.py`** — per-trade accent colour and a generated backdrop (inline SVG data URIs:
  fronds for a nursery, crates for distribution, cogs for manufacturing, shelves for retail).
  No stock photography: the backdrops render instantly, work offline, never 404, and cannot be
  mistaken for someone else's shop. `theme.guess()` infers the trade from the business name so
  nobody picks twice. A client's own uploaded cover photo (`/c/<slug>/cover`) always wins.

## Operator vs tenant — the product boundary

`settings.install` is chosen once on first run and is **not** an editable preference, because
flipping it would change who can see what:

- **`operator`** — Vyuha's own copy. Portfolio, onboarding, every client's activity, and the
  credentials. This is Vishak's install.
- **`tenant`** — a copy handed to a business we onboarded. Exactly one workspace, named by
  `settings.tenant_slug`. No portfolio, no onboarding, no other business's data, and no
  awareness that any other exists. Their setup screen is about *their own operation* (business
  name, trade, how they keep records) — never about clients.

Enforcement is in `app.py`: `_deny_tenant()` closes the operator-only routes, and `client_page`
refuses any slug other than the tenant's own. `_tenant_client()` is deliberately strict — an
install with no `tenant_slug` shows setup rather than adopting whatever client happens to exist.
Four tests cover the boundary, including that a tenant cannot reach another workspace by URL.

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
