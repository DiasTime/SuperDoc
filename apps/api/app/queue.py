"""Redis job queue producer."""

from __future__ import annotations

import json

import redis

from app.config import settings

_client = redis.Redis.from_url(settings.redis_url)


def enqueue(document_id: str, source_key: str) -> None:
    _client.rpush(
        settings.queue_name,
        json.dumps({"document_id": document_id, "source_key": source_key}),
    )
