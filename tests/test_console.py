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

from vyuha_platform import (agent, app as app_mod, auth, books, config,  # noqa: E402
                            decks, followup, llm, money, people, store)

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
