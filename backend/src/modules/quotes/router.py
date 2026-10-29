"""Thin FastAPI routers for Customers, Quotes, and Public Quote Approval."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db_session
from src.core.dependencies import CurrentTenantContext, require_role
from src.core.security import UserRole
from src.core.storage import StorageClient, get_storage_client
from src.modules.quotes.models import QuoteStatus
from src.modules.quotes.schemas import (
    CustomerCreateRequest,
    CustomerResponse,
    PublicQuoteApproveRequest,
    QuoteCreateRequest,
    QuoteOwnerResponse,
    QuotePublicResponse,
    QuoteTechnicianResponse,
)
from src.modules.quotes.service import QuoteRoleResponse, QuoteService

router = APIRouter(tags=["quotes"])


def get_quote_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    storage_client: Annotated[StorageClient, Depends(get_storage_client)],
) -> QuoteService:
    """Provide scoped QuoteService instance."""
    return QuoteService(session, storage_client=storage_client)


def _extract_client_ip(request: Request) -> str | None:
    """Extract client IP from X-Forwarded-For header or request client socket."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client is not None:
        return request.client.host
    return None


@router.get(
    "/customers",
    response_model=list[CustomerResponse],
)
async def list_customers(
    ctx: Annotated[
        CurrentTenantContext,
        Depends(require_role(UserRole.OWNER, UserRole.TECHNICIAN)),
    ],
    service: Annotated[QuoteService, Depends(get_quote_service)],
) -> list[CustomerResponse]:
    """List all customers in the current tenant organization."""
    return await service.list_customers(ctx)


@router.post(
    "/customers",
    response_model=CustomerResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_customer(
    payload: CustomerCreateRequest,
    ctx: Annotated[CurrentTenantContext, Depends(require_role(UserRole.OWNER))],
    service: Annotated[QuoteService, Depends(get_quote_service)],
) -> CustomerResponse:
    """Create a new customer for the current tenant organization (OWNER only)."""
    return await service.create_customer(ctx, payload)


@router.get(
    "/quotes",
    response_model=list[QuoteOwnerResponse | QuoteTechnicianResponse],
)
async def list_quotes(
    ctx: Annotated[
        CurrentTenantContext,
        Depends(require_role(UserRole.OWNER, UserRole.TECHNICIAN)),
    ],
    service: Annotated[QuoteService, Depends(get_quote_service)],
    quote_status: Annotated[QuoteStatus | None, Query(alias="status")] = None,
) -> list[QuoteRoleResponse]:
    """List tenant quotes (cost and margin fields omitted for TECHNICIAN)."""
    return await service.list_quotes(ctx, status=quote_status)


@router.post(
    "/quotes",
    response_model=QuoteOwnerResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_quote(
    payload: QuoteCreateRequest,
    request: Request,
    ctx: Annotated[CurrentTenantContext, Depends(require_role(UserRole.OWNER))],
    service: Annotated[QuoteService, Depends(get_quote_service)],
) -> QuoteOwnerResponse:
    """Create a new quote in DRAFT state (OWNER only)."""
    return await service.create_quote(ctx, payload, actor_ip=_extract_client_ip(request))


@router.get(
    "/quotes/{quote_id}",
    response_model=QuoteOwnerResponse | QuoteTechnicianResponse,
)
async def get_quote(
    quote_id: UUID,
    ctx: Annotated[
        CurrentTenantContext,
        Depends(require_role(UserRole.OWNER, UserRole.TECHNICIAN)),
    ],
    service: Annotated[QuoteService, Depends(get_quote_service)],
) -> QuoteRoleResponse:
    """Retrieve a single quote with line items and audit trail."""
    return await service.get_quote(ctx, quote_id)


@router.post(
    "/quotes/{quote_id}/send",
    response_model=QuoteOwnerResponse,
)
async def send_quote(
    quote_id: UUID,
    request: Request,
    ctx: Annotated[CurrentTenantContext, Depends(require_role(UserRole.OWNER))],
    service: Annotated[QuoteService, Depends(get_quote_service)],
) -> QuoteOwnerResponse:
    """Transition quote from DRAFT -> SENT and enqueue QuoteSentEvent in outbox_events."""
    return await service.send_quote(ctx, quote_id, actor_ip=_extract_client_ip(request))


@router.post(
    "/quotes/{quote_id}/approve",
    response_model=QuoteOwnerResponse,
)
async def approve_quote_owner(
    quote_id: UUID,
    request: Request,
    ctx: Annotated[CurrentTenantContext, Depends(require_role(UserRole.OWNER))],
    service: Annotated[QuoteService, Depends(get_quote_service)],
) -> QuoteOwnerResponse:
    """Approve a SENT quote as OWNER with SELECT ... FOR UPDATE stock reservation."""
    return await service.approve_quote_by_owner(
        ctx,
        quote_id,
        actor_ip=_extract_client_ip(request),
    )


@router.post(
    "/quotes/{quote_id}/cancel",
    response_model=QuoteOwnerResponse,
)
async def cancel_quote(
    quote_id: UUID,
    request: Request,
    ctx: Annotated[CurrentTenantContext, Depends(require_role(UserRole.OWNER))],
    service: Annotated[QuoteService, Depends(get_quote_service)],
) -> QuoteOwnerResponse:
    """Cancel a quote and release reserved stock if previously APPROVED (OWNER only)."""
    return await service.cancel_quote(ctx, quote_id, actor_ip=_extract_client_ip(request))


@router.get(
    "/public/quotes/{public_token}",
    response_model=QuotePublicResponse,
)
async def get_public_quote(
    public_token: UUID,
    service: Annotated[QuoteService, Depends(get_quote_service)],
) -> QuotePublicResponse:
    """Token-scoped public proposal access for PUBLIC_CLIENT (no login required)."""
    return await service.get_public_quote(public_token)


@router.post(
    "/public/quotes/{public_token}/approve",
    response_model=QuotePublicResponse,
)
async def approve_public_quote(
    public_token: UUID,
    request: Request,
    service: Annotated[QuoteService, Depends(get_quote_service)],
    payload: Annotated[PublicQuoteApproveRequest | None, Body()] = None,
) -> QuotePublicResponse:
    """Atomically lock inventory, approve quote, create WorkOrder, and emit OutboxEvent."""
    notes = payload.client_notes if payload is not None else None
    return await service.approve_public_quote(
        public_token,
        client_ip=_extract_client_ip(request),
        client_notes=notes,
    )
