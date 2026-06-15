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

    # Self-hosted Qwen2.5-VL 7B via OpenAI-compatible vLLM server
    vl_model_name: str = "Qwen/Qwen2.5-VL-7B-Instruct"
    vl_endpoint: str = "http://vllm:8001/v1"
    vl_max_tokens: int = 4096


settings = Settings()
