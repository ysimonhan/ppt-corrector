from __future__ import annotations

from app.config import Settings


def test_settings_default_job_ttl_is_sixty_minutes(monkeypatch) -> None:
    monkeypatch.setenv("API_KEY", "test-api-key")
    monkeypatch.setenv("LANGDOCK_API_KEY", "test-langdock-key")
    monkeypatch.delenv("JOB_TTL_SECONDS", raising=False)
    monkeypatch.delenv("JOB_CLEANUP_INTERVAL_SECONDS", raising=False)

    settings = Settings.from_env()

    assert settings.job_ttl_seconds == 60 * 60
    assert settings.job_cleanup_interval_seconds == 60


def test_settings_allow_job_ttl_override(monkeypatch) -> None:
    monkeypatch.setenv("API_KEY", "test-api-key")
    monkeypatch.setenv("LANGDOCK_API_KEY", "test-langdock-key")
    monkeypatch.setenv("JOB_TTL_SECONDS", "1800")
    monkeypatch.setenv("JOB_CLEANUP_INTERVAL_SECONDS", "30")

    settings = Settings.from_env()

    assert settings.job_ttl_seconds == 1800
    assert settings.job_cleanup_interval_seconds == 30
