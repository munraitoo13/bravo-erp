"""Business logic and RBAC-aware service orchestration for the Equipment Catalog module."""

from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import CurrentTenantContext
from src.core.exceptions import (
    DemoProtectionError,
    DomainValidationError,
    ResourceNotFoundError,
)
from src.core.security import UserRole
from src.modules.catalog.models import CatalogCategory, CatalogItem
from src.modules.catalog.repository import CatalogRepository
from src.modules.catalog.schemas import (
    CatalogItemCreateRequest,
    CatalogItemOwnerResponse,
    CatalogItemTechnicianResponse,
    CatalogItemUpdateRequest,
    validate_specs_for_category,
)

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

type CatalogItemRoleResponse = CatalogItemOwnerResponse | CatalogItemTechnicianResponse


def serialize_catalog_item_for_role(
    item: CatalogItem,
    role: UserRole,
) -> CatalogItemRoleResponse:
    """Serialize a CatalogItem ORM instance into a role-segregated Pydantic v2 DTO."""
    if role == UserRole.OWNER:
        return CatalogItemOwnerResponse.model_validate(item)
    return CatalogItemTechnicianResponse.model_validate(item)


class CatalogService:
    """Application service managing tenant catalog items and stock adjustments."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = CatalogRepository(session)

    async def list_catalog_items(
        self,
        ctx: CurrentTenantContext,
        *,
        category: CatalogCategory | None = None,
        active_only: bool = False,
    ) -> list[CatalogItemRoleResponse]:
        """List catalog items for the current tenant, stripping cost fields for TECHNICIAN."""
        items = await self._repo.list_items(
            ctx.organization_id,
            category=category,
            active_only=active_only,
        )
        return [serialize_catalog_item_for_role(item, ctx.role) for item in items]

    async def get_catalog_item(
        self,
        ctx: CurrentTenantContext,
        item_id: UUID,
    ) -> CatalogItemRoleResponse:
        """Retrieve a single catalog item scoped to the current tenant."""
        item = await self._repo.get_by_id(ctx.organization_id, item_id)
        if item is None:
            raise ResourceNotFoundError(
                detail=f"Catalog item '{item_id}' was not found in this organization.",
                errors=[{"catalog_item_id": str(item_id)}],
            )
        return serialize_catalog_item_for_role(item, ctx.role)

    async def create_catalog_item(
        self,
        ctx: CurrentTenantContext,
        payload: CatalogItemCreateRequest,
    ) -> CatalogItemOwnerResponse:
        """Create a new catalog SKU for the tenant after validating uniqueness and JSONB specs."""
        existing = await self._repo.get_by_sku(ctx.organization_id, payload.sku)
        if existing is not None:
            raise DomainValidationError(
                detail=f"A catalog item with SKU '{payload.sku}' already exists in this tenant.",
                errors=[{"sku": payload.sku, "reason": "duplicate_sku"}],
            )

        validated_specs = validate_specs_for_category(payload.category, payload.specs)
        item = CatalogItem(
            organization_id=ctx.organization_id,
            sku=payload.sku,
            name_pt_br=payload.name_pt_br,
            category=payload.category,
            brand=payload.brand,
            cost_price_cents=payload.cost_price_cents,
            sale_price_cents=payload.sale_price_cents,
            stock_quantity=payload.stock_quantity,
            reserved_quantity=0,
            specs=validated_specs,
            is_seed_protected=False,
            is_active=payload.is_active,
        )
        await self._repo.add(item)
        await self._session.commit()
        await self._session.refresh(item)
        logger.info(
            "catalog_item_created",
            catalog_item_id=str(item.id),
            sku=item.sku,
            category=item.category.value,
        )
        return CatalogItemOwnerResponse.model_validate(item)

    async def update_catalog_item(
        self,
        ctx: CurrentTenantContext,
        item_id: UUID,
        payload: CatalogItemUpdateRequest,
    ) -> CatalogItemOwnerResponse:
        """Update an existing catalog item's prices, stock, or category specs."""
        item = await self._repo.get_by_id(ctx.organization_id, item_id)
        if item is None:
            raise ResourceNotFoundError(
                detail=f"Catalog item '{item_id}' was not found in this organization.",
                errors=[{"catalog_item_id": str(item_id)}],
            )

        if payload.stock_quantity is not None and payload.stock_quantity < item.reserved_quantity:
            raise DomainValidationError(
                detail=(
                    f"Cannot set stock_quantity ({payload.stock_quantity}) below currently "
                    f"reserved_quantity ({item.reserved_quantity})."
                ),
                errors=[
                    {
                        "stock_quantity": payload.stock_quantity,
                        "reserved_quantity": item.reserved_quantity,
                    }
                ],
            )

        if payload.specs is not None:
            item.specs = validate_specs_for_category(item.category, payload.specs)
        if payload.name_pt_br is not None:
            item.name_pt_br = payload.name_pt_br
        if payload.brand is not None:
            item.brand = payload.brand
        if payload.cost_price_cents is not None:
            item.cost_price_cents = payload.cost_price_cents
        if payload.sale_price_cents is not None:
            item.sale_price_cents = payload.sale_price_cents
        if payload.stock_quantity is not None:
            item.stock_quantity = payload.stock_quantity
        if payload.is_active is not None:
            item.is_active = payload.is_active

        await self._session.flush()
        await self._session.commit()
        await self._session.refresh(item)
        logger.info(
            "catalog_item_updated",
            catalog_item_id=str(item.id),
            sku=item.sku,
        )
        return CatalogItemOwnerResponse.model_validate(item)

    async def delete_catalog_item(
        self,
        ctx: CurrentTenantContext,
        item_id: UUID,
    ) -> None:
        """Soft-delete a catalog item or raise DemoProtectionError if is_seed_protected."""
        item = await self._repo.get_by_id(ctx.organization_id, item_id)
        if item is None:
            raise ResourceNotFoundError(
                detail=f"Catalog item '{item_id}' was not found in this organization.",
                errors=[{"catalog_item_id": str(item_id)}],
            )

        if item.is_seed_protected:
            raise DemoProtectionError(
                detail=(
                    f"Catalog item '{item.name_pt_br}' (SKU: {item.sku}) is protected by the "
                    "Recruiter Demo Seed policy and cannot be deleted."
                ),
                errors=[
                    {
                        "catalog_item_id": str(item.id),
                        "sku": item.sku,
                        "is_seed_protected": True,
                    }
                ],
            )

        item.is_active = False
        await self._session.flush()
        await self._session.commit()
        logger.info(
            "catalog_item_soft_deleted",
            catalog_item_id=str(item.id),
            sku=item.sku,
        )
