"""Number formatting shared by every output channel.

Indian digit grouping is channel-agnostic; the currency symbol is not. HTML
wants the entity ``&#8377;``, a WhatsApp message wants a literal ``₹``, and a
cp1252 console wants ``Rs.``. So this module returns the grouped digits and the
sign, and each renderer supplies its own symbol.
"""

from __future__ import annotations

RUPEE_HTML = "&#8377;"
RUPEE_TEXT = "₹"


def group(amount: float) -> str:
    """1234567 -> '12,34,567' (last three digits, then pairs)."""
    whole = f"{abs(float(amount)):.0f}"
    if len(whole) <= 3:
        return whole
    head, tail = whole[:-3], whole[-3:]
    pieces = []
    while len(head) > 2:
        pieces.insert(0, head[-2:])
        head = head[:-2]
    if head:
        pieces.insert(0, head)
    return ",".join(pieces) + "," + tail


def sign_of(amount: float) -> str:
    return "-" if float(amount) < 0 else ""


def rupees(amount: float | None, symbol: str = RUPEE_TEXT, dash: str = "-") -> str:
    """Full amount: ``₹12,34,567``."""
    if amount is None:
        return dash
    return f"{sign_of(amount)}{symbol}{group(amount)}"


def rupees_short(amount: float | None, symbol: str = RUPEE_TEXT, dash: str = "-") -> str:
    """Abbreviated amount: ``₹2.10 L``, ``₹1.20 Cr``."""
    if amount is None:
        return dash
    value, sign = abs(float(amount)), sign_of(amount)
    if value >= 1_00_00_000:
        return f"{sign}{symbol}{value / 1_00_00_000:.2f} Cr"
    if value >= 1_00_000:
        return f"{sign}{symbol}{value / 1_00_000:.2f} L"
    if value >= 1_000:
        return f"{sign}{symbol}{value / 1_000:.1f} K"
    return f"{sign}{symbol}{value:,.0f}"
