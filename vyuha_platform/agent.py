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
from datetime import date

from . import analysis, books, finance, followup, llm, money, people

#: What the console offers as one-tap questions. Ordered by how often an owner
#: would actually ask them, not by how well they demo.
SUGGESTED = [
    "Who owes me the most, and for how long?",
    "Which items make me the least margin?",
    "What changed this month against last month?",
    "What am I about to run out of?",
    "Which customers have gone quiet?",
    "Is my biggest customer a risk?",
    "Where is my money going?",
    "Make me a case study deck",
]

#: Kept separate from SUGGESTED: these are the ones ``rules()`` answers without
#: a model, so the console can still offer something useful when it is offline.
OFFLINE_SUGGESTED = [
    "Who owes me the most, and for how long?",
    "What is not selling?",
    "What am I about to run out of?",
    "Which customers have gone quiet?",
    "What is my best seller?",
    "Where is my money going?",
    "Make me a business review deck",
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
    #: Set when the answer produced a deck. The console turns it into links
    #: rather than a panel, because a deck is something you *ask for*, not a
    #: place you go — which is why it no longer has a tab.
    deck: str = ""
    deck_label: str = ""

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


#: build_deck calls this rather than ``facts`` directly, so the deck keeps
#: working if the public name ever changes.
def facts_for(client, book, ledger=None, org=None, quotes=None) -> dict:
    return facts(client, book, ledger, org, quotes)


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

    # --- a deck request, before anything else. "Make me a case study on my
    # biggest customer" mentions a customer and is not a question about one, so
    # the keyword branches below would answer the wrong thing entirely.
    if _match(q, "deck", "presentation", "slides", "ppt", "powerpoint",
              "case study", "pitch"):
        return Reply(False, error="wants-deck")

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
    if fallback.error in {"not-understood", "wants-deck"}:
        why = ("Vyuha could not match that to your numbers, and Claude is not available "
               f"to reason about it ({answer.error}).")
        action = answer.needs_action or "Try one of the suggested questions below."
    else:
        why = answer.error or "No answer could be produced."
        action = answer.needs_action or ""
    return Reply(False, error=why + (f" {action}" if action else ""), source="rules")


# =====================================================================
# Tools — what the model can actually do
#
# The fixed-summary design had a ceiling: a question outside the shapes
# somebody anticipated could not be answered, because the number was not in the
# summary and nothing could go and fetch it. These let the model ask its own
# questions of the books and chain the answers.
#
# `query_sales` carries most of the weight. One general group-by/filter/measure
# call replaces thirty specific ones, and it is what makes "which item has the
# worst margin at Hubballi since June" answerable without anyone having
# predicted it.
# =====================================================================

TOOLS: list[dict] = [
    {
        "name": "query_sales",
        "description": (
            "Group, filter and measure sales along any dimension. The main tool "
            "— use it for almost every question about what sold, to whom, when, "
            "where, and how profitably. Set ascending=true for worst-performing "
            "questions. Dates are ISO (YYYY-MM-DD)."),
        "input_schema": {
            "type": "object",
            "properties": {
                "group_by": {"type": "string",
                             "enum": list(analysis.DIMENSIONS),
                             "description": "The dimension to group by."},
                "measure": {"type": "string", "enum": list(analysis.MEASURES),
                            "description": "What to rank by."},
                "since": {"type": "string", "description": "Start date, inclusive."},
                "until": {"type": "string", "description": "End date, inclusive."},
                "party": {"type": "string", "description": "Filter to a customer (partial name works)."},
                "item": {"type": "string", "description": "Filter to an item (partial name works)."},
                "branch": {"type": "string", "description": "Filter to a branch."},
                "category": {"type": "string", "description": "Filter to an item category."},
                "unpaid_only": {"type": "boolean", "description": "Only credit sales not yet paid."},
                "top_n": {"type": "integer", "description": "How many groups to return (max 50)."},
                "ascending": {"type": "boolean",
                              "description": "True for the worst/smallest first."},
            },
            "required": [],
        },
    },
    {
        "name": "stock_report",
        "description": (
            "What is on the shelf. state: all | low (below reorder) | out "
            "(nothing left) | dead (never sold) | moving (has sold)."),
        "input_schema": {
            "type": "object",
            "properties": {
                "state": {"type": "string",
                          "enum": ["all", "low", "out", "dead", "moving"]},
                "sort": {"type": "string", "enum": ["value", "stock", "sold", "idle"]},
                "category": {"type": "string"},
                "top_n": {"type": "integer"},
            },
            "required": [],
        },
    },
    {
        "name": "customer_detail",
        "description": ("Everything about one customer: what they buy, what they "
                        "have spent, what they still owe, when they last came."),
        "input_schema": {
            "type": "object",
            "properties": {"party": {"type": "string"}},
            "required": ["party"],
        },
    },
    {
        "name": "item_detail",
        "description": ("One product: stock, cost, selling price, margin, units "
                        "sold, and who buys it."),
        "input_schema": {
            "type": "object",
            "properties": {"item": {"type": "string"}},
            "required": ["item"],
        },
    },
    {
        "name": "compare_periods",
        "description": ("The last N days against the N days before that, with the "
                        "biggest movers and anyone who stopped buying. Use this "
                        "for any question about trend, growth or change."),
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "Window length. 30 = month on month."},
                "group_by": {"type": "string", "enum": list(analysis.DIMENSIONS)},
                "measure": {"type": "string", "enum": list(analysis.MEASURES)},
            },
            "required": [],
        },
    },
    {
        "name": "financial_statements",
        "description": (
            "Profit and loss, cash flow, balance sheet, receivables and payables "
            "ageing, ratios (margins, debtor/creditor/stock days, cash cycle, "
            "current ratio), customer concentration and break-even. period is "
            "'all', 'fy:2026-27' or 'month:2026-08'."),
        "input_schema": {
            "type": "object",
            "properties": {"period": {"type": "string"}},
            "required": [],
        },
    },
    {
        "name": "make_deck",
        "description": (
            "Build a slide deck from this business's own numbers and return where "
            "it can be opened. Use it whenever the owner asks for a deck, "
            "presentation, case study or pitch. audience: review (for the owner) "
            "| case-study (for a prospect) | investor | bank. brief is one line "
            "saying what it should argue."),
        "input_schema": {
            "type": "object",
            "properties": {
                "audience": {"type": "string",
                             "enum": ["review", "case-study", "investor", "bank"]},
                "brief": {"type": "string"},
            },
            "required": [],
        },
    },
    {
        "name": "list_followups",
        "description": ("Who is worth contacting today: overdue payments and "
                        "regular customers who have gone quiet."),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "list_branches",
        "description": "Branch-by-branch revenue, spend, bills and customers.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
]


SYSTEM_TOOLS = """You are Vyuha, answering questions about one Indian small business
for its owner. You have tools that query his actual books.

How to work:
1. Call tools to get real figures. Never answer a factual question from memory or
   from what an earlier tool call implied — fetch it.
2. Chain calls when you need to. "Which of my slow items is my biggest customer
   still buying" is two or three calls, and that is fine.
3. Do arithmetic with the tools, not in your head. If you want a comparison, use
   compare_periods. If you want the worst performer, pass ascending=true.
4. If the tools genuinely cannot answer, say exactly what is missing and what he
   would have to record for you to answer it next time. Never estimate.

How to reply:
- Lead with the number, then the context. "Ramu Stores owes the most — Rs 45,000,
  overdue 34 days." Not "Looking at your receivables...".
- Amounts are Indian rupees. Write them as Rs 1,23,456 with Indian digit grouping.
- Three sentences or fewer unless a list is genuinely clearer. He is on a phone.
- Plain English. No metrics vocabulary, no preamble, no offer to help further.
- If something in the answer is worth acting on, say what to do in one clause."""


#: The last deck brief per client, so /deck/view rebuilds exactly what was
#: described rather than a generic one. In-process and small: a deck is cheap to
#: rebuild and losing this on restart costs nothing.
DECK_BRIEFS: dict[str, tuple[str, str]] = {}


def build_deck(client, book, ledger, org, settings, brief: str = "",
               audience: str = "review") -> dict:
    """Make a deck and say where it is. Shared by the tool and the offline path."""
    from . import decks, finance

    facts = {**facts_for(client, book, ledger, org), **finance.facts(book, ledger)}
    outline = decks.outline(brief, audience, client, facts, settings)
    DECK_BRIEFS[client.slug] = (brief, audience)
    return {
        "made": True,
        "title": outline.title,
        "slides": len(outline.slides),
        "headings": [s.heading for s in outline.slides],
        "written_by": outline.label,
        "open_at": f"/c/{client.slug}/deck/view",
        "download_pptx": f"/c/{client.slug}/deck/pptx",
        "download_pdf": f"/c/{client.slug}/deck/pdf",
    }


def _tools_for(client, book, ledger, org, quotes=None, settings=None):
    """Bind the tool names to real calls over this client's books."""

    def run(name: str, args: dict):
        if name == "query_sales":
            return analysis.query_sales(book, org, **args)
        if name == "stock_report":
            return analysis.stock_report(book, **args)
        if name == "customer_detail":
            return analysis.customer_detail(book, args.get("party", ""))
        if name == "item_detail":
            return analysis.item_detail(book, args.get("item", ""))
        if name == "compare_periods":
            return analysis.compare_windows(book, org, **args)
        if name == "financial_statements":
            return finance.facts(book, ledger, args.get("period", "all"))
        if name == "make_deck":
            return build_deck(client, book, ledger, org, settings,
                              brief=args.get("brief", ""),
                              audience=args.get("audience", "review"))
        if name == "list_followups":
            return followup.facts(client.slug, book, quotes)
        if name == "list_branches":
            return people.facts(org, book, ledger)
        raise ValueError(f"No such tool: {name}")

    return run


def investigate(question: str, client, book, settings, ledger=None, org=None,
                quotes=None) -> Reply:
    """Answer by letting the model query the books itself.

    Falls back to ``rules()`` the moment the model is unavailable, so the
    offline path is never a dead end.
    """
    ledger = ledger if ledger is not None else money.Ledger(slug=client.slug)
    org = org if org is not None else people.Org(slug=client.slug)

    context = (f"Business: {client.name}"
               f"{' (' + client.industry + ')' if client.industry else ''}. "
               f"Today is {date.today().isoformat()}. "
               f"Their financial year runs April to March.\n\n"
               f"The owner asks: {question}")

    conversation = llm.run_tools(
        context, settings, TOOLS,
        _tools_for(client, book, ledger, org, quotes, settings),
        system=SYSTEM_TOOLS)

    if conversation.ok:
        made = next((c for c in conversation.calls if c.name == "make_deck"), None)
        return Reply(True, text=conversation.text.strip(), source="claude",
                     used=[c.name for c in conversation.calls],
                     deck=f"/c/{client.slug}/deck/view" if made else "",
                     deck_label="Written by Claude from your brief" if made else "")

    fallback = rules(question, facts(client, book, ledger, org, quotes))

    # A deck asked for with no model available still gets built — from the same
    # numbers, through the same renderer. What is lost is the argument being
    # tailored, and the deck itself says so.
    if not fallback.ok and fallback.error == "wants-deck":
        audience = ("case-study" if _match(question, "case study") else
                    "investor" if _match(question, "investor", "funding", "pitch") else
                    "bank" if _match(question, "bank", "loan", "credit") else "review")
        made = build_deck(client, book, ledger, org, settings,
                          brief=question, audience=audience)
        return Reply(
            True, source="rules",
            text=(f"Built \"{made['title']}\" — {made['slides']} slides: "
                  + ", ".join(made["headings"][:4])
                  + (f" and {made['slides'] - 4} more" if made["slides"] > 4 else "")
                  + ". Open it below."),
            deck=made["open_at"], deck_label=made["written_by"])

    if fallback.ok:
        return fallback
    return Reply(False, source="rules",
                 error=(conversation.error or "No answer could be produced.")
                       + (f" {conversation.needs_action}" if conversation.needs_action else ""))
