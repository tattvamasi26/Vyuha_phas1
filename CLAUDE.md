# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

"Vyuha" is an early-stage founder project: an AI/automation service for distributors and manufacturers who run their operations on Excel (dashboards, WhatsApp stock alerts, auto-generated reports, quotation generation, supply-chain intelligence like reorder points and dead-stock detection).

Right now this repo does **not** contain the Vyuha product itself — it contains a single-file planning tool the founder uses to track the venture:

- `vyuha_package/vyuha_dashboard.html` — the "Vyuha Founder OS" dashboard: a self-contained HTML/CSS/JS app (no build step, no server, no dependencies) with six workspace sections (AI Learn, Platform Build, Business, Finance, Supply Chain, General) for tracking the learning plan, product roadmap, client-acquisition roadmap, financials, and a running list of business challenges/solutions.
- `vyuha_package/INSTRUCTIONS.md` — usage notes for the dashboard file.

There is no actual Vyuha product code (no backend, no Excel-processing pipeline, no client dashboards) yet — that is future work tracked *inside* the dashboard's "Platform Build" section.

As of 2026-08-04 the repo also carries the **Vyuha-1 Prime** operating contract (`vyuha-1-prime-bootstrap.md` plus the `requirements/` and `.claude/` scaffolding it generates) — see "Vyuha-1 Prime operating contract" below.

## Commands

There is no build, lint, or test tooling in this repo — `vyuha_dashboard.html` is a plain static file.

- **Run it**: open `vyuha_package/vyuha_dashboard.html` directly in a browser (double-click, or `start vyuha_package/vyuha_dashboard.html` on Windows). No server required.
- There is no package.json, no dependency manager, and nothing to install.

## Architecture of `vyuha_dashboard.html`

Everything lives in one file: inline `<style>`, inline HTML sections, inline `<script>`.

- **State**: a single global `state` object holds all data for every section (`state.ai`, `state.platform`, `state.biz`, `state.finance`, `state.supply`, `state.general`). Roadmap sections (`platform`, `biz`, `finance`, `supply`) share the same shape: `{ phases: [{ id, name, timeline, color, tasks: [{ id, text, done, note }] }], nextPhaseId, nextTaskId }`.
- **Rendering**: no framework — each section has a `render*()` function that wipes and rebuilds its DOM container from `state` (`renderWeek`, `renderVideos`, `renderNotes`, `renderGeneral`, and the generic `renderPhases()` used by platform/biz/finance/supply). `renderAll()` re-renders everything and is called after any state mutation that isn't handled locally.
- **Navigation**: `switchSection()` toggles which `.section-view` is visible, updates the accent color (`setAccent()`) and page header text (from the `PAGE_META` map), and re-renders.
- **Mutations**: task/video/day toggles and "add" functions (`addVideo`, `addNote`, `addPlatformTask`/`addBizTask`/`addFinTask`/`addSupTask` → shared `addTaskToSection()`, `addGenTask`) mutate `state` directly, then call the relevant render function. New roadmap phases are created on the fly when a task is added under a phase name that doesn't exist yet.
- **Persistence**: `saveAll()`/`loadState()` use `window.storage` (a key-value API only available when this HTML is rendered as a Claude.ai Artifact) to persist the entire `state` object under the key `vyuha_state`, with a `localStorage` fallback when `window.storage` is unavailable (i.e. when the file is opened as a plain local HTML file). The Reset button (`clearSection()`) is currently a stub — it only confirms and does not actually clear data.

## Vyuha-1 Prime operating contract

`vyuha-1-prime-bootstrap.md` is a paste-once operating prompt that turns the agent into "Vyuha-1 Prime", a plan-first orchestrator that delegates rather than writing code itself. Its first-run bootstrap was executed on 2026-08-04 and produced:

- **`requirements/` — the declared source of truth.** `00-charter.md` (still an empty template — the project charter has not been filled in yet), `01-features/` (one `NN-slug.md` per feature; currently only its `README.md` conventions file), `02-decisions.md` (ADR-lite, append-only; ADR 001 records why the bootstrap landed here rather than in the parent `Project V` folder), `03-token-log.md` (500k budget split 60/30/10 into 300k development / 150k iteration / 50k research), `99-changelog.md`.
- **`.claude/agents/`** — `planner`, `developer`, `tester`, `reviewer`. These drive the contract's 8-step loop (read → rough plan → final plan → pick one → develop → test → review → ship), where steps 2 and 3 are the only points the agent waits on the owner. Note they only resolve for sessions started **inside `Vyuha_phas1/`**; a session started from the parent `Project V` folder will not see them.
- **`.claude/skills/`** — `plan-drafting`, `requirements-update`, `test-protocol`, `token-budget-check`.
- **`.claude/hooks/`** — four Python scripts plus `hooks.json`. **These are currently inert**: Claude Code reads hook config from `.claude/settings.json`, not `.claude/hooks/hooks.json`; the event names in that file (`before_tool_use`, `after_tool_use`, `after_file_change`) are not real Claude Code events; and `pre-deploy.py` reads a `HOOK_TOOL_INPUT` environment variable, whereas real hooks receive their payload as JSON on stdin. Treat them as documentation of intent until they are rewired.

## Commands (Vyuha-1 Prime)

There is still no build/lint/test tooling. The hook scripts are plain Python 3 (`python .claude/hooks/<name>.py`) and are no-ops or stderr nudges as written.

## Tooling notes

A Stop hook (`.claude/settings.json`) checks whether any tracked file changed since the last turn and, if so, prompts Claude to review this CLAUDE.md before finishing. `autoCompactEnabled` is on, so context compacts automatically as it fills. That Stop hook lives in the **parent** `Project V/.claude/settings.json`, not in this repo — this repo's `.claude/` currently holds only agents, skills, and the inert hooks described above.
