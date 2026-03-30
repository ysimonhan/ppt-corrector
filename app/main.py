from __future__ import annotations

import asyncio
import base64
import binascii
import uuid
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timedelta, timezone

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from sqlalchemy import select

from app.config import Settings, get_settings
from app.corrector import validate_pptx_bytes
from app.entities import JobEntity
from app.models import AuthValidationResponse, HealthResponse, JobCreatedResponse, JobRequest, JobStatusResponse
from app.runtime import AppRuntime, build_runtime
from app.worker_tasks import cleanup_expired_content, make_input_object_key, record_audit_event


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def resolve_runtime(app: FastAPI) -> AppRuntime:
    runtime = getattr(app.state, "runtime", None)
    if runtime is None:
        runtime = build_runtime(getattr(app.state, "settings", None))
        app.state.runtime = runtime
    return runtime


async def cleanup_expired_jobs(app: FastAPI) -> None:
    runtime = resolve_runtime(app)
    while True:
        await asyncio.sleep(runtime.settings.job_cleanup_interval_seconds)
        await asyncio.to_thread(cleanup_expired_content, runtime)


@asynccontextmanager
async def lifespan(app: FastAPI):
    resolve_runtime(app)
    cleanup_task = asyncio.create_task(cleanup_expired_jobs(app))
    try:
        yield
    finally:
        cleanup_task.cancel()
        with suppress(asyncio.CancelledError):
            await cleanup_task


def create_app(
    settings: Settings | None = None,
    *,
    runtime: AppRuntime | None = None,
) -> FastAPI:
    app = FastAPI(lifespan=lifespan)
    app.state.settings = settings
    if runtime is not None:
        app.state.runtime = runtime

    def get_runtime(request: Request) -> AppRuntime:
        return resolve_runtime(request.app)

    def require_api_key(
        request: Request,
        current_runtime: AppRuntime = Depends(get_runtime),
    ) -> None:
        authorization = request.headers.get("authorization", "")
        if authorization != f"Bearer {current_runtime.settings.api_key}":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Unauthorized",
                headers={"WWW-Authenticate": "Bearer"},
            )

    @app.get("/health", response_model=HealthResponse)
    async def healthcheck() -> HealthResponse:
        return HealthResponse(status="ok")

    @app.get(
        "/auth/validate",
        response_model=AuthValidationResponse,
        dependencies=[Depends(require_api_key)],
    )
    async def validate_auth() -> AuthValidationResponse:
        return AuthValidationResponse(status="ok")

    @app.post(
        "/jobs",
        status_code=status.HTTP_202_ACCEPTED,
        response_model=JobCreatedResponse,
        dependencies=[Depends(require_api_key)],
    )
    async def create_job(
        body: JobRequest,
        request: Request,
        highlight: bool = Query(default=False),
    ) -> JobCreatedResponse:
        current_runtime = resolve_runtime(request.app)

        try:
            file_bytes = base64.b64decode(body.file_base64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid base64 data") from exc

        if len(file_bytes) > current_runtime.settings.max_upload_size_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=(
                    f"File too large ({len(file_bytes)} bytes). "
                    f"Max: {current_runtime.settings.max_upload_size_bytes} bytes."
                ),
            )

        try:
            safe_name = validate_pptx_bytes(file_bytes, body.file_name)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

        job_id = str(uuid.uuid4())
        input_object_key = make_input_object_key(job_id, safe_name)
        current_runtime.storage.put_bytes(
            input_object_key,
            file_bytes,
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        )

        expires_at = utcnow() + timedelta(seconds=current_runtime.settings.job_ttl_seconds)

        with current_runtime.session_factory() as session:
            job = JobEntity(
                id=job_id,
                status="queued",
                file_name=safe_name,
                highlight=highlight,
                input_object_key=input_object_key,
                expires_at=expires_at,
            )
            session.add(job)
            record_audit_event(
                session,
                job_id=job_id,
                event_type="job_created",
                metadata={"file_name": safe_name, "highlight": highlight},
            )
            session.commit()

        try:
            current_runtime.queue.enqueue(job_id)
        except Exception as exc:
            with current_runtime.session_factory() as session:
                job = session.get(JobEntity, job_id)
                if job is not None:
                    job.status = "error"
                    job.error_message = str(exc)
                    job.updated_at = utcnow()
                    record_audit_event(
                        session,
                        job_id=job_id,
                        event_type="job_enqueue_failed",
                        metadata={"error": str(exc)},
                    )
                    session.commit()
            raise HTTPException(status_code=500, detail="Unable to enqueue job") from exc

        return JobCreatedResponse(job_id=job_id)

    @app.get(
        "/jobs/{job_id}",
        response_model=JobStatusResponse,
        response_model_exclude_none=True,
        dependencies=[Depends(require_api_key)],
    )
    async def get_job(job_id: str, request: Request) -> JobStatusResponse:
        current_runtime = resolve_runtime(request.app)

        with current_runtime.session_factory() as session:
            job = session.get(JobEntity, job_id)
            if job is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

            if job.status == "done":
                if job.output_object_key is None:
                    raise HTTPException(status_code=status.HTTP_410_GONE, detail="Job result expired")
                output_bytes = current_runtime.storage.get_bytes(job.output_object_key)
                return JobStatusResponse(
                    status="done",
                    file_base64=base64.b64encode(output_bytes).decode("utf-8"),
                    file_name=job.file_name.rsplit(".", 1)[0] + "_corrected.pptx",
                    corrections_count=job.corrections_count,
                    changes=job.changes,
                )

            if job.status == "error":
                return JobStatusResponse(status="error", message=job.error_message or "Unknown processing error")

            return JobStatusResponse(status="processing")

    return app


app = create_app()
