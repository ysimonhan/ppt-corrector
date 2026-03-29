from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
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


@dataclass
class JobRecord:
    status: JobStatus = "processing"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    result_base64: str | None = None
    file_name: str | None = None
    corrections_count: int | None = None
    changes: list[dict[str, str | int]] = field(default_factory=list)
    error: str | None = None
    highlight: bool = False

