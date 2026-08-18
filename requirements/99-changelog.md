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
