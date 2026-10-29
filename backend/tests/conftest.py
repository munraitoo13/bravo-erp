"""Pytest fixtures providing isolated PostgreSQL 17 Testcontainers and FastAPI AsyncClient."""

from collections.abc import AsyncGenerator, Generator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool
from testcontainers.postgres import PostgresContainer

from src.core.database import Base, get_db_session
from src.main import app
from src.modules.catalog import models as _catalog_models  # noqa: F401
from src.modules.quotes import models as _quotes_models  # noqa: F401
from src.modules.tenants import models as _tenants_models  # noqa: F401
from src.modules.work_orders import models as _work_orders_models  # noqa: F401


@pytest.fixture(scope="session")
def postgres_container() -> Generator[PostgresContainer, None, None]:
    """Spin up an isolated PostgreSQL 17 container once per test session."""
    with PostgresContainer("postgres:17-alpine") as postgres:
        yield postgres


@pytest.fixture(scope="session")
def test_database_url(postgres_container: PostgresContainer) -> str:
    """Return an asyncpg-compatible connection URL for the Testcontainers PostgreSQL instance."""
    raw_url: str = postgres_container.get_connection_url()
    if raw_url.startswith("postgresql+psycopg2://"):
        return raw_url.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1)
    if raw_url.startswith("postgresql://"):
        return raw_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return raw_url


@pytest.fixture
async def db_engine(test_database_url: str) -> AsyncGenerator[AsyncEngine, None]:
    """Create a clean database schema before each integration test and drop it afterwards."""
    engine = create_async_engine(test_database_url, poolclass=NullPool, future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
def session_maker(db_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Provide an async_sessionmaker bound to the test PostgreSQL engine."""
    return async_sessionmaker(
        bind=db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )


@pytest.fixture
async def db_session(
    session_maker: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncSession, None]:
    """Provide a scoped AsyncSession for direct test setup and assertions."""
    async with session_maker() as session:
        yield session


@pytest.fixture
async def async_client(
    session_maker: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncClient, None]:
    """Provide an httpx.AsyncClient wired to the FastAPI app with overridden test DB session."""

    async def _override_get_db_session() -> AsyncGenerator[AsyncSession, None]:
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_db_session] = _override_get_db_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client
    app.dependency_overrides.clear()
