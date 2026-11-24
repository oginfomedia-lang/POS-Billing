"""Tesseract (the fallback engine): a cleaned image → words with their boxes.

Tesseract is a separate program (tesseract.exe), not a Python package. Where it is looked for:
    1. TESSERACT_CMD in backend.env / .env (full path to tesseract.exe)
    2. resources\\tesseract\\tesseract.exe in the installed app (bundled by electron-builder)
    3. "tesseract" on PATH (a developer PC with Tesseract installed)
"""
from __future__ import annotations

import functools
import os
import sys
from pathlib import Path

import numpy as np
import pytesseract
from flask import current_app
from pytesseract import Output

from app.errors.exceptions import BadRequestError
from app.ocr import Word
from app.utils.paths import is_frozen


def _bundled_dir() -> Path | None:
    """resources\\tesseract, next to resources\\backend (where literetailer-backend.exe is)."""
    if not is_frozen():
        return None
    folder = Path(sys.executable).resolve().parent.parent / "tesseract"
    return folder if (folder / "tesseract.exe").exists() else None


def _setup() -> None:
    configured = current_app.config.get("TESSERACT_CMD")
    bundled = _bundled_dir()
    if configured:
        pytesseract.pytesseract.tesseract_cmd = configured
    elif bundled:
        pytesseract.pytesseract.tesseract_cmd = str(bundled / "tesseract.exe")
        os.environ.setdefault("TESSDATA_PREFIX", str(bundled / "tessdata"))


@functools.lru_cache(maxsize=1)
def _version() -> str | None:
    """Asked once per server start (it runs tesseract.exe): restart the server after installing Tesseract."""
    try:
        return str(pytesseract.get_tesseract_version())
    except Exception:
        return None


def is_available() -> bool:
    _setup()
    return _version() is not None


def read_words(image: np.ndarray, timeout: int) -> list[Word]:
    _setup()
    cfg = current_app.config
    try:
        data = pytesseract.image_to_data(
            image,
            lang=cfg["OCR_LANGUAGES"],
            config=f"--oem 1 --psm {cfg['OCR_PSM']}",  # oem 1 = the LSTM (neural) engine
            output_type=Output.DICT,
            timeout=timeout,
        )
    except pytesseract.TesseractError as exc:
        raise BadRequestError(f"Tesseract could not read the bill: {exc.message}") from exc
    except RuntimeError as exc:  # pytesseract's timeout
        raise BadRequestError("Reading the bill took too long. Try a clearer photo or fewer pages.") from exc

    words = []
    for i, text in enumerate(data["text"]):
        text = (text or "").strip()
        conf = float(data["conf"][i])
        if not text or conf < 0:  # conf -1 = a block/line marker, not a word
            continue
        x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
        words.append(Word(text, float(x), float(y), float(x + w), float(y + h), conf))
    return words