"""Reading the things that are not files: conversations.

``sources.py`` already converts anything with a table in it — spreadsheets, CSVs,
PDFs, photographs of a register — into something the engine can read. This module
handles the input that has no table at all: **an exported WhatsApp thread**.

That matters more than it sounds. For a large share of Indian distributors the
order book *is* the WhatsApp thread. Nothing is ever typed into a system; the
customer sends "20 bags urea beku", the owner replies "done", and the only
record is a chat. A product that reads spreadsheets beautifully and cannot read
that is reading the wrong artefact.

Two ways to read it, and the fallback is not a lesser one:

* **Claude**, through ``llm.ask`` with a strict schema, which handles the register
  people actually type in — Kannada-English code-switching, "beku", numbers as
  words, an order spread over three messages.
* **Patterns**, when there is no API key or no signal. It matches quantities
  against the client's own item names, so it finds the orders that are phrased
  plainly and honestly reports lower confidence. A demo laptop on a bad network
  still shows the feature working.

Everything extracted is **a draft, never a fact**. ``ChatExtract`` carries a
confidence per line and the exact message it came from, because a number lifted
out of a conversation by a model has a different standing from one typed into a
spreadsheet, and the screen must be able to say so. Nothing here writes to the
books; it proposes rows for a person to confirm.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from . import llm

#: WhatsApp exports every line as "DD/MM/YYYY, H:MM am - Sender: text".
#: The separator and the date order vary by locale, so the sniff is loose and
#: only has to be surer than "this might be a CSV".
_LINE = re.compile(
    r"^\[?(\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4})[,\]]?\s+"
    r"(\d{1,2}:\d{2}(?::\d{2})?\s*(?:[ap]\.?m\.?)?)\s*[\]\-–]\s*"
    r"([^:]{1,60}?):\s*(.*)$",
    re.IGNORECASE)

#: Quantity words that appear in front of an item: "20 bags urea", "5 pkt seed".
_QTY = re.compile(
    r"(\d+(?:\.\d+)?)\s*"
    r"(bags?|bag|pkts?|packets?|pieces?|pcs?|nos?|kg|kgs|litres?|ltr|l|"
    r"coils?|boxes?|box|tins?|cans?|units?)?\b",
    re.IGNORECASE)

#: Words that mark a message as an order rather than chatter. Kannada-English
#: included because that is how the messages actually arrive.
_WANT = ("beku", "send", "need", "want", "give", "order", "supply", "deliver",
         "chahiye", "bhejo", "kalisi", "hold", "book", "arrange", "urgent")
_PAID = ("paid", "payment", "neft", "rtgs", "upi", "transferred", "sent money",
         "deposited", "cleared", "settled")

#: Asking is not ordering. "stock ideya?", "rate enu?", "available?" all carry a
#: quantity and an item name, and would otherwise read as orders -- which is the
#: expensive mistake in this direction, because it invents demand that does not
#: exist. When a message is a question, drop it.
_ASKING = ("rate enu", "rate what", "what rate", "how much", "price enu",
           "ideya", "stock ide", "available", "availability", "kitna",
           "enu rate", "quote", "rate?")

#: An unpaid balance the customer brings up is neither a payment nor an order.
#: It belongs against their account, so it gets its own kind rather than being
#: quietly counted as money received.
_BALANCE = ("pending", "balance", "baki", "due ide", "outstanding", "bill pending")


@dataclass
class ChatLine:
    """One message, kept whole so any extraction can be traced back to it."""
    when: str
    sender: str
    text: str
    raw: str


@dataclass
class Draft:
    """One row proposed from the conversation. Never written without approval."""
    kind: str                      # order | payment | balance
    party: str
    item: str = ""
    qty: float = 0.0
    unit: str = ""
    amount: float = 0.0
    when: str = ""
    confidence: str = "medium"     # high | medium | low
    evidence: str = ""             # the message it came from, verbatim


@dataclass
class ChatExtract:
    ok: bool
    drafts: list[Draft] = field(default_factory=list)
    messages: int = 0
    method: str = ""               # how it was read, shown in the UI
    error: str = ""
    needs_action: str = ""

    @property
    def orders(self) -> list[Draft]:
        return [d for d in self.drafts if d.kind == "order"]

    @property
    def payments(self) -> list[Draft]:
        return [d for d in self.drafts if d.kind == "payment"]


# ------------------------------------------------------------------ sniffing

def looks_like_chat(text: str) -> bool:
    """True when enough lines match the export format to be sure.

    A threshold rather than a single match, because one line of a CSV can look
    like a timestamped message by accident and misrouting a real spreadsheet
    into the chat parser would be a much worse failure than the reverse.
    """
    lines = [ln for ln in text.splitlines() if ln.strip()][:40]
    if len(lines) < 4:
        return False
    hits = sum(1 for ln in lines if _LINE.match(ln.strip()))
    return hits >= max(3, len(lines) // 3)


def read_lines(text: str) -> list[ChatLine]:
    """Parse the transcript into messages, joining continuation lines.

    A message that wraps onto the next line has no timestamp of its own, and
    dropping those loses exactly the long messages most likely to contain an
    order.
    """
    out: list[ChatLine] = []
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped:
            continue
        m = _LINE.match(stripped)
        if m:
            when, _time, sender, body = m.groups()
            out.append(ChatLine(when=when, sender=sender.strip(),
                                text=body.strip(), raw=stripped))
        elif out:
            out[-1].text += " " + stripped
            out[-1].raw += " " + stripped
    return out


def _iso(when: str) -> str:
    for fmt in ("%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y", "%d-%m-%y", "%d.%m.%Y"):
        try:
            return datetime.strptime(when, fmt).date().isoformat()
        except ValueError:
            continue
    return ""


# ------------------------------------------------------------- the pattern path

def _match_item(text: str, names: list[str]) -> tuple[str, int] | None:
    """Find the client's own item in a message, longest name first.

    Longest-first matters: "Urea 50kg" and "Urea" both match "20 bags urea
    50kg", and the shorter one would throw away the pack size.
    """
    low = text.lower()
    best = None
    for name in sorted(names, key=len, reverse=True):
        head = name.lower()
        idx = low.find(head)
        if idx == -1:
            # Try the first word alone: "urea" for "Urea 50kg", "dap" for
            # "DAP 50kg". Three characters, not four -- half the fertiliser
            # trade is DAP, MOP, NPK and SSP, and a four-character floor
            # silently dropped every one of them.
            #
            # Short names need a word boundary, though. A bare `find` would
            # match "dap" inside "adaptor" and book an order for fertiliser
            # because somebody mentioned a pipe fitting.
            first = head.split()[0]
            if len(first) >= 3:
                hit = re.search(r"\b" + re.escape(first) + r"\b", low)
                idx = hit.start() if hit else -1
        if idx != -1 and (best is None or idx < best[1]):
            best = (name, idx)
    return best


def by_patterns(lines: list[ChatLine], item_names: list[str],
                owner_names: set[str]) -> list[Draft]:
    """Extract without a model. Finds plainly-phrased orders, honestly."""
    drafts: list[Draft] = []
    for line in lines:
        low = line.text.lower()
        if line.sender in owner_names:
            continue                      # the shop's own replies are not orders
        when = _iso(line.when)

        amounts = [float(n.replace(",", ""))
                   for n in re.findall(r"\b(\d[\d,]{3,})\b", line.text)]

        if any(w in low for w in _PAID) and amounts:
            drafts.append(Draft(kind="payment", party=line.sender,
                                amount=max(amounts), when=when,
                                confidence="medium", evidence=line.text))
            continue

        if any(w in low for w in _BALANCE) and amounts:
            drafts.append(Draft(kind="balance", party=line.sender,
                                amount=max(amounts), when=when,
                                confidence="medium", evidence=line.text))
            continue

        # A question is never an order, however much it looks like one.
        if any(w in low for w in _ASKING):
            continue

        # Beyond that, a quantity next to one of the client's own item names is
        # an order on its own. Requiring a verb missed most of a real thread --
        # "10 bag DAP urgent", "40 bags cattle feed next week" -- because nobody
        # writes "I would like to place an order".

        # A message can carry more than one line: "20 bags urea and 5 gypsum".
        for chunk in re.split(r"\band\b|,|\+", line.text, flags=re.IGNORECASE):
            found = _match_item(chunk, item_names)
            if found is None:
                continue
            qty_match = _QTY.search(chunk)
            if qty_match is None:
                continue
            qty = float(qty_match.group(1))
            if qty <= 0 or qty > 10000:
                continue
            drafts.append(Draft(
                kind="order", party=line.sender, item=found[0], qty=qty,
                unit=(qty_match.group(2) or "").lower(), when=when,
                confidence="medium", evidence=line.text))

    # A thread restates an order as it is confirmed -- "20 bags urea beku", then
    # "ok send 20 bags urea and 5 gypsum". Counting both doubles it, and a
    # doubled order is a worse mistake than a missed one.
    seen: set[tuple] = set()
    unique = []
    for d in drafts:
        key = (d.kind, d.party.lower(), d.item.lower(), d.qty, d.amount)
        if key in seen:
            continue
        seen.add(key)
        unique.append(d)
    return unique


# --------------------------------------------------------------- the model path

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["drafts"],
    "properties": {
        "drafts": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["kind", "party", "item", "qty", "amount",
                             "confidence", "evidence"],
                "properties": {
                    "kind": {"type": "string", "enum": ["order", "payment", "balance"]},
                    "party": {"type": "string"},
                    "item": {"type": "string"},
                    "qty": {"type": "number"},
                    "amount": {"type": "number"},
                    "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                    "evidence": {"type": "string"},
                },
            },
        },
    },
}

SYSTEM = """You read WhatsApp threads from an Indian distributor and pull out
the business events. The messages mix English, Kannada and Hindi.

Rules:
1. Extract only what is actually stated. Never infer an order from a question
   about price, and never invent a quantity that is not written.
2. `item` must be copied from the supplied catalogue list, exactly. If the
   customer's wording does not clearly match a catalogue item, leave it blank
   and set confidence to "low".
3. Messages FROM the shop owner are replies, not orders. Only the customer
   orders.
4. `evidence` is the customer's message, verbatim, so a person can check you.
5. "beku"/"chahiye"/"bhejo" mean they want it. "ideya"/"stock ide" is asking
   whether it is available, which is not an order.
6. A payment mentions money that has already moved. An unpaid balance the
   customer mentions is kind "balance", not "payment"."""


def by_model(lines: list[ChatLine], item_names: list[str],
             owner_names: set[str], settings) -> tuple[list[Draft], str]:
    transcript = "\n".join(f"[{ln.when}] {ln.sender}: {ln.text}" for ln in lines)
    prompt = (f"Shop's own senders (their replies are not orders): "
              f"{', '.join(sorted(owner_names)) or 'You'}\n\n"
              f"Catalogue — `item` must be one of these exactly:\n"
              + "\n".join(f"- {n}" for n in item_names)
              + f"\n\nThread:\n{transcript}")

    answer = llm.ask(prompt, settings, system=SYSTEM, schema=SCHEMA)
    if not answer.ok or not answer.data:
        return [], answer.error or "Claude could not read the thread."

    drafts = []
    by_evidence = {ln.text: ln for ln in lines}
    for row in answer.data.get("drafts", []):
        evidence = str(row.get("evidence", ""))
        source = by_evidence.get(evidence)
        drafts.append(Draft(
            kind=str(row.get("kind", "order")),
            party=str(row.get("party", "")).strip(),
            item=str(row.get("item", "")).strip(),
            qty=float(row.get("qty") or 0),
            amount=float(row.get("amount") or 0),
            when=_iso(source.when) if source else "",
            confidence=str(row.get("confidence", "medium")),
            evidence=evidence,
        ))
    return drafts, ""


# -------------------------------------------------------------------- the door

def parse_chat(text: str, item_names: list[str], settings,
               owner_names: set[str] | None = None) -> ChatExtract:
    """Read a WhatsApp export. Tries Claude, falls back to patterns, never raises."""
    lines = read_lines(text)
    if not lines:
        return ChatExtract(False, error="That does not look like a WhatsApp export.",
                           needs_action="Export the chat from WhatsApp with "
                                        "“Without media” and upload the .txt file.")

    owner_names = owner_names or {"You", "you"}
    drafts, why = by_model(lines, item_names, owner_names, settings)
    if drafts:
        return ChatExtract(True, drafts=drafts, messages=len(lines),
                           method="Read by Claude")

    drafts = by_patterns(lines, item_names, owner_names)
    if drafts:
        return ChatExtract(
            True, drafts=drafts, messages=len(lines),
            method="Read by matching your item names — Claude was not available",
            error=why)

    return ChatExtract(False, messages=len(lines),
                       error=why or "No orders or payments were found in that thread.",
                       needs_action="Check the items mentioned are in your stock list.")


def to_csv(extract: ChatExtract, out: Path, rates: dict[str, float] | None = None) -> Path:
    """Write the orders as a sales CSV the unchanged engine can read.

    The same trick ``books.py`` uses: rather than teach the engine about chats,
    hand it a shape ``schema.py`` already recognises.
    """
    rates = rates or {}
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["Date", "Party Name", "Item Name", "Quantity", "Rate", "Amount"])
        for d in extract.orders:
            rate = rates.get(d.item, 0.0)
            w.writerow([d.when, d.party, d.item, d.qty, rate, round(d.qty * rate, 2)])
    return out
