# 01 — Excel → dashboard engine

## Description

The Phase 1 Foundation deliverable from the Platform Build roadmap. A Python
package (`vyuha/`) that reads an unmodified distributor spreadsheet, works out
what each sheet and column means, cleans the data, computes sales / stock /
receivables intelligence, and writes a single self-contained HTML dashboard.

Pipeline: `ingest` → `detect` → `clean` → `analyze` → `report`, tied together by
`pipeline.run()` and exposed as `vyuha run <file>`.

Nothing about the client's file changes. There is no template, no column mapping
step, and no upload — the founder runs it locally on a file the client emailed.

## Acceptance criteria

- [x] Opens .xlsx / .xlsm / .csv; reports a clear error for anything else.
- [x] Finds the header row when it is buried under title/address/blank rows.
- [x] Maps messy real-world headers ("Party Name", "Qty (Nos)", "Closing Stock")
      onto a canonical vocabulary without the user configuring anything.
- [x] Classifies each sheet as sales / stock / receivables from its columns, not
      its name; skips sheets that are prose.
- [x] Spreads merged cells, drops blank spacer rows, excludes total/subtotal rows.
- [x] Parses "₹ 1,23,456.00", "(4,500)", "5,000 Cr", "12%", and dd-mm-yyyy text dates.
- [x] Collapses one customer's many spellings into one line in the report.
- [x] Derives Amount from Qty × Rate when the file has no amount column.
- [x] Sales: revenue, orders, AOV, monthly trend, top customers/products/categories,
      revenue-concentration warning.
- [x] Stock: stock value, below-reorder list, days of cover, dead stock (joined
      against sales), where the stock money sits.
- [x] Receivables: total outstanding, ageing buckets, overdue total, worst debtors.
- [x] Emits structured alerts (severity + title + one line) — the same objects
      become the Phase 2 WhatsApp/email payloads.
- [x] Writes one .html with no external requests: no CDN, no scripts, no remote
      images, so it opens on a phone with no internet.
- [x] `vyuha demo` generates a deliberately messy sample workbook and its dashboard.
- [x] Tests cover parsing, detection, cleaning and a full end-to-end run.
- [ ] Validated against a real client file.

## Status: shipped (v0.1.0, 2026-08-11) — pending validation on real client data

## Notes / decisions

- Detection is rule-based, not LLM-based — see ADR 003. It runs offline, costs
  nothing per file, and is debuggable when a client's column is misread.
- The "What Vyuha read from your file" panel at the bottom of the dashboard is
  deliberate: it shows which columns were understood and which fixes were applied,
  so the owner can spot a misreading instead of quietly distrusting the numbers.
- Known gaps: no fuzzy matching on near-miss customer spellings (only rule-based
  normalisation); legacy .xls needs `xlrd`; formulas with no cached value read as
  blank; multi-currency and GST breakup are ignored.
