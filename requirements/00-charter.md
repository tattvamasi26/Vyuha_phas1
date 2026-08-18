# Project Charter

## What

Vyuha is an AI/automation service for Indian distributors and small manufacturers
who run their entire business on Excel. The first product is an engine that takes
a client's existing, messy spreadsheet — no template, no re-keying, no change to
how they work — and produces a business dashboard plus a short list of things that
need attention: SKUs about to stock out, stock that has not moved in months, and
invoices that are overdue. Later phases push those same findings out as WhatsApp
and email alerts, generate quotations, and move the whole thing onto a hosted
per-client platform.

## Why

These businesses already have the data. What they do not have is the hour a week
to pivot-table it, and nobody in the firm joins the stock sheet against the sales
sheet — which is exactly where the trapped working capital shows up. An ERP asks
them to change how they operate and costs lakhs; Vyuha asks them to send the file
they already have. That gap is the wedge: cheap to deliver, immediately legible in
a demo, and it earns the trust needed to sell the recurring automation later.

## Success looks like

- [x] Point the engine at a real, unmodified distributor Excel file and get a
      dashboard out, with no manual column mapping.
- [x] Survive the standard mess: junk rows above the header, merged cells, blank
      spacer rows, "Grand Total" rows, ₹ and comma formatted numbers, dates stored
      as text, and one customer spelled four ways.
- [x] Produce at least one insight the owner could not read off their own sheet —
      dead stock, days-of-cover, or receivables ageing.
- [ ] Run it against a real client file (not the generated sample) and have the
      owner confirm the numbers match their own understanding.
- [ ] First prospect demo delivered from a file they sent us.
- [ ] First paying client.

## Out of scope

- Writing back into the client's Excel file, or replacing their accounting system.
- A hosted multi-tenant web app with logins (Phase 3 — not now).
- Anything requiring the client to adopt a template or change their process.
- OCR / scanned PDFs / handwritten registers.

## Owner: Vishu · Created: 2026-08-04 · Charter filled in: 2026-08-11
