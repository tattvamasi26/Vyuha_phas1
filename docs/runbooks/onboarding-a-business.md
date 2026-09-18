# Runbook · Onboarding a business

*For the Vyuha operator doing the setup. One business, start to finish.*

The client does not drive this. We do. The whole point of the Studio is that a distributor
hands over what they already have and gets a working product back.

**Time:** about 90 minutes with the owner, plus an hour of our own work on their files.
**Tools:** the Studio at `/studio`, and whatever files they send.

---

## Before you sit down with them

Ask for these on WhatsApp, a day ahead. The single message to send:

> To set you up we need, in whatever form you keep them:
> 1. Your sales register or bill book for the last 12 months
> 2. A current stock list with rates
> 3. A list of who owes you money, with dates
> 4. Purchase bills or a purchase register for the same period
> 5. Your GSTIN, address as it should print on a bill, and bank details
> 6. Names, roles and phone numbers of the people who work with you
>
> Do not clean anything up. Send it exactly as it is.

That last line matters. A client who "tidies" a file first usually deletes the columns we
need, and takes a week doing it.

---

## Stage 1 · Business profile

`/studio/new`, then the profile stage.

| Field | Why it matters |
|---|---|
| Business name | Goes on every bill and every message |
| Owner's name | The greeting on Home, and who the messages address |
| WhatsApp number | **Every alert and brief goes here.** No number, no product |
| GSTIN + state | Without them, bills print as a *bill of supply*, not a tax invoice |
| Address, bank, terms | What prints at the top and the foot of an invoice |
| Financial year start | April for almost everybody in India |

**Do not skip the GSTIN** if they have one. It is the difference between a demo and a
document their buyer's accountant will accept.

---

## Stage 2 · The data map — the interview that decides everything

Eight kinds of record. For each, three questions:

1. **Where does it live today?** Tally · Excel / Sheets · other software · paper register ·
   bills only · WhatsApp · not kept
2. **How far back is it usable?**
3. **Who keeps it?**

| The record | What to actually ask |
|---|---|
| Sales | "How do you know what you sold last Tuesday?" |
| Purchases | "Where do supplier bills go after you pay them?" |
| Stock | "When did you last count the godown?" |
| Customers & dues | "Who owes you money right now — how would you check?" |
| Suppliers & payables | "What do you owe, and when is it due?" |
| Expenses | "Rent, salary, transport — where are those written?" |
| Cash & bank | "Do you keep a cash book, or is it the bank passbook?" |
| Staff & attendance | "Who marks who came in?" |

Then set the **cut-over date** — usually the 1st of a month — and how much history to bring
in. Everything before the cut-over is history; everything after it is the running record.

The page shows what each answer means in practice, for both jobs: how the past comes in,
and how new records keep flowing. Read that back to the owner. It is the moment they
understand what they are buying.

**Watch for:** "not kept" answers. They are not a failure — they are the gaps Vyuha will
fill from the cut-over onward, and saying so out loud stops a disappointed conversation
three weeks later.

---

## Stage 3 · Masters

Three things, in this order.

**Items.** Fastest first:
- **Starter catalogue** — tick what they carry from the trade's list, adjust the rates.
- **Their file** — if stock is in Excel, send it through Data › Add data instead.
- **The grid** — type the rest, one row each.

Every item needs three numbers to be worth anything:
- **Rate** — what they sell it for
- **Cost** — what they pay. *No cost, no margin, and half of Finance goes blank*
- **Reorder level** — when to warn. *A level of 0 means Vyuha will never warn them*

**Branches**, if there is more than one. A single-branch business should not have any.

**People.** Name, role, branch and — the part that matters — **a phone number**. Vyuha
tells whoever owns the problem: stock to the Manager, money to the Accountant, a quiet
customer to a Salesperson, everything to the Owner. A person with no number is skipped
silently, and the owner ends up being told everything, which is how role routing gets
blamed for not working.

---

## Stages 4–8 · What is coming, and what to do meanwhile

The Studio describes these and they are the next build: **opening position**, **history
import** with review and undo, **check & sign-off**, **continuous feeds**, and **people,
alerts & go-live**.

Until they land, do the same job by hand:

| Stage | What to do today |
|---|---|
| Opening position | Send their stock list and outstanding list through **Data › Add data**. Stock is a snapshot — the newest file wins. |
| History import | Send the sales register and purchase register the same way. Check **Data › What was read** afterwards, every time. |
| Check & sign-off | Open **Finance › Balance sheet** and **Sales › Overview** with the owner and get them to say the figures look right. Write the date in the Studio notes. |
| Continuous feeds | Agree who sends what, how often. Put it in the notes and set a reminder until feeds are built. |
| Go-live | **Settings › Access** — issue the private link and PIN, send them on WhatsApp separately. Then **Inbox › Routines** — an 8 am brief. Then **Inbox › Who gets told** — read it with the owner before anybody is told anything. |

---

## The worked example — a bearings distributor

Everything below exists in the repo, so you can rehearse the whole thing end to end.

```bash
# the client's own files, as they would send them
.venv/Scripts/python demo/make_bearings.py      # -> demo/samples/bearings/

# the same business, already set up, to compare against
.venv/Scripts/python -m vyuha_platform seed-bearings
```

The four files are the pile a real distributor sends:

| File | What it is, and what it proves |
|---|---|
| `01-sales-register.xlsx` | A year of bills with a merged title, three junk rows, text dates, ₹ symbols, two Grand Totals, and one customer spelled four ways |
| `02-stock-statement.xlsx` | Today's shelf with reorder levels — a snapshot, so the newest file wins rather than adding up |
| `03-outstanding.xlsx` | Who owes what, keyed by invoice number, with real date cells |
| `04-purchases.csv` | A year of purchases — the cost side of the margin |

**Practice run:** onboard "Shakti Bearings & Power Transmission" through stages 1–3 with the
data map answered as *Excel* for sales, purchases, stock and dues, *bills only* for
payables, and *paper* for expenses, cash and staff. Then send the four files through Data ›
Add data and read what comes back.

---

## Pitfalls, in the order they bite

1. **No phone numbers on staff.** Everything lands on the owner and role routing looks broken.
2. **Items with a rate but no cost.** Margin, gross profit and break-even all go to zero.
3. **Reorder levels left at zero.** The product's best feature never fires.
4. **No GSTIN.** Bills print as a bill of supply and the buyer's accountant sends them back.
5. **Cleaning the client's files first.** Do not. The engine is the thing that handles mess,
   and the read-back is the proof we show them.
6. **Skipping the read-back.** Always open **Data › What was read** after an import. A
   figure read from a guessed column is marked as guessed for a reason.
7. **Going live without reading "Who gets told".** Show the owner who will be messaged
   before anybody is messaged.
