"""Reconstruction outputs.

M1.1: wrap the restored page image into a clean PDF (Pillow).
M1.2+: searchable PDF (OCR text layer), and structure-aware HTML -> PDF/DOCX.
"""

from __future__ import annotations

import io

from PIL import Image


def image_to_pdf(image_bytes: bytes) -> bytes:
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    out = io.BytesIO()
    image.save(out, format="PDF", resolution=150.0)
    return out.getvalue()
