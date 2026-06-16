"""M2 smoke test: render a synthetic invoice and run the real VL understanding
stage against it (no Postgres/Redis/MinIO needed).

    # pull a model first:  ollama pull qwen2.5vl:3b
    PYTHONPATH=. .venv/Scripts/python.exe scripts/m2_smoke.py [model]

Exercises worker/pipeline/vl.py end-to-end against a live Ollama (or any
OpenAI-compatible endpoint in settings), printing the typed DocumentStructure.
"""

from __future__ import annotations

import io
import json
import sys

from PIL import Image, ImageDraw, ImageFont

from worker.config import settings
from worker.pipeline.ocr import run_ocr
from worker.pipeline.reconstruct import structure_to_json
from worker.pipeline.vl import OpenAICompatVL, understand

_FONTS = ["C:/Windows/Fonts/arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in _FONTS:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def render_invoice() -> bytes:
    """A crisp, realistic invoice page — title, parties, a line-item table, total."""
    page = Image.new("RGB", (1000, 1300), "white")
    d = ImageDraw.Draw(page)
    d.text((80, 60), "ACME CORPORATION", fill="black", font=_font(46))
    d.text((80, 130), "INVOICE", fill="black", font=_font(34))
    d.text((640, 70), "Invoice No: 2026-0042", fill="black", font=_font(24))
    d.text((640, 110), "Date: 2026-06-16", fill="black", font=_font(24))

    d.text((80, 230), "Billed to: Initech LLC", fill="black", font=_font(26))
    d.text((80, 270), "123 Office Park, Springfield", fill="black", font=_font(22))

    # line-item table
    rows = [
        ("Description", "Qty", "Unit", "Amount"),
        ("Consulting services", "10", "$100.00", "$1,000.00"),
        ("On-site support", "3", "$79.00", "$237.00"),
        ("Cloud hosting", "1", "$100.00", "$100.00"),
    ]
    y = 360
    cols = [80, 520, 640, 800]
    for r, row in enumerate(rows):
        f = _font(24 if r == 0 else 22)
        for x, cell in zip(cols, row):
            d.text((x, y), cell, fill="black", font=f)
        y += 50
        if r == 0:
            d.line((80, y - 8, 920, y - 8), fill="black", width=2)

    d.text((640, y + 40), "Total due: $1,337.00", fill="black", font=_font(28))
    d.text((80, y + 140), "Authorized signature: __________", fill="black", font=_font(22))

    buf = io.BytesIO()
    page.save(buf, format="PNG")
    return buf.getvalue()


def main() -> int:
    model = sys.argv[1] if len(sys.argv) > 1 else settings.vl_model_name
    print(f"endpoint={settings.vl_endpoint}  model={model}")

    image = render_invoice()
    ocr = run_ocr(image)  # empty when PaddleOCR is absent; the VL model reads the image directly
    print(f"OCR words: {len(ocr['words'])} (image-only understanding if 0)")

    provider = OpenAICompatVL(
        endpoint=settings.vl_endpoint,
        model=model,
        api_key=settings.vl_api_key,
        max_tokens=settings.vl_max_tokens,
        timeout=settings.vl_timeout,
    )
    structure = understand(image, ocr, provider=provider)
    print("\n=== DocumentStructure ===")
    print(structure_to_json(structure).decode("utf-8"))

    ok = structure["type"] != "UNKNOWN"
    print(f"\nresult: {'OK — model produced a typed structure' if ok else 'DEGRADED — UNKNOWN (model/endpoint issue)'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
