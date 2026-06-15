"""Pipeline unit tests (no external services).

Exercises the deterministic M1.1/M1.2 stage functions against a synthetic
"bad photo": restoration, the OCR result contract + graceful degrade when
PaddleOCR is absent, text-mask background whitening, and the searchable-PDF
text layer (verified selectable via pypdf round-trip).

Runnable directly (`python tests/test_pipeline.py`) or under pytest.
"""

from __future__ import annotations

import io

import cv2
import numpy as np
from PIL import Image, ImageDraw

from worker.pipeline.ocr import run_ocr, whiten_background
from worker.pipeline.reconstruct import image_to_pdf, searchable_pdf
from worker.pipeline.restoration import restore

LINES = ["INVOICE No. 2026-0042", "Billed to: Acme Corp", "Total due: $1,337.00"]


def _bad_photo() -> bytes:
    """A clean text page, then degraded: rotated (skew) + noise + a shadow gradient."""
    page = Image.new("L", (1000, 1400), color=245)
    draw = ImageDraw.Draw(page)
    for i, line in enumerate(LINES):
        draw.text((120, 200 + i * 90), line, fill=15)
    img = np.array(page)

    # skew ~7°
    h, w = img.shape
    m = cv2.getRotationMatrix2D((w / 2, h / 2), 7.0, 1.0)
    img = cv2.warpAffine(img, m, (w, h), borderValue=235)
    # diagonal shadow
    grad = np.tile(np.linspace(0, 60, w, dtype=np.float64), (h, 1))
    img = np.clip(img.astype(np.float64) - grad, 0, 255).astype(np.uint8)
    # speckle noise
    rng = np.random.default_rng(0)
    img = np.clip(img.astype(np.int16) + rng.integers(-18, 18, img.shape), 0, 255).astype(np.uint8)

    ok, buf = cv2.imencode(".png", img)
    assert ok
    return buf.tobytes()


def _decode_gray(b: bytes) -> np.ndarray:
    arr = cv2.imdecode(np.frombuffer(b, np.uint8), cv2.IMREAD_GRAYSCALE)
    assert arr is not None
    return arr


def _fake_words() -> list[dict]:
    """OCR-shaped boxes (normalized 0–1) over where the text lines sit."""
    words = []
    for i, line in enumerate(LINES):
        y0 = (200 + i * 90) / 1400
        y1 = (200 + i * 90 + 40) / 1400
        box = [[0.10, y0], [0.70, y0], [0.70, y1], [0.10, y1]]
        words.append({"text": line, "confidence": 0.97, "box": box})
    return words


def test_restore_produces_clean_page():
    out = restore(_bad_photo())
    gray = _decode_gray(out)
    assert gray.ndim == 2 and gray.size > 0
    # restoration should flatten the page toward white (background dominates)
    white_frac = float((gray >= 250).mean())
    assert white_frac > 0.5, f"page not flattened (white_frac={white_frac:.2f})"


def test_ocr_contract_and_graceful_degrade():
    out = restore(_bad_photo())
    result = run_ocr(out)
    assert set(result) == {"words", "languages", "imageSize"}
    gray = _decode_gray(out)
    assert result["imageSize"] == {"width": gray.shape[1], "height": gray.shape[0]}
    # PaddleOCR isn't installed in this env -> stage degrades, never raises.
    assert result["words"] == [] and result["languages"] == []


def test_whiten_background_cleans_outside_text():
    page = _bad_photo()
    before = _decode_gray(page)
    cleaned = whiten_background(page, _fake_words())
    after = _decode_gray(cleaned)
    assert after.shape == before.shape
    # more pure-white pixels after masking the background to 255
    assert int((after == 255).sum()) > int((before == 255).sum())
    # and with no words it's a no-op (returns input unchanged)
    assert whiten_background(page, []) == page


def test_searchable_pdf_text_layer_is_extractable():
    pdf = searchable_pdf(restore(_bad_photo()), _fake_words())
    assert pdf[:5] == b"%PDF-"
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(pdf))
    assert len(reader.pages) == 1
    text = reader.pages[0].extract_text() or ""
    for line in LINES:
        assert line in text, f"missing from text layer: {line!r}\n--- got ---\n{text}"


def test_image_only_pdf_fallback():
    pdf = image_to_pdf(restore(_bad_photo()))
    assert pdf[:5] == b"%PDF-"
    from pypdf import PdfReader

    assert len(PdfReader(io.BytesIO(pdf)).pages) == 1


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL  {t.__name__}: {exc}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    raise SystemExit(1 if failed else 0)
