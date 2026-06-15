"""FastAPI gateway entrypoint.

Thin by design: auth, uploads, job CRUD, downloads. All heavy compute lives in
the worker. Endpoints below are M0 stubs; M1 wires them to storage + the queue.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.logging import configure_logging

configure_logging(settings.log_level)
log = logging.getLogger("api")

app = FastAPI(
    title="Document Resurrection AI",
    version="0.0.0",
    description="Bad photo in, source-quality document out.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    log.exception("unhandled error", extra={"path": request.url.path})
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.get("/health", tags=["meta"])
async def health() -> dict[str, str]:
    """Liveness probe used by docker-compose and load balancers."""
    return {"status": "ok"}


# ─── M1 endpoint stubs (wired to storage + queue next) ───


@app.post("/upload", tags=["documents"], status_code=501)
async def upload() -> dict[str, str]:
    return {"detail": "not implemented (M1): store file, create document + job"}


@app.post("/process/{document_id}", tags=["documents"], status_code=501)
async def process(document_id: str) -> dict[str, str]:
    return {"detail": f"not implemented (M1): enqueue job for {document_id}"}


@app.get("/document/{document_id}", tags=["documents"], status_code=501)
async def get_document(document_id: str) -> dict[str, str]:
    return {"detail": f"not implemented (M1): status + result for {document_id}"}


@app.get("/download/{fmt}/{document_id}", tags=["downloads"], status_code=501)
async def download(fmt: str, document_id: str) -> dict[str, str]:
    return {"detail": f"not implemented (M1/M2): {fmt} for {document_id}"}
