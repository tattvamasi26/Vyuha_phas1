# What Vyuha is

*Paste this into any Claude chat before asking for a brochure, deck or document.*

---

## In one line

Vyuha reads the messy files an Indian distributor already keeps — or lets them
type sales in if they keep none — and turns that into a dashboard, alerts, tax
invoices, financial statements and answers to questions asked in plain English.

## The problem it solves

A distributor with ₹5 crore of turnover runs on Excel, WhatsApp and memory.

- Their stock register is a spreadsheet with a merged title, junk rows above the
  header, "Grand Total" in the middle and one customer spelled four ways.
- Their order book is a WhatsApp thread.
- They know roughly what sold. They do not know what has been sitting on the
  shelf for ninety days, who is 66 days late paying, or which item makes them
  the least money.
- Software exists for this. It requires them to change how they work first,
  which is why they don't use it.

**Vyuha's position: don't make them change anything.** Send the file as it is.
Or send nothing and type sales in. Either way you get the same answers.

## What it actually does

### 1. Reads what they already have
Excel, CSV, tab-separated exports from Tally-style packages, PDFs, **a
photograph of a handwritten register**, and **an exported WhatsApp thread**. No
configuration — it works out which sheet is sales, which row the header is on,
which column means what, and drops the total rows before they double everything.

Then it says what it read: which sheet, which row, which columns understood,
which ignored, and every fix it applied. Nothing is a black box.

### 2. The console — one page, five things
- **Stock** — opens on what needs ordering, with days of cover per item, because
  twelve bags is a fortnight of urea and two years of soil test kits
- **Ask** — questions in plain English, answered from their own numbers
- **Follow-ups** — who is overdue, who has gone quiet, with the message written
- **Money** — profit and loss, cash flow, balance sheet, ageing, ratios,
  break-even
- **Bills** — proper GST tax invoices on a template
- **People** — branches, staff, who is actually selling

### 3. Sends
A WhatsApp brief, an email, a self-contained dashboard that opens on a phone
with no internet, PDF and PowerPoint exports, and a slide deck built from their
own figures.

## The five things that make it different

**It reads the file unchanged.** Not "export to our format" — the actual file,
with all its mess. This is the demo moment and the whole pitch.

**Every number is computed, never generated.** The AI decides *which* question
to ask of the data. Python computes the answer. So a figure can be checked
against the books by hand, and the screen says which parts it read.

**It works with no internet and no API key.** The dashboard is self-contained.
The agent answers the common questions from patterns. The deck still builds.
Add a Claude key and it handles anything you ask — but nothing breaks without one.

**It says what it cannot see.** The balance sheet lists what it is missing
rather than quietly omitting it. A business with no GSTIN gets a clean bill of
supply, not an invoice with a blank tax field. Sales with nobody recorded
against them are reported as unattributed, not shared out.

**Two ways in.** The operator manages a portfolio of clients. Or the shop owner
gets a private link and a 4-digit PIN over WhatsApp — no password, no email, no
account to remember.

## Who it is for

Distributors and manufacturers doing roughly **₹2–20 crore a year**, in
agri-inputs, hardware, feed, seed, building materials or spares. One to five
locations. Someone in the family keeps the books in Excel.

Not for: businesses already on a full ERP, or shops too small to have stock
worth tracking.

## What it is not

- Not an ERP. It does not replace how they work; it reads it.
- Not accounting software. It produces the statements a CA would, from the
  trading records — not a general ledger.
- Not a WhatsApp Business API product. Messages go through a `wa.me` link the
  operator taps, or a connected provider if one is set up.

## The name

Vyuha (व्यूह) — a battle formation. Individually ordinary units arranged so the
whole is far stronger than the parts. That is the product: nothing here is
exotic on its own; the arrangement is the thing.
