"""Tax invoices — the document a buyer's accountant will accept.

``channels.as_receipt`` already produces a WhatsApp bill, and it is right for
what it is: a line the buyer can keep. It is not an invoice. An invoice is a
legal document, and the difference is not decoration —

* it carries **both** parties' GSTIN and address, and a **place of supply**,
* it splits tax into **CGST + SGST** within a state and **IGST** across one,
* it shows taxable value and tax separately per line, with an HSN code,
* it is **numbered sequentially with no gaps**, per financial year.

Get any of those wrong and the buyer cannot claim input credit, which is the
entire reason they asked for a printed bill rather than a WhatsApp message.

Three decisions worth keeping:

**Tax is computed per line, then summed — never on the total.** Rounding a
mixed-rate invoice at the bottom produces a figure that disagrees with the
buyer's own books by a rupee or two, and a rupee is enough for a clerk to reject
it. Each line rounds to two decimals and the totals are sums of rounded lines.

**Numbering is issued once and never reused.** ``next_number`` bumps a counter
on the client and resets it at the start of each financial year. A gap in an
invoice series is a question from the tax office, so a failed render must not
consume a number — the number is taken only when the invoice is saved.

**What is missing is stated, never invented.** A business with no GSTIN gets a
clean bill of supply rather than an invoice with a blank tax field; ``missing()``
lists what would have to be filled in for it to be a tax invoice, and the screen
prints that list.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path

from . import atomic

REPO = Path(__file__).resolve().parent.parent
INVOICES = REPO / "vyuha_data" / "invoices"

#: The looks on offer. A "preloaded template" implies a choice, and the three
#: differ in what they emphasise, not merely in colour.
TEMPLATES = {
    "classic": ("Classic", "Bordered and formal — what most accountants expect"),
    "modern": ("Modern", "Clean and roomy, with the total set large"),
    "compact": ("Compact", "Fits a long bill on one page"),
}

#: State code to name, for the place-of-supply line. Only the ones a Karnataka
#: distributor actually bills; anything else is shown as its bare code rather
#: than guessed at.
STATES = {
    "KA": "Karnataka", "MH": "Maharashtra", "TN": "Tamil Nadu", "AP": "Andhra Pradesh",
    "TS": "Telangana", "KL": "Kerala", "GA": "Goa", "GJ": "Gujarat", "DL": "Delhi",
    "UP": "Uttar Pradesh", "MP": "Madhya Pradesh", "RJ": "Rajasthan", "WB": "West Bengal",
    "PB": "Punjab", "HR": "Haryana", "BR": "Bihar", "OR": "Odisha", "AS": "Assam",
    "JH": "Jharkhand", "CG": "Chhattisgarh", "UK": "Uttarakhand", "HP": "Himachal Pradesh",
}


def _today() -> str:
    return date.today().isoformat()


def _fy(iso: str = "") -> str:
    """The Indian financial year a date falls in, as "2026-27"."""
    d = date.fromisoformat((iso or _today())[:10])
    start = d.year if d.month >= 4 else d.year - 1
    return f"{start}-{str(start + 1)[2:]}"


def _r2(value: float) -> float:
    return round(float(value or 0), 2)


@dataclass
class Line:
    """One row of the bill, with its own tax because rates differ per item."""

    item: str
    qty: float
    rate: float
    sku: str = ""
    unit: str = "piece"
    hsn: str = ""
    gst_rate: float = 0.0
    discount: float = 0.0          # absolute, applied before tax

    @property
    def gross(self) -> float:
        return _r2(self.qty * self.rate)

    @property
    def taxable(self) -> float:
        return _r2(self.gross - self.discount)

    @property
    def tax(self) -> float:
        return _r2(self.taxable * self.gst_rate / 100)

    @property
    def total(self) -> float:
        return _r2(self.taxable + self.tax)


@dataclass
class Invoice:
    id: str
    number: str
    date: str
    #: Buyer
    party: str
    party_address: str = ""
    party_gstin: str = ""
    party_state: str = ""
    party_phone: str = ""
    lines: list[Line] = field(default_factory=list)
    #: True when supplier and buyer are in the same state — CGST + SGST rather
    #: than IGST. Frozen onto the invoice at issue, because a client's state can
    #: be corrected later and a already-issued invoice must not silently change.
    intra_state: bool = True
    notes: str = ""
    terms: str = ""
    due_date: str = ""
    paid: bool = False
    template: str = "classic"
    #: The sale ids this invoice covers, when it was raised from the book.
    sale_ids: list[str] = field(default_factory=list)
    #: Microseconds, not seconds. Four invoices raised inside one second all
    #: carried the same stamp, so load_all()'s "newest first" became arbitrary
    #: and the list showed them in a random order.
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    # ---- totals, all derived from the lines
    @property
    def taxable(self) -> float:
        return _r2(sum(ln.taxable for ln in self.lines))

    @property
    def discount(self) -> float:
        return _r2(sum(ln.discount for ln in self.lines))

    @property
    def tax(self) -> float:
        return _r2(sum(ln.tax for ln in self.lines))

    @property
    def cgst(self) -> float:
        return _r2(self.tax / 2) if self.intra_state else 0.0

    @property
    def sgst(self) -> float:
        return self.cgst

    @property
    def igst(self) -> float:
        return 0.0 if self.intra_state else self.tax

    @property
    def total(self) -> float:
        return _r2(self.taxable + self.tax)

    @property
    def rounded(self) -> float:
        return float(round(self.total))

    @property
    def round_off(self) -> float:
        return _r2(self.rounded - self.total)

    @property
    def taxed(self) -> bool:
        """False when nothing on the bill carries a rate — a bill of supply."""
        return any(ln.gst_rate for ln in self.lines)

    def by_rate(self) -> list[dict]:
        """The HSN summary a tax invoice needs when rates differ per line."""
        groups: dict[float, dict] = {}
        for ln in self.lines:
            g = groups.setdefault(ln.gst_rate, {"gst_rate": ln.gst_rate,
                                                "taxable": 0.0, "tax": 0.0})
            g["taxable"] += ln.taxable
            g["tax"] += ln.tax
        rows = sorted(groups.values(), key=lambda g: g["gst_rate"])
        for g in rows:
            g["taxable"], g["tax"] = _r2(g["taxable"]), _r2(g["tax"])
            g["half"] = _r2(g["tax"] / 2)
        return rows


# ------------------------------------------------------------------ numbering

def next_number(client, when: str = "") -> tuple[str, int, str]:
    """The next invoice number, without consuming it.

    Returns ``(number, sequence, financial_year)``. The caller commits it by
    writing the sequence back to the client — so a render that fails part way
    does not burn a number and leave a gap in the series.
    """
    fy = _fy(when)
    used = dict(getattr(client, "invoice_seq_by_fy", None) or {})
    seq = int(used.get(fy, 0)) + 1
    return f"INV/{fy}/{seq:04d}", seq, fy


def missing(client) -> list[str]:
    """What would have to be filled in for this to be a tax invoice."""
    gaps = []
    if not client.gstin:
        gaps.append("your GSTIN")
    if not client.address:
        gaps.append("your business address")
    if not client.state:
        gaps.append("your state, which decides CGST/SGST against IGST")
    return gaps


# ------------------------------------------------------------------ building

def from_sales(client, book, sale_ids: list[str], party_state: str = "",
               party_gstin: str = "", party_address: str = "",
               due_date: str = "", notes: str = "") -> Invoice:
    """Raise one invoice covering one or more sales already in the book.

    Several sales, one invoice: a customer who bought three things over a
    morning gets one bill, which is what he expects and what the shop's own
    numbering assumes.
    """
    sales = [s for s in book.sales if s.id in set(sale_ids)]
    if not sales:
        raise ValueError("No such sale on this book.")

    by_sku = {i.sku: i for i in book.items}
    lines = []
    for s in sales:
        item = by_sku.get(s.sku)
        lines.append(Line(
            item=s.item or s.sku, sku=s.sku, qty=s.qty, rate=s.rate,
            unit=getattr(item, "unit", "piece"),
            hsn=getattr(item, "hsn", ""),
            gst_rate=float(getattr(item, "gst_rate", 0) or 0),
        ))

    party = sales[0].party or "Cash sale"
    state = (party_state or client.state or "").upper()
    # Dated when it is raised, not when the goods moved. Invoicing a March sale
    # in April is ordinary; back-dating the document to make the numbering line
    # up is not, and would put an April invoice in the previous year's series.
    when = _today()
    number, _seq, _fy_label = next_number(client, when)

    return Invoice(
        id=uuid.uuid4().hex[:8],
        number=number,
        date=when,
        party=party,
        party_address=party_address,
        party_gstin=party_gstin,
        party_state=state,
        party_phone=sales[0].party_phone,
        lines=lines,
        # Same state, or the buyer's state unknown: treat it as local, which is
        # the common case and the one a shop assumes when nobody says otherwise.
        intra_state=(not state or not client.state
                     or state == (client.state or "").upper()),
        due_date=due_date or (sales[0].due_date if not sales[0].paid else ""),
        paid=all(s.paid for s in sales),
        terms=client.invoice_terms,
        template=client.invoice_template or "classic",
        notes=notes,
        sale_ids=[s.id for s in sales],
    )


# ---------------------------------------------------------------- persistence

def _path(slug: str) -> Path:
    INVOICES.mkdir(parents=True, exist_ok=True)
    return INVOICES / f"{slug}.json"


def load_all(slug: str) -> list[Invoice]:
    raw = atomic.read_json(_path(slug), [])
    out = []
    for row in raw:
        lines = [Line(**{k: v for k, v in ln.items() if k in Line.__dataclass_fields__})
                 for ln in row.pop("lines", [])]
        known = {k: v for k, v in row.items() if k in Invoice.__dataclass_fields__}
        out.append(Invoice(**known, lines=lines))
    out.sort(key=lambda i: i.created_at, reverse=True)
    return out


def get(slug: str, invoice_id: str) -> Invoice | None:
    return next((i for i in load_all(slug) if i.id == invoice_id), None)


def save(slug: str, invoice: Invoice) -> None:
    existing = [i for i in load_all(slug) if i.id != invoice.id]
    existing.append(invoice)
    rows = []
    for inv in existing:
        row = asdict(inv)
        rows.append(row)
    atomic.write_json(_path(slug), rows)


def issue(client, book, sale_ids: list[str], **kwargs) -> tuple[Invoice, str]:
    """Build, number and store an invoice. The number is consumed here only."""
    from . import store

    invoice = from_sales(client, book, sale_ids, **kwargs)
    _number, seq, fy = next_number(client, invoice.date)
    used = dict(getattr(client, "invoice_seq_by_fy", None) or {})
    used[fy] = seq
    client.invoice_seq_by_fy = used
    store.update_client(client)
    save(client.slug, invoice)
    return invoice, f"Invoice {invoice.number} raised for {invoice.party}."


def delete(slug: str, invoice_id: str) -> str:
    """Remove an invoice. The number is **not** returned to the pool.

    A cancelled invoice leaves a gap on purpose: reusing its number would mean
    two different documents had shared one, which is worse than a gap and far
    harder to explain.
    """
    invoice = get(slug, invoice_id)
    if invoice is None:
        return "That invoice is already gone."
    atomic.write_json(_path(slug),
                      [asdict(i) for i in load_all(slug) if i.id != invoice_id])
    return f"{invoice.number} cancelled. Its number stays used, so the series has no reuse."
