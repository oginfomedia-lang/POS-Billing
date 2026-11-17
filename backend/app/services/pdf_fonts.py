"""Fonts for the PDFs the backend makes (e-bill, purchase order): Noto Sans with a Devanagari fallback, so
Marathi store, product and supplier names render correctly."""
from __future__ import annotations

from pathlib import Path

from fpdf import FPDF

FONTS = Path(__file__).resolve().parent.parent / "assets" / "fonts"
FAMILY = "NotoSans"


def setup(pdf: FPDF) -> None:
    """Registers the fonts and turns on text shaping (uharfbuzz). Call before add_page()."""
    for family, file in ((FAMILY, "NotoSans"), ("NotoDeva", "NotoSansDevanagari")):
        pdf.add_font(family, "", str(FONTS / f"{file}-Regular.ttf"))
        pdf.add_font(family, "B", str(FONTS / f"{file}-Bold.ttf"))
    pdf.set_fallback_fonts(["NotoDeva"])
    pdf.set_text_shaping(True)
