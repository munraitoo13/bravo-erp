"""Taskiq worker and scheduler entrypoint importing all background task modules."""

from src.core.broker import broker, scheduler
from src.modules.tasks import (
    demo_reset_cron,
    outbox_relay,
    pdf_generator,
    warranty_cron,
)

__all__ = [
    "broker",
    "demo_reset_cron",
    "outbox_relay",
    "pdf_generator",
    "scheduler",
    "warranty_cron",
]
