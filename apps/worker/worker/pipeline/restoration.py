"""Image restoration: terrible phone photo -> clean, OCR-ready page.

Pipeline: downscale -> detect document quad -> perspective warp -> denoise ->
shadow removal (background division) -> contrast (CLAHE) -> deskew.

All steps are defensive: if a step can't find what it needs (e.g. no document
contour), it degrades gracefully instead of failing the whole job.
"""

from __future__ import annotations

import cv2
import numpy as np


def _resize_max(img: np.ndarray, max_side: int = 2200) -> np.ndarray:
    h, w = img.shape[:2]
    scale = max_side / max(h, w)
    if scale < 1:
        img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    return img


def _order_points(pts: np.ndarray) -> np.ndarray:
    rect = np.zeros((4, 2), dtype="float32")
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]  # top-left
    rect[2] = pts[np.argmax(s)]  # bottom-right
    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]  # top-right
    rect[3] = pts[np.argmax(diff)]  # bottom-left
    return rect


def _find_document_quad(gray: np.ndarray) -> np.ndarray | None:
    edged = cv2.Canny(gray, 75, 200)
    edged = cv2.dilate(edged, np.ones((5, 5), np.uint8), iterations=1)
    contours, _ = cv2.findContours(edged, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    contours = sorted(contours, key=cv2.contourArea, reverse=True)[:5]
    area = gray.shape[0] * gray.shape[1]
    for c in contours:
        peri = cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, 0.02 * peri, True)
        if len(approx) == 4 and cv2.contourArea(approx) > 0.25 * area:
            return approx.reshape(4, 2).astype("float32")
    return None


def _four_point_warp(img: np.ndarray, quad: np.ndarray) -> np.ndarray:
    rect = _order_points(quad)
    (tl, tr, br, bl) = rect
    width = int(max(np.linalg.norm(br - bl), np.linalg.norm(tr - tl)))
    height = int(max(np.linalg.norm(tr - br), np.linalg.norm(tl - bl)))
    if width < 10 or height < 10:
        return img
    dst = np.array(
        [[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]],
        dtype="float32",
    )
    matrix = cv2.getPerspectiveTransform(rect, dst)
    return cv2.warpPerspective(img, matrix, (width, height))


def _remove_shadow(gray: np.ndarray) -> np.ndarray:
    dilated = cv2.dilate(gray, np.ones((7, 7), np.uint8))
    background = cv2.medianBlur(dilated, 21)
    diff = 255 - cv2.absdiff(gray, background)
    return cv2.normalize(diff, None, 0, 255, cv2.NORM_MINMAX)


def _estimate_skew(gray: np.ndarray, search: float = 12.0, step: float = 0.5) -> float:
    """Find the rotation that best aligns text rows, via projection-profile search.

    Robust across OpenCV versions (no reliance on minAreaRect's angle convention):
    the correcting angle is the one whose horizontal projection has the sharpest
    row-to-row transitions (text lines stacked = high variance).
    """
    scale = 800 / gray.shape[1] if gray.shape[1] > 800 else 1.0
    small = cv2.resize(gray, (0, 0), fx=scale, fy=scale) if scale != 1.0 else gray
    binary = cv2.threshold(small, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    h, w = binary.shape[:2]
    center = (w / 2, h / 2)

    best_angle, best_score = 0.0, -1.0
    for angle in np.arange(-search, search + 1e-6, step):
        matrix = cv2.getRotationMatrix2D(center, float(angle), 1.0)
        rotated = cv2.warpAffine(binary, matrix, (w, h), flags=cv2.INTER_NEAREST)
        projection = rotated.sum(axis=1, dtype=np.float64)
        score = float(np.square(np.diff(projection)).sum())
        if score > best_score:
            best_score, best_angle = score, float(angle)
    return best_angle


def _deskew(gray: np.ndarray) -> np.ndarray:
    angle = _estimate_skew(gray)
    if abs(angle) < 0.3:
        return gray
    h, w = gray.shape[:2]
    matrix = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    return cv2.warpAffine(
        gray, matrix, (w, h),
        flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_CONSTANT, borderValue=255,
    )


def restore(image_bytes: bytes) -> bytes:
    """Restore a photo of a document. Returns PNG bytes of the cleaned page."""
    arr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("could not decode image")

    img = _resize_max(img)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    quad = _find_document_quad(gray)
    if quad is not None:
        warped = _four_point_warp(img, quad)
        gray = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)

    # shadow removal first (background division), then denoise so we don't
    # amplify grain in the dark regions, then contrast, then deskew.
    gray = _remove_shadow(gray)
    gray = cv2.fastNlMeansDenoising(gray, None, h=10, templateWindowSize=7, searchWindowSize=21)
    gray = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    # flatten near-white background to pure white (kills residual paper grain)
    gray[gray > 210] = 255
    gray = _deskew(gray)

    ok, buf = cv2.imencode(".png", gray)
    if not ok:
        raise ValueError("could not encode restored image")
    return buf.tobytes()
