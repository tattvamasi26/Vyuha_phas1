"""Alert renderers — one per delivery channel.

Pure functions ``Insights -> str``. No I/O, no network, no sending. They sit
beside ``report.render()`` rather than inside a new pipeline: the engine
produces one ``Insights`` and every channel is a different view of it.

Delivery is a deep link, not an API call. ``wa.me`` opens WhatsApp with the
message pre-filled and the founder taps send. That needs no Meta Business
account, no BSP and no template pre-approval, and it is the honest shape of a
founder-operated service. Swapping in the Cloud API later means adding a
sender here; the renderers do not change.
"""

from __future__ import annotations

import re
import urllib.parse

from vyuha import fmt
from vyuha.analyze import Insights

WHATSAPP_LIMIT = 1024

_RANK = {"critical": 0, "warning": 1, "info": 2}
_MARK = {"critical": "‼", "warning": "❗", "info": "ℹ"}

#: How many entities each channel shows before collapsing the tail.
_KEEP_WHATSAPP = 3


def money(amount: float | None) -> str:
    return fmt.rupees(amount)


def ordered(insights: Insights) -> list:
    return sorted(insights.alerts, key=lambda a: _RANK.get(a.severity, 9))


def _clip(items: list[str], keep: int) -> str:
    if len(items) <= keep:
        return ", ".join(items)
    return ", ".join(items[:keep]) + f" …and {len(items) - keep} more"


def as_whatsapp(insights: Insights, client: str = "", limit: int = WHATSAPP_LIMIT) -> str:
    """Phone-shaped. Sheds detail, then whole alerts, to stay under the cap."""
    when = insights.generated_at.strftime("%d %b")
    header = f"*Vyuha brief — {client or insights.source} — {when}*"

    blocks: list[list[str]] = []
    for alert in ordered(insights):
        block = [f"{_MARK.get(alert.severity, '•')} *{alert.title}*"]
        if alert.entities:
            block.append(f"   {_clip(alert.entities, _KEEP_WHATSAPP)}")
        blocks.append(block)

    def assemble(bs: list[list[str]], note: str = "") -> str:
        body = "\n\n".join("\n".join(b) for b in bs)
        return f"{header}\n\n{body}" + (f"\n\n{note}" if note else "")

    text = assemble(blocks)
    if len(text) <= limit:
        return text

    # 1. drop the entity lines (keep every headline) before dropping any alert.
    stripped = [[b[0]] for b in blocks]
    text = assemble(stripped)
    if len(text) <= limit:
        return text

    # 2. still too long: shed the lowest-severity alerts, keeping the count honest.
    kept = list(stripped)
    while kept and len(assemble(kept, f"…and {len(blocks) - len(kept)} more in the dashboard.")) > limit:
        kept.pop()
    return assemble(kept, f"…and {len(blocks) - len(kept)} more in the dashboard.")


def as_email(insights: Insights, client: str = "") -> str:
    """Fuller. No cap, so nothing is truncated."""
    when = insights.generated_at.strftime("%d %b %Y")
    out = [f"Vyuha brief — {client or insights.source}", f"Generated {when}", "=" * 56, ""]
    for alert in ordered(insights):
        out.append(f"[{alert.severity.upper()}] {alert.title}")
        out.append(f"  {alert.detail}")
        out += [f"    - {e}" for e in alert.entities]
        out.append("")
    out += [
        "-" * 56,
        f"Revenue: {money(insights.sales.get('revenue', 0))}    "
        f"Orders: {insights.sales.get('orders', 0)}",
        f"Stock value: {money(insights.stock.get('value', 0))}    "
        f"Outstanding: {money(insights.receivables.get('total', 0))}",
    ]
    return "\n".join(out)


def normalise_phone(phone: str, default_cc: str = "91") -> str:
    """Digits only, country code prefixed. wa.me rejects '+', spaces and dashes."""
    digits = re.sub(r"\D", "", phone or "")
    if not digits:
        return ""
    if digits.startswith("00"):
        digits = digits[2:]
    if len(digits) == 10:                    # bare Indian mobile
        digits = default_cc + digits
    return digits


def whatsapp_link(phone: str, text: str) -> str:
    """A wa.me deep link that opens WhatsApp with the brief already typed."""
    number = normalise_phone(phone)
    encoded = urllib.parse.quote(text, safe="")
    return f"https://wa.me/{number}?text={encoded}" if number else f"https://wa.me/?text={encoded}"


def mailto_link(email: str, subject: str, body: str) -> str:
    query = urllib.parse.urlencode({"subject": subject, "body": body}, quote_via=urllib.parse.quote)
    return f"mailto:{email}?{query}"
