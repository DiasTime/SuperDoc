"""Postgres access for the API (psycopg over the Prisma-owned schema)."""

from __future__ import annotations

import uuid
from typing import Any

import psycopg
from psycopg.rows import dict_row

from app.config import settings


def gen_id() -> str:
    return "c" + uuid.uuid4().hex[:24]


def _conn() -> psycopg.Connection:
    return psycopg.connect(settings.database_url, autocommit=True)


def create_document_and_job(
    original_name: str, mime_type: str, size_bytes: int, source_key: str
) -> tuple[str, str]:
    """Insert a document + its queued job in one transaction. Returns (doc_id, job_id)."""
    doc_id = gen_id()
    job_id = gen_id()
    with psycopg.connect(settings.database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                'INSERT INTO documents '
                '(id, "originalName", "mimeType", "sizeBytes", "sourceKey", "updatedAt") '
                "VALUES (%s, %s, %s, %s, %s, now())",
                (doc_id, original_name, mime_type, size_bytes, source_key),
            )
            cur.execute(
                'INSERT INTO processing_jobs (id, "documentId", "updatedAt") '
                "VALUES (%s, %s, now())",
                (job_id, doc_id),
            )
        conn.commit()
    return doc_id, job_id


def get_document(document_id: str) -> dict[str, Any] | None:
    with _conn() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                'SELECT d.id, d."originalName", d."docType", d.title, d.summary, '
                '       d."createdAt", j.status, j.progress, j.error '
                "FROM documents d "
                'JOIN processing_jobs j ON j."documentId" = d.id '
                "WHERE d.id = %s",
                (document_id,),
            )
            doc = cur.fetchone()
            if doc is None:
                return None
            cur.execute(
                'SELECT format, "artifactKey" FROM exports WHERE "documentId" = %s',
                (document_id,),
            )
            doc["exports"] = cur.fetchall()
            return doc


def set_source_key(document_id: str, source_key: str) -> None:
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                'UPDATE documents SET "sourceKey" = %s, "updatedAt" = now() WHERE id = %s',
                (source_key, document_id),
            )


def get_source_key(document_id: str) -> str | None:
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT "sourceKey" FROM documents WHERE id = %s', (document_id,))
            row = cur.fetchone()
            return row[0] if row else None


def get_export_key(document_id: str, fmt: str) -> str | None:
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                'SELECT "artifactKey" FROM exports '
                'WHERE "documentId" = %s AND format = %s::"ExportFormat"',
                (document_id, fmt),
            )
            row = cur.fetchone()
            return row[0] if row else None
