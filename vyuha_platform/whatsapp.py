"""WhatsApp delivery — real senders, with an honest fallback.

Three providers behind one ``send()``:

* ``twilio`` — the fastest route to a message actually arriving. Twilio's public
  WhatsApp sandbox works the moment the recipient sends the join code to the
  sandbox number, with no business verification and no template approval. This
  is what to use for testing.
* ``meta``   — the WhatsApp Cloud API, for production. Note the hard rule Meta
  enforces: a *free-form* text may only be sent inside the 24-hour window after
  the customer last messaged you. Outside it you must send an approved template.
  ``settings.meta_template`` selects one; leaving it blank means free-form, which
  will be rejected with error 131047 outside the window. The failure is reported,
  never swallowed.
* ``link``   — no credentials at all: build a wa.me deep link and let the operator
  tap send. Always available, and the honest default.

Delivery attempts are returned as ``SendResult`` so the caller can record them in
the activity ledger whether they succeeded or not.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import httpx

from . import channels

META_API = "https://graph.facebook.com/v21.0"
TWILIO_API = "https://api.twilio.com/2010-04-01"
TIMEOUT = 20.0


@dataclass
class SendResult:
    ok: bool
    provider: str
    detail: str = ""
    message_id: str = ""
    link: str = ""
    needs_action: str = ""          # what the human must do for this to work
    meta: dict = field(default_factory=dict)


def _link_result(to: str, text: str, why: str, action: str = "") -> SendResult:
    return SendResult(
        ok=False, provider="link", detail=why,
        link=channels.whatsapp_link(to, text),
        needs_action=action or "Tap the WhatsApp button to send it yourself.",
    )


def _send_meta(settings, to: str, text: str) -> SendResult:
    number = channels.normalise_phone(to)
    url = f"{META_API}/{settings.meta_phone_number_id}/messages"
    headers = {"Authorization": f"Bearer {settings.meta_token}",
               "Content-Type": "application/json"}

    if settings.meta_template:
        payload = {
            "messaging_product": "whatsapp", "to": number, "type": "template",
            "template": {
                "name": settings.meta_template,
                "language": {"code": "en"},
                "components": [{"type": "body",
                                "parameters": [{"type": "text", "text": text[:1024]}]}],
            },
        }
    else:
        payload = {"messaging_product": "whatsapp", "to": number,
                   "type": "text", "text": {"preview_url": False, "body": text[:4096]}}

    try:
        r = httpx.post(url, headers=headers, json=payload, timeout=TIMEOUT)
    except httpx.HTTPError as exc:
        return _link_result(to, text, f"Could not reach Meta: {exc}")

    if r.status_code < 300:
        body = r.json()
        mid = (body.get("messages") or [{}])[0].get("id", "")
        return SendResult(ok=True, provider="meta", detail="Delivered to Meta.",
                          message_id=mid, meta=body)

    try:
        err = r.json().get("error", {})
        code, msg = err.get("code"), err.get("message", r.text[:200])
    except (json.JSONDecodeError, ValueError):
        code, msg = r.status_code, r.text[:200]

    action = ""
    if code == 131047 or "24" in str(msg):
        action = ("Outside the 24-hour window Meta only accepts an approved template. "
                  "Set a template name in Settings, or have the client message you first.")
    elif code in (190, 401):
        action = "The Meta access token is invalid or expired. Regenerate it."
    return _link_result(to, text, f"Meta rejected it ({code}): {msg}", action)


def _send_twilio(settings, to: str, text: str) -> SendResult:
    number = channels.normalise_phone(to)
    url = f"{TWILIO_API}/Accounts/{settings.twilio_sid}/Messages.json"
    data = {"From": settings.twilio_from, "To": f"whatsapp:+{number}", "Body": text[:1500]}

    try:
        r = httpx.post(url, data=data, auth=(settings.twilio_sid, settings.twilio_token),
                       timeout=TIMEOUT)
    except httpx.HTTPError as exc:
        return _link_result(to, text, f"Could not reach Twilio: {exc}")

    if r.status_code < 300:
        body = r.json()
        return SendResult(ok=True, provider="twilio",
                          detail=f"Queued by Twilio ({body.get('status', 'sent')}).",
                          message_id=body.get("sid", ""), meta=body)

    try:
        err = r.json()
        code, msg = err.get("code"), err.get("message", "")
    except (json.JSONDecodeError, ValueError):
        code, msg = r.status_code, r.text[:200]

    action = ""
    if code == 63015 or "sandbox" in str(msg).lower():
        action = ("This number has not joined the Twilio sandbox. Send the join code "
                  "from that phone to the sandbox number once, then retry.")
    elif code in (20003,):
        action = "Twilio credentials rejected. Check the SID and auth token."
    return _link_result(to, text, f"Twilio rejected it ({code}): {msg}", action)


def send(settings, to: str, text: str) -> SendResult:
    """Send ``text`` to ``to``. Never raises — failures come back as SendResult."""
    if not channels.normalise_phone(to):
        return SendResult(ok=False, provider="none", detail="No WhatsApp number on file.",
                          needs_action="Add a WhatsApp number for this client.")
    if not settings.whatsapp_live:
        return _link_result(
            to, text, "No WhatsApp provider configured — deep link only.",
            "Connect Twilio or Meta in Settings to send automatically.",
        )
    if settings.whatsapp_provider == "meta":
        return _send_meta(settings, to, text)
    if settings.whatsapp_provider == "twilio":
        return _send_twilio(settings, to, text)
    return _link_result(to, text, "Provider set to link-only.")


TEST_MESSAGE = (
    "✅ *Vyuha is connected.*\n\n"
    "This is a test from your Vyuha workspace. Stock, dead-inventory and "
    "overdue-payment alerts will arrive on this number.\n\n"
    "_Reply STOP at any time to switch them off._"
)


def send_test(settings, to: str) -> SendResult:
    """Fire a connection test at onboarding, so a wrong number is caught on day one."""
    return send(settings, to, TEST_MESSAGE)
