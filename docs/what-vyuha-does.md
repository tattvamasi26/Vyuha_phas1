# What Vyuha does

*Written for somebody who has never seen it. Read this first; then
[Using Vyuha fully](using-vyuha-fully.md).*

---

## The one-line version

Vyuha reads the records a distributor already keeps — Excel files, Tally exports, paper
registers, even WhatsApp messages — and turns them into a daily list of decisions, the
statements an accountant would prepare, and the messages that chase the money.

Nothing about it asks the business to change how they work first. That is the whole idea:
the software meets the shop where it is.

---

## 1 · Getting the numbers in

| How | What it means |
|---|---|
| **Send files** | Drop in whatever they have — a sales register, a stock statement, an outstanding list. Junk rows above the header, merged title cells, a "Grand Total" in the middle, ₹ symbols, one customer spelled four ways: Vyuha reads it anyway and says what it understood. |
| **Point at a folder** | Nobody wants to select ninety files in a dialog. Give it a folder and it reads everything in place. |
| **Type entries** | For a business that keeps no spreadsheet at all: a sale is one line — what, how many, who, their number — and stock comes down as it saves. |
| **Photographs** | A picture of a handwritten register page or a bill, read by AI, with every row shown next to the photo for checking. (Needs a Claude key.) |
| **WhatsApp threads** | Export a customer chat and Vyuha finds the orders and payments inside it. |

Every file is read into the same place, so a business can send files this month, type
entries next month, and the numbers stay one set.

**Not built yet:** files arriving on their own (a watched inbox or folder), live WhatsApp,
and a Tally connector. Today somebody sends the file.

---

## 2 · What it does with them

### Home — what needs you today
A ranked list of decisions, each with one button: stock that has run out, customers past
their due date, supplier bills landing this week, cash sitting in items that never sold, a
regular who has stopped buying, staff not marked in. Ranked by what it costs to ignore, so
the top of the list is the top of the list for a reason. Plus today's sales, the four
headline figures, and where the numbers came from.

### Sales — what is selling and who still has to pay
- **Overview** — revenue, collected, owed, customers; month by month; what sells and who buys.
- **Bills** — every bill, searchable, with "mark paid" and "send the receipt".
- **Customers** — each customer's history, what they buy, what they owe, unpaid bills.
- **Collections** — who to chase, worst first, with the message already written and a
  WhatsApp button next to it.

### Operations — the daily work
- **Record** — a sale in one line; a new item for the shelf.
- **Inventory** — what is on the shelf against its reorder level, days of cover, what is
  out, what never sold; receive a delivery or count the shelf.
- **Purchases & expenses** — supplier bills and every other payment, paid or owed.
- **Invoices** — real GST tax invoices: per-line tax, CGST+SGST within the state and IGST
  outside it, HSN codes, amount in words, numbering that is never reused. One invoice is
  for one customer, and Vyuha refuses to mix them.

### Finance — what a bank or a CA asks for
Profit and loss on an accrual basis, cash flow on a cash basis (never blended), a working
balance sheet that **prints what it cannot see**, receivables and payables by age, the
ratios a lender looks at, GST collected with the filing dates, and a downloadable pack.

### Team — who works where and who is selling
Staff with roles and branches, today's register and the fortnight behind it, sales per
person against target with commission, and branch against branch.

### Analytics — any question of the numbers
Group by customer, item, month, branch or category; measure revenue, quantity, bills,
margin or average bill; filter by period or customer. Plus the ratios, concentration risk,
and documents — a deck and a PDF built from the same figures.

### Inbox — everything that goes out
Vyuha writes messages; **one gate** decides what happens to each:

- an **alert** to the business's own number sends itself (it is worthless tomorrow),
- **every email** is saved as a draft for a person to send,
- anything touching **money leaving** or a **GST filing** waits for a named person to approve it.

"Who gets told" shows who would hear about what *before* anybody is told: stock to the
manager, money to the accountant, a quiet customer to a salesperson, everything to the
owner. Routines are scheduled briefs — the 8 am WhatsApp with what needs a decision.

### Data — where it came from
Every file, what was read from it, what was ignored, what was fixed, and how sure Vyuha
is. A number read off a labelled column and one reconstructed from a headerless sheet do
not look the same here.

### The assistant
Ask in plain words — "who owes me the most?", "what is not selling?", "make a deck for the
bank". Every figure it quotes is computed in Python from the books; the model chooses what
to look at and how to say it, never what the number is. With no key and no internet, a
rule-based path still answers the common questions.

---

## 3 · The rules Vyuha holds itself to

1. **Every number is computed, never generated.** The arithmetic is checkable by hand.
2. **One source, many views.** Home, the statements, a deck and the assistant read the same
   book, so they cannot disagree.
3. **Say what is assumed.** The balance sheet lists what it does not capture. Input GST is
   labelled an estimate. A guessed column is marked as guessed.
4. **Nothing leaves quietly.** Everything outbound goes through one gate, and money or a
   filing waits for a person.
5. **It works offline.** The dashboard, the statements and the assistant's fallback need no
   internet and no API key.

---

## 4 · What is not built yet

Say this plainly; being caught overclaiming costs more than the feature is worth.

- **Nothing runs on a clock by itself.** Routines fire when somebody opens a page. The
  messages are written; scheduling them properly is next.
- **Orders cannot arrive on their own** — no live WhatsApp or email inbox yet. Vyuha reads
  an exported thread today.
- **Quotations** are not built. Invoicing is; quotes are the same machinery pointed the
  other way.
- **Staff roles do not gate access yet.** A role decides who *hears* about what, not what
  they can open.
- **The balance sheet is partial** — no opening balances, fixed assets, depreciation or
  loans. It says so on the screen.
- **Onboarding stages 4–8** (opening position, history import, sign-off, continuous feeds,
  go-live) are described in the Studio but are the next build.
