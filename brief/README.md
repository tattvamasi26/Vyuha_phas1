# Vyuha brief pack

Six files you paste into a Claude chat so it can write **brochures, decks,
one-pagers, case studies and PDFs** about Vyuha without you re-explaining the
product every time.

## How to use it

**Paste two files, then ask.**

1. Always paste **`01-what-vyuha-is.md`**. That is the product.
2. Add whichever of these the job needs:
   - **`02-the-numbers.md`** — for anything with figures in it (a deck, a case
     study, a bank file)
   - **`03-who-youre-reading-to.md`** — when the audience is not you
   - **`04-how-vyuha-talks.md`** — for anything a customer will read
3. Then ask. **`05-ready-prompts.md`** has the asks already written — copy one
   and change the details.

That is the whole method. If an output comes back wrong, it is almost always
because one of those files was not pasted.

## What each file is for

| File | Paste it when |
|---|---|
| `01-what-vyuha-is.md` | Always. Nothing works without it. |
| `02-the-numbers.md` | The output needs real figures |
| `03-who-youre-reading-to.md` | Writing for a prospect, investor or bank |
| `04-how-vyuha-talks.md` | A customer will read the output |
| `05-ready-prompts.md` | You want the ask already written |
| `06-what-is-not-built.md` | Before promising anything in a meeting |

## Two rules that matter

**Never let it invent a number.** Every figure in `02-the-numbers.md` is real,
computed from the demo workspace. If Claude needs a number that is not in that
file, the honest answer is to leave it out — a made-up figure in a bank file or
an investor deck is the one mistake you cannot walk back.

**Read `06-what-is-not-built.md` before a meeting.** Three of the ten features
are not built. Saying so is fine. Being caught is not.

---

Regenerate the figures in `02-the-numbers.md` after any change to the demo:

```
.venv/Scripts/python -m vyuha_platform seed
```
