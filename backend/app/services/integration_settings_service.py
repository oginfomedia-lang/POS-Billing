"""Payment and WhatsApp credentials entered by the admin (Settings → Integrations) instead of backend/.env.

Values are kept in system_settings as "int.<name>"; secrets are encrypted (utils/crypto.py) and never sent
back to the browser. A field not saved in the app falls back to the .env value (current_app.config), so
older installs keep working.
"""
from __future__ import annotations

from dataclasses import dataclass

from flask import current_app

from app.models.user import User
from app.repositories.settings_repository import SettingsRepository
from app.services import audit_service
from app.utils.crypto import decrypt, encrypt
from app.utils.transactions import transaction

KEY_PREFIX = "int."


@dataclass(frozen=True)
class Field:
    section: str  # razorpay / paytm / whatsapp
    kind: str = "str"  # str / bool / int
    secret: bool = False


FIELDS: dict[str, Field] = {
    "RAZORPAY_KEY_ID": Field("razorpay"),
    "RAZORPAY_KEY_SECRET": Field("razorpay", secret=True),
    "RAZORPAY_POS_BASE_URL": Field("razorpay"),
    "RAZORPAY_POS_USERNAME": Field("razorpay"),
    "RAZORPAY_POS_APP_KEY": Field("razorpay", secret=True),
    "RAZORPAY_MOCK": Field("razorpay", "bool"),
    "UPI_QR_EXPIRY_SECONDS": Field("razorpay", "int"),
    # Saved for the Paytm card machine connection, which isn't built yet: nothing reads these today.
    "PAYTM_MID": Field("paytm"),
    "PAYTM_CLIENT_ID": Field("paytm"),
    "PAYTM_MERCHANT_KEY": Field("paytm", secret=True),
    "PAYTM_BASE_URL": Field("paytm"),
    "PAYTM_MOCK": Field("paytm", "bool"),
    "WHATSAPP_TOKEN": Field("whatsapp", secret=True),
    "WHATSAPP_PHONE_NUMBER_ID": Field("whatsapp"),
    "WHATSAPP_TEMPLATE_NAME": Field("whatsapp"),
    "WHATSAPP_EBILL_TEMPLATE_NAME": Field("whatsapp"),
    "WHATSAPP_TEMPLATE_LANG": Field("whatsapp"),
    "WHATSAPP_MOCK": Field("whatsapp", "bool"),
}
MOCK_FIELDS = {name for name in FIELDS if name.endswith("_MOCK")}


def _db_key(name: str) -> str:
    return KEY_PREFIX + name.lower()


def _saved() -> dict[str, str]:
    """{name: stored text} for fields saved in the app. Read fresh each time (a tiny table), so a change
    applies at once in every process: server, scheduled jobs and the e-bill background thread."""
    rows = SettingsRepository().all()
    return {n: rows[_db_key(n)] for n in FIELDS if _db_key(n) in rows}


def _parse(field: Field, text: str):
    if field.kind == "bool":
        return text == "1"
    if field.kind == "int":
        return int(text)
    return text


def value(name: str):
    """The value the gateways use: saved in the app, else from .env. Tests always run in mock mode."""
    if name in MOCK_FIELDS and current_app.testing:
        return True
    field = FIELDS[name]
    stored = _saved().get(name)
    if stored is None:
        return current_app.config.get(name)
    if field.secret:
        return decrypt(stored) or ""  # unreadable (SECRET_KEY changed) = not set
    return _parse(field, stored)


def public_view() -> dict[str, dict[str, dict]]:
    """What the admin screen may see, by section. Secrets: only whether one is set, never the value."""
    saved = _saved()
    out: dict[str, dict[str, dict]] = {}
    for name, field in FIELDS.items():
        stored = saved.get(name)
        if field.secret:
            if stored is not None:
                readable = decrypt(stored) is not None
                entry = {"set": readable, "unreadable": not readable, "from_env": False}
            else:
                entry = {"set": bool(current_app.config.get(name)), "unreadable": False, "from_env": True}
        else:
            raw = _parse(field, stored) if stored is not None else current_app.config.get(name)
            entry = {"value": raw, "from_env": stored is None}
        out.setdefault(field.section, {})[name] = entry
    return out


def update(changes: dict, actor: User) -> dict[str, dict[str, dict]]:
    """changes: {name: None (keep) | "" (clear, back to .env) | value}. Audit logs names only, never values."""
    repo = SettingsRepository()
    changed: list[str] = []
    with transaction():
        for name, new in changes.items():
            if new is None or name not in FIELDS:
                continue
            field = FIELDS[name]
            if new == "":
                if repo.delete(_db_key(name)):
                    changed.append(name)
                continue
            if field.kind == "bool":
                text = "1" if new else "0"
            elif field.kind == "int":
                text = str(int(new))
            else:
                text = str(new).strip()
            repo.upsert(_db_key(name), encrypt(text) if field.secret else text, actor.id)
            changed.append(name)
        if changed:
            audit_service.log(actor, "integrations.update", "settings", None, None, {"changed": sorted(changed)})
    return public_view()
