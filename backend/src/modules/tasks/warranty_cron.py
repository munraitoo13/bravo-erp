"""11-month preventive maintenance & warranty expiration radar cron job."""

from dataclasses import dataclass
from datetime import date, timedelta
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.broker import broker
from src.core.database import async_session_factory
from src.core.logging import get_correlation_id
from src.modules.quotes.models import AuditLog, OutboxEvent, OutboxStatus
from src.modules.work_orders.models import WorkOrder, WorkOrderStatus

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

WARRANTY_ALERT_HORIZON_DAYS = 30


@dataclass(frozen=True)
class WarrantyCronScanSummary:
    """Summary returned by the 11-month preventive maintenance scanner."""

    scanned_date: date
    horizon_date: date
    flagged_count: int
    flagged_work_order_ids: tuple[UUID, ...]


async def scan_expiring_warranties(
    session: AsyncSession,
    *,
    reference_date: date | None = None,
    horizon_days: int = WARRANTY_ALERT_HORIZON_DAYS,
) -> WarrantyCronScanSummary:
    """Scan completed WorkOrders within 30 days of warranty expiration and emit alerts."""
    today = reference_date or date.today()
    horizon = today + timedelta(days=horizon_days)

    stmt = (
        select(WorkOrder)
        .where(
            WorkOrder.status == WorkOrderStatus.COMPLETED,
            WorkOrder.warranty_expires_at.is_not(None),
            WorkOrder.warranty_expires_at <= horizon,
            WorkOrder.preventive_maintenance_alert_sent.is_(False),
        )
        .order_by(WorkOrder.warranty_expires_at.asc())
        .with_for_update(skip_locked=True)
        .execution_options(populate_existing=True)
    )
    expiring_orders = (await session.scalars(stmt)).all()

    flagged_ids: list[UUID] = []
    correlation_id = get_correlation_id()

    for wo in expiring_orders:
        wo.preventive_maintenance_alert_sent = True
        expires_iso = (
            wo.warranty_expires_at.isoformat() if wo.warranty_expires_at is not None else ""
        )

        session.add(
            AuditLog(
                organization_id=wo.organization_id,
                entity_type="WORK_ORDER",
                entity_id=wo.id,
                action="WARRANTY_EXPIRING_ALERT_FLAGGED",
                actor_user_id=None,
                actor_ip="127.0.0.1",
                previous_state={"preventive_maintenance_alert_sent": False},
                new_state={
                    "preventive_maintenance_alert_sent": True,
                    "warranty_expires_at": expires_iso,
                },
            )
        )
        session.add(
            OutboxEvent(
                organization_id=wo.organization_id,
                event_type="WarrantyExpiringAlertEvent",
                status=OutboxStatus.PENDING,
                payload={
                    "work_order_id": str(wo.id),
                    "quote_id": str(wo.quote_id),
                    "organization_id": str(wo.organization_id),
                    "warranty_expires_at": expires_iso,
                    "correlation_id": correlation_id,
                },
            )
        )
        flagged_ids.append(wo.id)
        logger.info(
            "warranty_expiring_alert_flagged",
            work_order_id=str(wo.id),
            quote_id=str(wo.quote_id),
            organization_id=str(wo.organization_id),
            warranty_expires_at=expires_iso,
        )

    await session.commit()
    return WarrantyCronScanSummary(
        scanned_date=today,
        horizon_date=horizon,
        flagged_count=len(flagged_ids),
        flagged_work_order_ids=tuple(flagged_ids),
    )


@broker.task(
    task_name="tasks.scan_expiring_warranties",
    schedule=[{"cron": "0 8 * * *"}],
)
async def scan_expiring_warranties_task() -> dict[str, str | int]:
    """Daily Taskiq cron job scanning for 11-month preventive maintenance renewals."""
    async with async_session_factory() as session:
        summary = await scan_expiring_warranties(session)
        return {
            "scanned_date": summary.scanned_date.isoformat(),
            "horizon_date": summary.horizon_date.isoformat(),
            "flagged_count": summary.flagged_count,
        }
