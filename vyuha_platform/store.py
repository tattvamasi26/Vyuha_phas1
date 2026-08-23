"""Client registry and run history.

JSON on disk, not a database. At the scale this serves — a founder-operated
service with a handful of clients — a file is easier to inspect, back up and
hand-edit than sqlite, and swapping it later means replacing this module only.
Nothing above it knows how persistence works.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

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


def load_clients() -> list[Client]:
    _ensure_dirs()
    if not REGISTRY.exists():
        return []
    raw = json.loads(REGISTRY.read_text(encoding="utf-8"))
    clients = []
    for row in raw:
        runs = [Run(**r) for r in row.pop("runs", [])]
        clients.append(Client(**row, runs=runs))
    clients.sort(key=lambda c: c.created_at, reverse=True)
    return clients


def save_clients(clients: list[Client]) -> None:
    _ensure_dirs()
    payload = []
    for c in clients:
        row = asdict(c)
        row["runs"] = [asdict(r) for r in c.runs]
        payload.append(row)
    REGISTRY.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def get_client(slug: str) -> Client | None:
    return next((c for c in load_clients() if c.slug == slug), None)


def add_client(**kwargs) -> Client:
    clients = load_clients()
    base = slugify(kwargs.get("name", ""))
    slug, n = base, 2
    while any(c.slug == slug for c in clients):
        slug, n = f"{base}-{n}", n + 1
    client = Client(slug=slug, **kwargs)
    clients.append(client)
    save_clients(clients)
    return client


def update_client(client: Client) -> None:
    clients = [client if c.slug == client.slug else c for c in load_clients()]
    save_clients(clients)


def delete_client(slug: str) -> None:
    save_clients([c for c in load_clients() if c.slug != slug])


def add_run(slug: str, run: Run) -> None:
    client = get_client(slug)
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
