"""Makes a bill image easy for Tesseract: flat, straight, right size, black text on white."""
from __future__ import annotations

import cv2
import numpy as np
from PIL import Image

MIN_SIDE = 1800  # smaller pictures are enlarged: Tesseract needs letters about 20+ pixels high
MAX_SIDE = 4000  # bigger ones are reduced: slower, no more accurate


def prepare(image: Image.Image, is_photo: bool, binarize: bool = True) -> np.ndarray:
    """binarize=False (RapidOCR): straightened grey picture with even contrast; its neural models read thin and
    faint strokes that a black-and-white threshold would break."""
    gray = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2GRAY)
    if is_photo:
        gray = _flatten_paper(gray)  # only photos: on a scan the "paper" found could be the table's border
    gray = _limit_size(gray)
    gray = _deskew(gray)
    if not binarize:
        # Evens out shadows and faded print, tile by tile, without making it black-and-white.
        return cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    gray = cv2.medianBlur(gray, 3)  # removes specks and grain; fastNlMeansDenoising took ~8 s per page
    # Black and white with a threshold worked out per neighbourhood, so shadows don't turn black.
    return cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 15)


def _limit_size(gray: np.ndarray) -> np.ndarray:
    longest = max(gray.shape)
    if longest < MIN_SIDE:
        scale = min(2.0, MIN_SIDE / longest)
    elif longest > MAX_SIDE:
        scale = MAX_SIDE / longest
    else:
        return gray
    interpolation = cv2.INTER_CUBIC if scale > 1 else cv2.INTER_AREA
    return cv2.resize(gray, None, fx=scale, fy=scale, interpolation=interpolation)


def _order_corners(pts: np.ndarray) -> np.ndarray:
    """top-left, top-right, bottom-right, bottom-left."""
    s = pts.sum(axis=1)
    d = np.diff(pts, axis=1).ravel()  # y - x
    return np.array([pts[np.argmin(s)], pts[np.argmin(d)], pts[np.argmax(s)], pts[np.argmax(d)]], dtype="float32")


def _flatten_paper(gray: np.ndarray) -> np.ndarray:
    """A photo taken at an angle: find the paper's four corners and stretch it back into a rectangle."""
    scale = min(1.0, 1000 / max(gray.shape))
    small = cv2.resize(gray, None, fx=scale, fy=scale) if scale < 1 else gray
    edges = cv2.Canny(cv2.GaussianBlur(small, (5, 5), 0), 50, 150)
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8))
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return gray
    paper = max(contours, key=cv2.contourArea)
    if cv2.contourArea(paper) < 0.6 * small.shape[0] * small.shape[1]:
        return gray  # no clear sheet of paper: leave the picture as it is
    corners = cv2.approxPolyDP(paper, 0.02 * cv2.arcLength(paper, True), True)
    if len(corners) != 4:
        return gray
    tl, tr, br, bl = rect = _order_corners(corners.reshape(4, 2).astype("float32") / scale)
    width = int(max(np.linalg.norm(br - bl), np.linalg.norm(tr - tl)))
    height = int(max(np.linalg.norm(tr - br), np.linalg.norm(tl - bl)))
    target = np.array([[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]], dtype="float32")
    matrix = cv2.getPerspectiveTransform(rect, target)
    return cv2.warpPerspective(gray, matrix, (width, height))


def _deskew(gray: np.ndarray) -> np.ndarray:
    """Straightens a page tilted up to 5°: the angle at which the text rows line up best (sharpest row profile)."""
    scale = 800 / gray.shape[1]
    small = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    _, ink = cv2.threshold(small, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    h, w = ink.shape
    best_angle, best_score = 0.0, -1.0
    for angle in np.arange(-5.0, 5.25, 0.25):
        m = cv2.getRotationMatrix2D((w / 2, h / 2), float(angle), 1.0)
        rotated = cv2.warpAffine(ink, m, (w, h), flags=cv2.INTER_NEAREST)
        score = float(np.var(rotated.sum(axis=1)))
        if score > best_score:
            best_angle, best_score = float(angle), score
    if abs(best_angle) < 0.25:
        return gray
    h, w = gray.shape
    m = cv2.getRotationMatrix2D((w / 2, h / 2), best_angle, 1.0)
    return cv2.warpAffine(gray, m, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)