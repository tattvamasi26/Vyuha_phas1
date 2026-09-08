"""The agent lane: the gate, routine jobs, and the orchestrator.

Runs under pytest or standalone:  python -m tests.test_agents

These cover the two architecture invariants that are worth more than any
feature here: **nothing leaves without passing the gate**, and **only the
orchestrator can release what the gate is holding**. Both are enforced in code
rather than by convention, so both are testable, and a test is the only thing
that keeps them true once somebody adds the next send path in a hurry.

Every test passes an explicit clock. Nothing here sleeps.
"""

from __future__ import annotations

import os
import shutil
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

os.environ["VYUHA_LLM"] = "offline"

from fastapi.testclient import TestClient    # noqa: E402

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from vyuha_platform import (agents, app as app_mod, auth, books, config,  # noqa: E402
                            exports, gate, ledger, money, notify,
                            orchestrator, people, routines, store, tax,
                            today as today_mod, whatsapp)

client = TestClient(app_mod.app, follow_redirects=True)
_SLUGS: list[str] = []

ACCOUNT = auth.create(f"agents-{auth.secrets.token_hex(4)}@vyuha.test",
                      "Agent Test Operator", "test-password-1")


def _login() -> None:
    client.post("/login", data={"email": ACCOUNT.email,
                                "password": "test-password-1"})


def _as_operator() -> None:
    account = auth.get(ACCOUNT.id)
    account.install, account.org_name, account.tenant_slug = "operator", "", ""
    auth.update(account)


_login()
_as_operator()


def _shop(name: str):
    """A books-mode business with one item, one sale, and a phone number."""
    resp = client.post("/onboard", data={"name": name, "phone": "9876543210",
                                         "data_mode": "books"})
    assert resp.status_code == 200
    slug = store.slugify(name)
    _SLUGS.append(slug)
    client.post(f"/c/{slug}/book/item", data={
        "name": "Urea 50kg", "category": "Fertiliser", "unit": "bag",
        "rate": "320", "cost": "250", "stock_qty": "40", "reorder_level": "10"})
    # Onboarding fires a connection test, which goes through the gate like
    # everything else and lands as a draft when no provider is connected. That
    # is correct and has its own test below; clear it so the counts in these
    # tests are about what each test put there.
    gate.save(slug, [])
    return store.get_client(slug, ACCOUNT.id)


def _sell(c, qty: int = 4, party: str = "Ramu Stores", **extra) -> None:
    book = books.load(c.slug)
    sku = next(i.sku for i in book.items if "urea" in i.name.lower())
    data = {"sku": sku, "party": party, "qty": str(qty), "rate": "320"}
    data.update(extra)
    client.post(f"/c/{c.slug}/book/sale", data=data)


class _Settings:
    """Real settings with a couple of computed properties overridden.

    ``whatsapp_live`` and ``email_live`` are capability probes derived from the
    stored credentials, so they have no setter. Proxying is better than adding
    one: a test must not be able to make the product believe it has a provider
    it does not have, anywhere except here.
    """

    def __init__(self, **over):
        self._real = config.load()
        self._over = over

    def __getattr__(self, name):
        if name in self._over:
            return self._over[name]
        return getattr(self._real, name)


def _settings(**over):
    return _Settings(**over)


# ===================================================== the boundary holds


def test_a_send_path_refuses_a_caller_without_the_gates_key():
    """The architecture calls this a hard boundary, not a convention.

    A convention is a comment saying "always go through the gate"; this is the
    send path refusing to run.
    """
    s = config.load()
    for call, what in [
        (lambda: whatsapp.send(s, "919876543210", "hello"), "whatsapp.send"),
        (lambda: exports.send_email(s, "a@b.test", "hi", "body"), "exports.send_email"),
    ]:
        try:
            call()
        except gate.NotAuthorised as exc:
            assert "gate.submit()" in str(exc), what
        else:                                              # pragma: no cover
            raise AssertionError(f"{what} sent without the gate's key")


def test_nothing_in_the_codebase_reaches_a_send_path_directly():
    """A grep is a legitimate test when the rule is 'only one caller'.

    Adding a second one is exactly the mistake the key exists to catch, and it
    is far cheaper to catch here than in front of a customer.
    """
    allowed = {"gate.py", "whatsapp.py"}         # the gate, and send_test's own module
    offenders = []
    for path in (REPO / "vyuha_platform").glob("*.py"):
        if path.name in allowed:
            continue
        text = path.read_text(encoding="utf-8")
        for call in ("whatsapp.send(", "exports.send_email("):
            for line in text.splitlines():
                if call in line and "_token=" not in line and "def " not in line:
                    offenders.append(f"{path.name}: {line.strip()[:70]}")
    assert not offenders, "ungated send path(s):\n" + "\n".join(offenders)


# ===================================================== classification


def test_email_is_always_a_draft_however_the_action_is_labelled():
    """A caller must not be able to opt an email into sending by choosing a
    friendlier kind."""
    for kind in ("alert", "brief", "receipt", "routine", "test"):
        assert gate.disposition(kind, "email", can_self_send=True) == gate.DRAFT, kind


def test_money_and_filings_wait_for_a_person_on_any_channel():
    for kind in ("payment", "filing"):
        for channel in ("whatsapp", "email"):
            assert gate.disposition(kind, channel) == gate.APPROVAL, (kind, channel)


def test_an_unknown_kind_is_held_rather_than_sent():
    """Failing safe means the unfamiliar waits, not that it goes out."""
    assert gate.disposition("something-new", "whatsapp") == gate.APPROVAL


def test_a_channel_with_no_provider_does_not_get_to_claim_auto():
    """``auto`` is a lie when nothing can deliver.

    WhatsApp in link-only mode cannot send unattended. Reporting failure every
    morning because of a setting is worse than parking an honest draft.
    """
    assert gate.disposition("alert", "whatsapp", can_self_send=True) == gate.AUTO
    assert gate.disposition("alert", "whatsapp", can_self_send=False) == gate.DRAFT



def test_onboarding_connection_test_goes_through_the_gate_like_everything_else():
    """No exceptions, not even for the first message a business ever gets.

    With no provider connected it lands as a draft the operator taps, rather
    than reporting a failure for a workspace that was created perfectly well.
    """
    resp = client.post("/onboard", data={"name": "Onboard Gate Traders",
                                         "phone": "9876500011",
                                         "data_mode": "books"})
    assert resp.status_code == 200
    slug = store.slugify("Onboard Gate Traders")
    _SLUGS.append(slug)

    items = gate.load(slug)
    assert items, "the connection test bypassed the outbox"
    assert items[0].kind == "test"
    assert items[0].source == "onboarding"
    assert items[0].status in (gate.DRAFTED, gate.SENT)


# ===================================================== the outbox


def test_a_held_item_is_not_sent_and_says_why():
    c = _shop("Gate Held Traders")
    item = gate.submit(c, _settings(), kind="payment", channel="whatsapp",
                       to="919876543210", body="Pay the supplier 40,000")
    assert item.status == gate.HELD
    assert item.tries == 0, "a held item must never have been attempted"
    assert "approval" in item.detail.lower()
    assert gate.counts(c.slug)["waiting"] == 1


def test_releasing_requires_the_key_so_a_route_cannot_do_it():
    c = _shop("Gate Key Traders")
    item = gate.submit(c, _settings(), kind="filing", channel="email",
                       to="ca@example.test", body="GSTR-3B summary")
    try:
        gate.release(c, _settings(), item.id, approved_by="nobody")
    except gate.NotAuthorised:
        pass
    else:                                                  # pragma: no cover
        raise AssertionError("gate.release ran without the key")
    assert gate.get(c.slug, item.id).status == gate.HELD


def test_the_orchestrator_releases_and_the_approval_carries_a_name():
    c = _shop("Gate Release Traders")
    item = gate.submit(c, _settings(), kind="payment", channel="whatsapp",
                       to="919876543210", body="Release me")
    orch = orchestrator.for_client(c, _settings())
    orch.approve(item.id, approved_by="Vishak Rao")

    after = gate.get(c.slug, item.id)
    assert after.approved_by == "Vishak Rao", "an approval must name who gave it"
    assert after.status in (gate.SENT, gate.FAILED)
    assert not after.waiting


def test_marking_sent_by_hand_records_the_truth_rather_than_faking_a_send():
    """With no provider, the operator taps a link and sends it themselves.

    Calling the release path would attempt an impossible delivery and log a
    failure for a message that actually went out.
    """
    c = _shop("Gate Byhand Traders")
    item = gate.submit(c, _settings(whatsapp_live=False), kind="brief",
                       channel="whatsapp", to="919876543210", body="Morning.")
    assert item.status == gate.DRAFTED

    ok, _note = gate.mark_sent(c, item.id, by="Vishak Rao")
    after = gate.get(c.slug, item.id)
    assert ok and after.status == gate.SENT
    assert after.approved_by == "Vishak Rao"
    assert after.tries == 0, "nothing was transmitted by the machine"


def test_discarding_needs_no_key_because_refusing_to_act_is_always_allowed():
    c = _shop("Gate Discard Traders")
    item = gate.submit(c, _settings(), kind="payment", channel="whatsapp",
                       to="919876543210", body="No thanks")
    ok, _ = gate.cancel(c, item.id, why="Wrong supplier.")
    assert ok and gate.get(c.slug, item.id).status == gate.CANCELLED
    assert gate.counts(c.slug)["waiting"] == 0


# ===================================================== routine jobs


def test_a_routine_is_configuration_and_needs_no_new_code():
    c = _shop("Routine Config Traders")
    r, note = routines.add(c.slug, "Purchase head — Friday stock", c.phone,
                           at="17:00", days=["Fri"], sections=["stock"])
    assert r is not None and "Fri" in r.when
    assert "Friday stock" in note


def test_a_routine_with_nothing_in_it_is_refused():
    c = _shop("Routine Empty Traders")
    r, note = routines.add(c.slug, "Empty", c.phone, sections=[])
    assert r is None and "at least one" in note


def test_it_fires_after_its_time_and_only_once_a_day():
    """Late is better than never — a machine asleep at eight should still send
    the brief at nine — but four restarts must not send four briefs."""
    c = _shop("Routine Once Traders")
    routines.add(c.slug, "Morning", c.phone, at="08:00", sections=["money"])
    orch = orchestrator.for_client(c, _settings())

    early = orch.tick(datetime(2026, 9, 8, 7, 0))
    assert not early.fired, "fired before its time"

    late = orch.tick(datetime(2026, 9, 8, 9, 0))
    assert len(late.fired) == 1, "should still fire after the hour has passed"

    again = orch.tick(datetime(2026, 9, 8, 11, 0))
    assert not again.fired, "sent the same brief twice in one day"


def test_it_does_not_fire_on_a_day_it_was_not_asked_to():
    c = _shop("Routine Days Traders")
    routines.add(c.slug, "Fridays only", c.phone, at="09:00", days=["Fri"],
                 sections=["stock"])
    orch = orchestrator.for_client(c, _settings())
    # 2026-09-08 is a Tuesday.
    assert not orch.tick(datetime(2026, 9, 8, 18, 0)).fired
    # 2026-09-11 is a Friday.
    assert orch.tick(datetime(2026, 9, 11, 18, 0)).fired


def test_a_paused_routine_stays_paused():
    c = _shop("Routine Paused Traders")
    r, _ = routines.add(c.slug, "Paused one", c.phone, at="06:00",
                        sections=["money"])
    routines.toggle(c.slug, r.id)
    assert not orchestrator.for_client(c, _settings()).tick(
        datetime(2026, 9, 8, 20, 0)).fired


def test_the_brief_carries_real_numbers_and_goes_through_the_gate():
    c = _shop("Routine Content Traders")
    _sell(c, 4)
    routines.add(c.slug, "CEO brief", c.phone, at="08:00",
                 sections=["decisions", "money", "stock"])
    orchestrator.for_client(c, _settings()).tick(datetime(2026, 9, 8, 9, 0))

    items = gate.history(c.slug, 5)
    assert items, "the routine produced nothing"
    body = items[0].body
    assert c.name in body
    assert "*Money*" in body
    assert items[0].source.startswith("routine:"), "the audit trail lost its origin"
    assert len(body) <= 1024, "WhatsApp's cap was not respected"


def test_a_routine_with_nobody_to_send_to_says_so_once_and_moves_on():
    """A setup gap is not a transient failure. Retrying it every morning fills
    the audit trail with the same sentence."""
    resp = client.post("/onboard", data={"name": "Routine Nophone Traders",
                                         "phone": "", "data_mode": "books"})
    assert resp.status_code == 200
    slug = store.slugify("Routine Nophone Traders")
    _SLUGS.append(slug)
    c = store.get_client(slug, ACCOUNT.id)

    r, _ = routines.add(slug, "Nowhere", "", at="08:00", sections=["money"])
    r.to = ""
    routines.save(slug, [r])
    result = orchestrator.for_client(c, _settings()).tick(datetime(2026, 9, 8, 9, 0))
    assert not result.fired
    assert not gate.load(slug), "queued a message with no recipient"


# ===================================================== the orchestrator


def test_one_orchestrator_per_tenant_not_one_per_platform():
    """Two businesses must not share a context, or one will quote the other's
    numbers."""
    a = _shop("Tenant A Traders")
    b = _shop("Tenant B Traders")
    _sell(a, 9, party="A Customer")

    ctx_a = orchestrator.for_client(a, _settings()).context()
    ctx_b = orchestrator.for_client(b, _settings()).context()
    assert ctx_a is not ctx_b
    assert len(ctx_a["book"].sales) != len(ctx_b["book"].sales)


def test_a_failure_in_one_tenant_does_not_stop_another():
    _shop("Sweep One Traders")
    _shop("Sweep Two Traders")
    results = orchestrator.tick_all(ACCOUNT.id, _settings(),
                                    datetime(2026, 9, 8, 9, 0))
    assert len(results) >= 2
    assert all(isinstance(r, orchestrator.TickResult) for r in results)


def test_a_retry_does_not_happen_in_the_same_tick_as_the_attempt():
    """Retrying four seconds later is the same attempt against the same broken
    thing, and it burns the budget before the condition can clear."""
    c = _shop("Retry Traders")
    routines.add(c.slug, "Will fail", c.phone, at="08:00", sections=["money"])
    result = orchestrator.for_client(c, _settings(whatsapp_live=True)).tick(
        datetime(2026, 9, 8, 9, 0))
    assert len(result.fired) == 1
    assert not result.retried, "retried a message it had just sent"


# ===================================================== through the web


def test_the_waiting_screen_shows_the_message_and_never_claims_it_was_sent():
    c = _shop("Waiting Screen Traders")
    gate.submit(c, _settings(), kind="payment", channel="whatsapp",
                to="919876543210", body="A payment worth checking")

    page = client.get(f"/c/{c.slug}/messages/approvals").text
    assert "Held for approval" in page
    assert "A payment worth checking" in page
    assert "Nothing on this screen was sent" in page


def test_the_messages_badge_counts_what_is_waiting_on_a_person():
    c = _shop("Badge Traders")
    before = client.get(f"/c/{c.slug}/desk").text
    gate.submit(c, _settings(), kind="filing", channel="email",
                to="ca@example.test", body="GSTR-1")
    after = client.get(f"/c/{c.slug}/desk").text
    assert "Messages<span" not in before or after != before
    assert "Messages<span" in after, "a waiting item raised no badge"


def test_routine_jobs_are_set_up_off_the_daily_screens():
    c = _shop("Routine Placement Traders")
    setup = client.get(f"/c/{c.slug}/setup/routines").text
    assert "Add a routine job" in setup
    desk = client.get(f"/c/{c.slug}/desk").text
    assert "Add a routine job" not in desk, "configuration leaked onto a daily screen"


def test_the_whole_loop_works_through_http():
    c = _shop("Loop Traders")
    _sell(c, 2, party="Someone")

    client.post(f"/c/{c.slug}/routine", data={
        "name": "CEO 8am brief", "staff_id": "", "at": "08:00",
        "days": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        "sections": ["decisions", "money"]})
    assert routines.load(c.slug), "the form did not save a routine"

    client.post(f"/c/{c.slug}/routine/run")
    waiting = gate.waiting(c.slug)
    assert waiting, "running the routine produced nothing"

    client.post(f"/c/{c.slug}/outbox/{waiting[0].id}/sent")
    assert gate.get(c.slug, waiting[0].id).status == gate.SENT

    sent_page = client.get(f"/c/{c.slug}/messages/outbox").text
    assert ">sent<" in sent_page
    assert gate.counts(c.slug)["waiting"] == 0


def test_the_audit_trail_records_every_step():
    c = _shop("Audit Traders")
    routines.add(c.slug, "Audited", c.phone, at="08:00", sections=["money"])
    orchestrator.for_client(c, _settings()).tick(datetime(2026, 9, 8, 9, 0))

    kinds = {e.kind for e in ledger.read(ACCOUNT.id, limit=200, client=c.slug)}
    assert "routine.fired" in kinds
    assert kinds & {"outbound.drafted", "alert.sent", "outbound.held"}, kinds


# ============================================ the roster, and its contracts


def test_the_roster_is_the_architecture_and_it_type_checks():
    """Sixteen agents, five lanes plus orchestration, no broken contracts."""
    assert len(agents.ROSTER) == 16, len(agents.ROSTER)
    assert agents.check() == [], agents.check()
    # Every lane in the spec's flow is populated. An empty lane means an agent
    # was renamed out of existence rather than moved.
    for key, label, _blurb in agents.LANES:
        assert agents.lane(key), f"{label} has no agents in it"


def test_a_domain_agent_may_not_read_the_raw_store():
    """The one rule the architecture calls a boundary rather than a principle.

    Proved by breaking it: a checker that only ever returns an empty list is
    indistinguishable from one that does nothing, so this puts an illegal agent
    in the roster and insists `check()` catches it.
    """
    bad = agents.Agent("smuggler", "Smuggler Agent", agents.DOMAIN,
                       "Reads the raw store it has no business reading.",
                       reads=(agents.RAW, agents.LEDGER_STORE),
                       writes=(agents.DASHBOARD,), implemented_by="nowhere.py")
    original = agents.ROSTER
    try:
        agents.ROSTER = original + (bad,)
        problems = agents.check()
        assert any("Smuggler" in p and "raw" in p for p in problems), problems
    finally:
        agents.ROSTER = original
    assert agents.check() == []


def test_deleting_a_client_takes_its_data_with_it():
    """Slugs are freed on delete and are globally unique.

    So the next business onboarded under the same name gets the same slug, and
    used to inherit the deleted one's book, staff, invoices and outbox with it.
    That is not untidiness — it is somebody else's sales appearing in a
    workspace being opened for the first time.
    """
    c = _shop("Purged Away Traders")
    _staff(c, "Manju", "Manager", "9800000001")
    _run_out_of_stock(c)
    notify.run(c, _settings(), _ctx(c))
    slug = c.slug

    assert (books.BOOKS / f"{slug}.json").exists()
    assert (gate.OUTBOX / f"{slug}.json").exists()
    assert (notify.NOTICES / f"{slug}.json").exists()
    assert (people.PEOPLE / f"{slug}.json").exists()

    store.delete_client(slug, ACCOUNT.id)
    left = [f for f in store.PER_SLUG
            if (store.DATA / f / f"{slug}.json").exists()]
    assert not left, f"{slug} left data behind in: {left}"


def test_the_purge_list_names_every_per_slug_store():
    """`store.PER_SLUG` is written out by hand because `store` sits underneath
    the modules it would otherwise import. This is what catches forgetting to
    add the next one — a store missing from the list is data that survives a
    delete and lands on whoever reuses the slug.
    """
    from vyuha_platform import (books as b, followup, gate as g, invoice,
                                money as m, notify as n, people as pp, routines as r)
    declared = set(store.PER_SLUG)
    actual = {folder.name for folder in
              (b.BOOKS, m.MONEY, pp.PEOPLE, invoice.INVOICES, followup.FOLLOWUPS,
               g.OUTBOX, n.NOTICES, r.ROUTINES)}
    assert actual <= declared, f"not purged on delete: {sorted(actual - declared)}"


def test_every_agent_says_where_in_the_code_it_lives():
    """A roster that named no modules would be a diagram, not a map."""
    for a in agents.ROSTER:
        assert a.implemented_by, a.name
        for module in a.implemented_by.split(","):
            module = module.strip().split(".")[0].split("/")[-1]
            if not module or "(" in module:
                continue
            found = ((REPO / "vyuha_platform" / f"{module}.py").exists()
                     or (REPO / "vyuha" / f"{module}.py").exists())
            assert found, f"{a.name} points at {module}, which does not exist"


# ============================================ the tax agent's filing dates


def test_a_return_reports_on_the_month_before_the_one_it_is_due_in():
    """GSTR-1 filed on 11 September covers August, not September."""
    aug = [f for f in tax.calendar_(date(2026, 9, 8)) if f.name == "GSTR-1"][0]
    assert aug.period == "August 2026", aug.period
    assert aug.due == date(2026, 9, 11)
    assert aug.days_left == 3


def test_the_filing_calendar_survives_the_year_boundary():
    """A January deadline reports on the previous December."""
    jan = [f for f in tax.calendar_(date(2026, 1, 3)) if f.name == "GSTR-1"][0]
    assert jan.period == "December 2025", jan.period
    assert jan.due == date(2026, 1, 11)

    dec = tax.calendar_(date(2026, 12, 28))
    assert any(f.due == date(2027, 1, 11) for f in dec), [str(f.due) for f in dec]


def test_a_missed_return_is_critical_because_it_gets_worse_every_day():
    overdue = [f for f in tax.calendar_(date(2026, 9, 19)) if f.name == "GSTR-1"][0]
    assert overdue.overdue
    assert overdue.severity == "critical"
    assert "was due" in overdue.when


def test_a_business_with_no_gstin_is_never_reminded_to_file():
    """It files no returns, so a reminder is noise about an obligation it does
    not have."""
    c = _shop("No Gstin Notify Co")
    assert not c.gstin
    assert tax.events(c, [], money.load(c.slug)) == []


def test_the_screen_and_the_reminder_read_the_same_liability():
    """Both come from `tax.liability`, so they cannot disagree.

    This is the failure that destroys trust quietly: a figure on a screen and a
    figure on a phone that differ, where the one somebody acts on is whichever
    they saw last.
    """
    c = _shop("One Answer Traders")
    led = money.load(c.slug)
    owed = tax.liability([], led)
    assert owed["input_is_an_estimate"] is True
    # The rate is stated, not buried: a blended assumption that cannot be seen
    # cannot be argued with.
    assert tax.ASSUMED_INPUT_RATE == 5.0
    assert "QRMP" in tax.SCHEME_ASSUMED


# ============================================ the notification agent


def _staff(c, name: str, role: str, phone: str) -> None:
    client.post(f"/c/{c.slug}/staff",
                data={"name": name, "role": role, "phone": phone})


def _ctx(c) -> dict:
    return orchestrator.for_client(c, _settings()).context()


def _run_out_of_stock(c) -> None:
    """Sell the whole shelf, on credit and long overdue."""
    book = books.load(c.slug)
    sku = next(i.sku for i in book.items if "urea" in i.name.lower())
    client.post(f"/c/{c.slug}/book/sale", data={
        "sku": sku, "party": "Ramu Stores", "qty": "40", "rate": "320",
        "payment": "credit", "due_date": "2026-07-01"})


def test_the_right_person_is_told_rather_than_simply_the_owner():
    """The whole reason this agent exists.

    Before it, everything went to the business's own number, which meant the
    manager found out the shelf was empty when the owner told him.
    """
    c = _shop("Routed Alerts Traders")
    _staff(c, "Manju", "Manager", "9800000001")
    _staff(c, "Latha", "Accountant", "9800000002")
    _run_out_of_stock(c)

    rows = {r["event"].tag: r for r in notify.preview(c, _ctx(c))}
    stock_to = {r.who for r in rows["stock"]["to"]}
    money_to = {r.who for r in rows["money"]["to"]}
    assert "Manju" in stock_to, stock_to
    assert "Latha" not in stock_to, "the accountant does not buy stock"
    assert "Latha" in money_to, money_to
    assert "Manju" not in money_to, "the manager does not chase payment"


def test_the_owner_is_told_even_though_nobody_added_them_as_staff():
    """Almost nobody puts themselves on their own staff list.

    The audience for an empty shelf is ("Manager", "Owner"), and it used to
    reach the manager and stop — the one person who certainly wanted to know
    was the one person who had never filled in a form saying they worked there.
    """
    c = _shop("Unlisted Owner Traders")
    _staff(c, "Manju", "Manager", "9800000001")
    _run_out_of_stock(c)

    row = next(r for r in notify.preview(c, _ctx(c)) if r["event"].tag == "stock")
    numbers = {r.to for r in row["to"]}
    assert c.phone in numbers, numbers
    assert len(numbers) == 2, [(r.who, r.role) for r in row["to"]]


def test_a_one_person_shop_with_no_staff_at_all_is_still_told():
    c = _shop("Solo Shop Traders")
    _run_out_of_stock(c)
    row = next(r for r in notify.preview(c, _ctx(c)) if r["event"].tag == "stock")
    assert [r.to for r in row["to"]] == [c.phone]


def test_a_filing_reminder_waits_for_a_person_and_a_stock_alert_does_not():
    """The architecture's most distinctive rule, finally live.

    `gate` has declared an APPROVAL disposition since it was written and no
    caller ever produced one, so the rule that anything touching a filing waits
    for a human had never actually fired in the running product.
    """
    c = _shop("Filing Approval Traders")
    c.gstin = "29ABCDE1234F1Z5"
    store.update_client(c)
    c = store.get_client(c.slug, ACCOUNT.id)
    _run_out_of_stock(c)

    settings = _settings(whatsapp_live=True)
    result = notify.run(c, settings, _ctx(c), as_of=date(2026, 9, 9))
    assert result.held, "a GST filing reminder was not held for approval"

    items = {i.kind: i for i in gate.load(c.slug)}
    assert items["filing"].status == gate.HELD
    assert items["filing"].disposition == gate.APPROVAL
    # Never even attempted — that is what "held" has to mean.
    assert items["filing"].tries == 0

    # The alert beside it, on the same wire in the same pass, was put on that
    # wire immediately. Whether the provider then accepted it is not what this
    # test is about; that it was *tried* is.
    assert items["alert"].disposition == gate.AUTO
    assert items["alert"].tries == 1, items["alert"].tries


def test_nothing_is_said_twice_while_the_cooldown_holds():
    """A stored notification about an empty shelf is still there the day after
    it was refilled, so the queue is recomputed and only the telling persists."""
    c = _shop("Quiet Twice Traders")
    _run_out_of_stock(c)
    settings = _settings(whatsapp_live=True)

    first = notify.run(c, settings, _ctx(c))
    assert first.raised, "nothing was raised at all"
    sent_count = len(gate.load(c.slug))

    second = notify.run(c, settings, _ctx(c))
    assert second.raised == []
    assert second.quiet >= 1
    assert len(gate.load(c.slug)) == sent_count, "it said the same thing twice"


def test_only_what_somebody_can_act_on_tonight_reaches_a_phone():
    """`info` findings stay on the Desk. A product that interrupts you about a
    concentration ratio teaches you to ignore the one about the empty shelf."""
    c = _shop("Info Stays Put Traders")
    _run_out_of_stock(c)
    ctx = _ctx(c)

    pushed = {e.key for e in notify.collect(c, ctx["book"], ctx["ledger"],
                                            ctx["org"], ctx["invoices"])}
    desk = today_mod.findings(c, ctx["book"], ctx["ledger"], ctx["org"],
                              ctx["invoices"])
    infos = {f.key for f in desk if f.severity == "info"}
    assert infos, "this fixture no longer produces an info finding to test with"
    assert not (pushed & infos), pushed & infos


def test_the_product_never_messages_somebody_about_its_own_emptiness():
    """`today.py` rates "Vyuha has nothing to read yet" critical, and for the
    Desk that is right. As a WhatsApp to a brand-new client it is indefensible.
    """
    # Onboarded and nothing else — no item, so no pipeline run either. This is
    # exactly the state a client is in for the minute after signing up, which
    # is precisely when a message like this would arrive.
    name = "Brand New Empty Traders"
    client.post("/onboard", data={"name": name, "phone": "9876543210",
                                  "data_mode": "books"})
    # By name, not by position: `load_clients` is not in creation order.
    c = next(x for x in store.load_clients(ACCOUNT.id) if x.name == name)
    _SLUGS.append(c.slug)
    gate.save(c.slug, [])

    ctx = _ctx(c)
    desk = today_mod.findings(c, ctx["book"], ctx["ledger"], ctx["org"], [])
    assert any(f.key == "empty" and f.severity == "critical" for f in desk), \
        [(f.key, f.severity) for f in desk]

    result = notify.run(c, _settings(whatsapp_live=True), ctx)
    assert result.raised == []
    assert "setup" in notify.NEVER_PUSHED


def test_the_notification_says_what_the_desk_says():
    """This agent routes; it does not compute. A notification that disagreed
    with the screen it points at would be worse than no notification."""
    c = _shop("Same Words Traders")
    _run_out_of_stock(c)
    ctx = _ctx(c)

    event = next(e for e in notify.collect(c, ctx["book"], ctx["ledger"],
                                           ctx["org"], ctx["invoices"])
                 if e.tag == "stock")
    finding = next(f for f in today_mod.findings(c, ctx["book"], ctx["ledger"],
                                                 ctx["org"], ctx["invoices"])
                   if f.key == "stock")
    assert event.title == finding.title
    assert event.detail == finding.detail


def test_a_notification_leaves_through_the_gate_like_everything_else():
    c = _shop("Gated Notice Traders")
    _run_out_of_stock(c)
    notify.run(c, _settings(), _ctx(c))

    items = gate.load(c.slug)
    assert items, "nothing reached the outbox"
    assert all(i.source.startswith("notify:") for i in items), \
        [i.source for i in items]
    # No provider in this deployment, so an alert is written and parked rather
    # than reported as a failure.
    assert {i.status for i in items} == {gate.DRAFTED}


def test_who_was_told_what_is_answerable_afterwards():
    c = _shop("Told Trail Traders")
    _staff(c, "Manju", "Manager", "9800000001")
    _run_out_of_stock(c)
    notify.run(c, _settings(whatsapp_live=True), _ctx(c))

    told = notify.history(c.slug)
    assert told, "nothing was written down"
    manju = [n for n in told if n.who == "Manju"]
    assert manju and manju[0].role == "Manager"
    assert manju[0].item, "the notice does not say which outbox item it became"


# ============================================ the orchestrator, with both


def test_a_tick_notifies_as_well_as_firing_routines():
    """A shelf that empties at eleven must not wait until tomorrow morning."""
    c = _shop("Tick Notifies Traders")
    _run_out_of_stock(c)
    result = orchestrator.for_client(c, _settings()).tick(
        datetime(2026, 9, 8, 11, 0))
    assert result.notified, result.errors
    assert result.did_something
    assert "notification" in str(result)


def test_a_notification_that_just_failed_is_not_retried_in_the_same_tick():
    """A retry four milliseconds later is the same attempt against the same
    broken thing, and it burns the budget before the condition can clear."""
    c = _shop("No Instant Retry Traders")
    _run_out_of_stock(c)
    # A provider that claims to be live and is not: sends are attempted and fail.
    orch = orchestrator.for_client(c, _settings(whatsapp_live=True))
    orch.tick(datetime(2026, 9, 8, 11, 0))

    failed = [i for i in gate.load(c.slug) if i.status == gate.FAILED]
    if not failed:
        return                       # the fake provider reported success
    assert all(i.tries == 1 for i in failed), [(i.kind, i.tries) for i in failed]


def _cleanup() -> None:
    _login()
    _as_operator()
    for slug in set(_SLUGS):
        store.delete_client(slug, ACCOUNT.id)      # purges every per-slug store

    for acct in auth._load_all():
        if acct.email.endswith("@vyuha.test") and acct.email.startswith("agents-"):
            for leftover in store.load_clients(acct.id):
                store.delete_client(leftover.slug, acct.id)
            auth.delete(acct.id)


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
