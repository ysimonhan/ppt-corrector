from __future__ import annotations

from app.config import get_settings


def main() -> None:
    try:
        from redis import Redis
        from rq import Connection, Worker
    except Exception as exc:  # pragma: no cover - platform/env specific
        raise RuntimeError(
            "RQ worker startup failed. Ensure rq is installed and the runtime "
            "supports Redis worker execution."
        ) from exc

    settings = get_settings()
    redis = Redis.from_url(settings.redis_url)

    with Connection(redis):
        worker = Worker([settings.rq_queue_name])
        worker.work()


if __name__ == "__main__":
    main()
