"""SQLAlchemy 2.0 async repository for WorkOrders, InstalledSerials, Warranties, and Verifier."""

from collections.abc import Sequence
from datetime import date
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.modules.catalog.models import CatalogItem
from src.modules.quotes.models import AuditLog, OutboxEvent, Quote, QuoteItem
from src.modules.tenants.models import Organization, User
from src.modules.work_orders.models import InstalledSerial, WorkOrder, WorkOrderStatus


class WorkOrderRepository:
    """Data access layer for WorkOrder execution, Serial Vault, and Warranty queries."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_work_orders(
        self,
        organization_id: UUID,
        *,
        status: WorkOrderStatus | None = None,
    ) -> Sequence[WorkOrder]:
        """List tenant WorkOrders with eager loading of Quote, Customer, and InstalledSerials."""
        stmt = (
            select(WorkOrder)
            .options(
                selectinload(WorkOrder.quote).selectinload(Quote.customer),
                selectinload(WorkOrder.quote)
                .selectinload(Quote.items)
                .selectinload(QuoteItem.catalog_item),
                selectinload(WorkOrder.assigned_technician),
                selectinload(WorkOrder.installed_serials).selectinload(
                    InstalledSerial.catalog_item
                ),
            )
            .where(WorkOrder.organization_id == organization_id)
        )
        if status is not None:
            stmt = stmt.where(WorkOrder.status == status)
        stmt = stmt.order_by(WorkOrder.created_at.desc())
        result = await self._session.scalars(stmt)
        return result.all()

    async def get_work_order_by_id(
        self,
        organization_id: UUID,
        work_order_id: UUID,
        *,
        for_update: bool = False,
    ) -> WorkOrder | None:
        """Retrieve a single WorkOrder by ID within the tenant, optionally locking the row."""
        stmt = (
            select(WorkOrder)
            .options(
                selectinload(WorkOrder.quote).selectinload(Quote.customer),
                selectinload(WorkOrder.quote)
                .selectinload(Quote.items)
                .selectinload(QuoteItem.catalog_item),
                selectinload(WorkOrder.assigned_technician),
                selectinload(WorkOrder.installed_serials).selectinload(
                    InstalledSerial.catalog_item
                ),
            )
            .where(
                WorkOrder.organization_id == organization_id,
                WorkOrder.id == work_order_id,
            )
        )
        if for_update:
            stmt = stmt.with_for_update().execution_options(populate_existing=True)
        return await self._session.scalar(stmt)

    async def get_quote_for_update(
        self,
        organization_id: UUID,
        quote_id: UUID,
    ) -> Quote | None:
        """Acquire a row-level SELECT ... FOR UPDATE lock on the parent Quote."""
        stmt = (
            select(Quote)
            .options(
                selectinload(Quote.customer),
                selectinload(Quote.items).selectinload(QuoteItem.catalog_item),
            )
            .where(
                Quote.organization_id == organization_id,
                Quote.id == quote_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return await self._session.scalar(stmt)

    async def get_user_by_id(
        self,
        organization_id: UUID,
        user_id: UUID,
    ) -> User | None:
        """Fetch an active User within the tenant organization."""
        stmt = select(User).where(
            User.organization_id == organization_id,
            User.id == user_id,
            User.is_active.is_(True),
        )
        return await self._session.scalar(stmt)

    async def get_catalog_item_by_id(
        self,
        organization_id: UUID,
        catalog_item_id: UUID,
    ) -> CatalogItem | None:
        """Fetch a single CatalogItem scoped to organization_id."""
        stmt = select(CatalogItem).where(
            CatalogItem.organization_id == organization_id,
            CatalogItem.id == catalog_item_id,
        )
        return await self._session.scalar(stmt)

    async def lock_catalog_items_for_update(
        self,
        organization_id: UUID,
        item_ids: Sequence[UUID],
    ) -> Sequence[CatalogItem]:
        """Acquire SELECT ... FOR UPDATE locks on CatalogItems in ascending UUID order."""
        if not item_ids:
            return []
        sorted_ids: list[UUID] = sorted(set(item_ids))
        stmt = (
            select(CatalogItem)
            .where(
                CatalogItem.organization_id == organization_id,
                CatalogItem.id.in_(sorted_ids),
            )
            .order_by(CatalogItem.id.asc())
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        result = await self._session.scalars(stmt)
        return result.all()

    async def get_installed_serial_by_sn(
        self,
        organization_id: UUID,
        serial_number: str,
    ) -> InstalledSerial | None:
        """Check if a hardware serial_number is already registered in this organization."""
        stmt = select(InstalledSerial).where(
            InstalledSerial.organization_id == organization_id,
            InstalledSerial.serial_number == serial_number,
        )
        return await self._session.scalar(stmt)

    async def add_installed_serial(self, serial: InstalledSerial) -> InstalledSerial:
        """Persist a new InstalledSerial row and flush without committing."""
        self._session.add(serial)
        await self._session.flush()
        return serial

    async def add_audit_log(self, audit_log: AuditLog) -> AuditLog:
        """Persist an AuditLog entry and flush without committing."""
        self._session.add(audit_log)
        await self._session.flush()
        return audit_log

    async def add_outbox_event(self, outbox_event: OutboxEvent) -> OutboxEvent:
        """Persist a transactional OutboxEvent and flush without committing."""
        self._session.add(outbox_event)
        await self._session.flush()
        return outbox_event

    async def list_expiring_warranty_work_orders(
        self,
        organization_id: UUID,
        *,
        horizon_date: date,
    ) -> Sequence[WorkOrder]:
        """List completed WorkOrders flagged for 11-month maintenance or expiring by horizon."""
        stmt = (
            select(WorkOrder)
            .options(
                selectinload(WorkOrder.quote).selectinload(Quote.customer),
                selectinload(WorkOrder.installed_serials).selectinload(
                    InstalledSerial.catalog_item
                ),
            )
            .where(
                WorkOrder.organization_id == organization_id,
                WorkOrder.status == WorkOrderStatus.COMPLETED,
                WorkOrder.warranty_expires_at.is_not(None),
                or_(
                    WorkOrder.preventive_maintenance_alert_sent.is_(True),
                    WorkOrder.warranty_expires_at <= horizon_date,
                ),
            )
            .order_by(WorkOrder.warranty_expires_at.asc())
        )
        result = await self._session.scalars(stmt)
        return result.all()

    async def get_quote_and_org_by_pdf_sha256(
        self,
        pdf_sha256_hash: str,
    ) -> tuple[Quote, Organization] | None:
        """Look up a Quote and its Organization by its unique 64-char hex pdf_sha256_hash."""
        normalized_hash = pdf_sha256_hash.strip().lower()
        stmt = (
            select(Quote)
            .options(
                selectinload(Quote.customer),
                selectinload(Quote.work_order)
                .selectinload(WorkOrder.installed_serials)
                .selectinload(InstalledSerial.catalog_item),
            )
            .where(Quote.pdf_sha256_hash == normalized_hash)
        )
        quote = await self._session.scalar(stmt)
        if quote is None:
            return None

        org_stmt = select(Organization).where(Organization.id == quote.organization_id)
        org = await self._session.scalar(org_stmt)
        if org is None:  # pragma: no cover
            return None
        return quote, org
