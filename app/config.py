from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


DEFAULT_LANGDOCK_API_URL = "https://api.langdock.com/anthropic/eu/v1/messages"
DEFAULT_LANGDOCK_MODEL = "claude-sonnet-4-5-20250929"


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
    job_ttl_seconds: int = 10 * 60
    job_cleanup_interval_seconds: int = 60
    default_highlight_color: str = "FFFF00"

    @classmethod
    def from_env(cls) -> "Settings":
        api_key = os.getenv("API_KEY", "").strip()
        langdock_api_key = os.getenv("LANGDOCK_API_KEY", "").strip()

        if not api_key:
            raise ValueError("API_KEY not set. Add it to .env or export it.")
        if not langdock_api_key:
            raise ValueError("LANGDOCK_API_KEY not set. Add it to .env or export it.")

        return cls(
            api_key=api_key,
            langdock_api_key=langdock_api_key,
            langdock_api_url=os.getenv("LANGDOCK_API_URL", DEFAULT_LANGDOCK_API_URL).strip(),
            langdock_model=os.getenv("LANGDOCK_MODEL", DEFAULT_LANGDOCK_MODEL).strip(),
            port=int(os.getenv("PORT", "8000")),
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_env()

