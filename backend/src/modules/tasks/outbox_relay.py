"""Transactional Outbox relay worker using SELECT ... FOR UPDATE SKIP LOCKED."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.broker import broker
from src.core.database import async_session_factory
from src.core.exceptions import DomainError
from src.core.storage import StorageClient
from src.modules.quotes.models import OutboxEvent, OutboxStatus
from src.modules.tasks.pdf_generator import generate_and_store_quote_pdf

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

MAX_OUTBOX_RETRIES = 5

_PDF_TRIGGER_EVENTS: frozenset[str] = frozenset(
    {
        "QuoteSentEvent",
        "QuoteApprovedEvent",
        "WorkOrderCompletedEvent",
    }
)


@dataclass(frozen=True)
class OutboxRelaySummary:
    """Summary of a single outbox polling batch execution."""

    polled_count: int
    processed_count: int
    failed_count: int
    processed_event_ids: tuple[UUID, ...]


async def _dispatch_outbox_event(
    session: AsyncSession,
    event: OutboxEvent,
    *,
    storage_client: StorageClient | None = None,
) -> None:
    """Execute the domain side effect corresponding to event.event_type."""
    if event.event_type in _PDF_TRIGGER_EVENTS:
        raw_quote_id = event.payload.get("quote_id")
        if not isinstance(raw_quote_id, str) or not raw_quote_id:
            raise DomainError(
                detail=f"OutboxEvent '{event.id}' missing 'quote_id' in payload.",
            )
        await generate_and_store_quote_pdf(
            session,
            UUID(raw_quote_id),
            storage_client=storage_client,
        )
        return

    if event.event_type == "WarrantyExpiringAlertEvent":
        logger.info(
            "warranty_expiring_alert_processed",
            outbox_event_id=str(event.id),
            organization_id=str(event.organization_id),
            work_order_id=str(event.payload.get("work_order_id", "")),
            warranty_expires_at=str(event.payload.get("warranty_expires_at", "")),
        )
        return

    logger.warning(
        "unrecognized_outbox_event_type",
        outbox_event_id=str(event.id),
        event_type=event.event_type,
    )


async def process_pending_outbox_events(
    session: AsyncSession,
    *,
    batch_size: int = 25,
    storage_client: StorageClient | None = None,
    now: datetime | None = None,
) -> OutboxRelaySummary:
    """Poll PENDING outbox_events with SELECT ... FOR UPDATE SKIP LOCKED and process them."""
    effective_now = now or datetime.now(UTC)

    # 1. Recover stale PROCESSING events older than 5 minutes (e.g. abrupt worker crash/restart)
    stale_threshold = effective_now - timedelta(minutes=5)
    stale_stmt = (
        select(OutboxEvent)
        .where(
            OutboxEvent.status == OutboxStatus.PROCESSING,
            OutboxEvent.created_at <= stale_threshold,
        )
        .with_for_update(skip_locked=True)
        .execution_options(populate_existing=True)
    )
    stale_events = (await session.scalars(stale_stmt)).all()
    for stale in stale_events:
        stale.status = OutboxStatus.PENDING
        stale.next_retry_at = effective_now
        logger.warning(
            "recovered_stale_outbox_event",
            outbox_event_id=str(stale.id),
            event_type=stale.event_type,
        )
    if stale_events:
        await session.flush()

    # 2. Poll PENDING events ready for dispatch
    stmt = (
        select(OutboxEvent)
        .where(
            OutboxEvent.status == OutboxStatus.PENDING,
            OutboxEvent.next_retry_at <= effective_now,
        )
        .order_by(OutboxEvent.created_at.asc())
        .limit(batch_size)
        .with_for_update(skip_locked=True)
        .execution_options(populate_existing=True)
    )
    events = (await session.scalars(stmt)).all()

    processed_ids: list[UUID] = []
    failed_count = 0

    for event in events:
        corr_id = event.payload.get("correlation_id")
        if isinstance(corr_id, str) and corr_id:
            structlog.contextvars.bind_contextvars(correlation_id=corr_id)

        event.status = OutboxStatus.PROCESSING
        await session.flush()

        try:
            async with session.begin_nested():
                await _dispatch_outbox_event(
                    session,
                    event,
                    storage_client=storage_client,
                )
            event.status = OutboxStatus.PROCESSED
            processed_ids.append(event.id)
            logger.info(
                "outbox_event_processed",
                outbox_event_id=str(event.id),
                event_type=event.event_type,
                organization_id=str(event.organization_id),
            )
        except Exception as exc:
            failed_count += 1
            event.retry_count += 1
            if event.retry_count >= MAX_OUTBOX_RETRIES:
                event.status = OutboxStatus.FAILED
            else:
                event.status = OutboxStatus.PENDING
                backoff_seconds = 2**event.retry_count
                event.next_retry_at = effective_now + timedelta(seconds=backoff_seconds)
            logger.error(
                "outbox_event_processing_failed",
                outbox_event_id=str(event.id),
                event_type=event.event_type,
                retry_count=event.retry_count,
                new_status=event.status.value,
                error=str(exc),
            )

    await session.commit()
    return OutboxRelaySummary(
        polled_count=len(events),
        processed_count=len(processed_ids),
        failed_count=failed_count,
        processed_event_ids=tuple(processed_ids),
    )


@broker.task(
    task_name="tasks.poll_outbox_events",
    schedule=[{"cron": "* * * * *"}],
)
async def poll_outbox_events_task() -> dict[str, int]:
    """Scheduled Taskiq task that polls and processes pending transactional outbox events."""
    async with async_session_factory() as session:
        summary = await process_pending_outbox_events(session)
        return {
            "polled_count": summary.polled_count,
            "processed_count": summary.processed_count,
            "failed_count": summary.failed_count,
        }
