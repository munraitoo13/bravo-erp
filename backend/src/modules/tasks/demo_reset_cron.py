"""Scheduled Taskiq cron job for periodic Recruiter Demo Tenant state restoration."""

import structlog

from src.core.broker import broker
from src.core.database import async_session_factory
from src.seed.demo_seeder import DemoSeedSummary, seed_demo_tenant

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


@broker.task(
    task_name="tasks.reset_demo_tenant_state",
    schedule=[{"cron": "0 */6 * * *"}],
)
async def reset_demo_tenant_state_task() -> dict[str, str | int]:
    """Idempotently restore the Demo Tenant catalog stock, quotes, and work orders every 6 hours."""
    async with async_session_factory() as session:
        summary: DemoSeedSummary = await seed_demo_tenant(session, force_reset=True)
        await session.commit()
        logger.info(
            "demo_tenant_cron_reset_completed",
            organization_id=str(summary.organization_id),
            catalog_items_count=summary.catalog_items_count,
            quotes_count=summary.quotes_count,
        )
        return {
            "organization_id": str(summary.organization_id),
            "catalog_items_count": summary.catalog_items_count,
            "quotes_count": summary.quotes_count,
        }
