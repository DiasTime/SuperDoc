"""Postgres access for the worker.

The schema is owned by Prisma (TypeScript side). Python talks to the same tables
directly via psycopg. Column names are camelCase (Prisma default) so they must be
double-quoted. Enum columns are cast explicitly to their Postgres enum type.
"""

from __future__ import annotations

import uuid
from typing import Any

import psycopg
from psycopg.types.json import Json

from worker.config import settings


def gen_id() -> str:
    """Collision-resistant id (Prisma cuids are generated client-side; we mint
    our own for rows inserted from Python)."""
    return "c" + uuid.uuid4().hex[:24]


def _conn() -> psycopg.Connection:
    return psycopg.connect(settings.database_url, autocommit=True)


def start_job(document_id: str) -> None:
    with _conn() as c:
        c.execute(
            'UPDATE processing_jobs '
            'SET status=%s::"JobStatus", progress=%s, "startedAt"=now(), "updatedAt"=now() '
            'WHERE "documentId"=%s',
            ("RESTORING", 10, document_id),
        )


def set_status(document_id: str, status: str, progress: int) -> None:
    with _conn() as c:
        c.execute(
            'UPDATE processing_jobs '
            'SET status=%s::"JobStatus", progress=%s, "updatedAt"=now() '
            'WHERE "documentId"=%s',
            (status, progress, document_id),
        )


def complete_job(document_id: str, stage_timings: dict[str, Any]) -> None:
    with _conn() as c:
        c.execute(
            'UPDATE processing_jobs '
            'SET status=%s::"JobStatus", progress=100, "finishedAt"=now(), '
            '    "stageTimings"=%s, "updatedAt"=now() '
            'WHERE "documentId"=%s',
            ("COMPLETED", Json(stage_timings), document_id),
        )


def fail_job(document_id: str, error: str) -> None:
    with _conn() as c:
        c.execute(
            'UPDATE processing_jobs '
            'SET status=%s::"JobStatus", error=%s, "finishedAt"=now(), "updatedAt"=now() '
            'WHERE "documentId"=%s',
            ("FAILED", error[:2000], document_id),
        )


def set_understanding(
    document_id: str,
    doc_type: str,
    title: str | None,
    summary: str | None,
    structure: dict[str, Any],
    metadata: dict[str, Any],
) -> None:
    """Persist the understanding-stage output onto the document row (M2)."""
    with _conn() as c:
        c.execute(
            'UPDATE documents '
            'SET "docType"=%s::"DocumentType", title=%s, summary=%s, '
            '    structure=%s, metadata=%s, "updatedAt"=now() '
            "WHERE id=%s",
            (doc_type, title, summary, Json(structure), Json(metadata), document_id),
        )


def add_export(document_id: str, fmt: str, artifact_key: str, size_bytes: int) -> None:
    """Idempotent upsert keyed on (documentId, format)."""
    with _conn() as c:
        c.execute(
            'INSERT INTO exports (id, "documentId", format, "artifactKey", "sizeBytes") '
            'VALUES (%s, %s, %s::"ExportFormat", %s, %s) '
            'ON CONFLICT ("documentId", format) '
            'DO UPDATE SET "artifactKey"=EXCLUDED."artifactKey", "sizeBytes"=EXCLUDED."sizeBytes"',
            (gen_id(), document_id, fmt, artifact_key, size_bytes),
        )


def set_document_pages(document_id: str, page_count: int) -> None:
    with _conn() as c:
        c.execute(
            'UPDATE documents SET "pageCount"=%s, "updatedAt"=now() WHERE id=%s',
            (page_count, document_id),
        )
