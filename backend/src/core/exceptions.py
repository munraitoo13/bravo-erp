"""Typed domain exception hierarchy and RFC 7807 Problem Details exception handlers."""

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from src.core.logging import CORRELATION_ID_HEADER, get_correlation_id

PROBLEM_JSON_MEDIA_TYPE = "application/problem+json"
ERROR_BASE_URI = "https://bravo-erp.dev/errors"

type ErrorDetailItem = dict[str, str | int | float | bool | None]


class ProblemDetails(BaseModel):
    """RFC 7807 Problem Details for HTTP APIs response contract."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    type: str
    title: str
    status: int
    detail: str
    instance: str
    correlation_id: str
    errors: list[ErrorDetailItem] | None = None


class DomainError(Exception):
    """Base class for all structured domain and application service exceptions."""

    error_slug: str = "domain-error"
    title: str = "Domain Rule Violation"
    http_status: int = status.HTTP_400_BAD_REQUEST

    def __init__(
        self,
        detail: str,
        *,
        errors: list[ErrorDetailItem] | None = None,
    ) -> None:
        super().__init__(detail)
        self.detail = detail
        self.errors = errors


class ResourceNotFoundError(DomainError):
    """Raised when a requested entity does not exist or belongs to another tenant."""

    error_slug = "resource-not-found"
    title = "Resource Not Found"
    http_status = status.HTTP_404_NOT_FOUND


class InvalidStateTransitionError(DomainError):
    """Raised when an illegal Quote or Work Order state machine transition is attempted."""

    error_slug = "invalid-state-transition"
    title = "Invalid Lifecycle State Transition"
    http_status = status.HTTP_422_UNPROCESSABLE_CONTENT


class DomainValidationError(DomainError):
    """Raised when a domain invariant or engineering rule fails validation."""

    error_slug = "domain-validation-error"
    title = "Domain Validation Failed"
    http_status = status.HTTP_422_UNPROCESSABLE_CONTENT


class ValidationError(DomainValidationError):
    """Alias for DomainValidationError used across domain specifications."""


class StorageCapacityExceededError(DomainValidationError):
    """Raised when required storage TB exceeds the capacity of all compatible recorders."""

    error_slug = "storage-capacity-exceeded"
    title = "Storage Capacity Exceeded"


class TopologyIncompatibleError(DomainValidationError):
    """Raised when no recorder in the catalog can satisfy the requested camera topology."""

    error_slug = "topology-incompatible"
    title = "Camera Topology Incompatible With Available Recorders"


class InsufficientStockError(DomainError):
    """Raised during quote approval when available physical stock is insufficient."""

    error_slug = "insufficient-stock"
    title = "Insufficient Stock for Quote Approval"
    http_status = status.HTTP_409_CONFLICT


class ConcurrencyConflictError(DomainError):
    """Raised when optimistic or pessimistic concurrency checks detect a conflict."""

    error_slug = "concurrency-conflict"
    title = "Concurrent Modification Conflict"
    http_status = status.HTTP_409_CONFLICT


class AuthenticationFailedError(DomainError):
    """Raised when credentials or JWT tokens are invalid or expired."""

    error_slug = "authentication-failed"
    title = "Authentication Failed"
    http_status = status.HTTP_401_UNAUTHORIZED


class TenantAccessDeniedError(DomainError):
    """Raised when an actor attempts an unauthorized cross-tenant operation."""

    error_slug = "tenant-access-denied"
    title = "Tenant Access Denied"
    http_status = status.HTTP_403_FORBIDDEN


class RolePermissionDeniedError(DomainError):
    """Raised when a user's RBAC role lacks permission for the requested action."""

    error_slug = "role-permission-denied"
    title = "Role Permission Denied"
    http_status = status.HTTP_403_FORBIDDEN


class DemoProtectionError(DomainError):
    """Raised when attempting destructive deletion of protected Demo Tenant seed items."""

    error_slug = "demo-seed-protected"
    title = "Demo Seed Resource Protected"
    http_status = status.HTTP_403_FORBIDDEN


async def domain_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Convert any DomainError subclass into an RFC 7807 application/problem+json response."""
    domain_exc = (
        exc if isinstance(exc, DomainError) else DomainError(detail="Unexpected domain error.")
    )
    correlation_id = getattr(request.state, "correlation_id", None) or get_correlation_id()
    problem = ProblemDetails(
        type=f"{ERROR_BASE_URI}/{domain_exc.error_slug}",
        title=domain_exc.title,
        status=domain_exc.http_status,
        detail=domain_exc.detail,
        instance=request.url.path,
        correlation_id=correlation_id,
        errors=domain_exc.errors,
    )
    return JSONResponse(
        status_code=domain_exc.http_status,
        content=problem.model_dump(exclude_none=True),
        media_type=PROBLEM_JSON_MEDIA_TYPE,
        headers={CORRELATION_ID_HEADER: correlation_id},
    )


async def request_validation_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Convert FastAPI RequestValidationError into an RFC 7807 response."""
    correlation_id = getattr(request.state, "correlation_id", None) or get_correlation_id()
    formatted_errors: list[ErrorDetailItem] = []
    if isinstance(exc, RequestValidationError):
        for err in exc.errors():
            loc_parts = [str(part) for part in err.get("loc", ())]
            formatted_errors.append(
                {
                    "field": ".".join(loc_parts),
                    "message": str(err.get("msg", "Invalid value")),
                    "type": str(err.get("type", "value_error")),
                }
            )

    problem = ProblemDetails(
        type=f"{ERROR_BASE_URI}/request-validation-failed",
        title="Request Validation Failed",
        status=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail="One or more request parameters failed schema validation.",
        instance=request.url.path,
        correlation_id=correlation_id,
        errors=formatted_errors,
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content=problem.model_dump(exclude_none=True),
        media_type=PROBLEM_JSON_MEDIA_TYPE,
        headers={CORRELATION_ID_HEADER: correlation_id},
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register RFC 7807 exception handlers on the FastAPI application instance."""
    app.add_exception_handler(DomainError, domain_error_handler)
    app.add_exception_handler(RequestValidationError, request_validation_error_handler)
