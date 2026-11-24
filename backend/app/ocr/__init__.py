"""Reading supplier bills (PDF or photo) for the Direct purchase screen.

    pdf_text      PDF made by billing software → its words (no OCR needed, exact)
    rasterize     scanned PDF pages / photos → images
    preprocess    straightens and cleans an image (OpenCV)
    engine        RapidOCR (or Tesseract as fallback): image → words with their boxes
    header_parser GSTIN, invoice number, date, totals
    table_parser  words → item lines (rows, columns, supplier layouts)
    normalize     OCR text → numbers and dates

The whole pipeline is app/services/bill_ocr_service.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Word:
    """One word and its box on the page: pixels for images, PDF points for digital PDFs."""
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    conf: float = 100.0  # the OCR engine's confidence 0-100; 100 for text taken from a digital PDF

    @property
    def xc(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def yc(self) -> float:
        return (self.y0 + self.y1) / 2

    @property
    def height(self) -> float:
        return self.y1 - self.y0


@dataclass
class Page:
    width: float
    height: float
    words: list[Word] = field(default_factory=list)
    source: str = "ocr"  # "pdf_text" (digital PDF) or "ocr" (read by our OCR engine)
    scan: bool = False  # pdf_text only: the page is a scanned picture with another program's OCR text over it