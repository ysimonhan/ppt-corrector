from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


JobStatus = Literal["processing", "done", "error"]


class ChangeRecord(BaseModel):
    slide: int
    original: str
    corrected: str


class JobRequest(BaseModel):
    file_base64: str
    file_name: str


class JobCreatedResponse(BaseModel):
    job_id: str


class JobStatusResponse(BaseModel):
    status: JobStatus
    file_base64: str | None = None
    file_name: str | None = None
    corrections_count: int | None = None
    changes: list[ChangeRecord] | None = None
    message: str | None = None


class HealthResponse(BaseModel):
    status: str


class AuthValidationResponse(BaseModel):
    status: str
