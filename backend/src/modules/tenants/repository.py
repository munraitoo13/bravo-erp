"""SQLAlchemy 2.0 async repository for Organization and User lookups."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.tenants.models import Organization, User


class TenantRepository:
    """Data access layer for Organization and User entities."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_organization_by_id(self, organization_id: UUID) -> Organization | None:
        """Retrieve an Organization by primary key."""
        stmt = select(Organization).where(Organization.id == organization_id)
        return await self._session.scalar(stmt)

    async def get_organization_by_slug(self, slug: str) -> Organization | None:
        """Retrieve an Organization by unique slug."""
        stmt = select(Organization).where(Organization.slug == slug)
        return await self._session.scalar(stmt)

    async def get_user_by_id(
        self,
        organization_id: UUID,
        user_id: UUID,
    ) -> User | None:
        """Retrieve a User scoped to a specific organization_id."""
        stmt = select(User).where(
            User.organization_id == organization_id,
            User.id == user_id,
        )
        return await self._session.scalar(stmt)

    async def get_user_by_email(
        self,
        email: str,
        *,
        organization_slug: str | None = None,
    ) -> tuple[User, Organization] | None:
        """Retrieve an active User and their Organization by email (and optional org slug)."""
        stmt = (
            select(User, Organization)
            .join(Organization, User.organization_id == Organization.id)
            .where(User.email == email.lower().strip())
        )
        if organization_slug is not None:
            stmt = stmt.where(Organization.slug == organization_slug.strip())

        row = (await self._session.execute(stmt)).first()
        if row is None:
            return None
        user, organization = row
        return user, organization
