from __future__ import annotations

import asyncio
import base64
import binascii
import logging
import uuid
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status

from app.config import Settings, get_settings
from app.corrector import PresentationCorrectionResult, correct_presentation_bytes, validate_pptx_bytes
from app.llm import LangdockLLMClient
from app.models import JobCreatedResponse, JobRecord, JobRequest, JobStatusResponse


logger = logging.getLogger(__name__)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def resolve_settings(app: FastAPI) -> Settings:
    settings = getattr(app.state, "settings", None)
    if settings is None:
        settings = get_settings()
        app.state.settings = settings
    return settings


def default_process_presentation(
    file_bytes: bytes,
    file_name: str,
    highlight: bool,
    settings: Settings,
) -> PresentationCorrectionResult:
    llm_client = LangdockLLMClient(
        api_key=settings.langdock_api_key,
        api_url=settings.langdock_api_url,
        model=settings.langdock_model,
        min_text_length=settings.min_text_length,
        timeout_seconds=settings.llm_timeout_seconds,
    )
    return correct_presentation_bytes(
        file_bytes,
        file_name,
        llm_client,
        highlight=highlight,
        highlight_color=settings.default_highlight_color,
    )


async def cleanup_expired_jobs(app: FastAPI) -> None:
    settings = resolve_settings(app)

    while True:
        await asyncio.sleep(settings.job_cleanup_interval_seconds)
        cutoff = utcnow() - timedelta(seconds=settings.job_ttl_seconds)

        async with app.state.jobs_lock:
            expired_job_ids = [
                job_id
                for job_id, job in app.state.jobs.items()
                if job.created_at < cutoff
            ]
            for job_id in expired_job_ids:
                app.state.jobs.pop(job_id, None)

        if expired_job_ids:
            logger.info("Purged %s expired jobs", len(expired_job_ids))


async def process_job(
    app: FastAPI,
    job_id: str,
    file_bytes: bytes,
    file_name: str,
    highlight: bool,
) -> None:
    settings = resolve_settings(app)

    try:
        result = await asyncio.to_thread(
            app.state.process_presentation,
            file_bytes,
            file_name,
            highlight,
            settings,
        )
    except Exception as exc:
        logger.exception("Job %s failed", job_id)
        async with app.state.jobs_lock:
            job = app.state.jobs.get(job_id)
            if job is not None:
                job.status = "error"
                job.error = str(exc)
        return

    result_base64 = base64.b64encode(result.file_bytes).decode("utf-8")
    async with app.state.jobs_lock:
        job = app.state.jobs.get(job_id)
        if job is None:
            return
        job.status = "done"
        job.result_base64 = result_base64
        job.file_name = result.file_name
        job.corrections_count = result.corrections_count
        job.changes = result.changes


@asynccontextmanager
async def lifespan(app: FastAPI):
    resolve_settings(app)
    cleanup_task = asyncio.create_task(cleanup_expired_jobs(app))
    app.state.cleanup_task = cleanup_task
    try:
        yield
    finally:
        cleanup_task.cancel()
        with suppress(asyncio.CancelledError):
            await cleanup_task

        outstanding = list(app.state.job_tasks)
        for task in outstanding:
            task.cancel()
        if outstanding:
            with suppress(asyncio.CancelledError):
                await asyncio.gather(*outstanding, return_exceptions=True)


def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(lifespan=lifespan)
    app.state.settings = settings
    app.state.jobs: dict[str, JobRecord] = {}
    app.state.jobs_lock = asyncio.Lock()
    app.state.job_tasks: set[asyncio.Task[Any]] = set()
    app.state.process_presentation = default_process_presentation

    def track_task(task: asyncio.Task[Any]) -> None:
        app.state.job_tasks.add(task)
        task.add_done_callback(app.state.job_tasks.discard)

    def get_request_settings(request: Request) -> Settings:
        return resolve_settings(request.app)

    def require_api_key(
        request: Request,
        current_settings: Settings = Depends(get_request_settings),
    ) -> None:
        authorization = request.headers.get("authorization", "")
        if authorization != f"Bearer {current_settings.api_key}":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Unauthorized",
                headers={"WWW-Authenticate": "Bearer"},
            )

    @app.get("/health")
    async def healthcheck() -> dict[str, str]:
        return {"status": "ok"}

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
        settings = resolve_settings(request.app)

        try:
            file_bytes = base64.b64decode(body.file_base64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid base64 data") from exc

        if len(file_bytes) > settings.max_upload_size_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=(
                    f"File too large ({len(file_bytes)} bytes). "
                    f"Max: {settings.max_upload_size_bytes} bytes."
                ),
            )

        try:
            safe_name = validate_pptx_bytes(file_bytes, body.file_name)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

        job_id = str(uuid.uuid4())
        async with request.app.state.jobs_lock:
            request.app.state.jobs[job_id] = JobRecord(
                status="processing",
                created_at=utcnow(),
                highlight=highlight,
            )

        task = asyncio.create_task(process_job(request.app, job_id, file_bytes, safe_name, highlight))
        track_task(task)
        return JobCreatedResponse(job_id=job_id)

    @app.get(
        "/jobs/{job_id}",
        response_model=JobStatusResponse,
        dependencies=[Depends(require_api_key)],
    )
    async def get_job(job_id: str, request: Request) -> JobStatusResponse:
        async with request.app.state.jobs_lock:
            job = request.app.state.jobs.get(job_id)

        if job is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

        if job.status == "done":
            return JobStatusResponse(
                status=job.status,
                file_base64=job.result_base64,
                file_name=job.file_name,
                corrections_count=job.corrections_count,
                changes=job.changes,
            )

        if job.status == "error":
            return JobStatusResponse(status=job.status, message=job.error or "Unknown processing error")

        return JobStatusResponse(status=job.status)

    return app


app = create_app()
