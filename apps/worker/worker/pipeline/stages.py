"""Concrete pipeline stages.

M0: no-op skeletons that establish the contract and ordering.
M1: ImageRestoration + Ocr + (basic) Reconstruction get real implementations.
M2: DocumentUnderstanding (Qwen2.5-VL) + rich reconstruction.
"""

from __future__ import annotations

import logging

from worker.pipeline.base import PipelineContext, Stage

log = logging.getLogger("worker.pipeline")


class ImageRestoration(Stage):
    """OpenCV: denoise, shadow removal, normalize, deskew, perspective, crop."""

    status = "RESTORING"
    name = "image_restoration"

    def run(self, ctx: PipelineContext) -> PipelineContext:
        # M1: download source, run OpenCV restore pipeline, upload restored pages.
        log.info("restore (stub)", extra={"document_id": ctx.document_id})
        ctx.restored_image_keys = [ctx.source_key]
        return ctx


class Ocr(Stage):
    """PaddleOCR: text + bounding boxes + confidence, geometry preserved."""

    status = "OCR"
    name = "ocr"

    def run(self, ctx: PipelineContext) -> PipelineContext:
        # M1: run PaddleOCR over restored pages -> OcrResult.
        log.info("ocr (stub)", extra={"document_id": ctx.document_id})
        ctx.ocr = {"words": [], "languages": [], "imageSize": {"width": 0, "height": 0}}
        return ctx


class DocumentUnderstanding(Stage):
    """Qwen2.5-VL 7B (self-hosted): OCR + image -> typed structure, grounded."""

    status = "UNDERSTANDING"
    name = "understanding"

    def run(self, ctx: PipelineContext) -> PipelineContext:
        # M2: call self-hosted VL endpoint; ground every field to an OCR box.
        log.info("understanding (stub)", extra={"document_id": ctx.document_id})
        ctx.structure = {"type": "UNKNOWN", "sections": [], "signatures": [], "metadata": {}}
        return ctx


class Reconstruction(Stage):
    """Structure -> semantic HTML/CSS -> PDF + DOCX + JSON."""

    status = "RECONSTRUCTING"
    name = "reconstruction"

    def run(self, ctx: PipelineContext) -> PipelineContext:
        # M1: text -> HTML -> PDF.  M2: structure-aware templates + DOCX + JSON.
        log.info("reconstruct (stub)", extra={"document_id": ctx.document_id})
        return ctx


def build_default_pipeline() -> list[Stage]:
    return [ImageRestoration(), Ocr(), DocumentUnderstanding(), Reconstruction()]
