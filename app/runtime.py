from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings, get_settings
from app.db import get_engine, get_session_factory
from app.entities import Base
from app.llm import LangdockLLMClient
from app.queueing import JobQueue, build_queue
from app.storage import ObjectStorage, build_storage


@dataclass
class AppRuntime:
    settings: Settings
    session_factory: sessionmaker[Session]
    storage: ObjectStorage
    queue: JobQueue
    llm_client_factory: Callable[[], LangdockLLMClient]


def default_llm_client_factory(settings: Settings) -> Callable[[], LangdockLLMClient]:
    def factory() -> LangdockLLMClient:
        return LangdockLLMClient(
            api_key=settings.langdock_api_key,
            api_url=settings.langdock_api_url,
            model=settings.langdock_model,
            min_text_length=settings.min_text_length,
            timeout_seconds=settings.llm_timeout_seconds,
        )

    return factory


def build_runtime(
    settings: Settings | None = None,
    *,
    storage: ObjectStorage | None = None,
    queue: JobQueue | None = None,
    llm_client_factory: Callable[[], LangdockLLMClient] | None = None,
) -> AppRuntime:
    resolved_settings = settings or get_settings()
    engine = get_engine(resolved_settings.database_url)
    Base.metadata.create_all(engine)
    session_factory = get_session_factory(resolved_settings.database_url)

    return AppRuntime(
        settings=resolved_settings,
        session_factory=session_factory,
        storage=storage or build_storage(resolved_settings),
        queue=queue or build_queue(resolved_settings),
        llm_client_factory=llm_client_factory or default_llm_client_factory(resolved_settings),
    )
