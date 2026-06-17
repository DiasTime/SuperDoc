"""Concrete pipeline stages.

M1.1 (implemented): ImageRestoration + Reconstruction (image -> clean PDF).
M1.2 (implemented): Ocr (PaddleOCR) -> text-mask cleanup -> searchable PDF.
M2   (implemented): DocumentUnderstanding (Qwen-VL via Ollama/vLLM) -> typed
      DocumentStructure + JSON export + DOCX export + structure-aware rich PDF.
"""

from __future__ import annotations

import logging

from worker import db, storage
from worker.config import settings
from worker.pipeline.base import PipelineContext, Stage
from worker.pipeline.ocr import run_ocr
from worker.pipeline.reconstruct import (
    image_to_pdf,
    searchable_pdf,
    structure_to_docx,
    structure_to_json,
    structure_to_rich_pdf,
)
from worker.pipeline.restoration import restore
from worker.pipeline.vl import EMPTY_STRUCTURE, understand

log = logging.getLogger("worker.pipeline")


class ImageRestoration(Stage):
    """OpenCV: perspective correction, denoise, shadow removal, contrast, deskew."""

    status = "RESTORING"
    name = "image_restoration"

    def run(self, ctx: PipelineContext) -> PipelineContext:
        raw = storage.get_bytes(ctx.source_key)
        cleaned = restore(raw, max_side=settings.restore_max_side, mode=settings.restore_mode)
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
        # NB: we deliberately do NOT whiten outside the text mask — restoration
        # already flattens the background, and mask-whitening shreds photos/maps
        # (their light areas have no OCR boxes, so they get blown to noisy white).
        # The clean restored page is what reconstruction draws under the text layer.
        log.info(
            "ocr done",
            extra={"document_id": ctx.document_id, "words": len(ctx.ocr["words"])},
        )
        return ctx


class DocumentUnderstanding(Stage):
    """Qwen-VL (Ollama/vLLM): restored page + OCR -> typed DocumentStructure (M2).

    Degrades to an UNKNOWN structure if the VL endpoint is unavailable, so the
    job still finishes with a (searchable) PDF.
    """

    status = "UNDERSTANDING"
    name = "understanding"

    def run(self, ctx: PipelineContext) -> PipelineContext:
        structure = dict(EMPTY_STRUCTURE)
        if ctx.restored_image_keys:
            image = storage.get_bytes(ctx.restored_image_keys[0])
            structure = understand(image, ctx.ocr)
        ctx.structure = structure

        db.set_understanding(
            ctx.document_id,
            doc_type=structure.get("type", "UNKNOWN"),
            title=structure.get("title"),
            summary=structure.get("summary"),
            structure=structure,
            metadata=structure.get("metadata") or {},
        )
        log.info(
            "understanding done",
            extra={
                "document_id": ctx.document_id,
                "doc_type": structure.get("type"),
                "sections": len(structure.get("sections", [])),
            },
        )
        return ctx


class Reconstruction(Stage):
    """Restored page -> PDF + DOCX + JSON artifacts (M2: structure-aware)."""

    status = "RECONSTRUCTING"
    name = "reconstruction"

    def run(self, ctx: PipelineContext) -> PipelineContext:
        if not ctx.restored_image_keys:
            raise RuntimeError("no restored image to reconstruct from")
        image = storage.get_bytes(ctx.restored_image_keys[0])
        words = (ctx.ocr or {}).get("words", [])

        # PDF: prefer structure-aware WeasyPrint render; fall back to searchable image PDF.
        pdf: bytes | None = None
        if ctx.structure is not None:
            pdf = structure_to_rich_pdf(ctx.structure)
            if pdf:
                log.info("used rich PDF (WeasyPrint)", extra={"document_id": ctx.document_id})
        if not pdf:
            pdf = searchable_pdf(image, words) if words else image_to_pdf(image)
        pdf_key = f"exports/{ctx.document_id}/document.pdf"
        storage.put_bytes(pdf_key, pdf, "application/pdf")
        db.add_export(ctx.document_id, "PDF", pdf_key, len(pdf))
        ctx.export_keys["PDF"] = pdf_key
        log.info("reconstructed pdf", extra={"document_id": ctx.document_id, "bytes": len(pdf)})

        if ctx.structure is not None:
            # Structured JSON export (M2).
            blob = structure_to_json(ctx.structure)
            json_key = f"exports/{ctx.document_id}/document.json"
            storage.put_bytes(json_key, blob, "application/json")
            db.add_export(ctx.document_id, "JSON", json_key, len(blob))
            ctx.export_keys["JSON"] = json_key
            log.info("reconstructed json", extra={"document_id": ctx.document_id, "bytes": len(blob)})

            # DOCX export (M2).
            docx = structure_to_docx(ctx.structure)
            if docx:
                docx_key = f"exports/{ctx.document_id}/document.docx"
                mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                storage.put_bytes(docx_key, docx, mime)
                db.add_export(ctx.document_id, "DOCX", docx_key, len(docx))
                ctx.export_keys["DOCX"] = docx_key
                log.info("reconstructed docx", extra={"document_id": ctx.document_id, "bytes": len(docx)})

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
