"""Worker entrypoint: consume job payloads from Redis and run the pipeline.

Payload (JSON, pushed by the API): {"document_id": "...", "source_key": "..."}
Each stage transition is written to processing_jobs so the frontend can show
live progress.
"""

from __future__ import annotations

import json
import logging
import signal
import sys
from types import FrameType

import redis

from worker import db
from worker.config import settings
from worker.pipeline import STAGE_PROGRESS, PipelineContext, build_default_pipeline

logging.basicConfig(level=settings.log_level.upper(), format="%(message)s")
log = logging.getLogger("worker")

_running = True


def _stop(signum: int, frame: FrameType | None) -> None:
    global _running
    log.info("shutdown signal received", extra={"signal": signum})
    _running = False


def process_job(document_id: str, source_key: str) -> None:
    log.info("job start", extra={"document_id": document_id})
    try:
        db.start_job(document_id)
        ctx = PipelineContext(document_id=document_id, source_key=source_key)
        for stage in build_default_pipeline():
            db.set_status(document_id, stage.status, STAGE_PROGRESS.get(stage.status, 0))
            ctx = stage.timed(ctx)
        db.complete_job(document_id, ctx.stage_timings)
        log.info("job complete", extra={"document_id": document_id, "timings": ctx.stage_timings})
    except Exception as exc:  # noqa: BLE001 — top-level job guard
        log.exception("job failed", extra={"document_id": document_id})
        db.fail_job(document_id, str(exc))


def main() -> int:
    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    client = redis.Redis.from_url(settings.redis_url)
    client.ping()
    log.info("worker ready", extra={"queue": settings.queue_name})

    while _running:
        try:
            item = client.blpop([settings.queue_name], timeout=5)
        except redis.exceptions.TimeoutError:
            # RESP3: an empty blocking pop surfaces as a socket timeout, not None
            continue
        if item is None:
            continue
        _, payload = item
        try:
            data = json.loads(payload)
            process_job(data["document_id"], data["source_key"])
        except (json.JSONDecodeError, KeyError):
            log.error("bad job payload", extra={"payload": payload[:200].decode("utf-8", "replace")})

    log.info("worker stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
