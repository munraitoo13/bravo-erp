"""SQLAlchemy 2.0 async repository for Customers, Quotes, AuditLogs, OutboxEvents, and Locking."""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.modules.catalog.models import CatalogItem
from src.modules.quotes.models import (
    AuditLog,
    Customer,
    OutboxEvent,
    Quote,
    QuoteItem,
    QuoteStatus,
)
from src.modules.work_orders.models import WorkOrder


class QuoteRepository:
    """Data access layer for Customer, Quote, AuditLog, and OutboxEvent persistence."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_customers(self, organization_id: UUID) -> Sequence[Customer]:
        """List all customers belonging to the given organization_id."""
        stmt = (
            select(Customer)
            .where(Customer.organization_id == organization_id)
            .order_by(Customer.name.asc())
        )
        result = await self._session.scalars(stmt)
        return result.all()

    async def get_customer_by_id(
        self,
        organization_id: UUID,
        customer_id: UUID,
    ) -> Customer | None:
        """Retrieve a customer by ID scoped to organization_id."""
        stmt = select(Customer).where(
            Customer.organization_id == organization_id,
            Customer.id == customer_id,
        )
        return await self._session.scalar(stmt)

    async def add_customer(self, customer: Customer) -> Customer:
        """Add a Customer to the session and flush without committing."""
        self._session.add(customer)
        await self._session.flush()
        return customer

    async def list_quotes(
        self,
        organization_id: UUID,
        *,
        status: QuoteStatus | None = None,
    ) -> Sequence[Quote]:
        """List quotes scoped to the organization_id with eager relationship loading."""
        stmt = (
            select(Quote)
            .options(
                selectinload(Quote.customer),
                selectinload(Quote.items).selectinload(QuoteItem.catalog_item),
                selectinload(Quote.work_order),
            )
            .where(Quote.organization_id == organization_id)
        )
        if status is not None:
            stmt = stmt.where(Quote.status == status)
        stmt = stmt.order_by(Quote.created_at.desc())
        result = await self._session.scalars(stmt)
        return result.all()

    async def get_quote_by_id(
        self,
        organization_id: UUID,
        quote_id: UUID,
        *,
        for_update: bool = False,
    ) -> Quote | None:
        """Retrieve a single Quote by ID within the tenant, optionally locking the row."""
        stmt = (
            select(Quote)
            .options(
                selectinload(Quote.customer),
                selectinload(Quote.items).selectinload(QuoteItem.catalog_item),
                selectinload(Quote.work_order),
            )
            .where(
                Quote.organization_id == organization_id,
                Quote.id == quote_id,
            )
        )
        if for_update:
            stmt = stmt.with_for_update().execution_options(populate_existing=True)
        return await self._session.scalar(stmt)

    async def get_quote_by_public_token(
        self,
        public_token: UUID,
        *,
        for_update: bool = False,
    ) -> Quote | None:
        """Retrieve a Quote by its public_token, optionally acquiring a row-level lock."""
        stmt = (
            select(Quote)
            .options(
                selectinload(Quote.customer),
                selectinload(Quote.items).selectinload(QuoteItem.catalog_item),
                selectinload(Quote.work_order),
            )
            .where(Quote.public_token == public_token)
        )
        if for_update:
            stmt = stmt.with_for_update().execution_options(populate_existing=True)
        return await self._session.scalar(stmt)

    async def get_catalog_items_by_ids(
        self,
        organization_id: UUID,
        item_ids: Sequence[UUID],
    ) -> dict[UUID, CatalogItem]:
        """Fetch active tenant CatalogItems mapped by UUID."""
        if not item_ids:
            return {}
        unique_ids = list(set(item_ids))
        stmt = select(CatalogItem).where(
            CatalogItem.organization_id == organization_id,
            CatalogItem.id.in_(unique_ids),
        )
        items = (await self._session.scalars(stmt)).all()
        return {item.id: item for item in items}

    async def lock_catalog_items_for_update(
        self,
        organization_id: UUID,
        item_ids: Sequence[UUID],
    ) -> Sequence[CatalogItem]:
        """Acquire SELECT ... FOR UPDATE locks in ascending UUID order to prevent deadlocks."""
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

    async def add_quote(self, quote: Quote) -> Quote:
        """Add a Quote (and its cascaded QuoteItems) to the session and flush."""
        self._session.add(quote)
        await self._session.flush()
        return quote

    async def add_work_order(self, work_order: WorkOrder) -> WorkOrder:
        """Add a newly created WorkOrder to the session and flush."""
        self._session.add(work_order)
        await self._session.flush()
        return work_order

    async def get_work_order_by_quote_id(
        self,
        organization_id: UUID,
        quote_id: UUID,
    ) -> WorkOrder | None:
        """Retrieve the WorkOrder associated with a Quote if one exists."""
        stmt = select(WorkOrder).where(
            WorkOrder.organization_id == organization_id,
            WorkOrder.quote_id == quote_id,
        )
        return await self._session.scalar(stmt)

    async def add_audit_log(self, audit_log: AuditLog) -> AuditLog:
        """Add an AuditLog entry to the session and flush."""
        self._session.add(audit_log)
        await self._session.flush()
        return audit_log

    async def list_audit_logs_for_entity(
        self,
        organization_id: UUID,
        entity_type: str,
        entity_id: UUID,
    ) -> Sequence[AuditLog]:
        """List immutable audit logs for a given entity ordered by creation time descending."""
        stmt = (
            select(AuditLog)
            .where(
                AuditLog.organization_id == organization_id,
                AuditLog.entity_type == entity_type,
                AuditLog.entity_id == entity_id,
            )
            .order_by(AuditLog.created_at.desc())
        )
        result = await self._session.scalars(stmt)
        return result.all()

    async def add_outbox_event(self, outbox_event: OutboxEvent) -> OutboxEvent:
        """Enqueue a transactional OutboxEvent inside the current database transaction."""
        self._session.add(outbox_event)
        await self._session.flush()
        return outbox_event
