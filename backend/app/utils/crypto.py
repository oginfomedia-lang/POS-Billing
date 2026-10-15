"""Encrypts secrets kept in the database (payment / WhatsApp keys) with a key derived from SECRET_KEY.

The key never goes in the database, so a copied database or backup can't be decrypted without the
server's .env. If SECRET_KEY changes, old values can't be read any more and must be entered again.
"""
from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from flask import current_app

PREFIX = "enc:"


def _fernet() -> Fernet:
    digest = hashlib.sha256(current_app.config["SECRET_KEY"].encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt(text: str) -> str:
    return PREFIX + _fernet().encrypt(text.encode("utf-8")).decode("ascii")


def decrypt(stored: str) -> str | None:
    """The plain text, or None when it can't be decrypted (SECRET_KEY changed, or not our value)."""
    if not stored.startswith(PREFIX):
        return None
    try:
        return _fernet().decrypt(stored[len(PREFIX):].encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError):
        return None
