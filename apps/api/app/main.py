"""FastAPI gateway entrypoint.

Thin by design: auth, uploads, job CRUD, downloads. All heavy compute lives in
the worker. M1.1 wires upload -> storage + DB, /process -> queue, and download
-> presigned object-store URL.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse

from app import db, queue, storage
from app.config import settings
from app.logging import configure_logging
from app.security import sniff_image_type

configure_logging(settings.log_level)
log = logging.getLogger("api")

app = FastAPI(
    title="Document Resurrection AI",
    version="0.1.0",
    description="Bad photo in, source-quality document out.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_FORMATS = {"pdf": "PDF", "docx": "DOCX", "json": "JSON"}


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    log.exception("unhandled error", extra={"path": request.url.path})
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.get("/health", tags=["meta"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/upload", tags=["documents"], status_code=201)
async def upload(file: UploadFile) -> dict[str, str]:
    """Validate, store the raw upload, and create a document + queued job."""
    data = await file.read()
    if not data:
        raise HTTPException(400, "empty file")

    limit = settings.max_upload_mb * 1024 * 1024
    if len(data) > limit:
        raise HTTPException(413, f"file exceeds {settings.max_upload_mb} MB limit")

    content_type = sniff_image_type(data)
    if content_type is None:
        raise HTTPException(
            415, "unsupported file type (M1 accepts JPEG, PNG, WebP, TIFF, BMP)"
        )

    name = file.filename or "upload"
    doc_id, job_id = db.create_document_and_job(name, content_type, len(data), source_key="")
    source_key = f"uploads/{doc_id}/source"
    storage.put_bytes(source_key, data, content_type)
    db.set_source_key(doc_id, source_key)

    log.info("uploaded", extra={"document_id": doc_id, "bytes": len(data)})
    return {"documentId": doc_id, "jobId": job_id}


@app.post("/process/{document_id}", tags=["documents"])
async def process(document_id: str) -> dict[str, str]:
    """Enqueue the document for processing."""
    source_key = db.get_source_key(document_id)
    if not source_key:
        raise HTTPException(404, "document not found")
    queue.enqueue(document_id, source_key)
    log.info("enqueued", extra={"document_id": document_id})
    return {"status": "queued", "documentId": document_id}


@app.get("/document/{document_id}", tags=["documents"])
async def get_document(document_id: str) -> dict:
    doc = db.get_document(document_id)
    if doc is None:
        raise HTTPException(404, "document not found")
    return {
        "id": doc["id"],
        "originalName": doc["originalName"],
        "docType": doc["docType"],
        "title": doc["title"],
        "summary": doc["summary"],
        "status": doc["status"],
        "progress": doc["progress"],
        "error": doc["error"],
        "structure": doc["structure"],
        "exports": [
            {"format": e["format"], "url": f"/download/{e['format'].lower()}/{document_id}"}
            for e in doc["exports"]
        ],
        "createdAt": doc["createdAt"].isoformat(),
    }


@app.get("/download/{fmt}/{document_id}", tags=["downloads"])
async def download(fmt: str, document_id: str) -> RedirectResponse:
    canonical = _FORMATS.get(fmt.lower())
    if canonical is None:
        raise HTTPException(400, f"unknown format '{fmt}'")
    key = db.get_export_key(document_id, canonical)
    if key is None:
        raise HTTPException(404, f"{canonical} not available for this document")
    return RedirectResponse(url=storage.presigned_get(key))
