"""OCR engine (PaddleOCR) + text-mask background cleanup.

PaddleOCR is heavy (pulls paddlepaddle) and only ships reliable wheels for the
Linux/py3.12 worker image — so it is imported lazily and the stage degrades
gracefully if it can't load. When OCR is unavailable the pipeline still
completes; reconstruction just falls back to the image-only PDF.

Output mirrors `OcrResult` in packages/shared-types: each entry carries text,
a 0–1 confidence, and a 4-point box normalized to the image (0–1, y from top).
"""

from __future__ import annotations

import logging
from typing import Any

import cv2
import numpy as np

log = logging.getLogger("worker.pipeline.ocr")

_engine: Any | None = None
_engine_failed = False


def _get_engine() -> Any | None:
    """Lazily construct a single PaddleOCR instance (model load is expensive)."""
    global _engine, _engine_failed
    if _engine is not None or _engine_failed:
        return _engine
    try:
        from paddleocr import PaddleOCR

        _engine = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
        log.info("PaddleOCR engine ready")
    except Exception as exc:  # noqa: BLE001 — any import/runtime failure degrades to pass-through
        log.warning("PaddleOCR unavailable; OCR stage will pass through: %s", exc)
        _engine_failed = True
    return _engine


def run_ocr(image_bytes: bytes) -> dict[str, Any]:
    """Run OCR on a restored page. Returns an OcrResult-shaped dict.

    Never raises on OCR-engine failure: returns an empty word list so the job
    can still finish with an image-only PDF.
    """
    arr = np.frombuffer(image_bytes, np.uint8)
    gray = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
    if gray is None:
        raise ValueError("could not decode image for OCR")
    h, w = gray.shape[:2]
    result: dict[str, Any] = {
        "words": [],
        "languages": [],
        "imageSize": {"width": int(w), "height": int(h)},
    }

    engine = _get_engine()
    if engine is None:
        return result

    bgr = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    try:
        raw = engine.ocr(bgr, cls=True)
    except Exception:  # noqa: BLE001 — defensive: a bad page must not kill the job
        log.exception("OCR inference failed; returning empty result")
        return result

    # PaddleOCR returns one list of lines per image: [[ [box, (text, conf)], ... ]]
    lines = raw[0] if raw and raw[0] else []
    words = []
    for entry in lines:
        box_px, (text, conf) = entry[0], entry[1]
        if not text or not text.strip():
            continue
        norm_box = [[float(x) / w, float(y) / h] for (x, y) in box_px]
        words.append({"text": text, "confidence": float(conf), "box": norm_box})

    result["words"] = words
    result["languages"] = ["en"] if words else []
    log.info("ocr extracted %d text lines", len(words))
    return result


def whiten_background(
    image_bytes: bytes,
    words: list[dict[str, Any]],
    pad: float = 0.012,
    threshold: int = 160,
) -> bytes:
    """Force the non-text background to pure white using the OCR text mask.

    Builds a mask from the (dilated) text boxes and pushes light pixels outside
    it to 255 — this kills residual paper grain and margin speckle while leaving
    text strokes and dark marks (signatures, stamps, lines) untouched.

    If OCR found nothing we return the input unchanged rather than risk wiping a
    page the engine simply couldn't read.
    """
    if not words:
        return image_bytes

    arr = np.frombuffer(image_bytes, np.uint8)
    gray = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
    if gray is None:
        return image_bytes
    h, w = gray.shape[:2]

    mask = np.zeros((h, w), np.uint8)
    for word in words:
        pts = np.array([[int(x * w), int(y * h)] for (x, y) in word["box"]], np.int32)
        cv2.fillConvexPoly(mask, pts, 255)
    kernel = max(3, int(min(h, w) * pad) | 1)  # odd
    mask = cv2.dilate(mask, np.ones((kernel, kernel), np.uint8))

    out = gray.copy()
    out[(mask == 0) & (gray > threshold)] = 255

    ok, buf = cv2.imencode(".png", out)
    return buf.tobytes() if ok else image_bytes
