"""Thin FastAPI router for authentication and 1-Click Recruiter Demo (/api/v1/auth)."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db_session
from src.core.dependencies import CurrentTenantContext, require_role
from src.core.security import UserRole
from src.modules.tenants.schemas import (
    AuthMeResponse,
    AuthTokenResponse,
    DemoAuthResponse,
    DemoLoginRequest,
    DemoResetResponse,
    LoginRequest,
)
from src.modules.tenants.service import TenantAuthService

router = APIRouter(prefix="/auth", tags=["auth"])


def get_tenant_auth_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> TenantAuthService:
    """Provide scoped TenantAuthService instance."""
    return TenantAuthService(session)


@router.post("/login", response_model=AuthTokenResponse)
async def login(
    payload: LoginRequest,
    service: Annotated[TenantAuthService, Depends(get_tenant_auth_service)],
) -> AuthTokenResponse:
    """Authenticate user via email/password and return JWT access token."""
    return await service.login(payload)


@router.post("/demo-login", response_model=DemoAuthResponse)
async def demo_login(
    payload: DemoLoginRequest,
    service: Annotated[TenantAuthService, Depends(get_tenant_auth_service)],
) -> DemoAuthResponse:
    """1-Click Recruiter Demo login for OWNER, TECHNICIAN, or PUBLIC_CLIENT persona."""
    return await service.demo_login(payload)


@router.post("/demo-reset", response_model=DemoResetResponse)
async def demo_reset(
    service: Annotated[TenantAuthService, Depends(get_tenant_auth_service)],
) -> DemoResetResponse:
    """Restore Demo Tenant inventory, quotes, and work orders to initial seed state."""
    return await service.demo_reset()


@router.get("/me", response_model=AuthMeResponse)
async def get_me(
    ctx: Annotated[
        CurrentTenantContext,
        Depends(require_role(UserRole.OWNER, UserRole.TECHNICIAN)),
    ],
    service: Annotated[TenantAuthService, Depends(get_tenant_auth_service)],
) -> AuthMeResponse:
    """Return current authenticated user and organization metadata."""
    return await service.get_me(ctx)
