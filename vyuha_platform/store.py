"""Client registry and run history.

JSON on disk, not a database. At the scale this serves — a founder-operated
service with a handful of clients — a file is easier to inspect, back up and
hand-edit than sqlite, and swapping it later means replacing this module only.
Nothing above it knows how persistence works.

Since signup opened up, one file holds the clients of *every* account, and each
``Client`` carries the ``owner_id`` of the account that created it. Every read
in this module therefore demands an ``owner_id`` as a **required** argument:
forgetting to scope a query is then a ``TypeError`` on the first request rather
than one business quietly reading another's numbers. The only unscoped readers
are the two private helpers below, which exist so slugs stay unique across the
whole file.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from . import atomic

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "vyuha_data"
UPLOADS = DATA / "uploads"
DASHBOARDS = DATA / "dashboards"
COVERS = DATA / "covers"
REGISTRY = DATA / "clients.json"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def slugify(name: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")
    return slug or "client"


@dataclass
class Run:
    """One file, put through the engine once."""

    id: str
    filename: str
    uploaded_at: str
    status: str = "ok"              # ok | failed
    error: str = ""
    dashboard: str = ""             # path relative to DASHBOARDS
    # --- provenance: how this file was read before the engine ever saw it.
    # A number transcribed from a photograph must never look identical to one
    # typed into Excel, so every run carries its own reading method forward.
    source_kind: str = "native"     # native | text | pdf-text | vision-image | vision-pdf
    source_method: str = ""         # human-readable, e.g. "Handwriting read by Claude"
    confidence: str = "high"        # high | medium | low
    source_notes: list[str] = field(default_factory=list)
    converted: str = ""             # the CSV actually handed to the engine, if any
    alert_count: int = 0
    critical_count: int = 0
    sheets_read: list[str] = field(default_factory=list)
    sheets_skipped: list[str] = field(default_factory=list)
    revenue: float = 0.0
    stock_value: float = 0.0
    outstanding: float = 0.0
    alerts: list[dict] = field(default_factory=list)


@dataclass
class Client:
    slug: str
    name: str
    #: The account this workspace belongs to (``auth.Account.id``). Blank only
    #: for records written before accounts existed; those belong to nobody and
    #: are therefore invisible, which is the safe direction to fail.
    owner_id: str = ""
    contact: str = ""
    phone: str = ""                 # digits with country code, no +
    email: str = ""
    industry: str = ""
    created_at: str = field(default_factory=_now)
    #: "upload" — they send files. "books" — they have no spreadsheet at all and
    #: type entries in directly. Both end up in the same engine; see books.py.
    data_mode: str = "upload"
    #: Drives the workspace's colour and default backdrop. See ui.TRADES.
    trade: str = "general"
    #: True once they have uploaded their own cover photo (served at /c/<slug>/cover).
    has_cover: bool = False
    # Per-client alert thresholds. The engine's module-level constants are the
    # defaults; a slow-moving spares dealer and an FMCG distributor do not share
    # a definition of "dead".
    dead_stock_days: int = 90
    low_cover_days: int = 14

    # --- what a tax invoice must carry.
    # A GST invoice without a GSTIN, an address and a place of supply is not a
    # tax invoice — the buyer's accountant will reject it and the buyer cannot
    # claim input credit, which is the whole reason they want a printed bill.
    # All defaulted: a business that does not issue tax invoices still works,
    # and the invoice screen says plainly which of these are missing.
    address: str = ""
    gstin: str = ""
    #: Two-letter state code, e.g. "KA". Decides CGST+SGST (within the state)
    #: against IGST (across it) — the one field that changes the arithmetic.
    state: str = ""
    bank_name: str = ""
    bank_account: str = ""
    bank_ifsc: str = ""
    invoice_terms: str = "Payment due within 30 days. Goods once sold are not returnable."
    #: Which of the invoice looks to print. See invoice.TEMPLATES.
    invoice_template: str = "classic"
    #: Last number issued, **per financial year**. A single counter plus a
    #: "current year" field looks equivalent and is not: bill a March sale, then
    #: an April one, then March again, and the counter resets each time the year
    #: flips — reissuing numbers already used. Keyed by FY, it cannot.
    #: A cancelled invoice does not give its number back, so the series has
    #: gaps but never a reuse, which is the safe direction.
    invoice_seq_by_fy: dict = field(default_factory=dict)

    runs: list[Run] = field(default_factory=list)

    @property
    def latest(self) -> Run | None:
        return self.runs[0] if self.runs else None

    @property
    def initials(self) -> str:
        parts = [p for p in self.name.split() if p]
        return "".join(p[0] for p in parts[:2]).upper() or "C"


def _ensure_dirs() -> None:
    for d in (DATA, UPLOADS, DASHBOARDS):
        d.mkdir(parents=True, exist_ok=True)


def _load_all() -> list[Client]:
    """Every client on the machine, regardless of owner. Private on purpose."""
    _ensure_dirs()
    if not REGISTRY.exists():
        return []
    # atomic.read_json rather than a bare json.loads: a registry damaged by
    # anything (an older non-atomic build, a full disk, a killed process) used
    # to raise here, and since every private route reads clients first, one bad
    # file blanked the entire product. Now it quarantines the file and the app
    # still starts.
    raw = atomic.read_json(REGISTRY, [])
    clients = []
    for row in raw:
        runs = [Run(**{k: v for k, v in r.items() if k in Run.__dataclass_fields__})
                for r in row.pop("runs", [])]
        known = {k: v for k, v in row.items() if k in Client.__dataclass_fields__}
        clients.append(Client(**known, runs=runs))
    clients.sort(key=lambda c: c.created_at, reverse=True)
    return clients


def _save_all(clients: list[Client]) -> None:
    _ensure_dirs()
    payload = []
    for c in clients:
        row = asdict(c)
        row["runs"] = [asdict(r) for r in c.runs]
        payload.append(row)
    atomic.write_json(REGISTRY, payload)


def load_clients(owner_id: str) -> list[Client]:
    """The clients one account owns, newest first."""
    return [c for c in _load_all() if c.owner_id == owner_id]


def all_clients() -> list[Client]:
    """**Every client on the install, ignoring ownership.**

    Master console only. Named to be impossible to call by accident while
    reaching for the scoped ``load_clients(owner_id)`` — if you are reading this
    from a customer-facing route, you want that one instead.
    """
    return _load_all()


def find_client(slug: str) -> Client | None:
    """One client, **ignoring ownership**. Master console only — see above."""
    return next((c for c in _load_all() if c.slug == slug), None)


def get_client(slug: str, owner_id: str) -> Client | None:
    """One client, **only** if this account owns it.

    Returning None for somebody else's slug rather than raising is deliberate:
    the caller then renders the same "no longer exists" page it would for a
    genuine typo, so a URL cannot be used to probe which businesses exist.
    """
    return next((c for c in _load_all()
                 if c.slug == slug and c.owner_id == owner_id), None)


def add_client(owner_id: str, **kwargs) -> Client:
    clients = _load_all()
    base = slugify(kwargs.get("name", ""))
    slug, n = base, 2
    # Slugs are unique across every account, because they name directories on
    # disk (uploads/, dashboards/) that are not partitioned by owner.
    while any(c.slug == slug for c in clients):
        slug, n = f"{base}-{n}", n + 1
    client = Client(slug=slug, owner_id=owner_id, **kwargs)
    clients.append(client)
    _save_all(clients)
    return client


def update_client(client: Client) -> None:
    """Write a client back. The caller must already have fetched it scoped."""
    _save_all([client if c.slug == client.slug else c for c in _load_all()])


def delete_client(slug: str, owner_id: str) -> None:
    _save_all([c for c in _load_all()
               if not (c.slug == slug and c.owner_id == owner_id)])


def add_run(slug: str, owner_id: str, run: Run) -> None:
    client = get_client(slug, owner_id)
    if client is None:
        raise KeyError(slug)
    client.runs.insert(0, run)          # newest first
    update_client(client)


def upload_dir(slug: str) -> Path:
    d = UPLOADS / slug
    d.mkdir(parents=True, exist_ok=True)
    return d


def covers_dir() -> Path:
    COVERS.mkdir(parents=True, exist_ok=True)
    return COVERS


def dashboard_dir(slug: str) -> Path:
    d = DASHBOARDS / slug
    d.mkdir(parents=True, exist_ok=True)
    return d
