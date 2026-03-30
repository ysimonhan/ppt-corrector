from __future__ import annotations

import base64
from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.entities import AuditEventEntity, JobEntity
from app.main import create_app
from app.worker_tasks import cleanup_expired_content, process_job


def build_client(runtime):
    app = create_app(runtime=runtime)
    return TestClient(app)


def test_healthcheck_does_not_require_auth(runtime) -> None:
    with build_client(runtime) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_auth_validate_requires_auth(runtime) -> None:
    with build_client(runtime) as client:
        response = client.get("/auth/validate")

    assert response.status_code == 401


def test_auth_validate_returns_ok(runtime) -> None:
    with build_client(runtime) as client:
        response = client.get(
            "/auth/validate",
            headers={"Authorization": f"Bearer {runtime.settings.api_key}"},
        )

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_jobs_endpoints_require_auth(runtime, sample_pptx_base64: str) -> None:
    with build_client(runtime) as client:
        response = client.post(
            "/jobs",
            json={"file_base64": sample_pptx_base64, "file_name": "deck.pptx"},
        )

    assert response.status_code == 401


def test_create_job_persists_metadata_and_enqueues(runtime, recording_queue, sample_pptx_base64: str) -> None:
    with build_client(runtime) as client:
        response = client.post(
            "/jobs?highlight=true",
            headers={"Authorization": f"Bearer {runtime.settings.api_key}"},
            json={"file_base64": sample_pptx_base64, "file_name": "deck.pptx"},
        )

    assert response.status_code == 202
    job_id = response.json()["job_id"]
    assert recording_queue.job_ids == [job_id]

    with runtime.session_factory() as session:
        job = session.get(JobEntity, job_id)
        assert job is not None
        assert job.status == "queued"
        assert job.highlight is True
        assert job.file_name == "deck.pptx"

        events = session.scalars(
            select(AuditEventEntity).where(AuditEventEntity.job_id == job_id)
        ).all()
        assert [event.event_type for event in events] == ["job_created"]


def test_create_and_process_job_completion(runtime, sample_pptx_base64: str) -> None:
    with build_client(runtime) as client:
        response = client.post(
            "/jobs",
            headers={"Authorization": f"Bearer {runtime.settings.api_key}"},
            json={"file_base64": sample_pptx_base64, "file_name": "deck.pptx"},
        )
        job_id = response.json()["job_id"]

        processing = client.get(
            f"/jobs/{job_id}",
            headers={"Authorization": f"Bearer {runtime.settings.api_key}"},
        )

        process_job(job_id, runtime)

        done = client.get(
            f"/jobs/{job_id}",
            headers={"Authorization": f"Bearer {runtime.settings.api_key}"},
        )

    assert processing.status_code == 200
    assert processing.json() == {"status": "processing"}

    assert done.status_code == 200
    payload = done.json()
    assert payload["status"] == "done"
    assert payload["file_name"] == "deck_corrected.pptx"
    assert payload["corrections_count"] == 2
    assert len(payload["changes"]) == 2
    assert base64.b64decode(payload["file_base64"])[:4] == b"PK\x03\x04"


def test_nonexistent_job_returns_404(runtime) -> None:
    with build_client(runtime) as client:
        response = client.get(
            "/jobs/does-not-exist",
            headers={"Authorization": f"Bearer {runtime.settings.api_key}"},
        )

    assert response.status_code == 404


def test_invalid_base64_upload_returns_400(runtime) -> None:
    with build_client(runtime) as client:
        response = client.post(
            "/jobs",
            headers={"Authorization": f"Bearer {runtime.settings.api_key}"},
            json={"file_base64": "not-base64", "file_name": "deck.pptx"},
        )

    assert response.status_code == 400


def test_invalid_pptx_upload_returns_400(runtime) -> None:
    payload = base64.b64encode(b"not-a-pptx").decode("utf-8")

    with build_client(runtime) as client:
        response = client.post(
            "/jobs",
            headers={"Authorization": f"Bearer {runtime.settings.api_key}"},
            json={"file_base64": payload, "file_name": "deck.txt"},
        )

    assert response.status_code == 400


def test_worker_failure_sets_job_error_and_audit(runtime, sample_pptx_base64: str) -> None:
    runtime.llm_client_factory = lambda: (_ for _ in ()).throw(RuntimeError("LLM init failed"))

    with build_client(runtime) as client:
        response = client.post(
            "/jobs",
            headers={"Authorization": f"Bearer {runtime.settings.api_key}"},
            json={"file_base64": sample_pptx_base64, "file_name": "deck.pptx"},
        )
        job_id = response.json()["job_id"]

        process_job(job_id, runtime)

        job = client.get(
            f"/jobs/{job_id}",
            headers={"Authorization": f"Bearer {runtime.settings.api_key}"},
        )

    assert job.status_code == 200
    assert job.json()["status"] == "error"
    assert "LLM init failed" in job.json()["message"]

    with runtime.session_factory() as session:
        events = session.scalars(
            select(AuditEventEntity).where(AuditEventEntity.job_id == job_id)
        ).all()
        assert [event.event_type for event in events] == [
            "job_created",
            "job_processing_started",
            "job_failed",
        ]


def test_cleanup_expired_content_deletes_objects(runtime, sample_pptx_base64: str, memory_storage) -> None:
    with build_client(runtime) as client:
        response = client.post(
            "/jobs",
            headers={"Authorization": f"Bearer {runtime.settings.api_key}"},
            json={"file_base64": sample_pptx_base64, "file_name": "deck.pptx"},
        )
        job_id = response.json()["job_id"]

    process_job(job_id, runtime)

    with runtime.session_factory() as session:
        job = session.get(JobEntity, job_id)
        job.expires_at = job.expires_at - timedelta(hours=2)
        session.commit()
        input_key = job.input_object_key
        output_key = job.output_object_key

    deleted = cleanup_expired_content(runtime)

    assert deleted == 1
    assert input_key not in memory_storage.objects
    assert output_key not in memory_storage.objects

    with runtime.session_factory() as session:
        job = session.get(JobEntity, job_id)
        assert job.content_deleted_at is not None
