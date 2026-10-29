"""Application service for Field Work Orders, Serial Number Vault, Warranties, and Verifier."""

import re
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import generate_uuid7
from src.core.dependencies import CurrentTenantContext
from src.core.exceptions import (
    DomainValidationError,
    InsufficientStockError,
    InvalidStateTransitionError,
    ResourceNotFoundError,
)
from src.core.logging import get_correlation_id
from src.core.storage import StorageClient
from src.modules.catalog.models import CatalogCategory
from src.modules.quotes.models import (
    AuditLog,
    OutboxEvent,
    OutboxStatus,
    Quote,
    QuoteStatus,
)
from src.modules.quotes.schemas import CustomerResponse
from src.modules.quotes.service import normalize_client_ip, trigger_outbox_poll_safely
from src.modules.quotes.state_machine import QuoteStateMachine
from src.modules.work_orders.models import InstalledSerial, WorkOrder, WorkOrderStatus
from src.modules.work_orders.repository import WorkOrderRepository
from src.modules.work_orders.schemas import (
    ChecklistStepItem,
    DocumentVerificationResponse,
    ExpiringWarrantyItemResponse,
    InstalledSerialCreateRequest,
    InstalledSerialResponse,
    RequiredSerialItemSummary,
    WorkOrderChecklistUpdateRequest,
    WorkOrderCompleteRequest,
    WorkOrderResponse,
    WorkOrderScheduleRequest,
    WorkOrderStartRequest,
)
from src.modules.work_orders.state_machine import (
    RequiredHardwareSerialSpec,
    WorkOrderStateMachine,
)

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

_SAFE_FILENAME_RE = re.compile(r"[^a-zA-Z0-9._-]+")

ALLOWED_PHOTO_MIME_TYPES: frozenset[str] = frozenset({"image/jpeg", "image/png", "image/webp"})
MAX_PHOTO_SIZE_BYTES: int = 10 * 1024 * 1024  # 10 MB


def _sanitize_filename(filename: str) -> str:
    """Sanitize uploaded photo filename for safe S3 object keys."""
    cleaned = _SAFE_FILENAME_RE.sub("-", filename.strip()).strip("-")
    return cleaned or "instalacao.jpg"


def _mask_document(doc: str) -> str:
    """Partially mask CPF/CNPJ for public cryptographic verification display."""
    cleaned = doc.strip()
    if len(cleaned) <= 6:
        return cleaned
    return f"{cleaned[:4]}***{cleaned[-3:]}"


def serialize_installed_serial(serial: InstalledSerial) -> InstalledSerialResponse:
    """Convert an InstalledSerial ORM model into an InstalledSerialResponse DTO."""
    return InstalledSerialResponse(
        id=serial.id,
        organization_id=serial.organization_id,
        work_order_id=serial.work_order_id,
        catalog_item_id=serial.catalog_item_id,
        sku=serial.catalog_item.sku,
        name_pt_br=serial.catalog_item.name_pt_br,
        category=serial.catalog_item.category,
        serial_number=serial.serial_number,
        channel_or_slot_label=serial.channel_or_slot_label,
        distributor_warranty_until=serial.distributor_warranty_until,
        client_warranty_until=serial.client_warranty_until,
        created_at=serial.created_at,
    )


def build_required_serial_specs(quote: Quote) -> list[RequiredHardwareSerialSpec]:
    """Derive required serial counts for all quote items where requires_serial_number is True."""
    qty_by_catalog_id: dict[UUID, int] = defaultdict(int)
    meta_by_catalog_id: dict[UUID, tuple[str, str]] = {}

    for line in quote.items:
        cat_item = line.catalog_item
        requires_sn = bool(cat_item.specs.get("requires_serial_number", False))
        if requires_sn:
            qty_by_catalog_id[cat_item.id] += line.quantity
            meta_by_catalog_id[cat_item.id] = (cat_item.sku, cat_item.name_pt_br)

    specs: list[RequiredHardwareSerialSpec] = []
    for cat_id, req_qty in qty_by_catalog_id.items():
        sku, name_pt_br = meta_by_catalog_id[cat_id]
        specs.append(
            RequiredHardwareSerialSpec(
                catalog_item_id=cat_id,
                sku=sku,
                name_pt_br=name_pt_br,
                required_quantity=req_qty,
            )
        )
    return sorted(specs, key=lambda s: s.sku)


class WorkOrderService:
    """Orchestrates field Work Order execution, Serial Vault registration, and Warranty checks."""

    def __init__(
        self,
        session: AsyncSession,
        storage_client: StorageClient | None = None,
    ) -> None:
        self._session = session
        self._repo = WorkOrderRepository(session)
        self._storage = storage_client or StorageClient()

    async def _serialize_work_order(self, work_order: WorkOrder) -> WorkOrderResponse:
        """Serialize a WorkOrder ORM instance into a role-safe WorkOrderResponse."""
        quote = work_order.quote
        customer_dto = CustomerResponse.model_validate(quote.customer)

        checklist_dtos: list[ChecklistStepItem] = []
        for raw_step in work_order.checklist_json:
            checked_at_val = raw_step.get("checked_at")
            checklist_dtos.append(
                ChecklistStepItem(
                    step_id=str(raw_step.get("step_id", "")),
                    label_pt_br=str(raw_step.get("label_pt_br", "")),
                    is_checked=bool(raw_step.get("is_checked", False)),
                    checked_at=str(checked_at_val) if checked_at_val is not None else None,
                )
            )

        photo_urls: list[str] = []
        for key in work_order.installation_photos_keys:
            url = await self._storage.generate_presigned_download_url(object_key=key)
            photo_urls.append(url)

        serial_dtos = [serialize_installed_serial(s) for s in work_order.installed_serials]

        registered_counts: dict[UUID, int] = defaultdict(int)
        for s in work_order.installed_serials:
            registered_counts[s.catalog_item_id] += 1

        category_by_id = {line.catalog_item_id: line.catalog_item.category for line in quote.items}
        required_specs = build_required_serial_specs(quote)
        summary_dtos: list[RequiredSerialItemSummary] = []
        for spec in required_specs:
            reg_qty = registered_counts.get(spec.catalog_item_id, 0)
            summary_dtos.append(
                RequiredSerialItemSummary(
                    catalog_item_id=spec.catalog_item_id,
                    sku=spec.sku,
                    name_pt_br=spec.name_pt_br,
                    category=category_by_id.get(spec.catalog_item_id, CatalogCategory.ACCESSORY),
                    required_quantity=spec.required_quantity,
                    registered_quantity=reg_qty,
                    is_satisfied=reg_qty >= spec.required_quantity,
                )
            )

        tech_name = (
            work_order.assigned_technician.full_name
            if work_order.assigned_technician is not None
            else None
        )

        return WorkOrderResponse(
            id=work_order.id,
            organization_id=work_order.organization_id,
            quote_id=work_order.quote_id,
            quote_status=quote.status,
            customer=customer_dto,
            assigned_technician_id=work_order.assigned_technician_id,
            assigned_technician_name=tech_name,
            status=work_order.status,
            checklist_json=checklist_dtos,
            installation_photos_keys=list(work_order.installation_photos_keys),
            installation_photo_urls=photo_urls,
            cloud_p2p_id=work_order.cloud_p2p_id,
            notes=work_order.notes,
            completed_at=work_order.completed_at,
            warranty_expires_at=work_order.warranty_expires_at,
            preventive_maintenance_alert_sent=work_order.preventive_maintenance_alert_sent,
            installed_serials=serial_dtos,
            required_serials_summary=summary_dtos,
            created_at=work_order.created_at,
            updated_at=work_order.updated_at,
        )

    async def list_work_orders(
        self,
        ctx: CurrentTenantContext,
        *,
        status: WorkOrderStatus | None = None,
    ) -> list[WorkOrderResponse]:
        """List all field WorkOrders in the current tenant organization."""
        work_orders = await self._repo.list_work_orders(ctx.organization_id, status=status)
        return [await self._serialize_work_order(wo) for wo in work_orders]

    async def get_work_order(
        self,
        ctx: CurrentTenantContext,
        work_order_id: UUID,
    ) -> WorkOrderResponse:
        """Retrieve a single WorkOrder by ID scoped to the current tenant."""
        work_order = await self._repo.get_work_order_by_id(ctx.organization_id, work_order_id)
        if work_order is None:
            raise ResourceNotFoundError(
                detail=f"Work order '{work_order_id}' was not found in this organization.",
                errors=[{"work_order_id": str(work_order_id)}],
            )
        return await self._serialize_work_order(work_order)

    async def schedule_work_order(
        self,
        ctx: CurrentTenantContext,
        work_order_id: UUID,
        payload: WorkOrderScheduleRequest,
        *,
        actor_ip: str | None = None,
    ) -> WorkOrderResponse:
        """Transition a WorkOrder from PENDING -> SCHEDULED and optionally assign a technician."""
        work_order = await self._repo.get_work_order_by_id(
            ctx.organization_id,
            work_order_id,
            for_update=True,
        )
        if work_order is None:
            raise ResourceNotFoundError(
                detail=f"Work order '{work_order_id}' was not found in this organization.",
                errors=[{"work_order_id": str(work_order_id)}],
            )

        tech_id = payload.assigned_technician_id or work_order.assigned_technician_id
        if tech_id is not None:
            tech_user = await self._repo.get_user_by_id(ctx.organization_id, tech_id)
            if tech_user is None:
                raise ResourceNotFoundError(
                    detail=f"Technician user '{tech_id}' was not found in this organization.",
                    errors=[{"assigned_technician_id": str(tech_id)}],
                )

        diff = WorkOrderStateMachine.transition_to_scheduled(
            work_order.status,
            assigned_technician_id=tech_id,
        )
        work_order.status = WorkOrderStatus.SCHEDULED
        work_order.assigned_technician_id = tech_id
        if payload.notes is not None:
            work_order.notes = payload.notes

        await self._repo.add_audit_log(
            AuditLog(
                organization_id=ctx.organization_id,
                entity_type="WORK_ORDER",
                entity_id=work_order.id,
                action="STATE_TRANSITION",
                actor_user_id=ctx.user_id,
                actor_ip=normalize_client_ip(actor_ip),
                previous_state=diff.previous_state,
                new_state=diff.new_state,
            )
        )
        await self._session.commit()

        reloaded = await self._repo.get_work_order_by_id(ctx.organization_id, work_order.id)
        if reloaded is None:  # pragma: no cover
            raise ResourceNotFoundError(detail="Work order not found after scheduling.")
        return await self._serialize_work_order(reloaded)

    async def start_work_order(
        self,
        ctx: CurrentTenantContext,
        work_order_id: UUID,
        payload: WorkOrderStartRequest | None = None,
        *,
        actor_ip: str | None = None,
    ) -> WorkOrderResponse:
        """Transition WorkOrder to IN_FIELD and parent Quote from APPROVED to IN_PROGRESS."""
        work_order = await self._repo.get_work_order_by_id(
            ctx.organization_id,
            work_order_id,
            for_update=True,
        )
        if work_order is None:
            raise ResourceNotFoundError(
                detail=f"Work order '{work_order_id}' was not found in this organization.",
                errors=[{"work_order_id": str(work_order_id)}],
            )

        quote = await self._repo.get_quote_for_update(ctx.organization_id, work_order.quote_id)
        if quote is None:  # pragma: no cover
            raise ResourceNotFoundError(detail="Parent quote not found for work order.")

        requested_tech_id = payload.assigned_technician_id if payload is not None else None
        effective_tech_id = requested_tech_id or work_order.assigned_technician_id or ctx.user_id
        if effective_tech_id is not None:
            tech_user = await self._repo.get_user_by_id(ctx.organization_id, effective_tech_id)
            if tech_user is None:
                raise ResourceNotFoundError(
                    detail=(
                        f"Technician user '{effective_tech_id}' was not found in this organization."
                    ),
                    errors=[{"assigned_technician_id": str(effective_tech_id)}],
                )

        wo_diff = WorkOrderStateMachine.transition_to_in_field(
            work_order.status,
            assigned_technician_id=effective_tech_id,
        )
        work_order.status = WorkOrderStatus.IN_FIELD
        work_order.assigned_technician_id = effective_tech_id
        if payload is not None and payload.notes is not None:
            work_order.notes = payload.notes

        sanitized_ip = normalize_client_ip(actor_ip)

        if quote.status == QuoteStatus.APPROVED:
            quote_diff = QuoteStateMachine.transition_to_in_progress(
                quote.status,
                current_version=quote.version,
            )
            quote.status = QuoteStatus.IN_PROGRESS
            quote.version += 1
            await self._repo.add_audit_log(
                AuditLog(
                    organization_id=ctx.organization_id,
                    entity_type="QUOTE",
                    entity_id=quote.id,
                    action="STATE_TRANSITION",
                    actor_user_id=ctx.user_id,
                    actor_ip=sanitized_ip,
                    previous_state=quote_diff.previous_state,
                    new_state=quote_diff.new_state,
                )
            )

        await self._repo.add_audit_log(
            AuditLog(
                organization_id=ctx.organization_id,
                entity_type="WORK_ORDER",
                entity_id=work_order.id,
                action="STATE_TRANSITION",
                actor_user_id=ctx.user_id,
                actor_ip=sanitized_ip,
                previous_state=wo_diff.previous_state,
                new_state=wo_diff.new_state,
            )
        )
        await self._session.commit()

        reloaded = await self._repo.get_work_order_by_id(ctx.organization_id, work_order.id)
        if reloaded is None:  # pragma: no cover
            raise ResourceNotFoundError(detail="Work order not found after start.")
        logger.info(
            "work_order_started",
            work_order_id=str(reloaded.id),
            quote_id=str(reloaded.quote_id),
            organization_id=str(ctx.organization_id),
        )
        return await self._serialize_work_order(reloaded)

    async def update_checklist(
        self,
        ctx: CurrentTenantContext,
        work_order_id: UUID,
        payload: WorkOrderChecklistUpdateRequest,
        *,
        actor_ip: str | None = None,
    ) -> WorkOrderResponse:
        """Toggle checklist items and update cloud_p2p_id or field notes on a WorkOrder."""
        work_order = await self._repo.get_work_order_by_id(
            ctx.organization_id,
            work_order_id,
            for_update=True,
        )
        if work_order is None:
            raise ResourceNotFoundError(
                detail=f"Work order '{work_order_id}' was not found in this organization.",
                errors=[{"work_order_id": str(work_order_id)}],
            )

        if work_order.status == WorkOrderStatus.COMPLETED:
            raise InvalidStateTransitionError(
                detail="Cannot modify checklist or field notes of a COMPLETED WorkOrder.",
                errors=[
                    {
                        "entity_type": "WORK_ORDER",
                        "current_status": work_order.status.value,
                        "reason": "work_order_already_completed",
                    }
                ],
            )

        step_updates: dict[str, bool] = {}
        if payload.step_id is not None and payload.is_checked is not None:
            step_updates[payload.step_id] = payload.is_checked
        if payload.steps:
            for item in payload.steps:
                step_updates[item.step_id] = item.is_checked

        existing_ids = {str(step.get("step_id", "")) for step in work_order.checklist_json}
        unknown_ids = [sid for sid in step_updates if sid not in existing_ids]
        if unknown_ids:
            raise DomainValidationError(
                detail=f"Unknown checklist step_id(s): {', '.join(unknown_ids)}.",
                errors=[
                    {"step_id": sid, "reason": "unknown_checklist_step"} for sid in unknown_ids
                ],
            )

        now_iso = datetime.now(UTC).isoformat()
        updated_checklist: list[dict[str, object]] = []
        for step in work_order.checklist_json:
            sid = str(step.get("step_id", ""))
            label = str(step.get("label_pt_br", ""))
            if sid in step_updates:
                new_checked = step_updates[sid]
                updated_checklist.append(
                    {
                        "step_id": sid,
                        "label_pt_br": label,
                        "is_checked": new_checked,
                        "checked_at": now_iso if new_checked else None,
                    }
                )
            else:
                updated_checklist.append(dict(step))

        work_order.checklist_json = updated_checklist

        if payload.cloud_p2p_id is not None:
            work_order.cloud_p2p_id = payload.cloud_p2p_id.strip() or None
        if payload.notes is not None:
            work_order.notes = payload.notes

        checked_count = sum(1 for s in updated_checklist if bool(s.get("is_checked", False)))
        await self._repo.add_audit_log(
            AuditLog(
                organization_id=ctx.organization_id,
                entity_type="WORK_ORDER",
                entity_id=work_order.id,
                action="CHECKLIST_UPDATED",
                actor_user_id=ctx.user_id,
                actor_ip=normalize_client_ip(actor_ip),
                previous_state=None,
                new_state={
                    "checked_steps_count": checked_count,
                    "total_steps_count": len(updated_checklist),
                    "cloud_p2p_id": work_order.cloud_p2p_id,
                },
            )
        )
        await self._session.commit()

        reloaded = await self._repo.get_work_order_by_id(ctx.organization_id, work_order.id)
        if reloaded is None:  # pragma: no cover
            raise ResourceNotFoundError(detail="Work order not found after checklist update.")
        return await self._serialize_work_order(reloaded)

    async def upload_installation_photo(
        self,
        ctx: CurrentTenantContext,
        work_order_id: UUID,
        *,
        filename: str,
        content: bytes,
        content_type: str = "image/jpeg",
        explicit_key: str | None = None,
        actor_ip: str | None = None,
    ) -> WorkOrderResponse:
        """Upload an installation photo to MinIO and append its key to installation_photos_keys."""
        work_order = await self._repo.get_work_order_by_id(
            ctx.organization_id,
            work_order_id,
            for_update=True,
        )
        if work_order is None:
            raise ResourceNotFoundError(
                detail=f"Work order '{work_order_id}' was not found in this organization.",
                errors=[{"work_order_id": str(work_order_id)}],
            )

        if work_order.status == WorkOrderStatus.COMPLETED:
            raise InvalidStateTransitionError(
                detail="Cannot upload photos to a COMPLETED WorkOrder.",
                errors=[
                    {
                        "entity_type": "WORK_ORDER",
                        "current_status": work_order.status.value,
                        "reason": "work_order_already_completed",
                    }
                ],
            )

        if not content:
            raise DomainValidationError(
                detail="Uploaded installation photo file cannot be empty.",
                errors=[{"field": "file", "reason": "empty_photo_payload"}],
            )

        if len(content) > MAX_PHOTO_SIZE_BYTES:
            raise DomainValidationError(
                detail=(
                    f"Photo file size ({len(content)} bytes) exceeds the maximum allowed "
                    f"limit of {MAX_PHOTO_SIZE_BYTES} bytes (10MB)."
                ),
                errors=[{"field": "file", "reason": "photo_size_limit_exceeded"}],
            )

        normalized_mime = content_type.lower().split(";")[0].strip()
        if normalized_mime not in ALLOWED_PHOTO_MIME_TYPES:
            allowed = ", ".join(sorted(ALLOWED_PHOTO_MIME_TYPES))
            raise DomainValidationError(
                detail=(
                    f"Unsupported photo content type '{content_type}'. Allowed types: {allowed}."
                ),
                errors=[{"field": "content_type", "reason": "unsupported_media_type"}],
            )

        expected_prefix = f"photos/{ctx.organization_id}/{work_order.id}/"
        if explicit_key is not None and explicit_key.strip():
            stripped_key = explicit_key.strip()
            if ".." in stripped_key or not stripped_key.startswith(expected_prefix):
                raise DomainValidationError(
                    detail=(
                        f"Invalid photo_key '{explicit_key}'. Key must not contain '..' "
                        f"and must begin with '{expected_prefix}'."
                    ),
                    errors=[{"field": "photo_key", "reason": "invalid_tenant_photo_prefix"}],
                )
            object_key = stripped_key
        else:
            safe_name = _sanitize_filename(filename)
            generated_prefix = generate_uuid7().hex[:12]
            object_key = f"{expected_prefix}{generated_prefix}-{safe_name}"

        await self._storage.upload_bytes(
            object_key=object_key,
            data=content,
            content_type=normalized_mime,
        )

        updated_keys = list(work_order.installation_photos_keys)
        if object_key not in updated_keys:
            updated_keys.append(object_key)
        work_order.installation_photos_keys = updated_keys

        await self._repo.add_audit_log(
            AuditLog(
                organization_id=ctx.organization_id,
                entity_type="WORK_ORDER",
                entity_id=work_order.id,
                action="PHOTO_UPLOADED",
                actor_user_id=ctx.user_id,
                actor_ip=normalize_client_ip(actor_ip),
                previous_state=None,
                new_state={
                    "photo_key": object_key,
                    "photos_count": len(updated_keys),
                },
            )
        )
        await self._session.commit()

        reloaded = await self._repo.get_work_order_by_id(ctx.organization_id, work_order.id)
        if reloaded is None:  # pragma: no cover
            raise ResourceNotFoundError(detail="Work order not found after photo upload.")
        logger.info(
            "work_order_photo_uploaded",
            work_order_id=str(reloaded.id),
            photo_key=object_key,
            photos_count=len(updated_keys),
        )
        return await self._serialize_work_order(reloaded)

    async def register_serial_number(
        self,
        ctx: CurrentTenantContext,
        work_order_id: UUID,
        payload: InstalledSerialCreateRequest,
        *,
        actor_ip: str | None = None,
    ) -> InstalledSerialResponse:
        """Register a hardware Serial Number in the Serial Vault with automatic warranty dates."""
        work_order = await self._repo.get_work_order_by_id(
            ctx.organization_id,
            work_order_id,
            for_update=True,
        )
        if work_order is None:
            raise ResourceNotFoundError(
                detail=f"Work order '{work_order_id}' was not found in this organization.",
                errors=[{"work_order_id": str(work_order_id)}],
            )

        if work_order.status == WorkOrderStatus.COMPLETED:
            raise InvalidStateTransitionError(
                detail="Cannot register hardware serial numbers on a COMPLETED WorkOrder.",
                errors=[
                    {
                        "entity_type": "WORK_ORDER",
                        "current_status": work_order.status.value,
                        "reason": "work_order_already_completed",
                    }
                ],
            )

        catalog_item = await self._repo.get_catalog_item_by_id(
            ctx.organization_id,
            payload.catalog_item_id,
        )
        if catalog_item is None:
            raise ResourceNotFoundError(
                detail=(
                    f"Catalog item '{payload.catalog_item_id}' was not found in this organization."
                ),
                errors=[{"catalog_item_id": str(payload.catalog_item_id)}],
            )

        normalized_sn = payload.serial_number.strip().upper()
        existing_sn = await self._repo.get_installed_serial_by_sn(
            ctx.organization_id,
            normalized_sn,
        )
        if existing_sn is not None:
            raise DomainValidationError(
                detail=(
                    f"Hardware serial number '{normalized_sn}' is already registered "
                    f"in this organization."
                ),
                errors=[
                    {
                        "serial_number": normalized_sn,
                        "existing_work_order_id": str(existing_sn.work_order_id),
                        "reason": "duplicate_serial_number",
                    }
                ],
            )

        today = date.today()
        raw_months = catalog_item.specs.get("distributor_warranty_months", 12)
        dist_months = int(raw_months) if isinstance(raw_months, (int, float)) else 12
        dist_days = round(dist_months * 365 / 12)

        distributor_warranty_until = payload.distributor_warranty_until or (
            today + timedelta(days=dist_days)
        )
        client_warranty_until = payload.client_warranty_until or (today + timedelta(days=365))

        serial = InstalledSerial(
            organization_id=ctx.organization_id,
            work_order_id=work_order.id,
            catalog_item_id=catalog_item.id,
            serial_number=normalized_sn,
            channel_or_slot_label=payload.channel_or_slot_label.strip(),
            distributor_warranty_until=distributor_warranty_until,
            client_warranty_until=client_warranty_until,
        )
        serial.catalog_item = catalog_item
        await self._repo.add_installed_serial(serial)

        await self._repo.add_audit_log(
            AuditLog(
                organization_id=ctx.organization_id,
                entity_type="WORK_ORDER",
                entity_id=work_order.id,
                action="SERIAL_REGISTERED",
                actor_user_id=ctx.user_id,
                actor_ip=normalize_client_ip(actor_ip),
                previous_state=None,
                new_state={
                    "installed_serial_id": str(serial.id),
                    "catalog_item_id": str(catalog_item.id),
                    "sku": catalog_item.sku,
                    "serial_number": normalized_sn,
                    "channel_or_slot_label": serial.channel_or_slot_label,
                    "distributor_warranty_until": distributor_warranty_until.isoformat(),
                    "client_warranty_until": client_warranty_until.isoformat(),
                },
            )
        )
        await self._session.commit()
        await self._session.refresh(serial)

        logger.info(
            "hardware_serial_registered",
            work_order_id=str(work_order.id),
            serial_id=str(serial.id),
            sku=catalog_item.sku,
            serial_number=normalized_sn,
        )
        return serialize_installed_serial(serial)

    async def complete_work_order(
        self,
        ctx: CurrentTenantContext,
        work_order_id: UUID,
        payload: WorkOrderCompleteRequest | None = None,
        *,
        actor_ip: str | None = None,
    ) -> WorkOrderResponse:
        """Enforce completion guards, deduct physical stock, set 12m warranty, and emit Outbox."""
        work_order = await self._repo.get_work_order_by_id(
            ctx.organization_id,
            work_order_id,
            for_update=True,
        )
        if work_order is None:
            raise ResourceNotFoundError(
                detail=f"Work order '{work_order_id}' was not found in this organization.",
                errors=[{"work_order_id": str(work_order_id)}],
            )

        quote = await self._repo.get_quote_for_update(ctx.organization_id, work_order.quote_id)
        if quote is None:  # pragma: no cover
            raise ResourceNotFoundError(detail="Parent quote not found for work order.")

        if payload is not None:
            if payload.cloud_p2p_id is not None:
                work_order.cloud_p2p_id = payload.cloud_p2p_id.strip() or None
            if payload.notes is not None:
                work_order.notes = payload.notes

        required_specs = build_required_serial_specs(quote)
        registered_counts: dict[UUID, int] = defaultdict(int)
        for serial in work_order.installed_serials:
            registered_counts[serial.catalog_item_id] += 1

        now = datetime.now(UTC)
        warranty_expires_at = now.date() + timedelta(days=365)

        wo_diff = WorkOrderStateMachine.transition_to_completed(
            work_order.status,
            checklist_json=work_order.checklist_json,
            installation_photos_keys=work_order.installation_photos_keys,
            required_serial_specs=required_specs,
            registered_serial_counts=registered_counts,
            completed_at=now,
            warranty_expires_at=warranty_expires_at,
        )

        # Deduct physical stock_quantity and reserved_quantity in ascending UUID order
        physical_qty_by_catalog_id: dict[UUID, int] = defaultdict(int)
        for line in quote.items:
            if line.catalog_item.category != CatalogCategory.SERVICE_LABOR:
                physical_qty_by_catalog_id[line.catalog_item_id] += line.quantity

        if physical_qty_by_catalog_id:
            locked_catalog_items = await self._repo.lock_catalog_items_for_update(
                ctx.organization_id,
                list(physical_qty_by_catalog_id.keys()),
            )
            for cat_item in locked_catalog_items:
                qty = physical_qty_by_catalog_id[cat_item.id]
                if cat_item.stock_quantity < qty:
                    raise InsufficientStockError(
                        detail=(
                            f"Cannot deduct {qty} unit(s) of '{cat_item.name_pt_br}' "
                            f"(SKU: {cat_item.sku}) because physical stock is "
                            f"{cat_item.stock_quantity}."
                        ),
                        errors=[
                            {
                                "catalog_item_id": str(cat_item.id),
                                "sku": cat_item.sku,
                                "stock_quantity": cat_item.stock_quantity,
                                "requested_quantity": qty,
                            }
                        ],
                    )
                cat_item.stock_quantity -= qty
                cat_item.reserved_quantity = max(0, cat_item.reserved_quantity - qty)

        work_order.status = WorkOrderStatus.COMPLETED
        work_order.completed_at = now
        work_order.warranty_expires_at = warranty_expires_at

        for serial in work_order.installed_serials:
            serial.client_warranty_until = warranty_expires_at

        sanitized_ip = normalize_client_ip(actor_ip)

        if quote.status == QuoteStatus.APPROVED:
            quote.status = QuoteStatus.IN_PROGRESS
            quote.version += 1

        quote_diff = QuoteStateMachine.transition_to_completed(
            quote.status,
            current_version=quote.version,
        )
        quote.status = QuoteStatus.COMPLETED
        quote.version += 1

        await self._repo.add_audit_log(
            AuditLog(
                organization_id=ctx.organization_id,
                entity_type="WORK_ORDER",
                entity_id=work_order.id,
                action="STATE_TRANSITION",
                actor_user_id=ctx.user_id,
                actor_ip=sanitized_ip,
                previous_state=wo_diff.previous_state,
                new_state=wo_diff.new_state,
            )
        )
        await self._repo.add_audit_log(
            AuditLog(
                organization_id=ctx.organization_id,
                entity_type="QUOTE",
                entity_id=quote.id,
                action="STATE_TRANSITION",
                actor_user_id=ctx.user_id,
                actor_ip=sanitized_ip,
                previous_state=quote_diff.previous_state,
                new_state=quote_diff.new_state,
            )
        )

        outbox_event = OutboxEvent(
            organization_id=ctx.organization_id,
            event_type="WorkOrderCompletedEvent",
            status=OutboxStatus.PENDING,
            payload={
                "quote_id": str(quote.id),
                "work_order_id": str(work_order.id),
                "organization_id": str(ctx.organization_id),
                "warranty_expires_at": warranty_expires_at.isoformat(),
                "correlation_id": get_correlation_id(),
            },
        )
        await self._repo.add_outbox_event(outbox_event)
        await self._session.commit()
        await trigger_outbox_poll_safely()

        reloaded = await self._repo.get_work_order_by_id(ctx.organization_id, work_order.id)
        if reloaded is None:  # pragma: no cover
            raise ResourceNotFoundError(detail="Work order not found after completion.")
        logger.info(
            "work_order_completed",
            work_order_id=str(reloaded.id),
            quote_id=str(reloaded.quote_id),
            organization_id=str(ctx.organization_id),
            warranty_expires_at=warranty_expires_at.isoformat(),
            outbox_event_id=str(outbox_event.id),
        )
        return await self._serialize_work_order(reloaded)

    async def list_expiring_warranties(
        self,
        ctx: CurrentTenantContext,
    ) -> list[ExpiringWarrantyItemResponse]:
        """List completed installations approaching the 11-month preventive maintenance mark."""
        today = date.today()
        horizon = today + timedelta(days=30)
        work_orders = await self._repo.list_expiring_warranty_work_orders(
            ctx.organization_id,
            horizon_date=horizon,
        )

        results: list[ExpiringWarrantyItemResponse] = []
        for wo in work_orders:
            if wo.warranty_expires_at is None:  # pragma: no cover
                continue
            customer = wo.quote.customer
            serial_dtos = [serialize_installed_serial(s) for s in wo.installed_serials]
            days_left = (wo.warranty_expires_at - today).days
            results.append(
                ExpiringWarrantyItemResponse(
                    work_order_id=wo.id,
                    quote_id=wo.quote_id,
                    organization_id=wo.organization_id,
                    customer_id=customer.id,
                    customer_name=customer.name,
                    customer_phone_whatsapp=customer.phone_whatsapp,
                    customer_email=customer.email,
                    completed_at=wo.completed_at,
                    warranty_expires_at=wo.warranty_expires_at,
                    days_until_expiration=days_left,
                    preventive_maintenance_alert_sent=wo.preventive_maintenance_alert_sent,
                    cloud_p2p_id=wo.cloud_p2p_id,
                    installed_serials_count=len(serial_dtos),
                    installed_serials=serial_dtos,
                )
            )
        return results

    async def verify_document_by_sha256(
        self,
        pdf_sha256_hash: str,
    ) -> DocumentVerificationResponse:
        """Public cryptographic authenticity verification for a generated PDF SHA-256 hash."""
        normalized_hash = pdf_sha256_hash.strip().lower()
        found = await self._repo.get_quote_and_org_by_pdf_sha256(normalized_hash)
        if found is None:
            raise ResourceNotFoundError(
                detail=(
                    f"No authentic proposal or warranty certificate matches SHA-256 digest "
                    f"'{normalized_hash}'."
                ),
                errors=[
                    {
                        "pdf_sha256_hash": normalized_hash,
                        "reason": "sha256_digest_not_found",
                    }
                ],
            )

        quote, org = found
        wo = quote.work_order
        today = date.today()

        serial_dtos: list[InstalledSerialResponse] = []
        wo_id: UUID | None = None
        wo_status: WorkOrderStatus | None = None
        completed_at: datetime | None = None
        cloud_p2p_id: str | None = None
        warranty_expires_at: date | None = None
        is_warranty_active = False

        if wo is not None:
            wo_id = wo.id
            wo_status = wo.status
            completed_at = wo.completed_at
            cloud_p2p_id = wo.cloud_p2p_id
            warranty_expires_at = wo.warranty_expires_at
            if warranty_expires_at is not None and warranty_expires_at >= today:
                is_warranty_active = True
            serial_dtos = [serialize_installed_serial(s) for s in wo.installed_serials]

        return DocumentVerificationResponse(
            verified=True,
            pdf_sha256_hash=quote.pdf_sha256_hash or normalized_hash,
            organization_name=org.name,
            organization_cnpj=org.document_cnpj,
            quote_id=quote.id,
            quote_status=quote.status,
            quote_version=quote.version,
            customer_name=quote.customer.name,
            customer_document_masked=_mask_document(quote.customer.document_cpf_cnpj),
            total_sale_cents=quote.total_sale_cents,
            approved_at=quote.approved_at,
            approved_by_ip=str(quote.approved_by_ip) if quote.approved_by_ip else None,
            work_order_id=wo_id,
            work_order_status=wo_status,
            completed_at=completed_at,
            cloud_p2p_id=cloud_p2p_id,
            warranty_expires_at=warranty_expires_at,
            is_warranty_active=is_warranty_active,
            installed_serials=serial_dtos,
        )
