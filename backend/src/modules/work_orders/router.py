"""Thin FastAPI routers for Work Orders, Serial Vault, Warranties, and SHA-256 Verification."""

import base64
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Query, Request, status
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import UploadFile

from src.core.database import get_db_session
from src.core.dependencies import CurrentTenantContext, require_role
from src.core.exceptions import DomainValidationError
from src.core.security import UserRole
from src.core.storage import StorageClient, get_storage_client
from src.modules.work_orders.models import WorkOrderStatus
from src.modules.work_orders.schemas import (
    DocumentVerificationResponse,
    ExpiringWarrantyItemResponse,
    InstalledSerialCreateRequest,
    InstalledSerialResponse,
    WorkOrderChecklistUpdateRequest,
    WorkOrderCompleteRequest,
    WorkOrderPhotoJsonUploadRequest,
    WorkOrderResponse,
    WorkOrderScheduleRequest,
    WorkOrderStartRequest,
)
from src.modules.work_orders.service import (
    ALLOWED_PHOTO_MIME_TYPES,
    MAX_PHOTO_SIZE_BYTES,
    WorkOrderService,
)

router = APIRouter(tags=["work_orders"])

_DEFAULT_SAMPLE_JPEG_BYTES = (
    b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00\xff\xd9"
)


def get_work_order_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    storage_client: Annotated[StorageClient, Depends(get_storage_client)],
) -> WorkOrderService:
    """Provide scoped WorkOrderService instance with injected DB session and storage client."""
    return WorkOrderService(session, storage_client=storage_client)


def _extract_client_ip(request: Request) -> str | None:
    """Extract client IP from X-Forwarded-For header or request socket."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client is not None:
        return request.client.host
    return None


async def _parse_photo_upload(
    request: Request,
) -> tuple[str, bytes, str, str | None]:
    """Parse either a multipart/form-data file upload or an application/json photo payload."""
    content_type_header = request.headers.get("content-type", "").lower()
    if "multipart/form-data" in content_type_header:
        form = await request.form()
        uploaded = form.get("file") or form.get("photo")
        if not isinstance(uploaded, UploadFile):
            raise DomainValidationError(
                detail="Multipart upload must include a 'file' field.",
                errors=[{"field": "file", "reason": "missing_multipart_file"}],
            )
        file_bytes = await uploaded.read(MAX_PHOTO_SIZE_BYTES + 1)
        if len(file_bytes) > MAX_PHOTO_SIZE_BYTES:
            raise DomainValidationError(
                detail=(
                    f"Uploaded photo exceeds maximum allowed limit of "
                    f"{MAX_PHOTO_SIZE_BYTES} bytes (10MB)."
                ),
                errors=[{"field": "file", "reason": "photo_size_limit_exceeded"}],
            )
        filename = uploaded.filename or "instalacao_cftv.jpg"
        mime_type = (uploaded.content_type or "image/jpeg").lower().split(";")[0].strip()
        if mime_type not in ALLOWED_PHOTO_MIME_TYPES:
            allowed = ", ".join(sorted(ALLOWED_PHOTO_MIME_TYPES))
            raise DomainValidationError(
                detail=(
                    f"Unsupported photo content type '{uploaded.content_type}'. "
                    f"Allowed types: {allowed}."
                ),
                errors=[{"field": "content_type", "reason": "unsupported_media_type"}],
            )
        return filename, file_bytes, mime_type, None

    try:
        raw_json = await request.json()
        parsed = WorkOrderPhotoJsonUploadRequest.model_validate(raw_json)
    except (ValueError, PydanticValidationError) as exc:
        raise DomainValidationError(
            detail="Invalid photo upload payload.",
            errors=[{"field": "body", "reason": "invalid_photo_json"}],
        ) from exc

    normalized_mime = parsed.content_type.lower().split(";")[0].strip()
    if normalized_mime not in ALLOWED_PHOTO_MIME_TYPES:
        allowed = ", ".join(sorted(ALLOWED_PHOTO_MIME_TYPES))
        raise DomainValidationError(
            detail=(
                f"Unsupported photo content type '{parsed.content_type}'. Allowed types: {allowed}."
            ),
            errors=[{"field": "content_type", "reason": "unsupported_media_type"}],
        )

    if parsed.content_base64:
        try:
            decoded_bytes = base64.b64decode(parsed.content_base64)
        except ValueError as exc:
            raise DomainValidationError(
                detail="Invalid base64 encoding in content_base64.",
                errors=[{"field": "content_base64", "reason": "invalid_base64"}],
            ) from exc
    else:
        decoded_bytes = _DEFAULT_SAMPLE_JPEG_BYTES

    if len(decoded_bytes) > MAX_PHOTO_SIZE_BYTES:
        raise DomainValidationError(
            detail=(
                f"Photo file size ({len(decoded_bytes)} bytes) exceeds the maximum allowed "
                f"limit of {MAX_PHOTO_SIZE_BYTES} bytes (10MB)."
            ),
            errors=[{"field": "content_base64", "reason": "photo_size_limit_exceeded"}],
        )

    return parsed.filename, decoded_bytes, normalized_mime, parsed.photo_key


@router.get(
    "/work-orders",
    response_model=list[WorkOrderResponse],
)
async def list_work_orders(
    ctx: Annotated[
        CurrentTenantContext,
        Depends(require_role(UserRole.OWNER, UserRole.TECHNICIAN)),
    ],
    service: Annotated[WorkOrderService, Depends(get_work_order_service)],
    wo_status: Annotated[WorkOrderStatus | None, Query(alias="status")] = None,
) -> list[WorkOrderResponse]:
    """List field work orders for the current tenant organization."""
    return await service.list_work_orders(ctx, status=wo_status)


@router.get(
    "/work-orders/{work_order_id}",
    response_model=WorkOrderResponse,
)
async def get_work_order(
    work_order_id: UUID,
    ctx: Annotated[
        CurrentTenantContext,
        Depends(require_role(UserRole.OWNER, UserRole.TECHNICIAN)),
    ],
    service: Annotated[WorkOrderService, Depends(get_work_order_service)],
) -> WorkOrderResponse:
    """Retrieve a single field work order with checklist, photos, and registered serials."""
    return await service.get_work_order(ctx, work_order_id)


@router.post(
    "/work-orders/{work_order_id}/schedule",
    response_model=WorkOrderResponse,
)
async def schedule_work_order(
    work_order_id: UUID,
    payload: WorkOrderScheduleRequest,
    request: Request,
    ctx: Annotated[CurrentTenantContext, Depends(require_role(UserRole.OWNER))],
    service: Annotated[WorkOrderService, Depends(get_work_order_service)],
) -> WorkOrderResponse:
    """Schedule a PENDING work order and assign a field technician (OWNER only)."""
    return await service.schedule_work_order(
        ctx,
        work_order_id,
        payload,
        actor_ip=_extract_client_ip(request),
    )


@router.post(
    "/work-orders/{work_order_id}/start",
    response_model=WorkOrderResponse,
)
async def start_work_order(
    work_order_id: UUID,
    request: Request,
    ctx: Annotated[
        CurrentTenantContext,
        Depends(require_role(UserRole.OWNER, UserRole.TECHNICIAN)),
    ],
    service: Annotated[WorkOrderService, Depends(get_work_order_service)],
    payload: Annotated[WorkOrderStartRequest | None, Body()] = None,
) -> WorkOrderResponse:
    """Transition work order to IN_FIELD and parent quote to IN_PROGRESS."""
    return await service.start_work_order(
        ctx,
        work_order_id,
        payload,
        actor_ip=_extract_client_ip(request),
    )


@router.patch(
    "/work-orders/{work_order_id}/checklist",
    response_model=WorkOrderResponse,
)
async def update_work_order_checklist(
    work_order_id: UUID,
    payload: WorkOrderChecklistUpdateRequest,
    request: Request,
    ctx: Annotated[
        CurrentTenantContext,
        Depends(require_role(UserRole.OWNER, UserRole.TECHNICIAN)),
    ],
    service: Annotated[WorkOrderService, Depends(get_work_order_service)],
) -> WorkOrderResponse:
    """Update field checklist step states, cloud_p2p_id, or technician notes."""
    return await service.update_checklist(
        ctx,
        work_order_id,
        payload,
        actor_ip=_extract_client_ip(request),
    )


@router.post(
    "/work-orders/{work_order_id}/photos",
    response_model=WorkOrderResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_work_order_photo(
    work_order_id: UUID,
    request: Request,
    ctx: Annotated[
        CurrentTenantContext,
        Depends(require_role(UserRole.OWNER, UserRole.TECHNICIAN)),
    ],
    service: Annotated[WorkOrderService, Depends(get_work_order_service)],
) -> WorkOrderResponse:
    """Upload an installation photo to MinIO and append its key to installation_photos_keys."""
    filename, content, mime_type, explicit_key = await _parse_photo_upload(request)
    return await service.upload_installation_photo(
        ctx,
        work_order_id,
        filename=filename,
        content=content,
        content_type=mime_type,
        explicit_key=explicit_key,
        actor_ip=_extract_client_ip(request),
    )


@router.post(
    "/work-orders/{work_order_id}/serials",
    response_model=InstalledSerialResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register_work_order_serial(
    work_order_id: UUID,
    payload: InstalledSerialCreateRequest,
    request: Request,
    ctx: Annotated[
        CurrentTenantContext,
        Depends(require_role(UserRole.OWNER, UserRole.TECHNICIAN)),
    ],
    service: Annotated[WorkOrderService, Depends(get_work_order_service)],
) -> InstalledSerialResponse:
    """Register a hardware serial number in the Serial Vault with automatic warranty dates."""
    return await service.register_serial_number(
        ctx,
        work_order_id,
        payload,
        actor_ip=_extract_client_ip(request),
    )


@router.post(
    "/work-orders/{work_order_id}/complete",
    response_model=WorkOrderResponse,
)
async def complete_work_order(
    work_order_id: UUID,
    request: Request,
    ctx: Annotated[
        CurrentTenantContext,
        Depends(require_role(UserRole.OWNER, UserRole.TECHNICIAN)),
    ],
    service: Annotated[WorkOrderService, Depends(get_work_order_service)],
    payload: Annotated[WorkOrderCompleteRequest | None, Body()] = None,
) -> WorkOrderResponse:
    """Validate checklist, photos, and Serial Vault; deduct stock; set 12m warranty; complete."""
    return await service.complete_work_order(
        ctx,
        work_order_id,
        payload,
        actor_ip=_extract_client_ip(request),
    )


@router.get(
    "/warranties/expiring",
    response_model=list[ExpiringWarrantyItemResponse],
)
async def list_expiring_warranties(
    ctx: Annotated[CurrentTenantContext, Depends(require_role(UserRole.OWNER))],
    service: Annotated[WorkOrderService, Depends(get_work_order_service)],
) -> list[ExpiringWarrantyItemResponse]:
    """List installations approaching the 11-month preventive maintenance mark (OWNER only)."""
    return await service.list_expiring_warranties(ctx)


@router.get(
    "/verify/{pdf_sha256_hash}",
    response_model=DocumentVerificationResponse,
)
async def verify_document_authenticity(
    pdf_sha256_hash: str,
    service: Annotated[WorkOrderService, Depends(get_work_order_service)],
) -> DocumentVerificationResponse:
    """Public cryptographic verifier confirming PDF proposal/warranty SHA-256 authenticity."""
    return await service.verify_document_by_sha256(pdf_sha256_hash)
