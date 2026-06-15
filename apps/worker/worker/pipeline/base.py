"""Pipeline abstractions.

A job flows through an ordered list of Stages. Each stage reads/writes a shared
PipelineContext and reports the JobStatus it represents, so the worker can push
progress updates to Postgres as it advances. Stages are intentionally small and
independently testable — that is how we hit the 95%+ processing target: each
stage gets its own fixture corpus.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class PipelineContext:
    """Carries state between stages for a single document."""

    document_id: str
    source_key: str  # object-store key of the raw upload

    # filled in progressively by stages
    restored_image_keys: list[str] = field(default_factory=list)
    ocr: dict[str, Any] | None = None
    structure: dict[str, Any] | None = None
    export_keys: dict[str, str] = field(default_factory=dict)  # format -> key
    stage_timings: dict[str, float] = field(default_factory=dict)


class Stage(ABC):
    """One step of the reconstruction pipeline."""

    #: JobStatus value this stage maps to (kept as a plain str to avoid coupling
    #: the worker to the API's enum import path).
    status: str = "QUEUED"
    name: str = "stage"

    @abstractmethod
    def run(self, ctx: PipelineContext) -> PipelineContext:
        """Transform the context. Must be idempotent where possible."""

    def timed(self, ctx: PipelineContext) -> PipelineContext:
        start = time.perf_counter()
        ctx = self.run(ctx)
        ctx.stage_timings[self.name] = round(time.perf_counter() - start, 3)
        return ctx
