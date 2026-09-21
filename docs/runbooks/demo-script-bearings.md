# Runbook · The bearings demo

*Twelve minutes, one business, no live data. Every number below is what the seed produces,
so a rehearsed line is still true tomorrow.*

---

## Set up, five minutes before

```bash
.venv/Scripts/python -m vyuha_platform seed-bearings     # rebuilds the business
.venv/Scripts/python demo/make_bearings.py               # the client's own files
.venv/Scripts/python -m vyuha_platform --open            # the server on :8000
```

Log in as **bearings@vyuha.test / vyuha-bearings**. That account is an operator, so you land on
the Studio — open the business from there.

Have open: the site at `/app/shakti-bearings-power-transmission`, and a second tab on
`/studio`. Have `demo/samples/bearings/` in a Finder/Explorer window, ready to drag.

**Never demo off live data.** Re-run the seed after any rehearsal and it is exactly back.

---

## The business, in one line

> Shakti Bearings & Power Transmission, Hubballi. Two godowns, six people, 24 lines of
> stock — bearings, plummer blocks, belts, chains, seals. They sell to garages, a foundry,
> a sugar factory and dealers. Twelve months of trade is in here.

The figures the seed produces:

| | |
|---|---|
| Revenue, twelve months | **₹24.3 lakh** across 361 bills |
| Collected / still owed | ₹22.8 lakh / **₹1.45 lakh** |
| Gross margin | **27.9%** (₹6.79 lakh) |
| Net profit | **7.9%** (₹1.93 lakh) |
| Stock on the shelf | **₹3.42 lakh**, 24 items |
| Needs ordering | **1 out of stock** (grease), 4 below reorder |
| Dead stock | **3 items that never sold**, ₹37,480 |
| To chase | **₹1.15 lakh** overdue across 5 customers, 1 regular gone quiet |
| Invoices | **17 raised** — CGST+SGST for the Karnataka buyers, IGST for the Maharashtra one |

---

## The script

### 1 · Home — "what needs you this morning" (2 min)

Open `/app/shakti-bearings-power-transmission`.

> "This is what the owner sees at 8 am. Not a dashboard — a list of decisions, worst first,
> each with one button."

Point at, in this order:
- **5 customers owe you ₹1.15 lakh** — *"Worst is Nandi Sugars at 74 days. The reminder is
  already written."*
- **Bearing Grease 500g has run out, 3 more are low** — *"₹60,520 of orders he would have to
  turn away. That is what the number next to it means."*
- **Vishwa Engineering hasn't ordered in 89 days** — *"A regular who has gone quiet, and
  nobody noticed."*
- **₹37,480 sitting in 3 items that never sold** — *"That is cash on a shelf."*
- **supplier bills due this week**, and **credit sales with no invoice against them**

Then the four figures and the sparkline, and the badge that says where the numbers came
from. *"Everything on this screen is computed from their own book. Nothing is typed twice."*

### 2 · Collections — "the money conversation" (1.5 min)

Sales › Collections.

> "Five customers past their due date, worst first. Vyuha has written the message — the
> bill number, the amount, how many days. One tap opens WhatsApp with it typed out."

Click **See message** on Nandi Sugars. Then *"Done, or 'in a week' if they have promised.
A chase that arrives after payment costs more than ten that work."*

### 3 · Inventory — "why he will keep opening it" (2 min)

Operations › Inventory.

> "Ordered by how worried to be. Out of stock first, then below reorder, then things that
> have not moved."

Point at **days of cover**: *"Twelve pieces is a fortnight of 6205s and two years of
plummer blocks. The quantity alone tells you nothing."* Then type a quantity into the row
for a low item and press **Add** — *"a delivery came in; the shelf is now right, and the
warning has gone."*

### 4 · An invoice — "the document their buyer's accountant accepts" (2 min)

Operations › Invoices.

> "Sales are grouped by customer, because one invoice is for one customer — Vyuha refuses
> to mix them."

Tick two lines for a customer, raise the invoice, open it. Point at: per-line GST with HSN
codes, **CGST + SGST because the buyer is in Karnataka**, the amount in words, and the
number. *"Numbering is sequential and never reused. The second invoice here went to a buyer
in Maharashtra — that one is IGST. Same bill, different tax, decided by the state, frozen
at the moment it was issued."*

### 5 · Finance — "what the CA and the bank want" (2 min)

Finance › Profit & loss, then Balance sheet.

> "Accrual on the left: what was billed and what it cost. 27.9% gross, 8% net after
> everything."

Then the balance sheet, and read the assumptions panel out loud:

> "It prints what it cannot see — no opening balances, no fixed assets, no loans. A
> statement that quietly omitted half the liabilities would be worse than none."

Then Finance › GST: tax collected, the filing dates, and *"input credit is labelled an
estimate, because we do not hold their suppliers' GSTINs. This is where you stand between
filings, not a return."*

### 6 · Who gets told — "the part nobody else has" (1.5 min)

Inbox › Who gets told.

> "Before anybody is messaged, this shows who would be. Stock goes to the manager. Money to
> the accountant. A quiet customer to a salesperson. The owner hears everything."

Point at the GST rows: **Waits for approval**. *"Anything touching money leaving or a
filing waits for a named person. Alerts send themselves. Every email is a draft. That is
one gate, and the rule is on the action, not the channel."*

### 7 · The assistant — "ask it anything" (1.5 min)

Press **Ask** and type: *"Which customer owes the most, and since when?"*

Then: *"Make a deck for the bank."* Open Analytics › Documents and show the deck.

> "Every figure in that answer was computed in Python from their book. The model chose what
> to look at and how to say it. It never decided what the number was."

### 8 · The files — "but you have not seen my spreadsheets" (1.5 min)

Switch to the Studio, open a fresh business (or Data › Add data), and drag in
`demo/samples/bearings/01-sales-register.xlsx`.

> "Nobody cleaned this. A merged title, three junk rows above the header, dates as text,
> ₹ symbols, a Grand Total in the middle, and one customer spelled four ways."

Then **Data › What was read**: *"It tells you what it understood, what it ignored, and how
sure it is. A number read off a labelled column and one reconstructed from a headerless
sheet do not look the same here."*

---

## When they ask what is not built

Say it plainly. It has never cost a meeting:

> "Nothing runs on a clock on its own yet — the messages are written, a person taps send.
> Orders cannot arrive by themselves; we read an exported WhatsApp thread today. Quotations
> aren't built. Everything you would do once you are looking at the screen is there."

Also true, and worth saying before they find it: the balance sheet is partial and says so,
staff roles decide who *hears* about what rather than what they can open, and photographs
need an API key.

---

## Recovery

| If | Do |
|---|---|
| The data looks wrong after a rehearsal | `python -m vyuha_platform seed-bearings` — it wipes and rebuilds |
| A page errors | Note the address, move to the next beat, do not debug live |
| They ask for their own trade | The agri demo is `python -m vyuha_platform seed` (demo@vyuha.test / vyuha-demo) |
| No internet | Everything above still works. Say so — it is a feature |
