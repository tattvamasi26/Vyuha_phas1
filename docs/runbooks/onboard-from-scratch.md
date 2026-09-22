# Runbook · Onboarding a business from scratch

*Every screen, every option, and the three places the product will quietly give you a wrong
number if you do it in the wrong order. For the Vyuha operator doing the setup.*

**Time:** about 90 minutes with the owner, plus an hour on their files afterwards.
**You need:** an operator account, and whatever files they send.
**Practice on:** `demo/samples/practice/` — a whole business's pile, ready to upload.

---

## 0 · Which account — read this first

The Studio is operator-only. A tenant or a guest who finds `/studio` is sent to their own
business.

- **Real businesses:** make your own operator account at `/signup`, then choose **operator**
  on the screen straight after. That choice is permanent — it decides who can see what, so
  it is not an editable preference.
- **Never onboard anything you care about under `bearings@vyuha.test` or `demo@vyuha.test`.**
  Both seed commands call `_wipe(account.id)`, which deletes *every* business under that
  account before rebuilding ([demo_bearings.py:153-160](../../vyuha_platform/demo_bearings.py#L153-L160)).
  One rehearsal and a real client's workspace is gone.

---

## 1 · Before you sit down with them

Send this a day ahead, on WhatsApp:

> To set you up we need, in whatever form you keep them:
> 1. Your sales register or bill book for the last 12 months
> 2. A current stock list with rates
> 3. A list of who owes you money, with dates
> 4. Purchase bills or a purchase register for the same period
> 5. Your GSTIN, address as it should print on a bill, and bank details
> 6. Names, roles and phone numbers of the people who work with you
>
> Do not clean anything up. Send it exactly as it is.

That last line is the one that matters. A client who "tidies" first deletes the columns we
need and takes a week doing it. Handling the mess is the product.

---

## 2 · Create the business — `/studio` → **Onboard a business**

Four fields, one required.

| Field | What it does |
|---|---|
| **Business name** | Goes on every bill and message; generates the URL slug. Slugs are globally unique, so a second business of the same name becomes `<slug>-2` |
| **Owner's name** | The greeting on Home, and who messages address |
| **Owner's WhatsApp** | Ten digits assume +91. **Every alert, the brief and the private link land here** |
| **Kind of business** | Picks the starter catalogue in stage 3. Distribution & wholesale · Manufacturing & spares · Retail & hardware · Nursery, plants & manure · Farming & agri produce · Dairy & milk · Kirana & grocery. Leave it blank and `theme.guess()` reads the name |

Press **"Create and start the data map"**. Three things happen
([studio.py:102-113](../../vyuha_platform/web/routes/studio.py#L102-L113)):

1. The business is created in **books mode, provisionally** — merging never deletes anything
   a person typed, which is the safe default on day one.
2. An onboarding record is written with the **cut-over set to the 1st of this month**.
3. You land on the **data map**, not the profile — because filling name + owner + WhatsApp
   has *already completed* stage 1. Status is derived from the business, never from whether
   somebody pressed Save ([onboarding.py:201-202](../../vyuha_platform/onboarding.py#L201-L202)).

---

## 3 · Stage 2 · The data map — the interview that decides everything

Eight kinds of record. For each: **where it lives** · **since when** (YYYY-MM) · **who keeps
it** · **how often** · notes.

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

### The seven answers, and what each one commits you to

The page prints this back per record. **Read it to the owner** — it is the moment they
understand what they are buying.

| Answer | How the past comes in | How it keeps flowing |
|---|---|---|
| **Tally** | Export the Day Book and registers, then import | Tally sync from the office PC *(not built)* |
| **Excel / Sheets** | Collect the workbooks as they are and import — no clean-up | Files on a schedule: upload, email-in, watched folder |
| **Other software** | Export to Excel or CSV, then import | A scheduled export, sent as a file |
| **Paper register** | Photograph the pages, or type them into the entry grid | Typed into Vyuha on the phone as it happens |
| **Bills only** | Photograph the bills — Vyuha reads, a person checks | Bill photos forwarded on WhatsApp |
| **WhatsApp** | Export the chat — orders and payments are read out of it | Forwarded to Vyuha's number *(webhook not built)* |
| **Not kept** | Nothing to import — the record starts at cut-over | Typed into Vyuha from day one |

"Not kept" is not a failure. It is the gap Vyuha fills from cut-over onward, and saying so
out loud prevents a disappointed conversation three weeks later.

### ⚠ The answer that freezes

**The Sales answer silently decides how every future file is treated**
([studio.py:242-249](../../vyuha_platform/web/routes/studio.py#L242-L249)):

- Sales = **Tally / Excel / Other software** → **upload mode**. Files are the source of
  truth and each import rebuilds the book from them.
- Sales = **Paper / Bills only / WhatsApp / Not kept** → **books mode**. Entries are typed;
  a file sent later *merges* and never deletes typed rows.

It is only decided **while the business is still empty** — no items, no sales, no file ever
read. After that it is frozen, deliberately: flipping it later would change whether an
upload replaces or merges, which is not a thing to do silently. So answer Sales honestly,
and answer it before you touch stage 3.

### Then, at the foot of the page

- **Cut-over date** — defaults to the 1st of this month. Everything before it is history;
  everything after is the running record.
- **How much history** — None · 3 months · 6 months · 12 months · 2 years · 3 years.

The stage goes green only when **all eight are answered and the cut-over is set**.

---

## 4 · Stage 1 · Profile — the full record

Everything from the create screen, plus:

| Field | Why it matters |
|---|---|
| **Email** | Optional. Email is always a *draft* at the gate, never an auto-send |
| **What they sell, in their words** | e.g. "Motors, pumps, starters and cable" — used in their own language across the product |
| **GSTIN** | **Do not skip it if they have one.** Without it bills print as a *bill of supply*, not a tax invoice, and the buyer's accountant sends them back |
| **State** | Decides **CGST + SGST** within the state against **IGST** across one, frozen on the invoice at the moment it is issued |
| **Business address** | Prints at the head of the invoice |
| **Financial year starts in** | April for almost everybody in India |

**"Save and continue"** advances; **"Save"** stays.

---

## 5 · Stage 3 · Items, branches & staff

### Items — three ways, fastest first

1. **Starter list for their trade** — tick what they carry; ticking opens unit / selling
   price / cost inline. Correct the prices, press **Add ticked items**.
2. **Their file** — if stock is already in Excel, do not type anything. The stock statement
   *is* the item master (see §6).
3. **"Add their own items"** grid — name, category, unit, sells at, costs, reorder at.
   Blank rows are ignored.

Three numbers make an item worth having:

- **Rate** — what they sell it for.
- **Cost** — what they pay. *No cost, no margin, and half of Finance reads zero.*
- **Reorder level** — when to warn. *Left at zero, the best feature in the product never
  fires.*

> **Gotcha.** Items added from the **starter list get a reorder level of 0** — that form has
> no reorder field ([studio.py:275-278](../../vyuha_platform/web/routes/studio.py#L275-L278)).
> Only the typed grid asks for one. Fix them in a single pass at **Settings › Stock**, which
> flags every item with no level set, or in the "Reorder levels" panel on **Operations ›
> Inventory**.

### Branches

Only if there is more than one place of business. A single-branch business should have none —
rows written before a branch existed report under **Unassigned** rather than being guessed
into one.

### Staff — the part that decides whether alerts work

Name, role, branch, **and a phone number**. The role decides who hears what: stock to the
**Manager**, money to the **Accountant**, a customer gone quiet to a **Salesperson**,
everything to the **Owner**. A person with no number is skipped silently, everything lands on
the owner, and role routing gets blamed for not working.

Customer and supplier masters — phone, GSTIN, credit terms, opening balances — arrive with
the data core. Until then customers are picked up from sales as they are recorded.

The stage goes green as soon as there is one item.

---

## 6 · Stages 4–6 by hand — getting the history in

The Studio shows these stages, says what each will do, and links the pages that already do
part of the job. Until they are built, this is the work.

**Where:** **Data › Add data**. The drop zone takes Excel, CSV, tab-separated, PDF or a photo
of a register page, several at once — it submits the moment you choose them. For a pile of
ninety files use **"Or read a folder on this machine"**: paste the path, tick sub-folders.
Nothing is moved; the folder is read where it sits. Photographs and scanned PDFs need a
Claude key.

### The order that works

1. **Stock statement first.** It creates every item with its reorder level and selling rate,
   so a sale can attach to the item it sold ([library.py:422-437](../../vyuha_platform/library.py#L422-L437)).
2. **Sales register.** A year of history against those items.
3. **Outstanding list.** Who owes what.
4. **Type the costs in.** See the second trap below.
5. Anything else — a WhatsApp export, a photographed page.

### The three traps

**1. A purchases file is read as revenue.** `schema.TABLE_RULES` knows only three table kinds
— receivables, stock, sales — and anything with Date / Party / Amount satisfies the sales
rule. Measured on the bearings pack: the sales register is ₹38,91,205 and the purchases file
is read as a *further* ₹39,50,850 of sales. Upload both and revenue is overstated by 102%.
**Do not import a purchase register.** Open it, read the costs off it, and type those in.

**2. Nothing imports cost.** `library.materialise` sets stock quantity, reorder level, selling
rate and branch — never cost ([library.py:423-437](../../vyuha_platform/library.py#L423-L437))
— and `Book.margin` only counts items where a cost is known
([books.py:146-154](../../vyuha_platform/books.py#L146-L154)). So after a purely file-based
onboarding, **gross margin reads zero and stock is valued at the selling price**
(`Item.value` falls back to `rate` when `cost` is 0). Neither says anything is wrong. Type the
costs into the item form on **Operations › Record** before showing anybody Finance.

**3. A dues file headed "Amount" is read as sales.** The receivables rule *requires* an
`OUTSTANDING` field, and plain "Amount" resolves to `AMOUNT`, so the whole file lands as extra
sales with no ageing at all. Headings that work: **Outstanding**, **Outstanding Amount**,
**Balance**, **Balance Due**, **Amount Due**, **Pending**, **Receivable**, **Unpaid**,
**Overdue**, **Closing Balance**. A client's own export will often say "Amount" — rename that
one column before importing, or the money-owed half of the product stays empty.

### Then read the read-back, every time

**Data › What was read** names the sheet, the row the header landed on, which columns were
understood, which were ignored, and every fix applied. Each figure carries **how** it was
identified — `matched` (a close heading), `guessed` (read from its values, no usable heading),
`derived` (the file did not contain it; reconstructed, e.g. qty × rate). The last two are the
ones worth opening the client's file over. This panel is also the pitch: it is the proof that
nothing was invented.

---

## 7 · Sign-off, feeds and go-live

| Stage | What to do today |
|---|---|
| **Check & sign-off** | Open **Finance › Balance sheet** and **Sales › Overview** with the owner and have them say the figures look right. The balance sheet prints what it cannot see — no opening balances, no fixed assets, no loans — read that panel out loud. Note the date |
| **Continuous feeds** | Agree who sends what and how often; set a reminder until feeds exist. **Inbox › Routines** for the 8 am brief |
| **Go-live** | **Settings › Access** — mint the private link and 4-digit PIN. **The PIN is shown once**; a lost PIN means a new link, never a lookup. Send link and PIN as two separate WhatsApp messages. Then **Inbox › Who gets told** — read it with the owner *before* anybody is messaged |

---

## 8 · The practice exercise — a whole business, from empty

```bash
.venv/Scripts/python demo/make_practice.py       # -> demo/samples/practice/
.venv/Scripts/python -m vyuha_platform --open    # the server on :8000
```

**Deshpande Electricals & Motors, Dharwad** — a business that exists nowhere in the product
yet, in a trade neither demo uses, so nothing collides.

Type this in stage 1:

| | |
|---|---|
| Name | Deshpande Electricals & Motors |
| Owner | Anand Deshpande |
| WhatsApp | 9845012345 |
| Trade | Distribution & wholesale |
| GSTIN / State | 29DESHP7788K1Z4 / Karnataka |
| Address | Station Road, Dharwad 580001 |

The pile they sent:

| File | What it is, and what it teaches |
|---|---|
| `01-sales-register.xlsx` | 215 bills over 12 months: merged title, three junk rows, header on row 5, text dates, ₹ symbols, two Grand Totals, one customer spelled four ways |
| `02-stock-statement.xlsx` | 24 items with reorder levels and selling rates — the item master. One item at zero, two at or below reorder |
| `03-outstanding.xlsx` | Five invoices, real date cells, **₹1.52 L overdue across three** |
| `04-purchases.csv` | **Trap 1.** Never import it |
| `05-cost-list.csv` | **Trap 2.** The costs nothing imports — type these in |
| `06-whatsapp-orders.txt` | Five orders, a payment and a balance mention in Kannada-English. Drafts, never facts |
| `07-broken.xlsx` | A PDF renamed `.xlsx`. Must fail cleanly and say what to do |

**The run, about 40 minutes:**

1. Create it (§2). Data map: **Excel / Sheets** for sales, purchases, stock and dues;
   **Bills only** for payables; **Paper register** for expenses, cash and staff. Cut-over =
   1st of this month, history 12 months. → the business flips to **upload mode**.
2. Profile: GSTIN, state, address, FY April.
3. Masters: add two staff *with* phone numbers and a role each. Skip items — the file has them.
4. **Data › Add data** → `02-stock-statement.xlsx`. Check: 24 items on Operations › Inventory,
   one out of stock, two below reorder.
5. → `01-sales-register.xlsx`. Check: Sales › Overview shows 12 months; the four spellings of
   Shakti Borewells have collapsed into one customer.
6. → `03-outstanding.xlsx`. Check: Sales › Collections shows ₹1.52 L overdue across three.
7. **Data › What was read** — find the columns marked guessed or derived, and the ignored
   "Remarks" and "Days" columns.
8. Open **Finance › Profit & loss**. Gross margin is **zero** — trap 2, live. Type three or
   four costs from `05-cost-list.csv` into Operations › Record, reload, watch it appear.
9. Upload `04-purchases.csv` *deliberately*, watch revenue roughly double, then re-run from
   step 4 to clear it. Do this once so you never do it at a client.
10. Finish on `07-broken.xlsx` — the failure that proves the successes.

---

## 9 · Pitfalls, in the order they bite

1. **Onboarding under a demo account** — the next seed deletes the business.
2. **No phone numbers on staff** — everything lands on the owner; role routing looks broken.
3. **Importing a purchase register** — revenue roughly doubles, and nothing says so.
4. **Never typing costs** — margin, gross profit and break-even all read zero.
5. **A dues file headed "Amount"** — read as sales; no ageing, no collections queue.
6. **Reorder levels left at zero** (everything from the starter list) — no stock warnings.
7. **No GSTIN** — bills print as a bill of supply and come back.
8. **Cleaning the client's files first** — don't; the mess is what the engine is for.
9. **Skipping Data › What was read** after an import.
10. **Going live without reading "Who gets told"** to the owner.

---

## 10 · What is not built yet — say it plainly

Nothing runs on a clock on its own: opening the Desk is the scheduler, so messages are
written and a person taps send. Purchases, suppliers, payables, partial payments, returns and
opening balances have no home in the data core yet — which is why stages 4–6 are done by hand
and the balance sheet declares what it cannot see. Orders cannot arrive by themselves;
an exported WhatsApp thread is read today. Quotations are not built. Photographs need a
Claude key. Staff roles decide who *hears* about what, not what they can open.

It has never cost a meeting. Everything somebody would do once they are looking at the
screen is there.
