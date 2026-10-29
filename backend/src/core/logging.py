"""Structured logging setup (structlog) and Correlation-ID ASGI middleware."""

import logging
import sys
import uuid
from collections.abc import Awaitable, Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

CORRELATION_ID_HEADER = "X-Correlation-ID"


def get_correlation_id() -> str:
    """Retrieve the active correlation_id from structlog contextvars or generate a fallback."""
    ctx = structlog.contextvars.get_contextvars()
    corr_id = ctx.get("correlation_id")
    if isinstance(corr_id, str) and corr_id:
        return corr_id
    return f"req_{uuid.uuid4().hex[:20]}"


def configure_logging(*, json_logs: bool = True, log_level: str = "INFO") -> None:
    """Configure structlog for structured JSON or console output."""
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    renderer: structlog.types.Processor = (
        structlog.processors.JSONRenderer()
        if json_logs
        else structlog.dev.ConsoleRenderer(colors=True)
    )

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, log_level.upper(), logging.INFO)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Extract or generate X-Correlation-ID, bind to structlog contextvars, and echo on response."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """Bind correlation_id for the lifecycle of the incoming HTTP request."""
        incoming_id = request.headers.get(CORRELATION_ID_HEADER)
        correlation_id = (
            incoming_id.strip()
            if incoming_id and incoming_id.strip()
            else f"req_{uuid.uuid4().hex[:20]}"
        )

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            correlation_id=correlation_id,
            http_method=request.method,
            http_path=request.url.path,
        )
        request.state.correlation_id = correlation_id

        response = await call_next(request)
        response.headers[CORRELATION_ID_HEADER] = correlation_id
        return response
