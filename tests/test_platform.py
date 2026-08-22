"""End-to-end tests for the platform shell.

Drives the real routes against the real engine: onboard a client, upload the
messy sample workbook, and check the dashboard and WhatsApp brief come back.

Runs under pytest or standalone:  python -m tests.test_platform
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from fastapi.testclient import TestClient

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from vyuha import sample                      # noqa: E402
from vyuha_platform import app as app_mod     # noqa: E402
from vyuha_platform import channels, store    # noqa: E402

client = TestClient(app_mod.app, follow_redirects=True)

_TEST_SLUGS: list[str] = []


def _sample_workbook() -> Path:
    path = REPO / "out" / "sample-distributor.xlsx"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        sample.build(path)
    return path


def _onboard(name: str, **extra) -> str:
    body = {"name": name, "phone": "98765 43210", "email": "owner@firm.in",
            "dead_stock_days": "90", "low_cover_days": "14", **extra}
    resp = client.post("/onboard", data=body)
    assert resp.status_code == 200, resp.status_code
    slug = store.slugify(name)
    matches = [c.slug for c in store.load_clients() if c.slug.startswith(slug)]
    assert matches, f"client {name} was not persisted"
    _TEST_SLUGS.extend(matches)
    return matches[0]


# --------------------------------------------------------------------- tests

def test_home_renders_with_no_clients():
    resp = client.get("/")
    assert resp.status_code == 200
    assert "VYUHA" in resp.text


def test_onboarding_creates_a_workspace():
    slug = _onboard("Zeta Test Traders")
    got = store.get_client(slug)
    assert got is not None
    assert got.name == "Zeta Test Traders"
    assert got.phone == "919876543210", got.phone     # 10 digits -> +91 assumed
    assert client.get(f"/c/{slug}").status_code == 200


def test_upload_produces_dashboard_and_alerts():
    slug = _onboard("Zeta Upload Co")
    book = _sample_workbook()
    with book.open("rb") as fh:
        resp = client.post(
            f"/c/{slug}/upload",
            files={"file": (book.name, fh,
                            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
    assert resp.status_code == 200, resp.status_code

    run = store.get_client(slug).latest
    assert run is not None and run.status == "ok", getattr(run, "error", "no run")
    assert run.alert_count >= 3, run.alert_count
    assert run.revenue > 0 and run.stock_value > 0
    assert {"Sales", "Stock", "Receivables"} <= set(run.sheets_read), run.sheets_read

    # every alert carries a machine code, not just prose
    assert all(a["code"] != "generic" for a in run.alerts), run.alerts
    assert any(a["code"] == "dead_stock" and a["entities"] for a in run.alerts)

    page = client.get(f"/c/{slug}/dashboard")
    assert page.status_code == 200
    assert "What Vyuha read" in page.text or "Vyuha" in page.text


def test_alerts_tab_renders_a_sendable_whatsapp_brief():
    slug = _onboard("Zeta Brief Co")
    book = _sample_workbook()
    with book.open("rb") as fh:
        client.post(f"/c/{slug}/upload", files={"file": (book.name, fh, "application/octet-stream")})

    resp = client.get(f"/c/{slug}?tab=alerts")
    assert resp.status_code == 200
    assert "wa.me/919876543210" in resp.text, "WhatsApp deep link missing"
    assert "Send on WhatsApp" in resp.text


def test_rejected_file_type_does_not_create_a_run():
    slug = _onboard("Zeta Reject Co")
    resp = client.post(f"/c/{slug}/upload",
                       files={"file": ("notes.txt", b"hello", "text/plain")})
    assert resp.status_code == 200
    assert store.get_client(slug).runs == []


def test_whatsapp_brief_respects_the_character_cap():
    from vyuha import pipeline
    insights = pipeline.run(_sample_workbook()).insights
    for cap in (1024, 400, 220):
        text = channels.as_whatsapp(insights, client="Cap Test", limit=cap)
        assert len(text) <= cap, f"cap {cap}: got {len(text)}"


def test_phone_normalisation():
    assert channels.normalise_phone("98765 43210") == "919876543210"
    assert channels.normalise_phone("+91 98765-43210") == "919876543210"
    assert channels.normalise_phone("0091 9876543210") == "919876543210"
    assert channels.normalise_phone("") == ""


def _cleanup() -> None:
    for slug in set(_TEST_SLUGS):
        shutil.rmtree(store.UPLOADS / slug, ignore_errors=True)
        shutil.rmtree(store.DASHBOARDS / slug, ignore_errors=True)
        store.delete_client(slug)


def main() -> int:
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    passed, failed = 0, 0
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
