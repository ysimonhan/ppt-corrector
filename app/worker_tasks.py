from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.corrector import correct_presentation_bytes
from app.entities import AuditEventEntity, JobEntity
from app.runtime import AppRuntime, build_runtime


logger = logging.getLogger(__name__)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def make_input_object_key(job_id: str, file_name: str) -> str:
    return f"jobs/{job_id}/input/{file_name}"


def make_output_object_key(job_id: str, file_name: str) -> str:
    return f"jobs/{job_id}/output/{file_name}"


def record_audit_event(
    session,
    *,
    event_type: str,
    job_id: str | None = None,
    actor_type: str = "system",
    actor_id: str | None = None,
    metadata: dict | None = None,
) -> None:
    session.add(
        AuditEventEntity(
            job_id=job_id,
            event_type=event_type,
            actor_type=actor_type,
            actor_id=actor_id,
            metadata_json=metadata,
        )
    )


def process_job(job_id: str, runtime: AppRuntime) -> None:
    with runtime.session_factory() as session:
        job = session.get(JobEntity, job_id)
        if job is None:
            logger.warning("Job %s not found for processing", job_id)
            return

        job.status = "processing"
        job.updated_at = utcnow()
        record_audit_event(session, job_id=job_id, event_type="job_processing_started")
        session.commit()

        try:
            input_bytes = runtime.storage.get_bytes(job.input_object_key)
            llm_client = runtime.llm_client_factory()
            result = correct_presentation_bytes(
                input_bytes,
                job.file_name,
                llm_client,
                highlight=job.highlight,
                highlight_color=runtime.settings.default_highlight_color,
            )

            output_object_key = make_output_object_key(job.id, result.file_name)
            runtime.storage.put_bytes(
                output_object_key,
                result.file_bytes,
                "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            )

            job.status = "done"
            job.updated_at = utcnow()
            job.completed_at = utcnow()
            job.output_object_key = output_object_key
            job.corrections_count = result.corrections_count
            job.changes = result.changes
            record_audit_event(
                session,
                job_id=job_id,
                event_type="job_completed",
                metadata={"corrections_count": result.corrections_count},
            )
            session.commit()
        except Exception as exc:
            session.rollback()
            job = session.get(JobEntity, job_id)
            if job is None:
                raise
            job.status = "error"
            job.error_message = str(exc)
            job.updated_at = utcnow()
            record_audit_event(
                session,
                job_id=job_id,
                event_type="job_failed",
                metadata={"error": str(exc)},
            )
            session.commit()
            logger.exception("Job %s failed", job_id)


def cleanup_expired_content(runtime: AppRuntime) -> int:
    deleted = 0
    now = utcnow()
    metadata_cutoff = now - timedelta(seconds=runtime.settings.metadata_retention_seconds)

    with runtime.session_factory() as session:
        expirable = session.scalars(
            select(JobEntity).where(
                JobEntity.expires_at < now,
                JobEntity.content_deleted_at.is_(None),
            )
        ).all()

        for job in expirable:
            runtime.storage.delete_object(job.input_object_key)
            if job.output_object_key:
                runtime.storage.delete_object(job.output_object_key)
            job.content_deleted_at = now
            job.output_object_key = None
            deleted += 1
            record_audit_event(session, job_id=job.id, event_type="job_content_deleted")

        old_jobs = session.scalars(
            select(JobEntity).where(
                JobEntity.content_deleted_at.is_not(None),
                JobEntity.updated_at < metadata_cutoff,
            )
        ).all()
        for job in old_jobs:
            session.delete(job)

        session.commit()

    return deleted


def run_job(job_id: str) -> None:
    runtime = build_runtime()
    process_job(job_id, runtime)
