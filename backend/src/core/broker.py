"""Taskiq Redis async broker and scheduler initialization."""

import taskiq_fastapi
from taskiq import AsyncBroker, InMemoryBroker, TaskiqScheduler
from taskiq.schedule_sources import LabelScheduleSource
from taskiq_redis import ListQueueBroker, RedisAsyncResultBackend

from src.core.config import get_settings

_settings = get_settings()


def _create_broker() -> AsyncBroker:
    """Create the Taskiq AsyncBroker (InMemoryBroker during unit tests, Redis in dev/prod)."""
    if _settings.environment == "test":
        return InMemoryBroker()

    result_backend: RedisAsyncResultBackend[object] = RedisAsyncResultBackend(
        redis_url=_settings.redis_url,
    )
    return ListQueueBroker(url=_settings.redis_url).with_result_backend(result_backend)


broker: AsyncBroker = _create_broker()

scheduler = TaskiqScheduler(
    broker=broker,
    sources=[LabelScheduleSource(broker)],
)

taskiq_fastapi.init(broker, "src.main:app")
