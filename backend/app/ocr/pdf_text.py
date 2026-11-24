"""PDFs made by billing software (Tally, Marg, Busy ...) already hold their text: read it, no OCR needed."""
from __future__ import annotations

import io

import pdfplumber

from app.ocr import Page, Word

MIN_TEXT_CHARS = 50  # less than this on all pages = a scanned PDF (only pictures inside)
SCAN_COVER = 0.8  # a picture covering this much of the page = the page is a scan


def is_pdf(data: bytes) -> bool:
    return data[:5] == b"%PDF-"


def read_text_pages(data: bytes, max_pages: int) -> list[Page] | None:
    """The words of each page with their boxes (PDF points), or None for a scanned PDF."""
    pages: list[Page] = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for p in pdf.pages[:max_pages]:
            words = [
                Word(w["text"], float(w["x0"]), float(w["top"]), float(w["x1"]), float(w["bottom"]), 100.0)
                for w in p.extract_words()
            ]
            pages.append(Page(width=float(p.width), height=float(p.height), words=words, source="pdf_text",
                              scan=_is_scan(p)))
    if sum(len(w.text) for page in pages for w in page.words) < MIN_TEXT_CHARS:
        return None
    return pages


def _is_scan(page) -> bool:
    """One picture covers the page: a scan or photo, its text (if any) laid over it by some OCR program, often
    badly ("OCR ready" PDFs). Our own OCR reads it better."""
    area = float(page.width) * float(page.height)
    if area <= 0:
        return False
    for im in page.images:
        w = min(float(im["x1"]), float(page.width)) - max(float(im["x0"]), 0.0)
        h = min(float(im["bottom"]), float(page.height)) - max(float(im["top"]), 0.0)
        if w > 0 and h > 0 and w * h >= SCAN_COVER * area:
            return True
    return False