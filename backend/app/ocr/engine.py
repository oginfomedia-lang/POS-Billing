"""The OCR engine: a cleaned image → words with their boxes.

    OCR_ENGINE = "rapidocr" (default)  RapidOCR, offline neural OCR; Tesseract if it can't be loaded
    OCR_ENGINE = "tesseract"           Tesseract only (the old engine)
"""
from __future__ import annotations

import numpy as np
from flask import current_app

from app.errors.exceptions import BadRequestError
from app.ocr import Word, rapid_engine, tesseract_engine


def name() -> str | None:
    """The engine that will read the bill: "rapidocr", "tesseract", or None when neither works."""
    if current_app.config.get("OCR_ENGINE", "rapidocr") != "tesseract" and rapid_engine.is_available():
        return "rapidocr"
    return "tesseract" if tesseract_engine.is_available() else None


def is_available() -> bool:
    return name() is not None


def needs_black_and_white() -> bool:
    """Tesseract reads black text on white best; RapidOCR reads the grey picture better."""
    return name() != "rapidocr"


def read_words(image: np.ndarray, timeout: int) -> list[Word]:
    engine = name()
    if engine == "rapidocr":
        return rapid_engine.read_words(image, timeout)
    if engine == "tesseract":
        return tesseract_engine.read_words(image, timeout)
    raise BadRequestError("Bill reading is not installed on the Main PC.")
