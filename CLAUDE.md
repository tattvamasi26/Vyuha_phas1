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
.venv/Scripts/python -m tests.test_platform     # 7 platform tests, same runner

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
- **`app.py`** — routes: `/` portfolio, `/onboard`, `/c/{slug}?tab=data|dashboard|alerts`,
  `POST /c/{slug}/upload`, `/c/{slug}/dashboard`, `POST /c/{slug}/delete`.

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
