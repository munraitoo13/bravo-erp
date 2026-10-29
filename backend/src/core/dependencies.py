"""FastAPI dependency injection for multi-tenancy (CurrentTenantContext) and RBAC enforcement."""

from collections.abc import Callable, Coroutine
from typing import Annotated
from uuid import UUID

import structlog
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict

from src.core.exceptions import AuthenticationFailedError, RolePermissionDeniedError
from src.core.security import UserRole, decode_access_token

_bearer_scheme = HTTPBearer(auto_error=False)


class CurrentTenantContext(BaseModel):
    """Immutable tenant and actor context injected into every authenticated service call."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    organization_id: UUID
    user_id: UUID
    role: UserRole
    email: str
    full_name: str
    is_demo: bool = False


async def get_current_tenant_context(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
) -> CurrentTenantContext:
    """Extract Bearer JWT, validate signature, and return CurrentTenantContext."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AuthenticationFailedError(
            detail="Missing or invalid Authorization Bearer token header."
        )

    token_payload = decode_access_token(credentials.credentials)
    ctx = CurrentTenantContext(
        organization_id=token_payload.organization_id,
        user_id=token_payload.sub,
        role=token_payload.role,
        email=token_payload.email,
        full_name=token_payload.full_name,
        is_demo=token_payload.is_demo,
    )
    structlog.contextvars.bind_contextvars(
        organization_id=str(ctx.organization_id),
        user_id=str(ctx.user_id),
        role=ctx.role.value,
    )
    return ctx


def require_role(
    *allowed_roles: UserRole,
) -> Callable[[CurrentTenantContext], Coroutine[object, object, CurrentTenantContext]]:
    """Create a FastAPI dependency that restricts endpoint access to specific RBAC roles."""

    async def _role_checker(
        ctx: Annotated[CurrentTenantContext, Depends(get_current_tenant_context)],
    ) -> CurrentTenantContext:
        if ctx.role not in allowed_roles:
            allowed_str = ", ".join(r.value for r in allowed_roles)
            raise RolePermissionDeniedError(
                detail=f"Role '{ctx.role.value}' is not authorized. Allowed roles: {allowed_str}.",
                errors=[{"current_role": ctx.role.value, "allowed_roles": allowed_str}],
            )
        return ctx

    return _role_checker
