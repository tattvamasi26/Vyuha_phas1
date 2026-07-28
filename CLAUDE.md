# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

"Vyuha" is an early-stage founder project: an AI/automation service for distributors and manufacturers who run their operations on Excel (dashboards, WhatsApp stock alerts, auto-generated reports, quotation generation, supply-chain intelligence like reorder points and dead-stock detection).

Right now this repo does **not** contain the Vyuha product itself — it contains a single-file planning tool the founder uses to track the venture:

- `vyuha_package/vyuha_dashboard.html` — the "Vyuha Founder OS" dashboard: a self-contained HTML/CSS/JS app (no build step, no server, no dependencies) with six workspace sections (AI Learn, Platform Build, Business, Finance, Supply Chain, General) for tracking the learning plan, product roadmap, client-acquisition roadmap, financials, and a running list of business challenges/solutions.
- `vyuha_package/INSTRUCTIONS.md` — usage notes for the dashboard file.

There is no actual Vyuha product code (no backend, no Excel-processing pipeline, no client dashboards) yet — that is future work tracked *inside* the dashboard's "Platform Build" section.

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

## Tooling notes

A Stop hook (`.claude/settings.json`) checks whether any tracked file changed since the last turn and, if so, prompts Claude to review this CLAUDE.md before finishing. `autoCompactEnabled` is on, so context compacts automatically as it fills.
