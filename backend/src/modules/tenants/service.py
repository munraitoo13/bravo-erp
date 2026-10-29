"""Authentication, tenant resolution, and 1-Click Recruiter Demo orchestration service."""

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import CurrentTenantContext
from src.core.exceptions import AuthenticationFailedError, ResourceNotFoundError
from src.core.security import UserRole, create_access_token, verify_password
from src.modules.tenants.repository import TenantRepository
from src.modules.tenants.schemas import (
    AuthMeResponse,
    AuthTokenResponse,
    DemoAuthResponse,
    DemoLoginRequest,
    DemoResetResponse,
    LoginRequest,
    OrganizationResponse,
    UserResponse,
)
from src.seed.demo_seeder import (
    DEMO_OWNER_EMAIL,
    DEMO_TECH_EMAIL,
    seed_demo_tenant,
)

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


class TenantAuthService:
    """Application service handling user authentication and 1-Click Recruiter Demo flows."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = TenantRepository(session)

    async def login(self, payload: LoginRequest) -> AuthTokenResponse:
        """Authenticate user by email/password using Argon2id and issue a signed JWT."""
        lookup = await self._repo.get_user_by_email(
            payload.email,
            organization_slug=payload.organization_slug,
        )
        if lookup is None:
            raise AuthenticationFailedError(detail="Invalid email or password.")

        user, organization = lookup
        if not user.is_active or not verify_password(payload.password, user.password_hash):
            raise AuthenticationFailedError(detail="Invalid email or password.")

        token = create_access_token(
            user_id=user.id,
            organization_id=organization.id,
            role=user.role,
            email=user.email,
            full_name=user.full_name,
            is_demo=organization.is_demo,
        )
        logger.info(
            "user_logged_in",
            user_id=str(user.id),
            organization_id=str(organization.id),
            role=user.role.value,
        )
        return AuthTokenResponse(
            access_token=token,
            persona=user.role,
            user=UserResponse.model_validate(user),
            organization=OrganizationResponse.model_validate(organization),
        )

    async def demo_login(self, payload: DemoLoginRequest) -> DemoAuthResponse:
        """Execute 1-Click Recruiter Demo Login for OWNER, TECHNICIAN, or PUBLIC_CLIENT."""
        summary = await seed_demo_tenant(self._session, force_reset=False)
        await self._session.commit()

        organization = await self._repo.get_organization_by_id(summary.organization_id)
        if organization is None:
            raise ResourceNotFoundError(detail="Demo Tenant organization could not be initialized.")

        if payload.persona == UserRole.PUBLIC_CLIENT:
            public_token = summary.sent_quote_public_token
            logger.info(
                "demo_login_public_client",
                organization_id=str(organization.id),
                public_token=str(public_token),
            )
            return DemoAuthResponse(
                persona=UserRole.PUBLIC_CLIENT,
                access_token=None,
                user=None,
                organization=OrganizationResponse.model_validate(organization),
                demo_public_quote_token=public_token,
                demo_active_work_order_id=summary.active_work_order_id,
                redirect_path=f"/public/quotes/{public_token}",
            )

        target_email = DEMO_OWNER_EMAIL if payload.persona == UserRole.OWNER else DEMO_TECH_EMAIL
        lookup = await self._repo.get_user_by_email(
            target_email,
            organization_slug=organization.slug,
        )
        if lookup is None:
            raise ResourceNotFoundError(detail=f"Demo user '{target_email}' was not found.")

        user, _ = lookup
        token = create_access_token(
            user_id=user.id,
            organization_id=organization.id,
            role=user.role,
            email=user.email,
            full_name=user.full_name,
            is_demo=True,
        )
        redirect_path = "/dashboard" if user.role == UserRole.OWNER else "/work-orders"
        logger.info(
            "demo_login_authenticated",
            persona=user.role.value,
            user_id=str(user.id),
            organization_id=str(organization.id),
        )
        return DemoAuthResponse(
            persona=user.role,
            access_token=token,
            user=UserResponse.model_validate(user),
            organization=OrganizationResponse.model_validate(organization),
            demo_public_quote_token=summary.sent_quote_public_token,
            demo_active_work_order_id=summary.active_work_order_id,
            redirect_path=redirect_path,
        )

    async def demo_reset(self) -> DemoResetResponse:
        """Restore Demo Tenant catalog inventory, quotes, and work orders to clean seed state."""
        summary = await seed_demo_tenant(self._session, force_reset=True)
        await self._session.commit()
        logger.info(
            "demo_tenant_reset_completed",
            organization_id=str(summary.organization_id),
        )
        return DemoResetResponse(
            organization_id=summary.organization_id,
            catalog_items_restored=summary.catalog_items_count,
            quotes_restored=summary.quotes_count,
            demo_public_quote_token=summary.sent_quote_public_token,
            demo_active_work_order_id=summary.active_work_order_id,
        )

    async def get_me(self, ctx: CurrentTenantContext) -> AuthMeResponse:
        """Retrieve current authenticated User and Organization metadata."""
        user = await self._repo.get_user_by_id(ctx.organization_id, ctx.user_id)
        organization = await self._repo.get_organization_by_id(ctx.organization_id)
        if user is None or organization is None:
            raise ResourceNotFoundError(
                detail="Authenticated user or organization no longer exists."
            )
        return AuthMeResponse(
            user=UserResponse.model_validate(user),
            organization=OrganizationResponse.model_validate(organization),
        )
