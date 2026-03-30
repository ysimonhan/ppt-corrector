from __future__ import annotations

import threading
from typing import Protocol

from redis import Redis

from app.config import Settings


class JobQueue(Protocol):
    def enqueue(self, job_id: str) -> None:
        ...


class InlineJobQueue:
    def enqueue(self, job_id: str) -> None:
        from app.worker_tasks import run_job

        worker = threading.Thread(target=run_job, args=(job_id,), daemon=True)
        worker.start()


class RedisRQJobQueue:
    def __init__(self, settings: Settings) -> None:
        try:
            from rq import Queue
        except Exception as exc:  # pragma: no cover - platform/env specific
            raise RuntimeError(
                "Redis queue backend is unavailable in this environment. "
                "Install and run RQ on a supported platform, or use QUEUE_BACKEND=inline."
            ) from exc

        self.redis = Redis.from_url(settings.redis_url)
        self.queue = Queue(settings.rq_queue_name, connection=self.redis)

    def enqueue(self, job_id: str) -> None:
        self.queue.enqueue("app.worker_tasks.run_job", job_id)


def build_queue(settings: Settings) -> JobQueue:
    if settings.queue_backend == "redis":
        return RedisRQJobQueue(settings)
    return InlineJobQueue()
