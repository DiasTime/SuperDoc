"""Concrete pipeline stages.

M1.1 (implemented): ImageRestoration + Reconstruction (image -> clean PDF).
M1.2 (implemented): Ocr (PaddleOCR) -> text-mask cleanup -> searchable PDF.
M2:   DocumentUnderstanding (Qwen2.5-VL) + rich, structure-aware reconstruction.

Understanding is still a pass-through so the full async pipe runs end-to-end;
it gets a real body in M2.
"""

from __future__ import annotations

import logging

from worker import db, storage
from worker.pipeline.base import PipelineContext, Stage
from worker.pipeline.ocr import run_ocr, whiten_background
from worker.pipeline.reconstruct import image_to_pdf, searchable_pdf
from worker.pipeline.restoration import restore

log = logging.getLogger("worker.pipeline")


class ImageRestoration(Stage):
    """OpenCV: perspective correction, denoise, shadow removal, contrast, deskew."""

    status = "RESTORING"
    name = "image_restoration"

    def run(self, ctx: PipelineContext) -> PipelineContext:
        raw = storage.get_bytes(ctx.source_key)
        cleaned = restore(raw)
        restored_key = f"restored/{ctx.document_id}/page-1.png"
        storage.put_bytes(restored_key, cleaned, "image/png")
        ctx.restored_image_keys = [restored_key]
        db.set_document_pages(ctx.document_id, 1)
        log.info("restored", extra={"document_id": ctx.document_id, "key": restored_key})
        return ctx


class Ocr(Stage):
    """PaddleOCR: text + boxes + confidence, then text-mask background cleanup."""

    status = "OCR"
    name = "ocr"

    def run(self, ctx: PipelineContext) -> PipelineContext:
        if not ctx.restored_image_keys:
            raise RuntimeError("no restored image to OCR")
        image = storage.get_bytes(ctx.restored_image_keys[0])
        ctx.ocr = run_ocr(image)

        # OCR-driven background removal: whiten everything outside the text mask.
        # Same geometry as the input, so the boxes stay valid for the text layer.
        cleaned = whiten_background(image, ctx.ocr["words"])
        clean_key = f"restored/{ctx.document_id}/page-1-clean.png"
        storage.put_bytes(clean_key, cleaned, "image/png")
        ctx.restored_image_keys = [clean_key]

        log.info(
            "ocr done",
            extra={"document_id": ctx.document_id, "words": len(ctx.ocr["words"])},
        )
        return ctx


class DocumentUnderstanding(Stage):
    """Qwen2.5-VL 7B (self-hosted): typed structure (M2). Pass-through for now."""

    status = "UNDERSTANDING"
    name = "understanding"

    def run(self, ctx: PipelineContext) -> PipelineContext:
        log.info("understanding (pass-through, M2)", extra={"document_id": ctx.document_id})
        ctx.structure = {"type": "UNKNOWN", "sections": [], "signatures": [], "metadata": {}}
        return ctx


class Reconstruction(Stage):
    """Restored page -> clean PDF artifact."""

    status = "RECONSTRUCTING"
    name = "reconstruction"

    def run(self, ctx: PipelineContext) -> PipelineContext:
        if not ctx.restored_image_keys:
            raise RuntimeError("no restored image to reconstruct from")
        image = storage.get_bytes(ctx.restored_image_keys[0])
        words = (ctx.ocr or {}).get("words", [])
        pdf = searchable_pdf(image, words) if words else image_to_pdf(image)
        pdf_key = f"exports/{ctx.document_id}/document.pdf"
        storage.put_bytes(pdf_key, pdf, "application/pdf")
        db.add_export(ctx.document_id, "PDF", pdf_key, len(pdf))
        ctx.export_keys["PDF"] = pdf_key
        log.info("reconstructed pdf", extra={"document_id": ctx.document_id, "bytes": len(pdf)})
        return ctx


def build_default_pipeline() -> list[Stage]:
    return [ImageRestoration(), Ocr(), DocumentUnderstanding(), Reconstruction()]


# progress % shown to the user as each stage starts
STAGE_PROGRESS = {
    "RESTORING": 25,
    "OCR": 50,
    "UNDERSTANDING": 70,
    "RECONSTRUCTING": 90,
}
