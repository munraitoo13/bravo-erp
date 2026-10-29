"""SQLAlchemy 2.0 async repository for CatalogItem with deterministic pessimistic locking."""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.catalog.models import CatalogCategory, CatalogItem


class CatalogRepository:
    """Data access layer for tenant-scoped CatalogItem entities."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_items(
        self,
        organization_id: UUID,
        *,
        category: CatalogCategory | None = None,
        active_only: bool = False,
    ) -> Sequence[CatalogItem]:
        """List catalog items scoped strictly to the given organization_id."""
        stmt = select(CatalogItem).where(CatalogItem.organization_id == organization_id)
        if category is not None:
            stmt = stmt.where(CatalogItem.category == category)
        if active_only:
            stmt = stmt.where(CatalogItem.is_active.is_(True))
        stmt = stmt.order_by(CatalogItem.category.asc(), CatalogItem.sku.asc())
        result = await self._session.scalars(stmt)
        return result.all()

    async def get_by_id(
        self,
        organization_id: UUID,
        item_id: UUID,
    ) -> CatalogItem | None:
        """Retrieve a single catalog item by ID and organization_id."""
        stmt = select(CatalogItem).where(
            CatalogItem.organization_id == organization_id,
            CatalogItem.id == item_id,
        )
        return await self._session.scalar(stmt)

    async def get_by_sku(
        self,
        organization_id: UUID,
        sku: str,
    ) -> CatalogItem | None:
        """Retrieve a single catalog item by SKU within the tenant."""
        stmt = select(CatalogItem).where(
            CatalogItem.organization_id == organization_id,
            CatalogItem.sku == sku,
        )
        return await self._session.scalar(stmt)

    async def lock_items_for_update(
        self,
        organization_id: UUID,
        item_ids: Sequence[UUID],
    ) -> Sequence[CatalogItem]:
        """Acquire SELECT ... FOR UPDATE locks in ascending UUID order to prevent deadlocks."""
        if not item_ids:
            return []
        sorted_ids = sorted(set(item_ids))
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

    async def add(self, item: CatalogItem) -> CatalogItem:
        """Add a new CatalogItem to the session and flush without committing."""
        self._session.add(item)
        await self._session.flush()
        return item

    async def delete(self, item: CatalogItem) -> None:
        """Delete a CatalogItem from the session and flush without committing."""
        await self._session.delete(item)
        await self._session.flush()
