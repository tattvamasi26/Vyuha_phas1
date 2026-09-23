"""Tests for the guided demo — the script, the actions, and who may run one.

Runs under pytest or standalone:  python -m tests.test_demo

Two kinds of test here. The cheap ones check the *script* — that every step points at a
page that exists and names an action the code has — because a demo that 404s in front of a
prospect is the worst bug this repo can ship, and it is a bug nobody notices until the
room is watching. The rest drive the real actions against the real ``vyuha_data/`` and
delete what they made in ``_cleanup()``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ["VYUHA_LLM"] = "offline"          # before the platform imports llm

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from fastapi.testclient import TestClient                                   # noqa: E402

from vyuha_platform import app as app_mod, auth, books, demo_tour, onboarding, store  # noqa: E402
from vyuha_platform.web.views import pages as page_registry                 # noqa: E402

client = TestClient(app_mod.app, follow_redirects=True)
PASSWORD = "test-password-1"

ACCOUNT = auth.create(f"demo-{auth.secrets.token_hex(4)}@vyuha.test", "Demo Presenter",
                      PASSWORD)
TENANT = auth.create(f"demo-t-{auth.secrets.token_hex(4)}@vyuha.test", "A Business",
                     PASSWORD)


def _install(acct, kind: str = "operator", slug: str = "") -> None:
    a = auth.get(acct.id)
    a.install, a.tenant_slug = kind, slug
    auth.update(a)


def _login(acct=ACCOUNT) -> None:
    client.cookies.clear()
    client.post("/login", data={"email": acct.email, "password": PASSWORD})


_install(ACCOUNT)
_install(TENANT, "tenant")
_login()


def _act(key: str) -> dict:
    return client.post(f"/demo/act/{key}").json()


def _clear() -> None:
    """Back to nothing, whatever a previous test left behind."""
    _login()
    client.post("/demo/reset")


# ------------------------------------------------------------------ the script

def test_every_step_names_an_action_the_code_has():
    unknown = [s.key for s in demo_tour.STEPS
               if s.action and s.action not in demo_tour.ACTIONS]
    assert not unknown, f"steps point at actions that do not exist: {unknown}"


def test_every_step_belongs_to_a_chapter_that_exists():
    keys = {c.key for c in demo_tour.CHAPTERS}
    orphans = [s.key for s in demo_tour.STEPS if s.chapter not in keys]
    assert not orphans, orphans


def test_step_keys_are_unique():
    keys = [s.key for s in demo_tour.STEPS]
    assert len(keys) == len(set(keys))


def test_every_step_points_at_a_page_that_exists():
    """The check that matters: no step may address a screen the product lacks."""
    missing = []
    for step in demo_tour.STEPS:
        path = step.path
        if not path:
            continue
        if path.startswith("/studio"):
            rest = path.replace("/studio", "").strip("/").split("/")
            stage = rest[-1] if len(rest) > 1 else ""
            if stage and stage not in onboarding.BY_KEY and rest[0] != "new":
                missing.append((step.key, path))
            continue
        # /app/{slug}[/section/page]
        rest = path.replace("/app/{slug}", "").strip("/")
        if not rest:
            continue                                    # Home
        section, _, page = rest.partition("/")
        if (section, page) not in page_registry.REGISTRY:
            missing.append((step.key, path))
    assert not missing, f"steps point at pages that do not exist: {missing}"


def test_every_action_is_reachable_from_some_step():
    """An action nobody can trigger is dead code in a demo — the worst place for it."""
    used = {s.action for s in demo_tour.STEPS if s.action}
    assert used == set(demo_tour.ACTIONS), set(demo_tour.ACTIONS) ^ used


def test_the_script_says_something_at_every_step():
    silent = [s.key for s in demo_tour.STEPS if len(s.say.strip()) < 40]
    assert not silent, f"steps with nothing to say: {silent}"


# -------------------------------------------------------------- who may run it

def test_a_tenant_cannot_open_the_demo():
    _login(TENANT)
    assert 'data-testid="demo"' not in client.get("/demo").text
    assert client.get("/demo/steps.json").status_code == 403
    assert client.post("/demo/act/create").status_code == 403
    _login()


def test_an_operator_gets_the_script():
    _login()
    body = client.get("/demo/steps.json").json()
    assert body["ok"] is True
    assert len(body["steps"]) == len(demo_tour.STEPS)
    assert body["chapters"]


def test_the_demo_page_offers_a_start_button():
    assert 'data-testid="demo-start"' in client.get("/demo").text


# -------------------------------------------------------------------- actions

def test_an_action_before_the_business_exists_explains_itself():
    _clear()
    out = _act("datamap")
    assert out["ok"] is False
    assert "Create the business" in out["message"]


def test_create_makes_the_business_and_reset_removes_it():
    _clear()
    out = _act("create")
    assert out["ok"] is True and out["slug"]
    slug = out["slug"]
    assert store.get_client(slug, ACCOUNT.id) is not None

    again = _act("create")                      # idempotent: never a second workspace
    assert again["slug"] == slug
    assert sum(1 for c in store.load_clients(ACCOUNT.id)
               if c.name == demo_tour.NAME) == 1

    assert client.post("/demo/reset").json()["ok"] is True
    assert store.get_client(slug, ACCOUNT.id) is None


def test_the_data_map_turns_it_into_a_business_read_from_files():
    _clear()
    slug = _act("create")["slug"]
    assert store.get_client(slug, ACCOUNT.id).data_mode == "books"
    assert _act("datamap")["ok"] is True
    assert store.get_client(slug, ACCOUNT.id).data_mode == "upload"
    record = onboarding.load(slug)
    assert record.answered == len(onboarding.DOMAIN_KEYS)
    assert record.cutover
    _clear()


def test_the_profile_fills_in_what_a_tax_invoice_needs():
    _clear()
    slug = _act("create")["slug"]
    assert _act("profile")["ok"] is True
    c = store.get_client(slug, ACCOUNT.id)
    assert c.gstin and c.state == "KA" and c.address
    _clear()


def test_the_staff_all_have_a_number_so_alerts_can_reach_them():
    from vyuha_platform import people

    _clear()
    slug = _act("create")["slug"]
    assert _act("people")["ok"] is True
    org = people.load(slug)
    assert len(org.staff) == len(demo_tour.STAFF)
    assert all(p.phone for p in org.staff), "a person with no number is never told anything"
    assert {p.role for p in org.staff} >= {"Owner", "Manager", "Accountant"}
    _clear()


def test_the_stock_file_lands_and_the_costs_can_be_typed_in():
    """The demo's best beat: margin is zero until the costs go in, then it is not."""
    _clear()
    slug = _act("create")["slug"]
    _act("datamap")
    assert _act("import_stock")["ok"] is True

    book = books.load(slug)
    assert book.items, "the stock statement should have created the shelf"
    assert not any(i.cost for i in book.items), "no file carries cost — that is the point"

    assert _act("costs")["ok"] is True
    book = books.load(slug)
    assert sum(1 for i in book.items if i.cost) == len(book.items)
    _clear()


def test_costs_before_any_item_says_what_to_do_first():
    _clear()
    _act("create")
    out = _act("costs")
    assert out["ok"] is False and "stock statement" in out["message"]
    _clear()


def test_an_unknown_action_is_refused_politely():
    out = _act("drop-everything")
    assert out["ok"] is False and "not something the demo can do" in out["message"]


# ------------------------------------------------------------------ runner

def _cleanup() -> None:
    try:
        _login()
        client.post("/demo/reset")
    except Exception:                                      # noqa: BLE001
        pass
    for acct in (ACCOUNT, TENANT):
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
