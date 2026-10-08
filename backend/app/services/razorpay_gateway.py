"""Thin Razorpay client: UPI QR codes + Razorpay POS (card machine) push-to-pay.

With RAZORPAY_MOCK=1 nothing leaves the machine: QRs/card pushes are "paid" after ~6 seconds.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

import requests
from flask import current_app

from app.errors.exceptions import AppError

RZP_API = "https://api.razorpay.com/v1"
TIMEOUT = 15  # seconds
_mock_started: dict[str, float] = {}


@dataclass
class GatewayStatus:
    state: str                  # "pending" | "paid" | "failed" | "cancelled"
    paid_paise: int = 0
    txn_id: str | None = None
    reason: str | None = None


def _cfg(key: str):
    return current_app.config[key]


def _mock() -> bool:
    return bool(_cfg("RAZORPAY_MOCK"))


def _mock_status(ref: str, amount_paise: int) -> GatewayStatus:
    if ref not in _mock_started:
        return GatewayStatus("cancelled")
    if time.time() - _mock_started[ref] > 6:
        return GatewayStatus("paid", amount_paise, f"mock_txn_{ref}")
    return GatewayStatus("pending")


# ---------- UPI QR (Razorpay QR Codes API) ----------

def create_upi_qr(amount_paise: int, sale_id: int, description: str) -> tuple[str, str]:
    """Returns (qr_id, image_url) for a single-use QR that accepts ONLY this exact amount."""
    if _mock():
        ref = f"qr_mock_{sale_id}_{uuid.uuid4().hex[:10]}"
        _mock_started[ref] = time.time()
        upi = f"upi://pay?pa=mock@razorpay&pn=POS&am={amount_paise / 100:.2f}&cu=INR&tn={ref}"
        return ref, f"https://api.qrserver.com/v1/create-qr-code/?size=280x280&data={requests.utils.quote(upi)}"
    body = {
        "type": "upi_qr",
        "name": "POS Counter",
        "usage": "single_use",
        "fixed_amount": True,                    # customer cannot change the amount
        "payment_amount": amount_paise,
        "description": description,
        "close_by": int(time.time()) + _cfg("UPI_QR_EXPIRY_SECONDS"),
        "notes": {"sale_id": str(sale_id)},
    }
    data = _rzp("POST", "/payments/qr_codes", json=body)
    return data["id"], data["image_url"]


def upi_qr_status(qr_id: str, amount_paise: int) -> GatewayStatus:
    if _mock():
        return _mock_status(qr_id, amount_paise)
    qr = _rzp("GET", f"/payments/qr_codes/{qr_id}")
    if qr.get("payments_amount_received", 0) >= amount_paise:
        pays = _rzp("GET", f"/payments/qr_codes/{qr_id}/payments").get("items", [])
        captured = next((p for p in pays if p.get("status") == "captured"), None)
        return GatewayStatus("paid", qr["payments_amount_received"], captured["id"] if captured else None)
    if qr.get("status") == "closed":
        return GatewayStatus("cancelled", reason=qr.get("close_reason") or "QR expired")
    return GatewayStatus("pending")


def close_upi_qr(qr_id: str) -> None:
    if _mock():
        _mock_started.pop(qr_id, None)
        return
    try:
        _rzp("POST", f"/payments/qr_codes/{qr_id}/close")
    except AppError:
        pass  # already closed/paid — nothing to do


def _rzp(method: str, path: str, **kw) -> dict:
    try:
        r = requests.request(method, RZP_API + path, timeout=TIMEOUT,
                             auth=(_cfg("RAZORPAY_KEY_ID"), _cfg("RAZORPAY_KEY_SECRET")), **kw)
    except requests.RequestException as exc:
        raise AppError("Cannot reach Razorpay. Check the internet connection.") from exc
    if r.status_code >= 400:
        msg = r.json().get("error", {}).get("description", r.text) if r.content else r.reason
        raise AppError(f"Razorpay error: {msg}")
    return r.json()


# ---------- Card (Razorpay POS / Ezetap P2P push-to-pay) ----------

def push_to_card_machine(amount_paise: int, sale_id: int, device_id: str) -> str:
    """Sends the exact amount to the counter's card machine. Returns p2pRequestId."""
    if _mock():
        ref = f"p2p_mock_{sale_id}_{uuid.uuid4().hex[:10]}"
        _mock_started[ref] = time.time()
        return ref
    data = _pos("pay", {
        "amount": f"{amount_paise / 100:.2f}",
        "externalRefNumber": f"SALE-{sale_id}-{int(time.time())}",  # unique per attempt
        "pushTo": {"deviceId": device_id},
        "mode": "CARD",
    })
    return data["p2pRequestId"]


def card_status(p2p_id: str, amount_paise: int) -> GatewayStatus:
    if _mock():
        return _mock_status(p2p_id, amount_paise)
    data = _pos("status", {"origP2pRequestId": p2p_id})
    status = (data.get("status") or "").upper()
    if status == "AUTHORIZED":
        paid = round(float(data.get("amount", 0)) * 100)
        return GatewayStatus("paid", paid, data.get("txnId") or data.get("authCode"))
    if status in ("FAILED", "DECLINED") or data.get("messageCode") == "P2P_DEVICE_CANCELED":
        return GatewayStatus("failed", reason=data.get("message") or "Card payment failed")
    return GatewayStatus("pending")  # P2P_DEVICE_RECEIVED / P2P_STATUS_QUEUED etc.


def cancel_card_push(p2p_id: str, device_id: str) -> None:
    if _mock():
        _mock_started.pop(p2p_id, None)
        return
    try:
        _pos("cancel", {"origP2pRequestId": p2p_id, "pushTo": {"deviceId": device_id}})
    except AppError:
        pass


def _pos(action: str, body: dict) -> dict:
    body = {"username": _cfg("RAZORPAY_POS_USERNAME"), "appKey": _cfg("RAZORPAY_POS_APP_KEY"), **body}
    try:
        r = requests.post(f"{_cfg('RAZORPAY_POS_BASE_URL')}/{action}", json=body, timeout=TIMEOUT)
        data = r.json()
    except (requests.RequestException, ValueError) as exc:
        raise AppError("Cannot reach the Razorpay card machine service.") from exc
    if not data.get("success", False) and action != "status":
        raise AppError(f"Card machine error: {data.get('message') or data.get('errorMessage')}")
    return data