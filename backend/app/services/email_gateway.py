"""Thin SMTP client: send one email with an optional attachment (purchase orders to suppliers).

Settings → Integrations → Email (or backend/.env). Port 465 uses SSL; any other port (usually 587) STARTTLS.
With EMAIL_MOCK=1 nothing leaves the machine: the email is written to the log.
"""
from __future__ import annotations

import smtplib
import socket
import ssl
from email.message import EmailMessage
from email.utils import formataddr

from flask import current_app

from app.errors.exceptions import AppError
from app.services import integration_settings_service

TIMEOUT = 20  # seconds


def _cfg(key: str):
    """Settings → Integrations, else backend/.env."""
    return integration_settings_service.value(key)


def is_configured() -> bool:
    """True when emails can go out: test mode, or a server and login are filled in."""
    if _cfg("EMAIL_MOCK"):
        return True
    return bool(_cfg("SMTP_HOST") and _cfg("SMTP_USERNAME") and _cfg("SMTP_PASSWORD"))


def _require_setup() -> None:
    if not (_cfg("SMTP_HOST") and _cfg("SMTP_USERNAME") and _cfg("SMTP_PASSWORD")):
        raise AppError("Email is not set up. Add the mail server, username and password in Admin → Settings → Integrations.")


def _connect() -> smtplib.SMTP:
    """A logged-in connection. Turns the usual failures into messages the shop can act on."""
    host = _cfg("SMTP_HOST")
    port = int(_cfg("SMTP_PORT") or 587)
    context = ssl.create_default_context()
    try:
        if port == 465:
            server: smtplib.SMTP = smtplib.SMTP_SSL(host, port, timeout=TIMEOUT, context=context)
        else:
            server = smtplib.SMTP(host, port, timeout=TIMEOUT)
            server.starttls(context=context)
        server.login(_cfg("SMTP_USERNAME"), _cfg("SMTP_PASSWORD"))
        return server
    except smtplib.SMTPAuthenticationError as exc:
        raise AppError(
            "The mail server refused the username or password. For Gmail use an app password, not the normal one."
        ) from exc
    except (OSError, smtplib.SMTPException, socket.timeout) as exc:
        raise AppError(f"Cannot reach the mail server {host}:{port}. Check the internet connection and the settings.") from exc


def check_credentials() -> str:
    """Settings → Integrations "Test connection": logs in and out, sends nothing."""
    if _cfg("EMAIL_MOCK"):
        return "Test mode is on: nothing was checked."
    _require_setup()
    server = _connect()
    try:
        server.quit()
    except smtplib.SMTPException:
        pass
    return f"Connected to {_cfg('SMTP_HOST')} as {_cfg('SMTP_USERNAME')}."


def send(
    to: str,
    subject: str,
    body: str,
    sender_name: str | None = None,
    attachment: tuple[str, bytes] | None = None,
) -> None:
    """Sends one email (attachment: (filename, PDF bytes)). Raises AppError with a readable reason."""
    if _cfg("EMAIL_MOCK"):
        current_app.logger.info("EMAIL_MOCK: to=%s subject=%r attachment=%s", to, subject, attachment and attachment[0])
        return
    _require_setup()
    sender = _cfg("SMTP_FROM") or _cfg("SMTP_USERNAME")
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((sender_name, sender)) if sender_name else sender
    msg["To"] = to
    msg.set_content(body)
    if attachment:
        filename, data = attachment
        msg.add_attachment(data, maintype="application", subtype="pdf", filename=filename)

    server = _connect()
    try:
        server.send_message(msg)
    except smtplib.SMTPRecipientsRefused as exc:
        raise AppError(f"The mail server refused the address {to}. Check the supplier's email.") from exc
    except (OSError, smtplib.SMTPException) as exc:
        raise AppError(f"The email could not be sent: {exc}") from exc
    finally:
        try:
            server.quit()
        except (OSError, smtplib.SMTPException):
            pass
