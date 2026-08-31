"""Append-only activity ledger — the traceability spine.

Clients arrive by different routes and send different things: one emails a
monthly .xlsx, one photographs a register, one forwards a PDF from their
accountant. The dashboards show *what the numbers are*; this shows **where each
number came from and what happened to it**.

One JSONL file, appended and never rewritten, so a crash or a concurrent write
can lose at most the last line. Each entry records who it was about, what
happened, and enough detail to reconstruct the chain:

    client.onboarded -> source.received -> source.converted -> run.completed
                                                            -> alert.sent
                                                            -> export.created

Reading is a filter over the file rather than an index — at a founder-operated
scale that is faster than maintaining one, and the file stays greppable by hand.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from .store import DATA

LEDGER = DATA / "activity.jsonl"

#: Every kind that can appear, with the label the UI renders and its accent.
KINDS = {
    "account.created":   ("Account created", "ok"),
    "client.onboarded":  ("Client onboarded", "ok"),
    "client.deleted":    ("Client deleted", "dim"),
    "source.received":   ("File received", "info"),
    "source.converted":  ("File converted", "info"),
    "source.rejected":   ("File rejected", "crit"),
    "run.completed":     ("Data understood", "ok"),
    "run.failed":        ("Could not read the file", "crit"),
    "alert.raised":      ("Alerts raised", "warn"),
    "alert.sent":        ("Brief sent", "ok"),
    "alert.send_failed": ("Brief not sent", "crit"),
    "export.created":    ("Export generated", "info"),
    "share.created":     ("Workspace link issued", "info"),
    "share.opened":      ("Owner opened workspace", "ok"),
    "share.revoked":     ("Workspace link revoked", "dim"),
    "share.locked":      ("Link paused after wrong PINs", "warn"),
    "account.password":  ("Password changed", "dim"),
    "master.viewed":     ("Vyuha support opened it", "warn"),
    "account.login":     ("Signed in", "dim"),
    "receipt.sent":      ("Receipt sent to buyer", "ok"),
    "receipt.failed":    ("Receipt not sent", "warn"),
    "settings.changed":  ("Settings changed", "dim"),
    # -- the console (stock, ask, follow-ups, money, people)
    "agent.asked":       ("Question asked", "info"),
    "followup.handled":  ("Follow-up handled", "ok"),
    "money.recorded":    ("Payment recorded", "info"),
    "people.changed":    ("Branches or staff changed", "dim"),
    "invoice.raised":    ("Invoice raised", "ok"),
    "invoice.cancelled": ("Invoice cancelled", "warn"),
}


@dataclass
class Entry:
    ts: str
    kind: str
    #: The account this event belongs to. One file still holds every account's
    #: history — it is append-only and must stay that way — so the scoping is a
    #: filter on read. Entries written before accounts existed have no owner and
    #: are shown to nobody.
    owner: str = ""
    client: str = ""            # slug, blank for platform-level events
    client_name: str = ""
    summary: str = ""
    channel: str = ""           # upload | whatsapp | email | pdf | pptx | vision
    detail: dict = field(default_factory=dict)

    @property
    def label(self) -> str:
        return KINDS.get(self.kind, (self.kind, "dim"))[0]

    @property
    def tone(self) -> str:
        return KINDS.get(self.kind, (self.kind, "dim"))[1]

    @property
    def when(self) -> str:
        return self.ts.replace("T", " ")[:16]


def log(kind: str, summary: str, client=None, channel: str = "", owner: str = "",
        **detail) -> Entry:
    """Append one event. Never raises — a ledger failure must not fail the action.

    ``owner`` is taken from the client when one is passed, so the ordinary call
    sites did not have to change; platform-level events pass it explicitly.
    """
    entry = Entry(
        ts=datetime.now().isoformat(timespec="seconds"),
        kind=kind,
        owner=owner or getattr(client, "owner_id", ""),
        client=getattr(client, "slug", "") or (client if isinstance(client, str) else ""),
        client_name=getattr(client, "name", ""),
        summary=summary,
        channel=channel,
        detail=detail,
    )
    try:
        LEDGER.parent.mkdir(parents=True, exist_ok=True)
        with LEDGER.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(asdict(entry), ensure_ascii=False) + "\n")
    except OSError:
        pass
    return entry


def read(owner: str, limit: int = 200, client: str = "",
         kinds: set[str] | None = None) -> list[Entry]:
    """One account's history, newest first.

    ``owner`` is required for the same reason ``store`` requires it: a reader
    that forgets to scope should fail, not quietly show somebody else's files.
    A malformed line is skipped rather than killing the read.
    """
    if not LEDGER.exists():
        return []
    out: list[Entry] = []
    try:
        lines = LEDGER.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []

    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
            entry = Entry(**row)
        except (json.JSONDecodeError, TypeError):
            continue
        if entry.owner != owner:
            continue
        if client and entry.client != client:
            continue
        if kinds and entry.kind not in kinds:
            continue
        out.append(entry)
        if len(out) >= limit:
            break
    return out


def read_all(limit: int = 200) -> list[Entry]:
    """**Every account's events.** Master console only.

    Named apart from :func:`read` on purpose: the scoped one is what customer
    routes want, and mixing them up is exactly the mistake the required ``owner``
    argument exists to prevent.
    """
    if not LEDGER.exists():
        return []
    out: list[Entry] = []
    try:
        lines = LEDGER.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            out.append(Entry(**json.loads(line)))
        except (json.JSONDecodeError, TypeError):
            continue
        if len(out) >= limit:
            break
    return out


def counts(owner: str) -> dict:
    """Headline numbers for the activity view, for one account."""
    entries = read(owner, limit=10_000)
    by_kind: dict[str, int] = {}
    for e in entries:
        by_kind[e.kind] = by_kind.get(e.kind, 0) + 1
    return {
        "total": len(entries),
        "files": by_kind.get("source.received", 0),
        "runs": by_kind.get("run.completed", 0),
        "sends": by_kind.get("alert.sent", 0),
        "failures": by_kind.get("run.failed", 0) + by_kind.get("source.rejected", 0)
                    + by_kind.get("alert.send_failed", 0),
        "by_kind": by_kind,
    }
