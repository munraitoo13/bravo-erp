"""Thin FastAPI router for the Equipment Catalog module (/api/v1/catalog)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db_session
from src.core.dependencies import CurrentTenantContext, require_role
from src.core.security import UserRole
from src.modules.catalog.models import CatalogCategory
from src.modules.catalog.schemas import (
    CatalogItemCreateRequest,
    CatalogItemOwnerResponse,
    CatalogItemTechnicianResponse,
    CatalogItemUpdateRequest,
)
from src.modules.catalog.service import CatalogItemRoleResponse, CatalogService

router = APIRouter(prefix="/catalog", tags=["catalog"])


def get_catalog_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> CatalogService:
    """Provide scoped CatalogService instance."""
    return CatalogService(session)


@router.get(
    "",
    response_model=list[CatalogItemOwnerResponse | CatalogItemTechnicianResponse],
)
async def list_catalog(
    ctx: Annotated[
        CurrentTenantContext,
        Depends(require_role(UserRole.OWNER, UserRole.TECHNICIAN)),
    ],
    service: Annotated[CatalogService, Depends(get_catalog_service)],
    category: Annotated[CatalogCategory | None, Query()] = None,
    active_only: Annotated[bool, Query()] = False,
) -> list[CatalogItemRoleResponse]:
    """List tenant catalog items (cost_price_cents redacted for TECHNICIAN)."""
    return await service.list_catalog_items(ctx, category=category, active_only=active_only)


@router.get(
    "/{item_id}",
    response_model=CatalogItemOwnerResponse | CatalogItemTechnicianResponse,
)
async def get_catalog_item(
    item_id: UUID,
    ctx: Annotated[
        CurrentTenantContext,
        Depends(require_role(UserRole.OWNER, UserRole.TECHNICIAN)),
    ],
    service: Annotated[CatalogService, Depends(get_catalog_service)],
) -> CatalogItemRoleResponse:
    """Retrieve a single tenant catalog item by ID."""
    return await service.get_catalog_item(ctx, item_id)


@router.post(
    "",
    response_model=CatalogItemOwnerResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_catalog_item(
    payload: CatalogItemCreateRequest,
    ctx: Annotated[CurrentTenantContext, Depends(require_role(UserRole.OWNER))],
    service: Annotated[CatalogService, Depends(get_catalog_service)],
) -> CatalogItemOwnerResponse:
    """Create a new catalog item (OWNER only)."""
    return await service.create_catalog_item(ctx, payload)


@router.patch(
    "/{item_id}",
    response_model=CatalogItemOwnerResponse,
)
async def update_catalog_item(
    item_id: UUID,
    payload: CatalogItemUpdateRequest,
    ctx: Annotated[CurrentTenantContext, Depends(require_role(UserRole.OWNER))],
    service: Annotated[CatalogService, Depends(get_catalog_service)],
) -> CatalogItemOwnerResponse:
    """Update a catalog item's price, stock, or specs (OWNER only)."""
    return await service.update_catalog_item(ctx, item_id, payload)


@router.delete(
    "/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_catalog_item(
    item_id: UUID,
    ctx: Annotated[CurrentTenantContext, Depends(require_role(UserRole.OWNER))],
    service: Annotated[CatalogService, Depends(get_catalog_service)],
) -> Response:
    """Soft-delete a catalog item (blocked with 403 Problem+JSON if is_seed_protected)."""
    await service.delete_catalog_item(ctx, item_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
