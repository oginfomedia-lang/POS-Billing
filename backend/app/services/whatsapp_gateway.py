"""Thin WhatsApp Business Cloud API client: send one approved template message, optionally with a PDF.

With WHATSAPP_MOCK=1 nothing leaves the machine: the message is written to the log and a fake id returned.
"""
from __future__ import annotations

import re
import uuid

import requests
from flask import current_app

from app.errors.exceptions import AppError
from app.services import integration_settings_service

GRAPH_API = "https://graph.facebook.com/v21.0"
TIMEOUT = 15  # seconds
UPLOAD_TIMEOUT = 30  # seconds, for the PDF
MAX_PARAM_LEN = 1024  # Meta's limit for one template variable


def _cfg(key: str):
    """Settings → Integrations, else backend/.env."""
    return integration_settings_service.value(key)


def clean_param(text: str) -> str:
    """Template variables may not contain newlines, tabs or more than 4 spaces in a row."""
    return re.sub(r"\s{2,}", " ", re.sub(r"[\r\n\t]+", " ", text)).strip()[:MAX_PARAM_LEN]


def _require_setup() -> None:
    if not _cfg("WHATSAPP_TOKEN") or not _cfg("WHATSAPP_PHONE_NUMBER_ID"):
        raise AppError("WhatsApp is not set up. Add the token and phone number ID in Admin → Settings → Integrations.")


def _post(path: str, timeout: int, **kwargs) -> dict:
    try:
        r = requests.post(
            f"{GRAPH_API}/{_cfg('WHATSAPP_PHONE_NUMBER_ID')}/{path}",
            headers={"Authorization": f"Bearer {_cfg('WHATSAPP_TOKEN')}"},
            timeout=timeout,
            **kwargs,
        )
        data = r.json()
    except (requests.RequestException, ValueError) as exc:
        raise AppError("Cannot reach WhatsApp. Check the internet connection.") from exc
    if r.status_code >= 400:
        raise AppError(f"WhatsApp error: {data.get('error', {}).get('message') or r.reason}")
    return data


def check_credentials() -> str:
    """Settings → Integrations "Test connection": reads the sending number's details from Meta."""
    if _cfg("WHATSAPP_MOCK"):
        return "Test mode is on: nothing was checked."
    _require_setup()
    try:
        r = requests.get(
            f"{GRAPH_API}/{_cfg('WHATSAPP_PHONE_NUMBER_ID')}",
            params={"fields": "display_phone_number,verified_name"},
            headers={"Authorization": f"Bearer {_cfg('WHATSAPP_TOKEN')}"},
            timeout=TIMEOUT,
        )
        data = r.json()
    except (requests.RequestException, ValueError) as exc:
        raise AppError("Cannot reach WhatsApp. Check the internet connection.") from exc
    if r.status_code >= 400:
        raise AppError(f"WhatsApp error: {data.get('error', {}).get('message') or r.reason}")
    return f"Connected: {data.get('verified_name', '')} ({data.get('display_phone_number', '')})"


def upload_media(data: bytes, filename: str, mime: str = "application/pdf") -> str:
    """Uploads a file to WhatsApp (kept there for 30 days). Returns the media id to send it with."""
    if _cfg("WHATSAPP_MOCK"):
        current_app.logger.info("WhatsApp (mock) upload %s (%d bytes)", filename, len(data))
        return f"media.mock_{uuid.uuid4().hex[:12]}"
    _require_setup()
    return _post(
        "media", UPLOAD_TIMEOUT,
        data={"messaging_product": "whatsapp", "type": mime},
        files={"file": (filename, data, mime)},
    )["id"]


def send_template(
    mobile: str,
    params: list[str],
    template: str | None = None,
    document: tuple[str, str] | None = None,
) -> str:
    """Sends an approved template to a 10-digit Indian mobile. Returns WhatsApp's message id.

    template defaults to WHATSAPP_TEMPLATE_NAME (the daily report). document = (media_id, filename) for a
    template whose header is a document.
    """
    params = [clean_param(p) for p in params]
    template = template or _cfg("WHATSAPP_TEMPLATE_NAME")
    if _cfg("WHATSAPP_MOCK"):
        current_app.logger.info(
            "WhatsApp (mock) %s to %s: %s%s", template, mobile, params, f" + {document[1]}" if document else ""
        )
        return f"wamid.mock_{uuid.uuid4().hex[:12]}"
    _require_setup()
    components = [{"type": "body", "parameters": [{"type": "text", "text": p} for p in params]}]
    if document:
        media_id, filename = document
        components.insert(0, {
            "type": "header",
            "parameters": [{"type": "document", "document": {"id": media_id, "filename": filename}}],
        })
    body = {
        "messaging_product": "whatsapp",
        "to": f"91{mobile}",
        "type": "template",
        "template": {
            "name": template,
            "language": {"code": _cfg("WHATSAPP_TEMPLATE_LANG")},
            "components": components,
        },
    }
    return _post("messages", TIMEOUT, json=body)["messages"][0]["id"]
