"""Thin FastAPI router for the CCTV Engineering & Sizing Engine (/api/v1/sizing)."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db_session
from src.core.dependencies import CurrentTenantContext, require_role
from src.core.security import UserRole
from src.modules.sizing.schemas import (
    SizingCalculateOwnerResponse,
    SizingCalculateRequest,
    SizingCalculateTechnicianResponse,
)
from src.modules.sizing.service import SizingRoleResponse, SizingService

router = APIRouter(prefix="/sizing", tags=["sizing"])


def get_sizing_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SizingService:
    """Provide scoped SizingService instance."""
    return SizingService(session)


@router.post(
    "/calculate",
    response_model=SizingCalculateOwnerResponse | SizingCalculateTechnicianResponse,
)
async def calculate_sizing(
    payload: SizingCalculateRequest,
    ctx: Annotated[
        CurrentTenantContext,
        Depends(require_role(UserRole.OWNER, UserRole.TECHNICIAN)),
    ],
    service: Annotated[SizingService, Depends(get_sizing_service)],
) -> SizingRoleResponse:
    """Execute CCTV Sizing Engine calculations and return matched role-redacted BOM."""
    return await service.calculate_sizing(ctx, payload)
