# Decision log (ADR-lite)

Each entry:
- ### <NNN>: <decision title> — <date>
- **Context:** ...
- **Options considered:** ...
- **Decision:** ...
- **Consequences / accepted risks:** ...

---

### 001: Bootstrap Vyuha-1 Prime inside `Vyuha_phas1/`, not the parent folder — 2026-08-04

- **Context:** `vyuha-1-prime-bootstrap.md` sets `repo_root: .` (current working directory). The CLI's working directory is the parent `Project V` folder, but `Project V` is not a git repository — `Vyuha_phas1/` is the git clone where active development happens (branch `feature/DOC-00-vishak`).
- **Options considered:** (a) bootstrap in `Project V` parent; (b) bootstrap in `Vyuha_phas1/`.
- **Decision:** (b) — `Vyuha_phas1/`. The bootstrap file itself lives there, and requirements/decisions must be version-controlled to be a source of truth.
- **Consequences / accepted risks:** Any Claude Code session started from the parent `Project V` folder will not auto-discover `Vyuha_phas1/.claude/agents/*`. Sessions must be started from inside `Vyuha_phas1/` for the sub-agents to resolve.

### 002: Build the engine in Python with pandas + openpyxl — 2026-08-11

- **Context:** First product deliverable is Phase 1 Foundation: read a distributor's Excel file and produce a dashboard. Needed a stack for the Excel-reading and analytics core.
- **Options considered:** (a) Python + pandas + openpyxl; (b) Node/TypeScript + SheetJS, matching the existing HTML dashboards; (c) pure browser, drag-and-drop, all client-side.
- **Decision:** (a). openpyxl exposes merged-cell ranges and cached formula values, which is what makes header/merge recovery possible at all; pandas carries the supply-chain math (ageing, days of cover, dead-stock joins) that Phases 2–3 build on. Output is still a static HTML file, so the demo artefact stays as portable as (c) would have been.
- **Consequences / accepted risks:** Two languages in the venture (Python engine, HTML/JS dashboards). The founder must have Python installed to run it — acceptable while this is a founder-operated service, revisit at Phase 3 when clients self-serve. Legacy `.xls` needs `xlrd` as an extra dependency; not installed, and the error message says so.

### 003: Rule-based column detection, not an LLM — 2026-08-11

- **Context:** The core problem is that every client names their columns differently. An LLM could map headers to fields in one prompt.
- **Options considered:** (a) rule-based canonical vocabulary with alias/veto scoring plus value-based inference; (b) send headers + sample rows to a model and let it map them; (c) make the client fill in a mapping form.
- **Decision:** (a). It runs offline with no per-file cost, is deterministic across re-runs of the same file, and when a client's column is misread the fix is one alias in `vyuha/schema.py` rather than a prompt gamble. (c) was rejected outright — "no setup" is the entire pitch.
- **Consequences / accepted risks:** New vocabulary has to be added by hand as real client files arrive; expect a handful of misses per new client at first. An LLM fallback for columns the rules cannot resolve stays open as a later addition, and the `unmapped` list on every table is already the hook for it.

### 004: Show the client what we read from their file — 2026-08-11

- **Context:** Auto-detection will occasionally get a column wrong, and a dashboard that is silently wrong is worse for trust than one that is visibly approximate.
- **Options considered:** (a) render only the results; (b) render results plus a panel listing sheets read, columns understood, and fixes applied.
- **Decision:** (b). Every dashboard ends with "What Vyuha read from your file".
- **Consequences / accepted risks:** Exposes the seams of the product in a sales demo. Judged a net positive: an owner who can see that "Closing Stock" was read as stock quantity is far more likely to believe the dead-stock number underneath it.
