"""Worker settings — mirrors the API where infra is shared."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    log_level: str = "INFO"

    database_url: str = "postgresql://docres:docres_dev_password@postgres:5432/docres"
    redis_url: str = "redis://redis:6379/0"
    queue_name: str = "docres:jobs"

    s3_endpoint: str = "http://minio:9000"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_bucket: str = "docres"
    s3_region: str = "us-east-1"

    # Document understanding (M2): Qwen-VL behind an OpenAI-compatible endpoint.
    # Defaults target a local Ollama (`ollama pull qwen2.5vl`). Point vl_endpoint
    # at a vLLM server for production throughput — the client code is identical.
    # From inside the Docker worker the host's Ollama is host.docker.internal.
    vl_backend: str = "ollama"  # "ollama" | "vllm" (both OpenAI-compatible)
    vl_endpoint: str = "http://localhost:11434/v1"
    vl_model_name: str = "qwen2.5vl"
    vl_api_key: str = "ollama"  # Ollama ignores it; the OpenAI client needs a non-empty value
    vl_max_tokens: int = 4096
    vl_timeout: float = 180.0  # 7B VL inference is slow on CPU / consumer GPUs
    vl_enabled: bool = True  # set false to keep understanding a pass-through

    # Image restoration tuning
    restore_max_side: int = 3500  # working-resolution cap; higher = crisper small text
    # "color" (default): keep real colours — stamps/signatures/photos — paper white.
    # "gray": smooth greyscale.  "binary": crisp 1-bit B/W (pure-text pages only).
    restore_mode: str = "color"


settings = Settings()
