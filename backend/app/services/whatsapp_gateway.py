"""Thin WhatsApp Business Cloud API client: send one approved template message.

With WHATSAPP_MOCK=1 nothing leaves the machine: the message is written to the log and a fake id returned.
"""
from __future__ import annotations

import re
import uuid

import requests
from flask import current_app

from app.errors.exceptions import AppError

GRAPH_API = "https://graph.facebook.com/v21.0"
TIMEOUT = 15  # seconds
MAX_PARAM_LEN = 1024  # Meta's limit for one template variable


def _cfg(key: str):
    return current_app.config[key]


def clean_param(text: str) -> str:
    """Template variables may not contain newlines, tabs or more than 4 spaces in a row."""
    return re.sub(r"\s{2,}", " ", re.sub(r"[\r\n\t]+", " ", text)).strip()[:MAX_PARAM_LEN]


def send_template(mobile: str, params: list[str]) -> str:
    """Sends the configured template to a 10-digit Indian mobile. Returns WhatsApp's message id."""
    params = [clean_param(p) for p in params]
    if _cfg("WHATSAPP_MOCK"):
        current_app.logger.info("WhatsApp (mock) to %s: %s", mobile, params)
        return f"wamid.mock_{uuid.uuid4().hex[:12]}"
    if not _cfg("WHATSAPP_TOKEN") or not _cfg("WHATSAPP_PHONE_NUMBER_ID"):
        raise AppError("WhatsApp is not set up. Add WHATSAPP_TOKEN and WHATSAPP_PHONE_NUMBER_ID to backend/.env.")
    body = {
        "messaging_product": "whatsapp",
        "to": f"91{mobile}",
        "type": "template",
        "template": {
            "name": _cfg("WHATSAPP_TEMPLATE_NAME"),
            "language": {"code": _cfg("WHATSAPP_TEMPLATE_LANG")},
            "components": [{"type": "body", "parameters": [{"type": "text", "text": p} for p in params]}],
        },
    }
    try:
        r = requests.post(
            f"{GRAPH_API}/{_cfg('WHATSAPP_PHONE_NUMBER_ID')}/messages",
            json=body,
            headers={"Authorization": f"Bearer {_cfg('WHATSAPP_TOKEN')}"},
            timeout=TIMEOUT,
        )
        data = r.json()
    except (requests.RequestException, ValueError) as exc:
        raise AppError("Cannot reach WhatsApp. Check the internet connection.") from exc
    if r.status_code >= 400:
        raise AppError(f"WhatsApp error: {data.get('error', {}).get('message') or r.reason}")
    return data["messages"][0]["id"]
