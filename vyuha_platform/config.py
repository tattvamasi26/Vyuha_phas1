"""Runtime settings and credentials.

Read from ``vyuha_data/config.json`` first, then environment variables. Nothing
secret is ever written into the registry or a run record, and the settings page
only ever renders a masked form of a key.

These are **deployment-level**: one WhatsApp sender, one SMTP account, one
Claude key for the machine. Anything that varies per logged-in account lives on
``auth.Account`` instead.

Every capability degrades rather than crashes when its credentials are absent:
WhatsApp falls back to a wa.me deep link, vision ingestion falls back to a clear
"cannot read this" message. That is deliberate — the platform has to stay usable
on a laptop with no accounts set up.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from .store import DATA

CONFIG_PATH = DATA / "config.json"


def _env(*names: str, default: str = "") -> str:
    for n in names:
        v = os.environ.get(n)
        if v:
            return v.strip()
    return default


@dataclass
class Settings:
    # --- WhatsApp -----------------------------------------------------------
    # "link"  : build a wa.me deep link, the operator taps send (no account)
    # "meta"  : WhatsApp Cloud API   (needs a template for proactive sends)
    # "twilio": Twilio WhatsApp      (sandbox works immediately for testing)
    whatsapp_provider: str = "link"
    meta_token: str = ""
    meta_phone_number_id: str = ""
    meta_template: str = ""              # blank = send free-form (24h window only)
    twilio_sid: str = ""
    twilio_token: str = ""
    twilio_from: str = "whatsapp:+14155238886"   # Twilio's public sandbox number

    # --- Vision / OCR for images, scans and handwriting ---------------------
    anthropic_key: str = ""
    vision_model: str = "claude-opus-5"

    # --- Email --------------------------------------------------------------
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""

    # NOTE: ``install`` / ``org_name`` / ``tenant_slug`` used to live here, back
    # when one machine meant one workspace. They now live on ``auth.Account``,
    # because a single deployment serves many accounts and the operator/tenant
    # fork belongs to whoever is logged in, not to the server. What remains here
    # is deployment-level: the credentials the machine sends messages with.

    secret_fields: tuple = field(
        default=("meta_token", "twilio_token", "anthropic_key", "smtp_password"),
        repr=False,
    )

    # -- capability probes ---------------------------------------------------
    @property
    def whatsapp_live(self) -> bool:
        """True when a message can actually leave the machine."""
        if self.whatsapp_provider == "meta":
            return bool(self.meta_token and self.meta_phone_number_id)
        if self.whatsapp_provider == "twilio":
            return bool(self.twilio_sid and self.twilio_token and self.twilio_from)
        return False

    @property
    def vision_live(self) -> bool:
        return bool(self.anthropic_key)

    @property
    def email_live(self) -> bool:
        return bool(self.smtp_host and self.smtp_from)


def _defaults_from_env() -> dict:
    return {
        "whatsapp_provider": _env("VYUHA_WHATSAPP_PROVIDER", default="link"),
        "meta_token": _env("VYUHA_META_TOKEN", "WHATSAPP_TOKEN"),
        "meta_phone_number_id": _env("VYUHA_META_PHONE_ID", "WHATSAPP_PHONE_NUMBER_ID"),
        "meta_template": _env("VYUHA_META_TEMPLATE"),
        "twilio_sid": _env("VYUHA_TWILIO_SID", "TWILIO_ACCOUNT_SID"),
        "twilio_token": _env("VYUHA_TWILIO_TOKEN", "TWILIO_AUTH_TOKEN"),
        "anthropic_key": _env("VYUHA_ANTHROPIC_KEY", "ANTHROPIC_API_KEY"),
        "smtp_host": _env("VYUHA_SMTP_HOST"),
        "smtp_user": _env("VYUHA_SMTP_USER"),
        "smtp_password": _env("VYUHA_SMTP_PASSWORD"),
        "smtp_from": _env("VYUHA_SMTP_FROM"),
    }


_ALLOWED = {f.name for f in fields(Settings)} - {"secret_fields"}


def load() -> Settings:
    data = {k: v for k, v in _defaults_from_env().items() if v}
    if CONFIG_PATH.exists():
        try:
            saved = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            data.update({k: v for k, v in saved.items() if k in _ALLOWED})
        except (json.JSONDecodeError, OSError):
            pass
    data = {k: v for k, v in data.items() if k in _ALLOWED}
    if "smtp_port" in data:
        try:
            data["smtp_port"] = int(data["smtp_port"])
        except (TypeError, ValueError):
            data.pop("smtp_port")
    return Settings(**data)


def save(settings: Settings) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    row = {k: v for k, v in asdict(settings).items() if k in _ALLOWED}
    CONFIG_PATH.write_text(json.dumps(row, indent=2), encoding="utf-8")


def mask(value: str) -> str:
    """Never render a full credential back into a page."""
    if not value:
        return ""
    if len(value) <= 8:
        return "•" * len(value)
    return f"{value[:4]}{'•' * 12}{value[-4:]}"
