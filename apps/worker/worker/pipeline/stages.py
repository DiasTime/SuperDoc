"""Concrete pipeline stages.

M1.1 (implemented): ImageRestoration + Reconstruction (image -> clean PDF).
M1.2: Ocr (PaddleOCR) -> searchable PDF.
M2:   DocumentUnderstanding (Qwen2.5-VL) + rich, structure-aware reconstruction.

OCR and Understanding are currently pass-throughs so the full async pipe runs
end-to-end; they get real bodies in their milestones.
"""

from __future__ import annotations

import logging

from worker import db, storage
from worker.pipeline.base import PipelineContext, Stage
from worker.pipeline.reconstruct import image_to_pdf
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
    """PaddleOCR: text + boxes + confidence (M1.2). Pass-through for now."""

    status = "OCR"
    name = "ocr"

    def run(self, ctx: PipelineContext) -> PipelineContext:
        log.info("ocr (pass-through, M1.2)", extra={"document_id": ctx.document_id})
        ctx.ocr = {"words": [], "languages": [], "imageSize": {"width": 0, "height": 0}}
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
        pdf = image_to_pdf(image)
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
