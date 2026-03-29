from __future__ import annotations

import asyncio
import base64
import time
from types import SimpleNamespace

from fastapi.testclient import TestClient

import app.main as main_module
from app.corrector import PresentationCorrectionResult
from tests.conftest import FakeLLMClient


def make_success_result() -> PresentationCorrectionResult:
    return PresentationCorrectionResult(
        file_bytes=b"PK\x03\x04" + b"0" * 200,
        file_name="proposal_corrected.pptx",
        corrections_count=2,
        total_slides=2,
        changes=[
            {"slide": 1, "original": "Teh", "corrected": "The"},
            {"slide": 2, "original": "Recieved", "corrected": "Received"},
        ],
    )


def build_test_app(test_settings):
    app = main_module.create_app(test_settings)
    app.state.process_presentation = lambda file_bytes, file_name, highlight, settings: make_success_result()
    return app


def test_healthcheck_does_not_require_auth(test_settings) -> None:
    app = build_test_app(test_settings)
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_jobs_endpoints_require_auth(test_settings, sample_pptx_base64: str) -> None:
    app = build_test_app(test_settings)
    with TestClient(app) as client:
        response = client.post(
            "/jobs",
            json={"file_base64": sample_pptx_base64, "file_name": "deck.pptx"},
        )

    assert response.status_code == 401


def test_create_and_poll_job_completion(test_settings, sample_pptx_base64: str, monkeypatch) -> None:
    app = main_module.create_app(test_settings)

    async def fake_process_job(app_obj, job_id, file_bytes, file_name, highlight):
        await asyncio.sleep(0.05)
        async with app_obj.state.jobs_lock:
            job = app_obj.state.jobs[job_id]
            job.status = "done"
            job.result_base64 = base64.b64encode(b"PK\x03\x04" + b"1" * 200).decode("utf-8")
            job.file_name = "deck_corrected.pptx"
            job.corrections_count = 2
            job.changes = [{"slide": 1, "original": "Teh", "corrected": "The"}]

    monkeypatch.setattr(main_module, "process_job", fake_process_job)

    with TestClient(app) as client:
        response = client.post(
            "/jobs?highlight=true",
            headers={"Authorization": f"Bearer {test_settings.api_key}"},
            json={"file_base64": sample_pptx_base64, "file_name": "deck.pptx"},
        )
        assert response.status_code == 202
        job_id = response.json()["job_id"]

        initial = client.get(
            f"/jobs/{job_id}",
            headers={"Authorization": f"Bearer {test_settings.api_key}"},
        )
        assert initial.status_code == 200
        assert initial.json()["status"] in {"processing", "done"}

        time.sleep(0.15)

        done = client.get(
            f"/jobs/{job_id}",
            headers={"Authorization": f"Bearer {test_settings.api_key}"},
        )

    assert done.status_code == 200
    payload = done.json()
    assert payload["status"] == "done"
    assert payload["file_name"] == "deck_corrected.pptx"
    assert payload["corrections_count"] == 2
    assert payload["file_base64"]
    assert payload["changes"][0]["slide"] == 1


def test_nonexistent_job_returns_404(test_settings) -> None:
    app = build_test_app(test_settings)
    with TestClient(app) as client:
        response = client.get(
            "/jobs/does-not-exist",
            headers={"Authorization": f"Bearer {test_settings.api_key}"},
        )

    assert response.status_code == 404


def test_invalid_base64_upload_returns_400(test_settings) -> None:
    app = build_test_app(test_settings)
    with TestClient(app) as client:
        response = client.post(
            "/jobs",
            headers={"Authorization": f"Bearer {test_settings.api_key}"},
            json={"file_base64": "not-base64", "file_name": "deck.pptx"},
        )

    assert response.status_code == 400


def test_invalid_pptx_upload_returns_400(test_settings) -> None:
    app = build_test_app(test_settings)
    payload = base64.b64encode(b"not-a-pptx").decode("utf-8")

    with TestClient(app) as client:
        response = client.post(
            "/jobs",
            headers={"Authorization": f"Bearer {test_settings.api_key}"},
            json={"file_base64": payload, "file_name": "deck.txt"},
        )

    assert response.status_code == 400


def test_llm_error_sets_job_error_status(test_settings, sample_pptx_base64: str, monkeypatch) -> None:
    app = main_module.create_app(test_settings)

    def raising_processor(file_bytes, file_name, highlight, settings):
        raise RuntimeError("LLM API error")

    app.state.process_presentation = raising_processor

    with TestClient(app) as client:
        response = client.post(
            "/jobs",
            headers={"Authorization": f"Bearer {test_settings.api_key}"},
            json={"file_base64": sample_pptx_base64, "file_name": "deck.pptx"},
        )
        assert response.status_code == 202
        job_id = response.json()["job_id"]

        time.sleep(0.1)

        job = client.get(
            f"/jobs/{job_id}",
            headers={"Authorization": f"Bearer {test_settings.api_key}"},
        )

    assert job.status_code == 200
    assert job.json()["status"] == "error"
    assert "LLM API error" in job.json()["message"]


def test_concurrent_job_creation_returns_unique_ids(test_settings, sample_pptx_base64: str, monkeypatch) -> None:
    app = main_module.create_app(test_settings)

    async def fake_process_job(app_obj, job_id, file_bytes, file_name, highlight):
        async with app_obj.state.jobs_lock:
            job = app_obj.state.jobs[job_id]
            job.status = "done"
            job.result_base64 = base64.b64encode(b"PK\x03\x04" + b"2" * 200).decode("utf-8")
            job.file_name = "parallel_corrected.pptx"
            job.corrections_count = 1
            job.changes = [{"slide": 1, "original": "Teh", "corrected": "The"}]

    monkeypatch.setattr(main_module, "process_job", fake_process_job)

    with TestClient(app) as client:
        responses = []
        for _ in range(3):
            responses.append(
                client.post(
                    "/jobs",
                    headers={"Authorization": f"Bearer {test_settings.api_key}"},
                    json={"file_base64": sample_pptx_base64, "file_name": "deck.pptx"},
                )
            )

    assert all(response.status_code == 202 for response in responses)
    job_ids = [response.json()["job_id"] for response in responses]
    assert len(set(job_ids)) == 3

