"""Scanned PDF pages and photos → images for Tesseract."""
from __future__ import annotations

import io

import pypdfium2 as pdfium
from PIL import Image, ImageOps

DPI = 300  # Tesseract reads best at about 300 dots per inch


def pdf_to_images(data: bytes, max_pages: int) -> list[Image.Image]:
    pdf = pdfium.PdfDocument(data)
    try:
        images = []
        for i in range(min(len(pdf), max_pages)):
            page = pdf[i]
            images.append(page.render(scale=DPI / 72).to_pil().convert("RGB"))
            page.close()
        return images
    finally:
        pdf.close()


def load_image(data: bytes) -> Image.Image:
    """A photo or scan. Phones store "rotate me" in the EXIF data instead of turning the picture: apply it."""
    image = Image.open(io.BytesIO(data))
    image = ImageOps.exif_transpose(image)
    return image.convert("RGB")


def images_to_pdf(images: list[Image.Image]) -> bytes:
    """Several photos of one long bill → one PDF, a page per photo, in the order chosen."""
    out = io.BytesIO()
    images[0].save(out, "PDF", save_all=True, append_images=images[1:], resolution=150)
    return out.getvalue()

