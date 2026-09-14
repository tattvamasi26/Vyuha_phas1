"""The Jinja2 environment: money and time filters, the icon helper, one render function."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from fastapi.templating import Jinja2Templates
from markupsafe import Markup, escape

from vyuha import fmt

HERE = Path(__file__).resolve().parent
STATIC = HERE.parent / "static" / "app"

templates = Jinja2Templates(directory=str(HERE / "templates"))
env = templates.env
env.trim_blocks = True
env.lstrip_blocks = True


# ----------------------------------------------------------------- money

def money(value, dash: str = "—") -> str:
    """₹12,34,567 — Indian grouping, the full figure."""
    if value is None or value == "":
        return dash
    return fmt.rupees(float(value), symbol="₹", dash=dash)


def money_short(value, dash: str = "—") -> str:
    """₹2.18 L · ₹1.20 Cr — for tiles, where width is scarce."""
    if value is None or value == "":
        return dash
    return fmt.rupees_short(float(value), symbol="₹", dash=dash)


def lakh(value) -> str:
    """₹2.18 lakh — the way an owner says it out loud, for sentences."""
    v = float(value or 0)
    if abs(v) >= 1_00_00_000:
        return f"₹{v / 1_00_00_000:.2f} crore"
    if abs(v) >= 1_00_000:
        return f"₹{v / 1_00_000:.2f} lakh"
    return fmt.rupees(v, symbol="₹")


def pct(value) -> str:
    return f"{float(value or 0):+.0f}%"


def qty(value) -> str:
    return f"{float(value or 0):g}"


# ------------------------------------------------------------------ time

def _parse(value) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        try:
            return datetime.combine(date.fromisoformat(text[:10]), datetime.min.time())
        except ValueError:
            return None


def ago(value) -> str:
    """"3 min ago", "yesterday", "12 Sep" — relative while it is recent."""
    then = _parse(value)
    if then is None:
        return ""
    if then.tzinfo is not None:
        then = then.replace(tzinfo=None)
    secs = (datetime.now() - then).total_seconds()
    if secs < 60:
        return "just now"
    if secs < 3600:
        return f"{int(secs // 60)} min ago"
    if secs < 86400 and then.date() == date.today():
        return f"{int(secs // 3600)} h ago"
    days = (date.today() - then.date()).days
    if days == 1:
        return "yesterday"
    if 1 < days < 7:
        return f"{days} days ago"
    return then.strftime("%d %b" if then.year == date.today().year else "%d %b %Y")


def nice_date(value, pattern: str = "%d %b %Y") -> str:
    then = _parse(value)
    return then.strftime(pattern) if then else (str(value) if value else "")


# ----------------------------------------------------------------- icons

def icon(name: str, cls: str = "size-5", label: str = "") -> Markup:
    """A Lucide icon from the sprite. Decorative unless given a label."""
    aria = (f'role="img" aria-label="{escape(label)}"' if label
            else 'aria-hidden="true" focusable="false"')
    return Markup(
        f'<svg class="icon {escape(cls)}" {aria} fill="none" stroke="currentColor" '
        f'stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">'
        f'<use href="/static/app/icons.svg#i-{escape(name)}"></use></svg>')


def asset_v() -> str:
    """Cache-buster for app.css — its build time."""
    try:
        return str(int((STATIC / "app.css").stat().st_mtime))
    except OSError:
        return "0"


env.filters.update(money=money, money_short=money_short, lakh=lakh, pct=pct, qty=qty,
                   ago=ago, date=nice_date)
env.globals.update(icon=icon, asset_v=asset_v)


def render(request, name: str, context: dict | None = None, *, status: int = 200,
           headers: dict | None = None):
    return templates.TemplateResponse(request, name, context or {}, status_code=status,
                                      headers=headers)
