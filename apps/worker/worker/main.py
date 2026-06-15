"""Worker entrypoint: consume job IDs from Redis and run the pipeline.

M0: connects to Redis, blocks on the job queue, runs the no-op pipeline, logs
progress. M1 adds Postgres status writes + object-store I/O.
"""

from __future__ import annotations

import logging
import signal
import sys
from types import FrameType

import redis

from worker.config import settings
from worker.pipeline import PipelineContext, build_default_pipeline

logging.basicConfig(level=settings.log_level.upper(), format="%(message)s")
log = logging.getLogger("worker")

_running = True


def _stop(signum: int, frame: FrameType | None) -> None:
    global _running
    log.info("shutdown signal received", extra={"signal": signum})
    _running = False


def process_job(document_id: str, source_key: str) -> None:
    ctx = PipelineContext(document_id=document_id, source_key=source_key)
    for stage in build_default_pipeline():
        # M1: update processing_jobs.status = stage.status here
        log.info("stage start", extra={"document_id": document_id, "stage": stage.name})
        ctx = stage.timed(ctx)
    log.info(
        "job complete",
        extra={"document_id": document_id, "timings": ctx.stage_timings},
    )


def main() -> int:
    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    client = redis.Redis.from_url(settings.redis_url)
    client.ping()
    log.info("worker ready", extra={"queue": settings.queue_name})

    while _running:
        # BLPOP returns (queue, payload) or None on timeout.
        item = client.blpop([settings.queue_name], timeout=5)
        if item is None:
            continue
        _, payload = item
        # M1: payload is JSON {document_id, source_key}; for M0 treat as id.
        document_id = payload.decode()
        process_job(document_id, source_key=f"uploads/{document_id}")

    log.info("worker stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
