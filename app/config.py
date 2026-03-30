from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


DEFAULT_LANGDOCK_API_URL = "https://api.langdock.com/openai/eu/v1/chat/completions"
DEFAULT_LANGDOCK_MODEL = "gpt-5.4"
DEFAULT_DATABASE_URL = "sqlite:///./ppt_corrector.db"
DEFAULT_REDIS_URL = "redis://localhost:6379/0"
DEFAULT_S3_PREFIX = "ppt-corrector"


@dataclass(frozen=True)
class Settings:
    api_key: str
    langdock_api_key: str
    langdock_api_url: str = DEFAULT_LANGDOCK_API_URL
    langdock_model: str = DEFAULT_LANGDOCK_MODEL
    port: int = 8000
    min_text_length: int = 3
    llm_timeout_seconds: float = 60.0
    max_upload_size_bytes: int = 50 * 1024 * 1024
    job_ttl_seconds: int = 60 * 60
    job_cleanup_interval_seconds: int = 60
    metadata_retention_seconds: int = 7 * 24 * 60 * 60
    default_highlight_color: str = "FFFF00"
    database_url: str = DEFAULT_DATABASE_URL
    queue_backend: str = "inline"
    redis_url: str = DEFAULT_REDIS_URL
    rq_queue_name: str = "ppt-corrector"
    storage_backend: str = "memory"
    s3_bucket: str = ""
    s3_region: str = "eu-central-1"
    s3_endpoint_url: str = ""
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    s3_prefix: str = DEFAULT_S3_PREFIX

    @classmethod
    def from_env(cls) -> "Settings":
        api_key = os.getenv("API_KEY", "").strip()
        langdock_api_key = os.getenv("LANGDOCK_API_KEY", "").strip()

        if not api_key:
            raise ValueError("API_KEY not set. Add it to .env or export it.")
        if not langdock_api_key:
            raise ValueError("LANGDOCK_API_KEY not set. Add it to .env or export it.")

        settings = cls(
            api_key=api_key,
            langdock_api_key=langdock_api_key,
            langdock_api_url=os.getenv("LANGDOCK_API_URL", DEFAULT_LANGDOCK_API_URL).strip(),
            langdock_model=os.getenv("LANGDOCK_MODEL", DEFAULT_LANGDOCK_MODEL).strip(),
            port=int(os.getenv("PORT", "8000")),
            min_text_length=int(os.getenv("MIN_TEXT_LENGTH", "3")),
            llm_timeout_seconds=float(os.getenv("LLM_TIMEOUT_SECONDS", "60")),
            max_upload_size_bytes=int(os.getenv("MAX_UPLOAD_SIZE_BYTES", str(50 * 1024 * 1024))),
            job_ttl_seconds=int(os.getenv("JOB_TTL_SECONDS", str(60 * 60))),
            job_cleanup_interval_seconds=int(os.getenv("JOB_CLEANUP_INTERVAL_SECONDS", "60")),
            metadata_retention_seconds=int(
                os.getenv("METADATA_RETENTION_SECONDS", str(7 * 24 * 60 * 60))
            ),
            default_highlight_color=os.getenv("DEFAULT_HIGHLIGHT_COLOR", "FFFF00").strip(),
            database_url=os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL).strip(),
            queue_backend=os.getenv("QUEUE_BACKEND", "inline").strip().lower(),
            redis_url=os.getenv("REDIS_URL", DEFAULT_REDIS_URL).strip(),
            rq_queue_name=os.getenv("RQ_QUEUE_NAME", "ppt-corrector").strip(),
            storage_backend=os.getenv("STORAGE_BACKEND", "memory").strip().lower(),
            s3_bucket=os.getenv("S3_BUCKET", "").strip(),
            s3_region=os.getenv("S3_REGION", "eu-central-1").strip(),
            s3_endpoint_url=os.getenv("S3_ENDPOINT_URL", "").strip(),
            s3_access_key_id=os.getenv("S3_ACCESS_KEY_ID", "").strip(),
            s3_secret_access_key=os.getenv("S3_SECRET_ACCESS_KEY", "").strip(),
            s3_prefix=os.getenv("S3_PREFIX", DEFAULT_S3_PREFIX).strip(),
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        if self.queue_backend not in {"inline", "redis"}:
            raise ValueError("QUEUE_BACKEND must be 'inline' or 'redis'.")
        if self.storage_backend not in {"memory", "s3"}:
            raise ValueError("STORAGE_BACKEND must be 'memory' or 's3'.")
        if self.job_ttl_seconds < 60:
            raise ValueError("JOB_TTL_SECONDS must be at least 60.")
        if self.storage_backend == "s3" and not self.s3_bucket:
            raise ValueError("S3_BUCKET is required when STORAGE_BACKEND=s3.")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_env()
