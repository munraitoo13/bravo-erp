"""FastAPI application factory and healthcheck endpoints for bravo-erp."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Literal

import structlog
from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict

from src.core.broker import broker
from src.core.config import get_settings
from src.core.exceptions import ResourceNotFoundError, register_exception_handlers
from src.core.logging import CorrelationIdMiddleware, configure_logging, get_correlation_id
from src.modules.catalog.router import router as catalog_router
from src.modules.quotes.router import router as quotes_router
from src.modules.sizing.router import router as sizing_router
from src.modules.tenants.router import router as auth_router
from src.modules.work_orders.router import router as work_orders_router

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


class HealthCheckResponse(BaseModel):
    """Typed response contract for /api/v1/health."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["ok"]
    service: str
    version: str
    environment: str
    correlation_id: str


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage FastAPI startup and shutdown lifecycle (Taskiq broker & structured logging)."""
    settings = get_settings()
    configure_logging(json_logs=settings.environment != "development")
    if not broker.is_worker_process and settings.environment != "test":
        await broker.startup()
    logger.info("application_started", app_name=settings.app_name, env=settings.environment)
    yield
    if not broker.is_worker_process and settings.environment != "test":
        await broker.shutdown()
    logger.info("application_stopped", app_name=settings.app_name)


def create_app() -> FastAPI:
    """Construct and configure the FastAPI application instance."""
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=lifespan,
        docs_url=f"{settings.api_v1_prefix}/docs",
        openapi_url=f"{settings.api_v1_prefix}/openapi.json",
    )

    app.add_middleware(CorrelationIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Correlation-ID"],
    )

    register_exception_handlers(app)

    router = APIRouter(prefix=settings.api_v1_prefix, tags=["system"])

    @router.get("/health", response_model=HealthCheckResponse)
    async def health_check() -> HealthCheckResponse:
        """Return service health status and echo active correlation_id."""
        return HealthCheckResponse(
            status="ok",
            service=settings.app_name,
            version=settings.app_version,
            environment=settings.environment,
            correlation_id=get_correlation_id(),
        )

    @router.get("/health/error-probe", response_model=HealthCheckResponse)
    async def error_probe() -> HealthCheckResponse:
        """Diagnostic probe endpoint raising a typed DomainError to verify RFC 7807 format."""
        raise ResourceNotFoundError(
            detail="Diagnostic resource 'dvr_mhdx_probe' was not found in this tenant.",
            errors=[{"resource": "dvr_mhdx_probe", "reason": "probe_verification"}],
        )

    app.include_router(router)
    app.include_router(auth_router, prefix=settings.api_v1_prefix)
    app.include_router(catalog_router, prefix=settings.api_v1_prefix)
    app.include_router(sizing_router, prefix=settings.api_v1_prefix)
    app.include_router(quotes_router, prefix=settings.api_v1_prefix)
    app.include_router(work_orders_router, prefix=settings.api_v1_prefix)
    return app


app = create_app()
