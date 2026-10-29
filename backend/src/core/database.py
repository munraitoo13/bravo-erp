"""SQLAlchemy 2.0 AsyncEngine, AsyncSession factory, DeclarativeBase, and UUIDv7 generator."""

import secrets
import time
from collections.abc import AsyncGenerator
from uuid import UUID

from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from src.core.config import get_settings

NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def generate_uuid7() -> UUID:
    """Generate an RFC 9562 time-ordered UUIDv7 for B-Tree index locality."""
    timestamp_ms = int(time.time() * 1000) & 0xFFFFFFFFFFFF
    rand_a = secrets.randbits(12)
    rand_b = secrets.randbits(62)
    uuid_int = (timestamp_ms << 80) | (0x7 << 76) | (rand_a << 64) | (0x2 << 62) | rand_b
    return UUID(int=uuid_int)


class Base(DeclarativeBase):
    """Declarative base for all SQLAlchemy 2.0 ORM models."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


_settings = get_settings()

engine: AsyncEngine = create_async_engine(
    _settings.database_url,
    echo=False,
    pool_pre_ping=True,
    future=True,
)

async_session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding a scoped SQLAlchemy 2.0 AsyncSession."""
    async with async_session_factory() as session:
        yield session
