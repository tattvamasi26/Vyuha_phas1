"""The one way out of the system.

Every message, every document, every receipt leaves Vyuha through this module.
Nothing else calls a send path — ``whatsapp.send`` and ``exports.send_email``
now refuse a caller that does not hold the key this module owns, so forgetting
the gate fails loudly at the boundary instead of quietly putting a wrong number
in front of a customer.

That refusal is the point. The architecture calls this a hard boundary rather
than a convention, and a convention is exactly what a comment saying "always go
through the gate" would be.

**Three dispositions, and why they differ.**

* ``AUTO`` — WhatsApp alerts to the business's own owner. An alert about an
  empty shelf is worth nothing tomorrow morning, and the blast radius of one
  wrong message to somebody who already knows their own stock is a phone call.
* ``DRAFT`` — every email, whatever it contains. Email is the channel that
  reaches accountants, banks and suppliers, where a wrong message is not a
  message but a document. A draft is written, stored, and shown; a human sends.
* ``APPROVAL`` — anything touching money leaving the business, or a regulatory
  filing. It waits. Only ``orchestrator.release()`` can let it go, and only
  after a named person approved it.

**The classification is on the action, not the channel.** A payment reminder is
money *arriving* and goes out on WhatsApp like any alert; a GST filing summary
is a regulatory document and waits, even though it would travel down the same
wire. Getting this backwards — gating by channel — is how a system ends up
either annoying people or filing something nobody read.

Queued and drafted items live in ``vyuha_data/outbox/<slug>.json`` so a restart
does not lose an approval somebody is halfway through, and so "what did we send
this client, and who released it" is answerable from disk.
"""

from __future__ import annotations

import secrets
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from . import atomic, ledger

REPO = Path(__file__).resolve().parent.parent
OUTBOX = REPO / "vyuha_data" / "outbox"

# --- dispositions ---------------------------------------------------------

AUTO = "auto"
DRAFT = "draft"
APPROVAL = "approval"

#: Statuses an item passes through. ``held`` and ``drafted`` both wait on a
#: person; they are separate because the person's job differs — one approves a
#: thing Vyuha wants to do, the other sends a thing Vyuha wrote.
QUEUED = "queued"
HELD = "held"
DRAFTED = "drafted"
SENT = "sent"
FAILED = "failed"
CANCELLED = "cancelled"

#: What kind of thing is going out. The disposition is decided from this and
#: nothing else, so a new caller has to say what it is doing rather than which
#: wire it wants.
KINDS = {
    "alert":     ("Stock and payment alerts", AUTO),
    "brief":     ("The daily brief", AUTO),
    "receipt":   ("A receipt for a sale just made", AUTO),
    "reminder":  ("A payment reminder to a customer", AUTO),
    "routine":   ("A scheduled routine job", AUTO),
    "test":      ("A connection test", AUTO),
    "report":    ("A statement or export by email", DRAFT),
    "invoice":   ("A tax invoice sent to a customer", DRAFT),
    "statement": ("A financial statement to a third party", DRAFT),
    "payment":   ("Money leaving the business", APPROVAL),
    "filing":    ("A regulatory return or filing", APPROVAL),
}

#: Email never sends itself, whatever the kind says. This is the one rule that
#: overrides the table above, and it is deliberately not expressible as a kind:
#: a caller must not be able to opt an email into sending by choosing a label.
EMAIL_IS_ALWAYS_A_DRAFT = True


def disposition(kind: str, channel: str, can_self_send: bool = True) -> str:
    """What should happen to this, before anybody looks at the payload.

    ``can_self_send`` is whether the channel has a provider behind it at all.
    Without one, ``AUTO`` is a lie: WhatsApp in link-only mode cannot deliver
    anything on its own, and a routine that reports failure every morning
    because of a setting is worse than one that honestly parks a tap-to-send
    draft. So an unprovisioned channel degrades to ``DRAFT`` rather than
    pretending it tried.
    """
    base = KINDS.get(kind, ("Unclassified", APPROVAL))[1]
    if base == APPROVAL:
        return APPROVAL
    if channel == "email" and EMAIL_IS_ALWAYS_A_DRAFT:
        return DRAFT
    if not can_self_send:
        return DRAFT
    return base



def _can_self_send(settings, channel: str) -> bool:
    """Is there a provider behind this channel that can deliver unattended?"""
    if channel == "whatsapp":
        return bool(getattr(settings, "whatsapp_live", False))
    if channel == "email":
        return bool(getattr(settings, "email_live", False))
    return False


# --- the key --------------------------------------------------------------

#: The capability that lets a caller reach a send path. Generated once per
#: process and held only here. ``whatsapp.py`` and ``exports.py`` check it, so a
#: route that calls them directly gets a ``PermissionError`` naming this module
#: rather than silently sending.
_KEY = secrets.token_hex(16)


def key() -> str:
    """The send key. Only ``gate`` and ``orchestrator`` have any business here."""
    return _KEY


def authorised(token: str) -> bool:
    return secrets.compare_digest(token or "", _KEY)


class NotAuthorised(PermissionError):
    """Raised by a send path reached without going through the gate."""


def require(token: str, what: str) -> None:
    if not authorised(token):
        raise NotAuthorised(
            f"{what} was called without the gate's key. Every outbound action "
            f"goes through gate.submit() — see vyuha_platform/gate.py."
        )


# --- the record -----------------------------------------------------------


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


@dataclass
class Outbound:
    """One thing trying to leave the system."""

    id: str
    kind: str
    channel: str                 # whatsapp | email
    to: str
    subject: str = ""
    body: str = ""
    status: str = QUEUED
    disposition: str = AUTO
    created: str = field(default_factory=_now)
    #: Set when it actually left, or when it was refused.
    settled: str = ""
    #: Who released it. Empty for anything that never needed a person.
    approved_by: str = ""
    detail: str = ""
    #: Delivery attempts so far. A counter rather than something inferred from
    #: the detail text, because prose is not a data structure.
    tries: int = 0
    attachments: list = field(default_factory=list)
    #: Which routine or agent produced it, for the audit trail.
    source: str = ""

    @property
    def waiting(self) -> bool:
        return self.status in (HELD, DRAFTED)

    @property
    def label(self) -> str:
        return KINDS.get(self.kind, ("Unclassified", APPROVAL))[0]


# --- storage --------------------------------------------------------------


def _path(slug: str) -> Path:
    return OUTBOX / f"{slug}.json"


def load(slug: str) -> list[Outbound]:
    rows = atomic.read_json(_path(slug), [])
    out = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        fields = {k: v for k, v in r.items() if k in Outbound.__annotations__}
        fields.setdefault("id", secrets.token_hex(6))
        fields.setdefault("kind", "alert")
        fields.setdefault("channel", "whatsapp")
        fields.setdefault("to", "")
        out.append(Outbound(**fields))
    return out


def save(slug: str, items: list[Outbound]) -> None:
    OUTBOX.mkdir(parents=True, exist_ok=True)
    # Keep the tail bounded — this is an outbox, not the audit log. `ledger`
    # holds the permanent record of what was sent.
    atomic.write_json(_path(slug), [asdict(i) for i in items[-400:]])


def get(slug: str, item_id: str) -> Outbound | None:
    return next((i for i in load(slug) if i.id == item_id), None)


def waiting(slug: str) -> list[Outbound]:
    """Everything a person still has to do something about, newest first."""
    return sorted([i for i in load(slug) if i.waiting],
                  key=lambda i: i.created, reverse=True)


def history(slug: str, limit: int = 60) -> list[Outbound]:
    return sorted(load(slug), key=lambda i: i.created, reverse=True)[:limit]


# --- the only entry point -------------------------------------------------


def submit(client, settings, *, kind: str, channel: str, to: str, body: str,
           subject: str = "", attachments: list | None = None,
           source: str = "") -> Outbound:
    """Offer something to the outside world. Returns what happened to it.

    This is the *only* function in the codebase that may cause a message to
    leave. It classifies first, sends only what is allowed to send itself, and
    parks everything else where a person will find it.
    """
    item = Outbound(
        id=secrets.token_hex(6), kind=kind, channel=channel, to=to,
        subject=subject, body=body, attachments=list(attachments or []),
        source=source,
    )
    item.disposition = disposition(kind, channel, _can_self_send(settings, channel))

    if item.disposition == APPROVAL:
        item.status = HELD
        item.detail = "Waiting for approval — this touches money or a filing."
    elif item.disposition == DRAFT:
        item.status = DRAFTED
        item.detail = ("Written and saved. Email never sends itself."
                       if channel == "email" else
                       "Written and saved. No WhatsApp provider is connected, "
                       "so this waits for one tap.")
    else:
        _deliver(item, client, settings)

    items = load(client.slug)
    items.append(item)
    save(client.slug, items)
    _log(item, client)
    return item


def _deliver(item: Outbound, client, settings) -> None:
    """Actually put it on the wire. Never called from outside this module."""
    from . import exports, whatsapp

    item.tries += 1
    try:
        if item.channel == "whatsapp":
            result = whatsapp.send(settings, item.to, item.body, _token=_KEY)
            item.status = SENT if result.ok else FAILED
            item.detail = result.detail
            if not result.ok and getattr(result, "needs_action", ""):
                item.detail += f" {result.needs_action}"
        elif item.channel == "email":
            ok, detail = exports.send_email(
                settings, item.to, item.subject, item.body,
                item.attachments, _token=_KEY)
            item.status = SENT if ok else FAILED
            item.detail = detail
        else:
            item.status = FAILED
            item.detail = f"No sender for channel '{item.channel}'."
    except NotAuthorised:                                    # pragma: no cover
        raise
    except Exception as exc:                                 # noqa: BLE001
        # A send path that raises must not lose the record of the attempt.
        item.status = FAILED
        item.detail = f"{type(exc).__name__}: {exc}"
    item.settled = _now()


def _log(item: Outbound, client) -> None:
    kind = {
        SENT: "alert.sent", FAILED: "alert.send_failed",
        HELD: "outbound.held", DRAFTED: "outbound.drafted",
        CANCELLED: "outbound.cancelled",
    }.get(item.status, "outbound.queued")
    ledger.log(kind, f"{item.label} → {item.to or 'nobody'}",
               client=client, channel=item.channel)


# --- release, which only the orchestrator may call ------------------------


def release(client, settings, item_id: str, *, approved_by: str,
            _token: str = "") -> tuple[bool, str]:
    """Let a held item go. Requires the key, so routes cannot call it.

    ``orchestrator.approve()`` is the sanctioned caller. Going through it rather
    than here is what keeps the audit trail honest about who released what.
    """
    require(_token, "gate.release")
    items = load(client.slug)
    item = next((i for i in items if i.id == item_id), None)
    if item is None:
        return False, "That item is no longer in the outbox."
    if item.status not in (HELD, DRAFTED):
        return False, f"Already {item.status}."

    item.approved_by = approved_by
    _deliver(item, client, settings)
    save(client.slug, items)
    _log(item, client)
    return item.status == SENT, item.detail


def mark_sent(client, item_id: str, *, by: str) -> tuple[bool, str]:
    """Record that a person sent this themselves.

    With no provider connected, a WhatsApp draft cannot be delivered by the
    machine — the operator taps a ``wa.me`` link and sends it from their own
    phone. Trying to "release" it would attempt an impossible send and report a
    failure for something that actually went out, which is the worst of both.
    So the tap-to-send path records the truth instead: it left, and a named
    person is the one who sent it.

    Needs no key. Nothing is transmitted here; this only writes down what
    already happened outside the system.
    """
    items = load(client.slug)
    item = next((i for i in items if i.id == item_id), None)
    if item is None:
        return False, "That item is no longer in the outbox."
    if item.status not in (HELD, DRAFTED):
        return False, f"Already {item.status}."
    item.status = SENT
    item.settled = _now()
    item.approved_by = by
    item.detail = "Sent by hand from the operator's own WhatsApp."
    save(client.slug, items)
    _log(item, client)
    return True, "Marked as sent."


def cancel(client, item_id: str, *, why: str = "") -> tuple[bool, str]:
    """Refuse something rather than sending it. Needs no key — declining to act
    is always allowed, and a person who cannot cancel will send instead."""
    items = load(client.slug)
    item = next((i for i in items if i.id == item_id), None)
    if item is None:
        return False, "That item is no longer in the outbox."
    if item.status not in (HELD, DRAFTED):
        return False, f"Already {item.status}."
    item.status = CANCELLED
    item.settled = _now()
    item.detail = why or "Cancelled without sending."
    save(client.slug, items)
    _log(item, client)
    return True, "Cancelled."


def counts(slug: str) -> dict:
    """For the nav badge — a number somebody should act on."""
    items = load(slug)
    return {
        "held": sum(1 for i in items if i.status == HELD),
        "drafted": sum(1 for i in items if i.status == DRAFTED),
        "waiting": sum(1 for i in items if i.waiting),
        "sent": sum(1 for i in items if i.status == SENT),
        "failed": sum(1 for i in items if i.status == FAILED),
    }
