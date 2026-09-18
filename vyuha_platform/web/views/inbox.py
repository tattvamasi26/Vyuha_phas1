"""Inbox — what is waiting to go out, what went, and who hears about what.

Everything leaves through ``gate.submit``: an alert to the business's own number sends
itself, every email is a draft, and anything touching money or a filing waits for a named
person. This section is that queue made visible, plus the scheduled briefs.
"""

from __future__ import annotations

from ... import (books, channels, config, gate, invoice, money, notify, people,
                 routines as routines_mod)

#: How each disposition reads. "Waiting for you to send" and "held for approval" are
#: different jobs; one word for both would flatten them into "pending".
DISPO = {
    gate.APPROVAL: ("Held for approval", "bad",
                    "This touches money or a filing. Nothing leaves until you release it."),
    gate.DRAFT: ("Waiting for you to send", "warn", "Written and saved. Nothing was sent."),
    gate.AUTO: ("Sent itself", "ok", "Worthless by tomorrow morning, so it went straight out."),
}

STATUS_TONE = {gate.SENT: "ok", gate.HELD: "bad", gate.DRAFTED: "warn",
               gate.FAILED: "bad", gate.CANCELLED: "dim", gate.QUEUED: "dim"}


def _short(v: float) -> str:
    from ..templating import money_short
    return money_short(v)


def _state(client) -> dict:
    """What the notification agent reads — loaded once, as the orchestrator does."""
    return {"book": books.load(client.slug), "ledger": money.load(client.slug),
            "org": people.load(client.slug), "invoices": invoice.load_all(client.slug)}


def waiting(client, account, request) -> dict:
    counts = gate.counts(client.slug)
    settings = config.load()
    rows = []
    for item in gate.waiting(client.slug):
        rows.append({
            "i": item,
            "dispo": DISPO.get(item.disposition, DISPO[gate.DRAFT]),
            "wa": (channels.whatsapp_link(item.to, item.body)
                   if item.channel == "whatsapp" and item.to else ""),
        })
    return {
        "rows": rows, "counts": counts,
        "whatsapp_live": settings.whatsapp_live, "email_live": settings.email_live,
        "stats": [
            {"label": "Waiting on you", "value": str(counts["waiting"]), "icon": "inbox",
             "sub": "drafts and approvals", "tone": "warn" if counts["waiting"] else ""},
            {"label": "Held for approval", "value": str(counts["held"]), "icon": "lock",
             "sub": "money or a filing", "tone": "bad" if counts["held"] else ""},
            {"label": "Drafted", "value": str(counts["drafted"]), "icon": "square-pen",
             "sub": "written, not sent"},
            {"label": "Sent", "value": str(counts["sent"]), "icon": "send",
             "sub": "all time"},
        ],
    }


def sent(client, account, request) -> dict:
    items = gate.history(client.slug, 60)
    return {"items": items, "tones": STATUS_TONE, "counts": gate.counts(client.slug)}


def brief(client, account, request) -> dict:
    """Today's alerts as one message. The same text on WhatsApp and in the email."""
    settings = config.load()
    run = client.latest
    alerts = (run.alerts or []) if (run and run.status == "ok") else []
    headline = f"{len(alerts)} thing{'' if len(alerts) == 1 else 's'} to know"
    lines = [f"*{client.name}* — {headline}", ""]
    for a in alerts[:5]:
        mark = {"critical": "‼️", "warning": "⚠️"}.get(a.get("severity", ""), "•")
        lines.append(f"{mark} {a.get('title', '')}")
        if a.get("detail"):
            lines.append(f"   {a['detail']}")
    text = "\n".join(lines)[:1024]
    subject = f"{client.name} — {headline}"
    return {
        "alerts": alerts, "text": text, "subject": subject,
        "phone": client.phone, "email": client.email,
        "whatsapp_live": settings.whatsapp_live,
        "wa": channels.whatsapp_link(client.phone, text) if client.phone else "",
    }


def rules(client, account, request) -> dict:
    """Who Vyuha would tell, before it tells them."""
    state = _state(client)
    rows = notify.preview(client, state)
    org = state["org"]
    with_phone = [s for s in org.staff if s.active and s.phone]
    return {
        "rows": rows,
        "history": notify.history(client.slug, 30),
        "audiences": notify.AUDIENCES,
        "reachable": len(with_phone),
        "staff_count": len([s for s in org.staff if s.active]),
        "own_number": client.phone,
    }


def routines(client, account, request) -> dict:
    org = people.load(client.slug)
    return {
        "routines": routines_mod.load(client.slug),
        "sections": routines_mod.SECTIONS,
        "days": routines_mod.DAYS,
        "role_sections": routines_mod.ROLE_SECTIONS,
        "staff": [s for s in org.staff if s.active and s.phone],
        "own_number": client.phone,
    }
