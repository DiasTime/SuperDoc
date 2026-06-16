"""Reconstruction outputs.

M1.1: wrap the restored page image into a clean PDF (Pillow).
M1.2: searchable PDF — restored image as the page, plus an invisible OCR text
      layer positioned per line so the PDF is selectable / searchable.
M2+:  structure-aware HTML -> PDF/DOCX.
"""

from __future__ import annotations

import io
import json
import logging
from typing import Any

from PIL import Image

log = logging.getLogger("worker.pipeline.reconstruct")

_DPI = 150.0
_PT_PER_PX = 72.0 / _DPI
_INVISIBLE = 3  # PDF text render mode: no fill, no stroke


def structure_to_json(structure: dict[str, Any]) -> bytes:
    """Serialize the understanding output into a downloadable JSON artifact.

    This is the M2 `GET /download/json/:id` payload — the typed
    `DocumentStructure` (type, sections, key-values, signatures, metadata).
    """
    return json.dumps(structure, ensure_ascii=False, indent=2).encode("utf-8")


def image_to_pdf(image_bytes: bytes) -> bytes:
    """Image-only PDF (no text layer). Fallback when OCR produced nothing."""
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    out = io.BytesIO()
    image.save(out, format="PDF", resolution=_DPI)
    return out.getvalue()


def searchable_pdf(image_bytes: bytes, words: list[dict[str, Any]]) -> bytes:
    """Restored image + invisible, positioned OCR text → searchable PDF.

    Boxes are normalized 0–1 (y from the top). Each line is drawn invisibly and
    horizontally scaled to span its box, so selection/search line up with the
    visible glyphs underneath. Degrades to `image_to_pdf` if reportlab is absent.
    """
    try:
        from reportlab.lib.utils import ImageReader
        from reportlab.pdfgen import canvas
    except Exception as exc:  # noqa: BLE001
        log.warning("reportlab unavailable; emitting image-only PDF: %s", exc)
        return image_to_pdf(image_bytes)

    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    w_px, h_px = image.size
    page_w, page_h = w_px * _PT_PER_PX, h_px * _PT_PER_PX

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(page_w, page_h))
    c.drawImage(ImageReader(image), 0, 0, width=page_w, height=page_h)

    for word in words:
        text = word.get("text", "").strip()
        if not text:
            continue
        xs = [p[0] for p in word["box"]]
        ys = [p[1] for p in word["box"]]
        x0 = min(xs) * page_w
        box_w = (max(xs) - min(xs)) * page_w
        # PDF origin is bottom-left; OCR y grows downward from the top.
        baseline_y = page_h - (max(ys) * page_h)
        font_size = max((max(ys) - min(ys)) * page_h * 0.8, 4.0)

        to = c.beginText()
        to.setTextRenderMode(_INVISIBLE)
        to.setFont("Helvetica", font_size)
        glyph_w = c.stringWidth(text, "Helvetica", font_size)
        if glyph_w > 0 and box_w > 0:
            to.setHorizScale(100.0 * box_w / glyph_w)
        to.setTextOrigin(x0, baseline_y)
        to.textLine(text)
        c.drawText(to)

    c.showPage()
    c.save()
    return buf.getvalue()
