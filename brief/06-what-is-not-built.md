# What is not built

*Paste this before any meeting, and into any document that makes a promise.*

**Rule for Claude: never present anything in the "not built" list as working.
If a document needs it, mark it as planned. Being caught overclaiming costs more
than the feature was worth.**

---

## The ten agreed features

| # | Feature | State |
|---|---|---|
| 1 | Data intake | **Working**, with gaps listed below |
| 2 | Inventory & understock | **Working** |
| 3 | Business agent | **Working** |
| 4 | Morning / evening automations | **Not built** |
| 5 | Orders in from WhatsApp / email / web | **Not built** |
| 6 | Quotations | **Not built** |
| 7 | Customer follow-up | **Working** |
| 8 | Financial tracking | **Working** |
| 9 | Decks and documents | **Working** |
| 10 | People & branches | **Working** |
| — | Tax invoicing | **Working** (added after the original ten) |

Seven of eleven work. Three do not.

## The three that do not

**4 · Automations.** Nothing runs on a clock. There is no morning brief that
arrives by itself and no evening report. The alerts, the WhatsApp brief and the
email all exist and work — somebody has to press the button. *Say: "the messages
are written for you; scheduling them is next."*

**5 · Inbound orders.** Vyuha can **read** an exported WhatsApp thread you upload
— it pulled 9 orders and payments out of an 18-message conversation with no API
key. What it cannot do is **listen**: no webhook, nothing arrives on its own.
*Say: "it reads the thread today; receiving live is next."*

**6 · Quotations.** Not started. Prices and costs are on every item so the
arithmetic is there, but there is no quote document and no send. *Say: "not yet
— invoicing is done, quotes are the same machinery pointed the other way."*

## Honest limits inside what does work

- **Per-item history shows sales only.** Stock deliveries are not individually
  dated, so it is a sales history, not a full stock ledger.
- **The balance sheet is partial** — no opening balances, no fixed assets, no
  depreciation, no loans, no owner's capital. It says so on screen.
- **Cash is derived**, not a bank balance: receipts minus payments recorded here.
- **Staff roles do not gate access yet.** A role says what a person *would* see;
  everyone with the workspace link sees everything.
- **Photographs and scanned PDFs need a Claude API key.** Everything else —
  Excel, CSV, tab-separated, text PDFs, WhatsApp threads — works without one.
- **Data intake has no streams.** A folder that gets a new file monthly, or an
  inbox, is not watched. Files are uploaded one at a time, and two files covering
  the same period are not reconciled against each other.

## What to say when asked directly

> "Seven of the ten things we agreed work today. Three don't: nothing runs on a
> schedule yet, orders can't arrive on their own, and quotations aren't built.
> Everything you'd do once you're looking at the screen is there."

That answer has never cost a meeting. Being caught claiming otherwise would.

## What is genuinely strong

Worth leading on, because it is unusual:

- It reads a file **nobody cleaned first** — junk rows, merged cells, a Grand
  Total in the middle, four spellings of one customer — and says what it read.
- It reads a **photograph of a handwritten register**.
- It reads an **exported WhatsApp thread** and finds the orders in it.
- **Every number is computed in Python, never generated.** The AI picks which
  question to ask; the arithmetic is checkable by hand.
- The whole thing **works offline** — dashboard, agent, deck. No key required.
- Invoices are **real tax invoices**: per-line GST, CGST/SGST against IGST,
  gap-free numbering, amount in words.
