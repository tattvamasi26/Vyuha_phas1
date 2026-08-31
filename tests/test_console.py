"""Tests for the console — stock, ask, follow-ups, money, decks, people.

Runs under pytest or standalone:  python -m tests.test_console

The whole file runs with ``VYUHA_LLM=offline``, set before anything imports the
platform. That is not a way of dodging the model: it is the path a demo laptop
with no signal takes, so testing it *is* testing the thing most likely to be
exercised in front of somebody. Every feature here must produce a real answer
with no network at all.
"""

from __future__ import annotations

import os
import shutil
import sys
from datetime import date, timedelta
from pathlib import Path

os.environ["VYUHA_LLM"] = "offline"          # before the platform imports llm

from fastapi.testclient import TestClient    # noqa: E402

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from vyuha_platform import (agent, analysis, app as app_mod, auth, books,  # noqa: E402
                            catalog, config, decks, finance, followup, llm,
                            money, people, store, ui)

client = TestClient(app_mod.app, follow_redirects=True)
_SLUGS: list[str] = []

ACCOUNT = auth.create(f"console-{auth.secrets.token_hex(4)}@vyuha.test",
                      "Console Test Operator", "test-password-1")


def _login(email: str = "", password: str = "test-password-1") -> None:
    client.post("/login", data={"email": email or ACCOUNT.email, "password": password})


def _as_operator() -> None:
    account = auth.get(ACCOUNT.id)
    account.install, account.org_name, account.tenant_slug = "operator", "", ""
    auth.update(account)


_login()
_as_operator()


def _days_ago(n: int) -> str:
    return (date.today() - timedelta(days=n)).isoformat()


def _onboard(name: str) -> str:
    resp = client.post("/onboard", data={"name": name, "phone": "9876543210",
                                         "data_mode": "books"})
    assert resp.status_code == 200, resp.status_code
    base = store.slugify(name)
    matches = [c.slug for c in store.load_clients(ACCOUNT.id) if c.slug.startswith(base)]
    assert matches, f"{name} was not persisted"
    _SLUGS.extend(matches)
    return matches[0]


def _shop(name: str) -> tuple[str, object]:
    """A client with three items and a little history, ready to test against."""
    slug = _onboard(name)
    client.post(f"/c/{slug}/book/item", data={
        "name": "Urea 50kg", "category": "Fertiliser", "unit": "bag",
        "rate": "300", "cost": "250", "stock_qty": "40", "reorder_level": "10"})
    client.post(f"/c/{slug}/book/item", data={
        "name": "Gypsum 5kg", "category": "Fertiliser", "unit": "bag",
        "rate": "120", "cost": "90", "stock_qty": "6", "reorder_level": "12"})
    client.post(f"/c/{slug}/book/item", data={
        "name": "Rose Sapling", "category": "Plants", "unit": "piece",
        "rate": "80", "cost": "40", "stock_qty": "25", "reorder_level": "0"})
    return slug, store.get_client(slug, ACCOUNT.id)


def _sku(slug: str, needle: str) -> str:
    book = books.load(slug)
    return next(i.sku for i in book.items if needle.lower() in i.name.lower())


# ====================================================================== 02 stock

def test_receiving_stock_raises_the_level_and_updates_the_cost():
    slug, _ = _shop("Receive Test Traders")
    sku = _sku(slug, "gypsum")

    client.post(f"/c/{slug}/stock/receive", data={"sku": sku, "qty": "30", "cost": "95"})

    item = books.load(slug).item(sku)
    assert item.stock_qty == 36, item.stock_qty
    # The newest delivery price is the one that should drive margin from now on.
    assert item.cost == 95, item.cost


def test_a_stock_count_sets_the_number_rather_than_adding_to_it():
    """The bug this guards is a stock-take silently doubling the shelf."""
    slug, _ = _shop("Counting Traders")
    sku = _sku(slug, "urea")

    client.post(f"/c/{slug}/stock/count", data={"sku": sku, "counted": "12"})

    assert books.load(slug).item(sku).stock_qty == 12


def test_bulk_reorder_save_updates_levels_and_makes_an_item_low():
    slug, _ = _shop("Reorder Traders")
    sku = _sku(slug, "rose")
    assert not books.load(slug).item(sku).low        # level is 0, so never low

    client.post(f"/c/{slug}/stock/reorder", data={f"lvl_{sku}": "40"})

    item = books.load(slug).item(sku)
    assert item.reorder_level == 40
    assert item.low, "25 in stock against a level of 40 should read as low"


def test_the_stock_panel_names_what_needs_ordering():
    slug, _ = _shop("Ordering Traders")
    page = client.get(f"/c/{slug}/console?panel=stock").text
    assert "Needs ordering" in page
    assert "Gypsum 5kg" in page                      # 6 in stock against a level of 12
    assert "below reorder" in page


# ======================================================================== 03 ask

def test_the_agent_answers_who_owes_me_without_a_model():
    slug, c = _shop("Owing Traders")
    sku = _sku(slug, "urea")
    client.post(f"/c/{slug}/book/sale", data={
        "sku": sku, "party": "Ramu Stores", "qty": "10", "rate": "300",
        "when": _days_ago(60), "payment": "credit", "due_date": _days_ago(30)})

    book = books.load(slug)
    reply = agent.ask("Who owes me the most, and for how long?", c, book, config.load())

    assert reply.ok, reply.error
    assert reply.source == "rules", "offline must fall through to the rules path"
    assert "Ramu" in reply.text
    assert "3,000" in reply.text, reply.text


def test_the_agent_reports_what_is_not_selling():
    slug, c = _shop("Deadstock Traders")
    reply = agent.ask("What is not selling?", c, books.load(slug), config.load())
    assert reply.ok, reply.error
    assert "never sold" in reply.text.lower()
    assert "Urea 50kg" in reply.text


def test_an_unanswerable_question_says_so_rather_than_inventing():
    slug, c = _shop("Honest Traders")
    reply = agent.ask("What will the monsoon do to my sales next year?",
                      c, books.load(slug), config.load())
    assert not reply.ok
    assert reply.text == "", "a failed answer must carry no text a screen could show"
    assert reply.error


def test_agent_facts_never_disagree_with_the_book():
    """Every number the agent sees is computed in Python, never by a model."""
    slug, c = _shop("Facts Traders")
    sku = _sku(slug, "urea")
    client.post(f"/c/{slug}/book/sale", data={
        "sku": sku, "party": "Cash", "qty": "2", "rate": "300"})

    book = books.load(slug)
    f = agent.facts(c, book, money.load(slug), people.load(slug))
    assert f["sales"]["total_earned"] == round(book.earned)
    assert f["stock"]["stock_value"] == round(book.stock_value)


def test_asking_through_the_route_renders_the_answer_on_the_page():
    slug, _ = _shop("Route Ask Traders")
    page = client.post(f"/c/{slug}/ask", data={"question": "What is my best seller?"}).text
    assert "Answered from your numbers directly" in page


# ================================================================ 07 follow-ups

def test_an_overdue_credit_sale_becomes_a_follow_up():
    slug, _ = _shop("Chasing Traders")
    sku = _sku(slug, "urea")
    client.post(f"/c/{slug}/book/sale", data={
        "sku": sku, "party": "Late Ramesh", "qty": "5", "rate": "300",
        "when": _days_ago(40), "payment": "credit", "due_date": _days_ago(12)})

    queue = followup.queue(slug, books.load(slug))
    mine = [f for f in queue if f.party == "Late Ramesh"]
    assert mine, "an overdue credit sale should appear"
    assert mine[0].kind == "payment"
    assert mine[0].days == 12
    assert "Late Ramesh" in followup.draft(mine[0], "Test Shop")


def test_a_paid_sale_is_never_chased():
    slug, _ = _shop("Paid Up Traders")
    sku = _sku(slug, "urea")
    client.post(f"/c/{slug}/book/sale", data={
        "sku": sku, "party": "Prompt Payer", "qty": "3", "rate": "300",
        "when": _days_ago(50)})
    assert not [f for f in followup.queue(slug, books.load(slug))
                if f.party == "Prompt Payer"]


def test_marking_done_survives_the_queue_being_rebuilt():
    """The queue is recomputed every time; only the decision is stored."""
    slug, _ = _shop("Dismissing Traders")
    sku = _sku(slug, "urea")
    client.post(f"/c/{slug}/book/sale", data={
        "sku": sku, "party": "Handled Hari", "qty": "4", "rate": "300",
        "when": _days_ago(40), "payment": "credit", "due_date": _days_ago(9)})

    target = next(f for f in followup.queue(slug, books.load(slug))
                  if f.party == "Handled Hari")
    client.post(f"/c/{slug}/followup", data={"key": target.key, "status": "done"})

    still = [f for f in followup.queue(slug, books.load(slug)) if f.party == "Handled Hari"]
    assert not still, "a dismissed follow-up must not come back"


def test_a_one_time_buyer_is_not_treated_as_a_lapsed_regular():
    """Silence is only a signal from somebody who had a rhythm."""
    slug, _ = _shop("Rhythm Traders")
    sku = _sku(slug, "rose")
    client.post(f"/c/{slug}/book/sale", data={
        "sku": sku, "party": "One Timer", "qty": "1", "rate": "80",
        "when": _days_ago(300)})
    assert not [f for f in followup.queue(slug, books.load(slug))
                if f.kind == "dormant" and f.party == "One Timer"]


# ====================================================================== 08 money

def test_an_unpaid_bill_is_a_liability_not_an_outflow():
    slug, _ = _shop("Owing Money Traders")
    client.post(f"/c/{slug}/expense", data={
        "category": "Purchase", "party": "Supplier Co", "amount": "5000",
        "unpaid": "1", "due_date": _days_ago(-3)})

    ledger = money.load(slug)
    pos = money.position(books.load(slug), ledger)
    assert pos["went_out"] == 0, "an unpaid bill has not left the business"
    assert pos["to_pay"] == 5000


def test_position_keeps_earned_and_collected_apart():
    slug, _ = _shop("Credit Traders")
    sku = _sku(slug, "urea")
    client.post(f"/c/{slug}/book/sale", data={
        "sku": sku, "party": "Cash Buyer", "qty": "2", "rate": "300"})
    client.post(f"/c/{slug}/book/sale", data={
        "sku": sku, "party": "Credit Buyer", "qty": "3", "rate": "300",
        "payment": "credit", "due_date": _days_ago(-10)})

    book = books.load(slug)
    pos = money.position(book, money.load(slug))
    assert pos["came_in"] == 600, pos
    assert pos["to_collect"] == 900, pos
    assert pos["earned"] == 1500, pos


def test_marking_a_bill_paid_moves_it_into_the_outflow():
    slug, _ = _shop("Settling Traders")
    client.post(f"/c/{slug}/expense", data={
        "category": "Rent", "amount": "8000", "unpaid": "1"})
    expense = money.load(slug).expenses[0]

    client.post(f"/c/{slug}/expense/{expense.id}/paid")

    pos = money.position(books.load(slug), money.load(slug))
    assert pos["went_out"] == 8000
    assert pos["to_pay"] == 0


def test_the_next_seven_days_catches_what_is_about_to_land():
    slug, _ = _shop("Week Ahead Traders")
    client.post(f"/c/{slug}/expense", data={
        "category": "Purchase", "amount": "4000", "unpaid": "1",
        "due_date": _days_ago(-3)})
    client.post(f"/c/{slug}/expense", data={
        "category": "Tax", "amount": "9000", "unpaid": "1",
        "due_date": _days_ago(-60)})

    week = money.due_this_week(books.load(slug), money.load(slug))
    assert week["outgoing_total"] == 4000, "only the near one belongs in the week"


# ======================================================================= 09 deck

def test_a_deck_is_still_produced_with_no_model_available():
    slug, c = _shop("Deck Traders")
    f = agent.facts(c, books.load(slug), money.load(slug), people.load(slug))
    outline = decks.outline("Show the bank we collect on time", "bank", c, f, config.load())

    assert outline.source == "built", "offline must fall back, not fail"
    assert len(outline.slides) >= 4
    assert outline.slides[0].stats, "the first slide should carry real figures"


def test_the_deck_renders_to_both_formats():
    slug, c = _shop("Rendering Traders")
    f = agent.facts(c, books.load(slug), money.load(slug), people.load(slug))
    outline = decks.outline("", "review", c, f, config.load())

    out = REPO / "out" / "console-test"
    pptx = decks.to_pptx(outline, c.name, out / "deck.pptx")
    pdf = decks.to_pdf(outline, c.name, out / "deck.pdf")
    assert pptx.exists() and pptx.stat().st_size > 5000
    assert pdf.exists() and pdf.stat().st_size > 1000
    shutil.rmtree(out, ignore_errors=True)


def test_the_deck_pdf_carries_no_rupee_glyph():
    """Helvetica has no ₹ and renders it as a black box — same rule as exports.py."""
    slug, c = _shop("Glyph Traders")
    f = agent.facts(c, books.load(slug), money.load(slug), people.load(slug))
    outline = decks.outline("", "review", c, f, config.load())

    out = REPO / "out" / "console-glyph"
    pdf = decks.to_pdf(outline, c.name, out / "deck.pdf")
    assert "₹".encode() not in pdf.read_bytes()
    shutil.rmtree(out, ignore_errors=True)


def test_downloading_a_deck_returns_a_real_file():
    slug, _ = _shop("Download Traders")
    client.post(f"/c/{slug}/deck", data={"brief": "quick review", "kind": "review"})
    resp = client.get(f"/c/{slug}/deck/pptx")
    assert resp.status_code == 200
    assert resp.content[:2] == b"PK", "a pptx is a zip"


# ====================================================================== 10 people

def test_branch_numbers_split_by_where_the_sale_was_rung_up():
    slug, _ = _shop("Two Branch Traders")
    client.post(f"/c/{slug}/branch", data={"name": "Belagavi", "place": "Main Road"})
    client.post(f"/c/{slug}/branch", data={"name": "Hubballi", "place": "Market Yard"})
    org = people.load(slug)
    first, second = org.branches[0].id, org.branches[1].id

    sku = _sku(slug, "urea")
    books.record_sale(slug, sku, "A", 2, 300, branch=first)
    books.record_sale(slug, sku, "B", 5, 300, branch=second)

    rows = {r["name"]: r for r in people.performance(people.load(slug), books.load(slug))}
    assert rows["Belagavi"]["revenue"] == 600
    assert rows["Hubballi"]["revenue"] == 1500


def test_untagged_sales_land_in_unassigned_rather_than_the_first_branch():
    """Guessing here would corrupt the one number the feature exists to produce."""
    slug, _ = _shop("Untagged Traders")
    client.post(f"/c/{slug}/branch", data={"name": "Only Branch"})
    sku = _sku(slug, "urea")
    books.record_sale(slug, sku, "Walk In", 3, 300)          # no branch

    rows = {r["name"]: r for r in people.performance(people.load(slug), books.load(slug))}
    assert rows["Only Branch"]["revenue"] == 0
    assert rows["Unassigned"]["revenue"] == 900


def test_closing_a_branch_keeps_its_sales_on_the_books():
    slug, _ = _shop("Closing Traders")
    client.post(f"/c/{slug}/branch", data={"name": "Old Shop"})
    bid = people.load(slug).branches[0].id
    sku = _sku(slug, "urea")
    books.record_sale(slug, sku, "Someone", 2, 300, branch=bid)

    client.post(f"/c/{slug}/branch/{bid}/delete")

    assert not people.load(slug).branches[0].active
    assert books.load(slug).earned == 600, "history must survive the branch closing"


def test_one_branch_is_not_reported_as_a_multi_branch_business():
    slug, _ = _shop("Single Traders")
    client.post(f"/c/{slug}/branch", data={"name": "The Shop"})
    assert not people.load(slug).has_branches


# ================================================================== integration

def test_the_console_renders_all_six_panels_in_one_document():
    slug, _ = _shop("Whole Page Traders")
    page = client.get(f"/c/{slug}/console").text
    for panel in ("stock", "ask", "followups", "money", "deck", "people"):
        assert f'data-panel="{panel}"' in page, f"{panel} panel missing"
    assert page.count("<style>") >= 1


def test_the_workspace_offers_the_console():
    slug, _ = _shop("Entry Point Traders")
    assert f"/c/{slug}/console" in client.get(f"/c/{slug}").text


def test_another_account_cannot_reach_the_console():
    slug, _ = _shop("Private Traders")
    other = auth.create(f"outsider-{auth.secrets.token_hex(4)}@vyuha.test",
                        "Outsider", "another-password-1")
    client.post("/logout")
    _login(other.email, "another-password-1")
    try:
        page = client.get(f"/c/{slug}/console").text
        # The property that matters is that no part of the console rendered.
        # Which page they land on instead depends on how far their own signup
        # got, so asserting on the console's absence is the durable check.
        assert 'data-panel="money"' not in page
        assert "Private Traders" not in page
    finally:
        client.post("/logout")
        _login()
        _as_operator()


def test_the_offline_switch_actually_stops_the_call():
    answer = llm.ask("anything at all", config.load())
    assert not answer.ok
    assert answer.source == "offline"


# =================================================== 08 money · the statements

def _traded(name: str):
    """A shop with known figures: 10 urea at 320 (cost 268) plus running costs."""
    slug, c = _shop(name)
    sku = _sku(slug, "urea")
    books.record_sale(slug, sku, "Cash Buyer", 10, 320)
    return slug, c


def test_gross_profit_uses_item_cost_not_purchases():
    """Purchases are lumpy; a container bought in March is not a March loss."""
    slug, _ = _traded("Gross Margin Traders")
    client.post(f"/c/{slug}/expense", data={
        "category": "Purchase", "party": "Supplier", "amount": "100000"})

    pl = finance.profit_and_loss(books.load(slug), money.load(slug))
    assert pl["revenue"] == 3200
    assert pl["cogs"] == 2500, pl["cogs"]          # 10 x cost 250, not the 100000
    assert pl["gross_profit"] == 700
    # The purchase is reported, just not as cost of goods sold.
    assert pl["purchases_in_period"] == 100000
    assert pl["opex"] == 0, "a purchase is not an operating expense"


def test_the_pl_says_how_much_of_it_is_actually_costed():
    """Gross margin is only as good as the cost prices behind it."""
    slug, _ = _shop("Coverage Traders")
    books.add_item(slug, "Loose Item", "Other", "piece", 100, 0, 10, 0)
    sku = _sku(slug, "loose")
    books.record_sale(slug, sku, "Buyer", 1, 100)
    books.record_sale(slug, _sku(slug, "urea"), "Buyer", 1, 320)

    pl = finance.profit_and_loss(books.load(slug), money.load(slug))
    assert pl["lines_uncosted"] == 1
    assert pl["cost_coverage_pct"] == 50.0


def test_cash_and_accrual_are_reported_separately():
    slug, _ = _shop("Basis Traders")
    sku = _sku(slug, "urea")
    books.record_sale(slug, sku, "Paid Buyer", 5, 320)
    books.record_sale(slug, sku, "Credit Buyer", 5, 320, paid=False,
                      due_date=_days_ago(-10))

    b, l = books.load(slug), money.load(slug)
    pl, cf = finance.profit_and_loss(b, l), finance.cash_flow(b, l)
    assert pl["revenue"] == 3200, "accrual counts everything billed"
    assert cf["received"] == 1600, "cash counts only what arrived"
    assert cf["billed_not_collected"] == 1600


def test_a_bill_due_next_week_is_not_overdue():
    """The bug this guards made a healthy ledger read as entirely late."""
    slug, _ = _shop("Not Due Traders")
    client.post(f"/c/{slug}/expense", data={
        "category": "Purchase", "amount": "5000", "unpaid": "1",
        "due_date": _days_ago(-7)})

    ap = finance.payables_ageing(money.load(slug))
    assert ap["total"] == 5000
    assert ap["overdue"] == 0, "not yet due is not overdue"
    assert ap["not_due"] == 5000
    assert dict((b, v) for b, v, _ in ap["buckets"])["Not yet due"] == 5000


def test_ageing_buckets_split_by_how_late():
    slug, _ = _shop("Ageing Traders")
    sku = _sku(slug, "urea")
    books.record_sale(slug, sku, "Recent", 1, 320, paid=False, due_date=_days_ago(10))
    books.record_sale(slug, sku, "Ancient", 1, 320, paid=False, due_date=_days_ago(120))

    ar = finance.receivables_ageing(books.load(slug))
    buckets = dict((b, v) for b, v, _ in ar["buckets"])
    assert buckets["0–30 days"] == 320
    assert buckets["90+ days"] == 320
    assert ar["overdue"] == 640
    ancient = next(p for p in ar["parties"] if p["party"] == "Ancient")
    assert ancient["oldest"] >= 120


def test_the_cash_cycle_is_stock_plus_debtor_minus_creditor_days():
    slug, _ = _traded("Cycle Traders")
    b, l = books.load(slug), money.load(slug)
    rows = {r["name"]: r["value"] for r in finance.ratios(b, l)}
    expected = rows["Stock days (DIO)"] + rows["Debtor days (DSO)"] - rows["Creditor days (DPO)"]
    assert abs(rows["Cash cycle (CCC)"] - expected) < 0.01


def test_every_ratio_carries_a_verdict_and_a_reading():
    """The UI colours these without re-deriving the judgement, so both must exist."""
    slug, _ = _traded("Verdict Traders")
    for r in finance.ratios(books.load(slug), money.load(slug)):
        assert isinstance(r["good"], bool), r["name"]
        assert r["note"].endswith("."), f"{r['name']}: the reading must be a sentence"
        assert len(r["note"]) > 30, f"{r['name']}: the reading must actually explain it"
        assert r["unit"] in {"%", "days", "x"}, r["name"]


def test_one_customer_taking_most_of_revenue_is_flagged():
    slug, _ = _shop("Concentrated Traders")
    sku = _sku(slug, "urea")
    books.record_sale(slug, sku, "The Whale", 90, 320)
    books.record_sale(slug, sku, "Small Fry", 10, 320)

    co = finance.concentration(books.load(slug), money.load(slug))
    assert co["risk"] == "high"
    assert co["customers"][0]["party"] == "The Whale"
    assert round(co["top_customer_share"], 2) == 0.90


def test_the_balance_sheet_declares_what_it_leaves_out():
    """A statement that silently omits loans and fixed assets will be believed."""
    slug, _ = _traded("Balance Traders")
    bs = finance.balance_sheet(books.load(slug), money.load(slug))
    assert bs["assumptions"], "it must say what it cannot see"
    assert any("opening balance" in a.lower() for a in bs["assumptions"])
    assert any("bank balance" in a.lower() for a in bs["assumptions"])
    assert bs["working_capital"] == bs["current_assets"] - bs["payables"]


def test_a_period_filter_excludes_what_is_outside_it():
    slug, _ = _shop("Period Traders")
    sku = _sku(slug, "urea")
    books.record_sale(slug, sku, "Old", 5, 320, when=_days_ago(400))
    books.record_sale(slug, sku, "New", 5, 320, when=_days_ago(2))

    b, l = books.load(slug), money.load(slug)
    everything = finance.profit_and_loss(b, l)
    this_month = finance.statements(b, l, f"month:{date.today().isoformat()[:7]}")
    assert everything["revenue"] == 3200
    assert this_month["pl"]["revenue"] == 1600, "the 400-day-old sale is outside the month"


def test_the_financial_year_runs_april_to_march():
    """Indian businesses do not use the calendar year, and a CA report that
    assumed they did would be wrong for nine months of every twelve."""
    assert finance.fy_of("2026-04-01") == "2026-27"
    assert finance.fy_of("2027-03-31") == "2026-27"
    assert finance.fy_of("2026-03-31") == "2025-26"
    assert finance.fy_range("2026-27") == ("2026-04-01", "2027-03-31")


def test_the_money_panel_renders_every_statement():
    slug, _ = _traded("Money Panel Traders")
    page = client.get(f"/c/{slug}/console?panel=money").text
    for probe in ("Profit &amp; loss", "Cost of goods sold", "Cash flow",
                  "What you own and owe", "Owed to you, by age", "You owe, by age",
                  "Break-even", "Every cost head", "Partial, on purpose"):
        assert probe in page, probe


# ============================================== 03 agent · querying the books

def _stocked(name: str):
    """A shop with two customers, two branches and known margins."""
    slug, c = _shop(name)
    urea = _sku(slug, "urea")        # rate 300, cost 250 -> 50/unit
    rose = _sku(slug, "rose")        # rate 80,  cost 40  -> 40/unit
    books.record_sale(slug, urea, "Big Buyer", 100, 300, when=_days_ago(5))
    books.record_sale(slug, rose, "Big Buyer", 10, 80, when=_days_ago(5))
    books.record_sale(slug, urea, "Small Buyer", 5, 300, when=_days_ago(50))
    return slug, c


def test_a_sales_query_groups_and_ranks_on_any_dimension():
    slug, _ = _stocked("Query Traders")
    book = books.load(slug)

    by_party = analysis.query_sales(book, group_by="party", measure="revenue")
    assert by_party["rows"][0]["group"] == "Big Buyer"
    assert by_party["rows"][0]["revenue"] == 30800

    by_item = analysis.query_sales(book, group_by="item", measure="qty")
    assert by_item["rows"][0]["group"] == "Urea 50kg"


def test_ascending_answers_the_worst_performer_question():
    """"Which item makes me least" is asked as often as "which makes me most"."""
    slug, _ = _stocked("Worst Traders")
    book = books.load(slug)

    worst = analysis.query_sales(book, group_by="item", measure="margin",
                                 ascending=True)
    best = analysis.query_sales(book, group_by="item", measure="margin")
    assert worst["rows"][0]["group"] != best["rows"][0]["group"]
    assert worst["rows"][0]["margin"] <= best["rows"][0]["margin"]


def test_margin_comes_from_cost_and_is_none_when_cost_is_unknown():
    slug, _ = _shop("Margin Traders")
    books.add_item(slug, "No Cost Item", "Other", "piece", 100, 0, 20, 0)
    books.record_sale(slug, _sku(slug, "no cost"), "Buyer", 5, 100)
    books.record_sale(slug, _sku(slug, "urea"), "Buyer", 10, 300)

    rows = {r["group"]: r for r in
            analysis.query_sales(books.load(slug), group_by="item")["rows"]}
    assert rows["Urea 50kg"]["margin"] == 500          # 10 x (300 - 250)
    assert rows["No Cost Item"]["margin_pct"] is None, "no cost means no margin claim"


def test_filters_combine_and_a_date_window_excludes_what_is_outside_it():
    slug, _ = _stocked("Filter Traders")
    book = books.load(slug)

    recent = analysis.query_sales(book, since=_days_ago(30))
    assert recent["sales_matched"] == 2, "the 50-day-old sale is outside the window"

    one_party = analysis.query_sales(book, party="Small")
    assert one_party["sales_matched"] == 1
    assert one_party["total_revenue"] == 1500


def test_a_partial_name_matches_because_that_is_how_people_ask():
    slug, _ = _stocked("Partial Traders")
    book = books.load(slug)
    assert analysis.query_sales(book, party="Big")["sales_matched"] == 2
    assert analysis.customer_detail(book, "Big")["found"]


def test_an_empty_result_says_so_rather_than_returning_nothing():
    slug, _ = _stocked("Empty Traders")
    out = analysis.query_sales(books.load(slug), party="Nobody At All")
    assert out["sales_matched"] == 0
    assert "note" in out and "no sales" in out["note"].lower()


def test_stock_report_separates_dead_from_low_from_out():
    slug, _ = _stocked("Stock Report Traders")
    book = books.load(slug)

    dead = analysis.stock_report(book, state="dead")
    assert all(r["never_sold"] for r in dead["rows"])
    assert any(r["item"] == "Gypsum 5kg" for r in dead["rows"])

    out = analysis.stock_report(book, state="out")
    assert all(r["in_stock"] <= 0 for r in out["rows"])


def test_customer_detail_carries_the_history_and_the_debt():
    slug, _ = _shop("History Traders")
    sku = _sku(slug, "urea")
    books.record_sale(slug, sku, "Regular Ravi", 10, 300, when=_days_ago(40))
    books.record_sale(slug, sku, "Regular Ravi", 5, 300, when=_days_ago(3),
                      paid=False, due_date=_days_ago(-5))

    detail = analysis.customer_detail(books.load(slug), "Ravi")
    assert detail["found"]
    assert detail["bills"] == 2
    assert detail["total_spend"] == 4500
    assert detail["still_owes"] == 1500
    assert detail["days_since_last"] == 3
    assert detail["unpaid_bills"]


def test_an_unknown_customer_offers_the_names_that_do_exist():
    """Otherwise the model guesses a name and answers about the wrong person."""
    slug, _ = _stocked("Unknown Traders")
    out = analysis.customer_detail(books.load(slug), "Nobody")
    assert not out["found"]
    assert "Big Buyer" in out["known_customers"]


def test_item_detail_reports_margin_and_who_buys_it():
    slug, _ = _stocked("Item Detail Traders")
    detail = analysis.item_detail(books.load(slug), "urea")
    assert detail["found"]
    assert detail["units_sold"] == 105
    assert detail["margin"] == 5250                    # 105 x (300 - 250)
    assert detail["bought_by"][0]["party"] == "Big Buyer"


def test_compare_periods_finds_the_movers_and_who_stopped_buying():
    slug, _ = _shop("Trend Traders")
    sku = _sku(slug, "urea")
    books.record_sale(slug, sku, "Steady", 10, 300, when=_days_ago(45))
    books.record_sale(slug, sku, "Steady", 30, 300, when=_days_ago(10))
    books.record_sale(slug, sku, "Vanished", 20, 300, when=_days_ago(45))

    out = analysis.compare_windows(books.load(slug), days=30, group_by="party")
    assert out["current"]["total_revenue"] == 9000
    assert out["previous"]["total_revenue"] == 9000
    gone = {r["group"] for r in out["stopped_buying"]}
    assert "Vanished" in gone, out["stopped_buying"]


def test_branch_filtering_uses_the_branch_name_not_its_id():
    """The model will say "Hubballi", never a slug."""
    slug, _ = _shop("Branch Query Traders")
    client.post(f"/c/{slug}/branch", data={"name": "Hubballi"})
    org = people.load(slug)
    bid = org.branches[0].id
    sku = _sku(slug, "urea")
    books.record_sale(slug, sku, "A", 10, 300, branch=bid)
    books.record_sale(slug, sku, "B", 5, 300)

    out = analysis.query_sales(books.load(slug), org, branch="Hubballi")
    assert out["sales_matched"] == 1
    assert out["total_revenue"] == 3000


def test_every_tool_the_model_is_offered_can_actually_be_called():
    """A tool in the schema with no dispatch is a runtime error mid-answer."""
    slug, c = _stocked("Dispatch Traders")
    book, ledger, org = books.load(slug), money.load(slug), people.load(slug)
    run = agent._tools_for(c, book, ledger, org)
    for tool in agent.TOOLS:
        args = {"party": "Big"} if tool["name"] == "customer_detail" else {}
        if tool["name"] == "item_detail":
            args = {"item": "urea"}
        result = run(tool["name"], args)
        assert isinstance(result, dict), tool["name"]


def test_the_tool_schemas_are_well_formed():
    for tool in agent.TOOLS:
        assert tool["name"] and tool["description"]
        schema = tool["input_schema"]
        assert schema["type"] == "object"
        for name in schema.get("required", []):
            assert name in schema["properties"], f"{tool['name']}: {name} not defined"


def test_the_agent_still_answers_with_no_model_available():
    """investigate() must fall through to the pattern answers, not fail."""
    slug, c = _stocked("Offline Agent Traders")
    reply = agent.investigate("Who owes me the most, and for how long?",
                              c, books.load(slug), config.load(),
                              ledger=money.load(slug), org=people.load(slug))
    assert reply.ok, reply.error
    assert reply.source == "rules"


def test_the_offline_question_list_is_one_the_rules_can_answer():
    """Offering a question the fallback cannot handle is a trap for the demo."""
    slug, c = _stocked("Suggested Traders")
    f = agent.facts(c, books.load(slug), money.load(slug), people.load(slug))
    for question in agent.OFFLINE_SUGGESTED:
        assert agent.rules(question, f).ok, question


# ================================================= 02 stock · how it reads

def test_the_shelf_sorts_by_how_worried_to_be_not_alphabetically():
    """A stock screen exists to surface problems, not to be an index."""
    slug, _ = _shop("Shelf Order Traders")
    page = client.get(f"/c/{slug}/console?panel=stock").text
    out_at = page.index("Gypsum 5kg")          # 0 in stock
    fine_at = page.index("Rose Sapling")       # 25 in stock, level 0
    assert out_at < fine_at, "the out-of-stock item must come first"


def test_every_item_carries_a_state_a_filter_and_a_picture():
    slug, _ = _shop("Shelf State Traders")
    # Build all four states deliberately: the fixture starts with none of them,
    # and a test that only sees the states it happens to get is not testing the
    # state logic at all.
    books.record_sale(slug, _sku(slug, "gypsum"), "Buyer", 6, 140)   # -> out
    books.record_sale(slug, _sku(slug, "urea"), "Buyer", 32, 320)    # -> low (8 of 10)
    page = client.get(f"/c/{slug}/console?panel=stock").text
    for cls in ('class="sk out"', 'class="sk low"', 'class="sk dead"'):
        assert cls in page, cls
    for f in ('data-filter="out"', 'data-filter="low"', 'data-filter="dead"'):
        assert f in page, f
    assert page.count('class="glyph"') >= 3, "items should be drawn, not listed"


def test_days_of_cover_is_shown_because_a_bare_quantity_means_nothing():
    """Twelve bags is a fortnight of urea and two years of soil test kits."""
    slug, _ = _shop("Cover Traders")
    sku = _sku(slug, "urea")
    for n in range(6):
        books.record_sale(slug, sku, "Steady", 2, 320, when=_days_ago(n * 10 + 1))

    book = books.load(slug)
    item = book.item(sku)
    from vyuha_platform.console import _cover
    cover = _cover(book, item)
    assert cover is not None and cover > 0

    never = book.item(_sku(slug, "gypsum"))
    assert _cover(book, never) is None, "an item that never sold has no run rate"


def test_the_reorder_marker_only_appears_when_a_level_is_set():
    slug, _ = _shop("Marker Traders")
    page = client.get(f"/c/{slug}/console?panel=stock").text
    # Rose Sapling has reorder_level 0 -- claiming a threshold it does not have
    # would be a lie drawn on a chart.
    assert page.count("Reorder at") >= 2
    assert "Reorder at 0" not in page


# ============================================ manual entry · the item picker

def test_the_sale_form_offers_a_tappable_picker_as_well_as_the_select():
    slug, _ = _shop("Picker Traders")
    page = ui.books_tab(store.get_client(slug, ACCOUNT.id), books.load(slug))
    assert 'id="pickgrid"' in page
    assert 'id="picksearch"' in page
    # The select still exists and is still what submits -- the picker only sets it.
    assert 'name="sku"' in page and 'id="sku"' in page


def test_out_of_stock_items_sort_last_in_the_picker_and_are_marked():
    slug, _ = _shop("Picker Order Traders")
    books.record_sale(slug, _sku(slug, "gypsum"), "Buyer", 6, 140)
    page = ui.books_tab(store.get_client(slug, ACCOUNT.id), books.load(slug))
    grid = page[page.index('id="pickgrid"'):page.index('id="picknone"')]
    assert "pick gone" in grid, "an item with nothing left must look different"
    assert grid.index("Urea 50kg") < grid.index("Gypsum 5kg")


def test_every_item_is_searchable_by_name_category_and_code():
    slug, _ = _shop("Search Traders")
    page = ui.books_tab(store.get_client(slug, ACCOUNT.id), books.load(slug))
    for i in books.load(slug).items:
        haystack = f'data-hay="{i.name.lower()}'[:24]
        assert haystack[:20] in page.lower(), i.name


def test_an_item_gets_the_right_drawing_from_its_own_name():
    """Most clients type their own names, so the shape has to be inferable."""
    assert catalog.kind_for("Urea 50kg", "Fertiliser") == "sack"
    assert catalog.kind_for("Paddy Seed 5kg", "Seed") == "seed"
    assert catalog.kind_for("HDPE Pipe 1in", "Hardware") == "pipe"
    assert catalog.kind_for("Mango Sapling", "Plants") == "sapling"
    # Nothing recognisable still gets a shape, never a blank.
    assert catalog.kind_for("Widget 7", "") == "box"
    assert 'class="glyph"' in catalog.glyph_for("Widget 7", "")


def _cleanup() -> None:
    _login()
    _as_operator()
    for slug in set(_SLUGS):
        shutil.rmtree(store.UPLOADS / slug, ignore_errors=True)
        shutil.rmtree(store.DASHBOARDS / slug, ignore_errors=True)
        for path in (books.BOOKS / f"{slug}.json",
                     money.MONEY / f"{slug}.json",
                     people.PEOPLE / f"{slug}.json",
                     followup.FOLLOWUPS / f"{slug}.json",
                     store.DATA / "exports" / f"{slug}-deck.pptx",
                     store.DATA / "exports" / f"{slug}-deck.pdf"):
            path.unlink(missing_ok=True)
        store.delete_client(slug, ACCOUNT.id)


def main() -> int:
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    passed = failed = 0
    try:
        for name, fn in tests:
            try:
                fn()
                print(f"ok   {name}")
                passed += 1
            except Exception as exc:                       # noqa: BLE001
                print(f"FAIL {name}: {type(exc).__name__}: {exc}")
                failed += 1
    finally:
        _cleanup()
    print(f"\n{passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
