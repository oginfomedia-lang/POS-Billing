"""RapidOCR (PaddleOCR's models on ONNX Runtime): an image → words with their boxes.

Much better than Tesseract on phone photos, small and dot-matrix fonts and ruled tables. Fully offline: the
models (~15 MB) ship inside the rapidocr package. It reads grey images, not black-and-white ones
(preprocess.prepare(..., binarize=False)).
"""
from __future__ import annotations

import functools
import logging
import os
import threading

import cv2
import numpy as np

from app.errors.exceptions import BadRequestError
from app.ocr import Word

log = logging.getLogger(__name__)
_lock = threading.Lock()


@functools.lru_cache(maxsize=1)
def _engine():
    """Loaded once per server start; None when rapidocr / onnxruntime are not installed or won't load."""
    try:
        from rapidocr import RapidOCR

        logging.getLogger("RapidOCR").setLevel(logging.WARNING)
        # Half the cores: two bills can be read at once and billing must stay quick meanwhile.
        threads = max(1, (os.cpu_count() or 2) // 2)
        return RapidOCR(params={
            "Global.log_level": "warning",
            "Global.text_score": 0.3,  # keep doubtful words: the line is marked "hard to read" instead of lost
            "EngineConfig.onnxruntime.intra_op_num_threads": threads,
            "EngineConfig.onnxruntime.inter_op_num_threads": 1,
        })
    except Exception:
        log.warning("RapidOCR could not be loaded", exc_info=True)
        return None


def is_available() -> bool:
    with _lock:
        return _engine() is not None


def read_words(image: np.ndarray, timeout: int) -> list[Word]:  # noqa: ARG001 - a page takes a few seconds
    with _lock:
        engine = _engine()
    if engine is None:
        raise BadRequestError("Bill reading (RapidOCR) is not installed on the Main PC.")
    if image.ndim == 2:
        image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    try:
        result = engine(image, return_word_box=True)
    except Exception as exc:
        log.warning("RapidOCR failed", exc_info=True)
        raise BadRequestError("The bill could not be read. Try a clearer photo.") from exc
    if not result.txts:
        return []

    word_results = result.word_results if len(result.word_results or ()) == len(result.txts) else None
    words: list[Word] = []
    for i, (box, text, score) in enumerate(zip(result.boxes, result.txts, result.scores)):
        parts = word_results[i] if word_results else None
        words += segment_words(np.asarray(box, dtype=float), text, float(score), parts)
    return words


def segment_words(box: np.ndarray, text: str, score: float, parts=None) -> list[Word]:
    """RapidOCR finds text segments ("TATA SALT 1KG"); the table parser needs words. Its own word boxes when it
    gave them, else the segment's box shared out by the characters' places."""
    if parts:
        words = []
        for part in parts:
            if not part or part[2] is None or not str(part[0]).strip():
                continue
            pts = np.asarray(part[2], dtype=float)
            words.append(Word(str(part[0]).strip(), pts[:, 0].min(), pts[:, 1].min(), pts[:, 0].max(),
                              pts[:, 1].max(), float(part[1]) * 100))
        if words and "".join(w.text for w in words).replace(" ", "") == text.replace(" ", ""):
            return words

    x0, x1 = float(box[:, 0].min()), float(box[:, 0].max())
    y0, y1 = float(box[:, 1].min()), float(box[:, 1].max())
    n = len(text) or 1
    per_char = (x1 - x0) / n
    words = []
    start = 0
    for token in text.split(" "):
        if token:
            words.append(Word(token, x0 + start * per_char, y0, x0 + (start + len(token)) * per_char, y1,
                              score * 100))
        start += len(token) + 1
    return words
