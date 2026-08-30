"""Ask the business a question in your own words.

The owner does not want a dashboard. He wants to ask "who owes me the most and
since when" the way he would ask his accountant, and get a number back.

Two rules shape everything here.

**The model never sees the raw book.** ``facts()`` builds a compact, exact
summary — totals already computed, top-ten lists already sorted — and that is
the entire context. Handing over five hundred sale rows and asking for a sum
invites arithmetic the model is not reliable at, costs more, and makes the
answer impossible to check. Every number in an answer therefore came from
Python, not from a language model.

**There is always an answer.** A missing API key, no network, or a venue's wifi
must not produce a spinner in front of a prospect, so ``rules()`` answers the
questions an owner actually asks using plain pattern matching over the same
facts. ``ask()`` tries Claude, and falls back the moment it cannot — reporting
which one answered, because a rule-based answer and a reasoned one are
different claims and the operator should be able to tell.

The suggested questions are not decoration either: they are the ones ``rules()``
is known to answer well, so the fallback path is also the demonstrated path.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from . import books, followup, llm, money, people

#: What the console offers as one-tap questions. Ordered by how often an owner
#: would actually ask them, not by how well they demo.
SUGGESTED = [
    "Who owes me the most, and for how long?",
    "What is not selling?",
    "How much cash came in this month?",
    "What am I about to run out of?",
    "Which customers have gone quiet?",
    "What is my best seller?",
    "Where is my money going?",
    "How are my branches doing?",
]

SYSTEM = """You are Vyuha, answering questions about one small business in India.

You are given a JSON summary of that business. Rules, in order of importance:

1. Answer ONLY from the JSON. Never estimate, never infer a number that is not
   there, never fill a gap with a plausible figure.
2. If the JSON does not contain the answer, say exactly what is missing and what
   the owner would have to record for you to answer it next time.
3. Quote figures exactly as given. Amounts are Indian rupees — write them as
   Rs 1,23,456 using Indian digit grouping.
4. Answer in three sentences or fewer unless a list is genuinely needed. The
   reader is busy and is reading on a phone.
5. Lead with the number, then the context. "Ramu owes the most - Rs 45,000,
   overdue 34 days." not "Looking at your receivables, I can see that..."
6. Plain English. No dashboards, no metrics vocabulary, no preamble, no offer
   to help further."""


@dataclass
class Reply:
    ok: bool
    text: str = ""
    #: "claude" | "cache" | "rules" — surfaced in the UI.
    source: str = "rules"
    error: str = ""
    used: list[str] = field(default_factory=list)   # which fact groups were read

    @property
    def label(self) -> str:
        return {"claude": "Answered by Claude",
                "cache": "Answered by Claude (from cache)",
                "rules": "Answered from your numbers directly"}.get(self.source, self.source)


# ------------------------------------------------------------------- the facts

def facts(client, book, ledger=None, org=None, quotes=None) -> dict:
    """Everything the agent is allowed to know, already computed.

    Small on purpose. Twenty exact numbers beat five hundred rows: the model
    reasons better over them, the call is cheaper, and a human can audit the
    answer against this dict in ten seconds.
    """
    ledger = ledger if ledger is not None else money.Ledger(slug=client.slug)
    org = org if org is not None else people.Org(slug=client.slug)
    summary = books.summary(book)

    sold_qty: dict[str, float] = {}
    for s in book.sales:
        sold_qty[s.sku] = sold_qty.get(s.sku, 0.0) + s.qty

    out = {
        "business": client.name,
        "trade": client.industry or client.trade,
        "as_of": summary["last_updated"] or "no sales recorded yet",
        "sales": {
            "total_earned": round(summary["earned"]),
            "cash_collected": round(summary["collected"]),
            "still_owed_to_you": round(summary["owed"]),
            "profit_where_cost_known": round(summary["margin"]),
            "bills": summary["bills"],
            "customers": summary["customers"],
            "best_sellers": [{"item": n, "qty_sold": q} for n, q in summary["best_sellers"]],
        },
        "stock": {
            "items_carried": summary["items"],
            "stock_value": round(summary["stock_value"]),
            "below_reorder": [
                {"item": i.name, "left": i.stock_qty, "reorder_at": i.reorder_level,
                 "unit": i.unit}
                for i in summary["low_stock"][:10]
            ],
            "out_of_stock": [i.name for i in summary["out_of_stock"][:10]],
            "never_sold": [
                {"item": i.name, "stock": i.stock_qty, "cash_locked_up": round(i.value)}
                for i in summary["never_sold"][:10]
            ],
        },
        "money": money.facts(book, ledger),
        "followups": followup.facts(client.slug, book, quotes),
    }
    if org.has_branches:
        out["branches"] = people.facts(org, book, ledger)
    return out


# ------------------------------------------------------------- the fallback

def _rs(v) -> str:
    """Indian digit grouping, without importing the HTML-flavoured formatter."""
    try:
        v = round(float(v))
    except (TypeError, ValueError):
        return "Rs 0"
    s = str(abs(v))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        head = re.sub(r"(\d)(?=(\d\d)+$)", r"\1,", head)
        s = f"{head},{tail}"
    return f"{'-' if v < 0 else ''}Rs {s}"


def _match(question: str, *words: str) -> bool:
    q = question.lower()
    return any(w in q for w in words)


def rules(question: str, f: dict) -> Reply:
    """Answer without a model. Covers what an owner actually asks."""
    q = question.strip()
    if not q:
        return Reply(False, error="Ask a question first.")

    sales, stock, cash, chase = f["sales"], f["stock"], f["money"], f["followups"]

    # --- refuse to speculate, before any keyword branch can catch it.
    # "What will the monsoon do to my sales next year?" contains "sales", and
    # without this guard the revenue branch answers it with last year total --
    # which reads as a forecast. Answering the wrong question confidently is
    # worse than not answering.
    if _match(q, "will ", "next year", "next month", "forecast", "predict",
              "expect", "future", "should i", "going to", "estimate",
              "projection", "monsoon", "weather"):
        return Reply(False, error="not-understood")

    # --- who owes me
    if _match(q, "owe", "owes", "outstanding", "receivable", "collect", "udhaar", "credit"):
        rows = chase.get("overdue_payments", [])
        if not rows:
            if sales["still_owed_to_you"] > 0:
                return Reply(True, f"{_rs(sales['still_owed_to_you'])} is still owed to you, "
                                   f"but none of it is past its due date yet.", used=["sales"])
            return Reply(True, "Nobody owes you anything right now — every bill is paid.",
                         used=["sales"])
        top = rows[0]
        rest = "".join(f"\n• {r['party']} — {_rs(r['amount'])}, {r['days_late']} days late"
                       for r in rows[1:5])
        return Reply(True,
                     f"{top['party']} owes the most — {_rs(top['amount'])} on bill "
                     f"{top['bill']}, {top['days_late']} days past due. "
                     f"{_rs(chase['money_to_chase'])} is overdue across "
                     f"{len(rows)} customer(s).{rest}", used=["followups"])

    # --- what is not selling
    if _match(q, "not selling", "dead", "slow", "stuck", "not moving", "unsold"):
        rows = stock.get("never_sold", [])
        if not rows:
            return Reply(True, "Everything you carry has sold at least once.", used=["stock"])
        locked = sum(r["cash_locked_up"] for r in rows)
        names = "".join(f"\n• {r['item']} — {r['stock']:g} in stock, "
                        f"{_rs(r['cash_locked_up'])} tied up" for r in rows[:5])
        return Reply(True, f"{len(rows)} item(s) have never sold, with {_rs(locked)} "
                           f"of your cash sitting in them.{names}", used=["stock"])

    # --- running out
    if _match(q, "run out", "running out", "low stock", "reorder", "restock", "short"):
        rows = stock.get("below_reorder", [])
        gone = stock.get("out_of_stock", [])
        if not rows and not gone:
            return Reply(True, "Nothing is below its reorder level right now.", used=["stock"])
        parts = []
        if gone:
            parts.append(f"{len(gone)} item(s) are already out: " + ", ".join(gone[:5]) + ".")
        if rows:
            names = "".join(f"\n• {r['item']} — {r['left']:g} {r['unit']} left, "
                            f"reorder at {r['reorder_at']:g}" for r in rows[:6])
            parts.append(f"{len(rows)} item(s) are below reorder level.{names}")
        return Reply(True, " ".join(parts), used=["stock"])

    # --- cash
    if _match(q, "cash", "money came", "came in", "went out", "spend", "spent", "expense",
              "where is my money", "profit", "margin"):
        if _match(q, "where", "spend", "spent", "expense", "going"):
            cats = cash.get("top_expense_categories", [])
            if not cats:
                return Reply(True, "No expenses have been recorded yet, so Vyuha only knows "
                                   "what came in. Add purchases and running costs on the "
                                   "Money panel and this becomes a real cash flow.",
                             used=["money"])

            names = "".join(f"\n• {c['category']} — {_rs(c['amount'])}" for c in cats)
            return Reply(True, f"{_rs(cash['cash_went_out'])} has gone out in total. "
                               f"Biggest heads:{names}", used=["money"])
        return Reply(True,
                     f"{_rs(cash['cash_came_in'])} has come in and "
                     f"{_rs(cash['cash_went_out'])} has gone out, leaving "
                     f"{_rs(cash['net_cash'])} net. "
                     f"{_rs(cash['still_to_collect'])} is still to be collected and "
                     f"{_rs(cash['still_to_pay'])} still to be paid.",
                     used=["money"])

    # --- quiet customers
    if _match(q, "quiet", "stopped", "not bought", "lost customer", "dormant", "come back"):
        rows = chase.get("customers_gone_quiet", [])
        if not rows:
            return Reply(True, "No regular customer has gone quiet — everyone who buys "
                               "repeatedly has bought recently.", used=["followups"])
        names = "".join(f"\n• {r['party']} — {r['days_silent']} days, "
                        f"{_rs(r['past_spend'])} spent before" for r in rows[:5])
        return Reply(True, f"{len(rows)} repeat customer(s) have gone quiet.{names}",
                     used=["followups"])

    # --- best seller
    if _match(q, "best", "top seller", "most sold", "popular", "fastest"):
        rows = sales.get("best_sellers", [])
        if not rows:
            return Reply(True, "No sales recorded yet, so there is no best seller.",
                         used=["sales"])
        names = "".join(f"\n• {r['item']} — {r['qty_sold']:g} sold" for r in rows[:5])
        return Reply(True, f"{rows[0]['item']} is your best seller at "
                           f"{rows[0]['qty_sold']:g} units.{names}", used=["sales"])

    # --- branches
    if _match(q, "branch", "branches", "shop", "godown", "location", "outlet"):
        b = f.get("branches")
        if not b or not b.get("branches"):
            return Reply(True, "Only one location is set up, so there is nothing to compare. "
                               "Add a branch on the People panel to split these numbers.",
                         used=["branches"])
        rows = b["branches"]
        def line(r):
            # A row with no revenue is company-wide cost sitting in Unassigned
            # (salary, for one). Reporting it by revenue reads as a dead branch;
            # dropping it would hide real money. So report what it actually is.
            if not r["revenue"]:
                return f"\n• {r['name']} — no sales, {_rs(r['spend'])} of shared cost"
            return (f"\n• {r['name']} — {_rs(r['revenue'])} from {r['bills']} bill(s), "
                    f"{int(r['share_of_revenue'] * 100)}% of revenue")

        names = "".join(line(r) for r in rows)
        return Reply(True, f"{b['branch_count']} branch(es), {b['staff_count']} people."
                           f"{names}", used=["branches"])

    # --- how much did I earn
    if _match(q, "earn", "revenue", "sales", "turnover", "how much", "business did"):
        return Reply(True,
                     f"{_rs(sales['total_earned'])} earned across {sales['bills']} bill(s) "
                     f"from {sales['customers']} customer(s). "
                     f"{_rs(sales['cash_collected'])} of that is collected, "
                     f"{_rs(sales['still_owed_to_you'])} is still owed.",
                     used=["sales"])

    return Reply(False, error="not-understood")


# ------------------------------------------------------------------- asking

def ask(question: str, client, book, settings, ledger=None, org=None,
        quotes=None, prefer_rules: bool = False) -> Reply:
    """Answer a question about this business. Never raises, always answers."""
    question = (question or "").strip()
    if not question:
        return Reply(False, error="Ask a question first.")

    f = facts(client, book, ledger, org, quotes)
    fallback = rules(question, f)

    # A question the rules answer exactly is better served by them: instant,
    # free, and provably arithmetic rather than generated.
    if prefer_rules and fallback.ok:
        return fallback

    prompt = (f"Business facts as JSON:\n\n```json\n"
              f"{json.dumps(f, indent=2, default=str)}\n```\n\n"
              f"The owner asks: {question}")

    answer = llm.ask(prompt, settings, system=SYSTEM)
    if answer.ok:
        return Reply(True, text=answer.text.strip(),
                     source="cache" if answer.cached else "claude",
                     used=list(f.keys()))

    if fallback.ok:
        fallback.error = ""     # the fallback worked; the failure is not the user's problem
        return fallback

    # Neither path could answer. Say which, and what to do about it.
    if fallback.error == "not-understood":
        why = ("Vyuha could not match that to your numbers, and Claude is not available "
               f"to reason about it ({answer.error}).")
        action = answer.needs_action or "Try one of the suggested questions below."
    else:
        why = answer.error or "No answer could be produced."
        action = answer.needs_action or ""
    return Reply(False, error=why + (f" {action}" if action else ""), source="rules")
