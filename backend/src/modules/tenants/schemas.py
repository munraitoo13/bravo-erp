"""Pydantic v2 schemas for authentication, multi-tenancy, and 1-Click Recruiter Demo."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from src.core.security import UserRole


class OrganizationResponse(BaseModel):
    """Public metadata for an Organization."""

    model_config = ConfigDict(from_attributes=True, frozen=True, extra="forbid")

    id: UUID
    name: str
    slug: str
    document_cnpj: str
    is_demo: bool
    created_at: datetime


class UserResponse(BaseModel):
    """Authenticated User profile response."""

    model_config = ConfigDict(from_attributes=True, frozen=True, extra="forbid")

    id: UUID
    organization_id: UUID
    email: str
    full_name: str
    role: UserRole
    is_active: bool
    created_at: datetime


class LoginRequest(BaseModel):
    """Standard email/password login payload."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    email: EmailStr
    password: str = Field(min_length=1, max_length=128)
    organization_slug: str | None = Field(default=None, max_length=80)


class AuthTokenResponse(BaseModel):
    """JWT access token and user/organization profile returned on login."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    access_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105
    persona: UserRole
    user: UserResponse
    organization: OrganizationResponse


class DemoLoginRequest(BaseModel):
    """1-Click Recruiter Demo persona selection payload."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    persona: UserRole


class DemoAuthResponse(BaseModel):
    """Response returned by POST /api/v1/auth/demo-login for any of the 3 demo personas."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    persona: UserRole
    access_token: str | None = None
    token_type: Literal["bearer"] = "bearer"  # noqa: S105
    user: UserResponse | None = None
    organization: OrganizationResponse
    demo_public_quote_token: UUID
    demo_active_work_order_id: UUID
    redirect_path: str


class DemoResetResponse(BaseModel):
    """Response returned by POST /api/v1/auth/demo-reset after restoring seed state."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["reset_completed"] = "reset_completed"
    organization_id: UUID
    catalog_items_restored: int
    quotes_restored: int
    demo_public_quote_token: UUID
    demo_active_work_order_id: UUID


class AuthMeResponse(BaseModel):
    """Response returned by GET /api/v1/auth/me."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    user: UserResponse
    organization: OrganizationResponse
