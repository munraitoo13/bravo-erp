"""Application service for Customers and Quotes with pessimistic locking and Outbox events."""

import ipaddress
from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import CurrentTenantContext
from src.core.exceptions import (
    DomainValidationError,
    ErrorDetailItem,
    InsufficientStockError,
    InvalidStateTransitionError,
    ResourceNotFoundError,
)
from src.core.logging import get_correlation_id
from src.core.security import UserRole
from src.core.storage import StorageClient
from src.modules.catalog.models import CatalogCategory
from src.modules.quotes.models import (
    AuditLog,
    Customer,
    OutboxEvent,
    OutboxStatus,
    Quote,
    QuoteItem,
    QuoteStatus,
)
from src.modules.quotes.repository import QuoteRepository
from src.modules.quotes.schemas import (
    AuditLogResponse,
    CustomerCreateRequest,
    CustomerResponse,
    QuoteCreateRequest,
    QuoteItemOwnerResponse,
    QuoteItemPublicResponse,
    QuoteItemTechnicianResponse,
    QuoteOwnerResponse,
    QuotePublicResponse,
    QuoteTechnicianResponse,
)
from src.modules.quotes.state_machine import QuoteStateMachine
from src.modules.work_orders.models import WorkOrder, WorkOrderStatus

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

type QuoteRoleResponse = QuoteOwnerResponse | QuoteTechnicianResponse

DEFAULT_WORK_ORDER_CHECKLIST_STEPS: tuple[tuple[str, str], ...] = (
    ("step_1", "Fixação e alinhamento das câmeras"),
    ("step_2", "Crimpagem e teste de cabos/baluns"),
    ("step_3", "Instalação do HD WD Purple e formatação no DVR"),
    ("step_4", "Configuração Intelbras Cloud P2P e aplicativo cliente"),
    ("step_5", "Limpeza do local e termo de aceite"),
)


def build_default_work_order_checklist() -> list[dict[str, object]]:
    """Build the default 5-step PT-BR field installation checklist for a new WorkOrder."""
    return [
        {
            "step_id": step_id,
            "label_pt_br": label_pt_br,
            "is_checked": False,
            "checked_at": None,
        }
        for step_id, label_pt_br in DEFAULT_WORK_ORDER_CHECKLIST_STEPS
    ]


def normalize_client_ip(raw_ip: str | None) -> str:
    """Validate an IP address string for PostgreSQL INET storage, falling back to 127.0.0.1."""
    if not raw_ip:
        return "127.0.0.1"
    candidate = raw_ip.split(",")[0].strip()
    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError:
        return "127.0.0.1"


def compute_margin_percent(total_cost_cents: int, total_sale_cents: int) -> Decimal:
    """Compute exact Decimal profit margin percentage: ((sale - cost) / sale) * 100."""
    if total_sale_cents <= 0:
        return Decimal("0.00")
    margin = (Decimal(total_sale_cents - total_cost_cents) / Decimal(total_sale_cents)) * Decimal(
        "100.00"
    )
    return margin.quantize(Decimal("0.01"))


async def trigger_outbox_poll_safely() -> None:
    """Trigger immediate non-blocking outbox processing via Taskiq with graceful fallback."""
    try:
        from src.modules.tasks.outbox_relay import poll_outbox_events_task

        await poll_outbox_events_task.kiq()
    except Exception as exc:
        logger.warning("failed_to_dispatch_outbox_kiq_trigger", error=str(exc))


def serialize_quote_for_public(
    quote: Quote,
    *,
    pdf_download_url: str | None = None,
    work_order_id: UUID | None = None,
) -> QuotePublicResponse:
    """Serialize a Quote ORM model into QuotePublicResponse (strictly omitting cost & margin)."""
    customer_dto = CustomerResponse.model_validate(quote.customer)
    items_dto = [
        QuoteItemPublicResponse(
            id=line.id,
            catalog_item_id=line.catalog_item_id,
            sku=line.catalog_item.sku,
            name_pt_br=line.catalog_item.name_pt_br,
            category=line.catalog_item.category,
            quantity=line.quantity,
            unit_sale_cents=line.unit_sale_cents,
            is_auto_derived=line.is_auto_derived,
        )
        for line in quote.items
    ]
    return QuotePublicResponse(
        id=quote.id,
        organization_id=quote.organization_id,
        customer_id=quote.customer_id,
        customer=customer_dto,
        public_token=quote.public_token,
        status=quote.status,
        sizing_input_json=quote.sizing_input_json,
        total_sale_cents=quote.total_sale_cents,
        valid_until=quote.valid_until,
        approved_at=quote.approved_at,
        pdf_download_url=pdf_download_url,
        pdf_sha256_hash=quote.pdf_sha256_hash,
        work_order_id=work_order_id,
        version=quote.version,
        items=items_dto,
        created_at=quote.created_at,
        updated_at=quote.updated_at,
    )


def serialize_quote_for_owner(
    quote: Quote,
    *,
    pdf_download_url: str | None = None,
    work_order_id: UUID | None = None,
    audit_logs: Sequence[AuditLog] = (),
) -> QuoteOwnerResponse:
    """Serialize a Quote ORM model into QuoteOwnerResponse (including cost & margin)."""
    customer_dto = CustomerResponse.model_validate(quote.customer)
    audit_dtos = [AuditLogResponse.model_validate(log) for log in audit_logs]
    owner_items = [
        QuoteItemOwnerResponse(
            id=line.id,
            catalog_item_id=line.catalog_item_id,
            sku=line.catalog_item.sku,
            name_pt_br=line.catalog_item.name_pt_br,
            category=line.catalog_item.category,
            quantity=line.quantity,
            unit_cost_cents=line.unit_cost_cents,
            unit_sale_cents=line.unit_sale_cents,
            is_auto_derived=line.is_auto_derived,
        )
        for line in quote.items
    ]
    return QuoteOwnerResponse(
        id=quote.id,
        organization_id=quote.organization_id,
        customer_id=quote.customer_id,
        customer=customer_dto,
        public_token=quote.public_token,
        status=quote.status,
        sizing_input_json=quote.sizing_input_json,
        total_cost_cents=quote.total_cost_cents,
        total_sale_cents=quote.total_sale_cents,
        margin_percent=quote.margin_percent,
        valid_until=quote.valid_until,
        approved_at=quote.approved_at,
        approved_by_ip=str(quote.approved_by_ip) if quote.approved_by_ip else None,
        pdf_download_url=pdf_download_url,
        pdf_sha256_hash=quote.pdf_sha256_hash,
        work_order_id=work_order_id,
        version=quote.version,
        items=owner_items,
        audit_logs=audit_dtos,
        created_at=quote.created_at,
        updated_at=quote.updated_at,
    )


def serialize_quote_for_role(
    quote: Quote,
    role: UserRole,
    *,
    pdf_download_url: str | None = None,
    work_order_id: UUID | None = None,
    audit_logs: Sequence[AuditLog] = (),
) -> QuoteRoleResponse:
    """Serialize a Quote ORM model into a role-segregated DTO (Owner vs Technician)."""
    if role == UserRole.OWNER:
        return serialize_quote_for_owner(
            quote,
            pdf_download_url=pdf_download_url,
            work_order_id=work_order_id,
            audit_logs=audit_logs,
        )

    customer_dto = CustomerResponse.model_validate(quote.customer)
    audit_dtos = [AuditLogResponse.model_validate(log) for log in audit_logs]
    tech_items = [
        QuoteItemTechnicianResponse(
            id=line.id,
            catalog_item_id=line.catalog_item_id,
            sku=line.catalog_item.sku,
            name_pt_br=line.catalog_item.name_pt_br,
            category=line.catalog_item.category,
            quantity=line.quantity,
            unit_sale_cents=line.unit_sale_cents,
            is_auto_derived=line.is_auto_derived,
        )
        for line in quote.items
    ]
    return QuoteTechnicianResponse(
        id=quote.id,
        organization_id=quote.organization_id,
        customer_id=quote.customer_id,
        customer=customer_dto,
        public_token=quote.public_token,
        status=quote.status,
        sizing_input_json=quote.sizing_input_json,
        total_sale_cents=quote.total_sale_cents,
        valid_until=quote.valid_until,
        approved_at=quote.approved_at,
        pdf_download_url=pdf_download_url,
        pdf_sha256_hash=quote.pdf_sha256_hash,
        work_order_id=work_order_id,
        version=quote.version,
        items=tech_items,
        audit_logs=audit_dtos,
        created_at=quote.created_at,
        updated_at=quote.updated_at,
    )


class QuoteService:
    """Orchestrates Customer and Quote lifecycle operations, stock reservation, and Outbox."""

    def __init__(
        self,
        session: AsyncSession,
        storage_client: StorageClient | None = None,
    ) -> None:
        self._session = session
        self._repo = QuoteRepository(session)
        self._storage = storage_client or StorageClient()

    async def _resolve_pdf_url(self, quote: Quote) -> str | None:
        """Return a presigned S3/MinIO download URL if pdf_storage_key is populated."""
        if not quote.pdf_storage_key:
            return None
        return await self._storage.generate_presigned_download_url(object_key=quote.pdf_storage_key)

    async def list_customers(self, ctx: CurrentTenantContext) -> list[CustomerResponse]:
        """List all customers in the current tenant organization."""
        customers = await self._repo.list_customers(ctx.organization_id)
        return [CustomerResponse.model_validate(c) for c in customers]

    async def create_customer(
        self,
        ctx: CurrentTenantContext,
        payload: CustomerCreateRequest,
    ) -> CustomerResponse:
        """Create a new customer for the current tenant organization."""
        customer = Customer(
            organization_id=ctx.organization_id,
            name=payload.name,
            document_cpf_cnpj=payload.document_cpf_cnpj,
            phone_whatsapp=payload.phone_whatsapp,
            email=str(payload.email),
            address_json=payload.address_json,
        )
        await self._repo.add_customer(customer)
        await self._session.commit()
        await self._session.refresh(customer)
        logger.info(
            "customer_created",
            customer_id=str(customer.id),
            organization_id=str(ctx.organization_id),
        )
        return CustomerResponse.model_validate(customer)

    async def list_quotes(
        self,
        ctx: CurrentTenantContext,
        *,
        status: QuoteStatus | None = None,
    ) -> list[QuoteRoleResponse]:
        """List all quotes for the current tenant, serialized according to the actor's role."""
        quotes = await self._repo.list_quotes(ctx.organization_id, status=status)
        responses: list[QuoteRoleResponse] = []
        for quote in quotes:
            pdf_url = await self._resolve_pdf_url(quote)
            wo_id = quote.work_order.id if quote.work_order is not None else None
            responses.append(
                serialize_quote_for_role(
                    quote,
                    ctx.role,
                    pdf_download_url=pdf_url,
                    work_order_id=wo_id,
                )
            )
        return responses

    async def get_quote(
        self,
        ctx: CurrentTenantContext,
        quote_id: UUID,
    ) -> QuoteRoleResponse:
        """Retrieve a single quote and its audit trail scoped to the current tenant."""
        quote = await self._repo.get_quote_by_id(ctx.organization_id, quote_id)
        if quote is None:
            raise ResourceNotFoundError(
                detail=f"Quote '{quote_id}' was not found in this organization.",
                errors=[{"quote_id": str(quote_id)}],
            )
        audit_logs = await self._repo.list_audit_logs_for_entity(
            ctx.organization_id,
            "QUOTE",
            quote.id,
        )
        pdf_url = await self._resolve_pdf_url(quote)
        wo_id = quote.work_order.id if quote.work_order is not None else None
        return serialize_quote_for_role(
            quote,
            ctx.role,
            pdf_download_url=pdf_url,
            work_order_id=wo_id,
            audit_logs=audit_logs,
        )

    async def get_public_quote(self, public_token: UUID) -> QuotePublicResponse:
        """Retrieve a proposal by its public_token for PUBLIC_CLIENT viewing."""
        quote = await self._repo.get_quote_by_public_token(public_token)
        if quote is None:
            raise ResourceNotFoundError(
                detail=f"Public proposal with token '{public_token}' was not found.",
                errors=[{"public_token": str(public_token)}],
            )
        pdf_url = await self._resolve_pdf_url(quote)
        wo_id = quote.work_order.id if quote.work_order is not None else None
        return serialize_quote_for_public(
            quote,
            pdf_download_url=pdf_url,
            work_order_id=wo_id,
        )

    async def create_quote(
        self,
        ctx: CurrentTenantContext,
        payload: QuoteCreateRequest,
        *,
        actor_ip: str | None = None,
    ) -> QuoteOwnerResponse:
        """Create a new Quote in DRAFT state from manual line items or a sizing snapshot."""
        customer = await self._repo.get_customer_by_id(ctx.organization_id, payload.customer_id)
        if customer is None:
            raise ResourceNotFoundError(
                detail=f"Customer '{payload.customer_id}' was not found in this organization.",
                errors=[{"customer_id": str(payload.customer_id)}],
            )

        requested_item_ids = [line.catalog_item_id for line in payload.items]
        catalog_map = await self._repo.get_catalog_items_by_ids(
            ctx.organization_id,
            requested_item_ids,
        )

        missing_ids = [str(cid) for cid in requested_item_ids if cid not in catalog_map]
        if missing_ids:
            raise ResourceNotFoundError(
                detail=f"One or more catalog items were not found: {', '.join(missing_ids)}.",
                errors=[{"catalog_item_id": cid} for cid in missing_ids],
            )

        inactive_skus = [
            catalog_map[cid].sku for cid in requested_item_ids if not catalog_map[cid].is_active
        ]
        if inactive_skus:
            raise DomainValidationError(
                detail=(
                    f"Cannot add inactive catalog items to a quote: "
                    f"{', '.join(sorted(set(inactive_skus)))}."
                ),
                errors=[{"sku": sku, "reason": "inactive_catalog_item"} for sku in inactive_skus],
            )

        now = datetime.now(UTC)
        valid_until = payload.valid_until or (now + timedelta(days=payload.valid_days))

        quote = Quote(
            organization_id=ctx.organization_id,
            customer_id=customer.id,
            status=QuoteStatus.DRAFT,
            sizing_input_json=payload.sizing_input_json,
            total_cost_cents=0,
            total_sale_cents=0,
            margin_percent=Decimal("0.00"),
            valid_until=valid_until,
            version=1,
        )
        await self._repo.add_quote(quote)

        total_cost_cents = 0
        total_sale_cents = 0
        for line_input in payload.items:
            cat_item = catalog_map[line_input.catalog_item_id]
            unit_cost = cat_item.cost_price_cents
            unit_sale = (
                line_input.unit_sale_cents
                if line_input.unit_sale_cents is not None
                else cat_item.sale_price_cents
            )
            total_cost_cents += unit_cost * line_input.quantity
            total_sale_cents += unit_sale * line_input.quantity

            quote_item = QuoteItem(
                quote_id=quote.id,
                organization_id=ctx.organization_id,
                catalog_item_id=cat_item.id,
                quantity=line_input.quantity,
                unit_cost_cents=unit_cost,
                unit_sale_cents=unit_sale,
                is_auto_derived=line_input.is_auto_derived,
            )
            self._session.add(quote_item)

        quote.total_cost_cents = total_cost_cents
        quote.total_sale_cents = total_sale_cents
        quote.margin_percent = compute_margin_percent(total_cost_cents, total_sale_cents)
        await self._session.flush()

        audit_log = AuditLog(
            organization_id=ctx.organization_id,
            entity_type="QUOTE",
            entity_id=quote.id,
            action="QUOTE_CREATED",
            actor_user_id=ctx.user_id,
            actor_ip=normalize_client_ip(actor_ip),
            previous_state=None,
            new_state={
                "status": QuoteStatus.DRAFT.value,
                "version": 1,
                "total_sale_cents": total_sale_cents,
                "item_count": len(payload.items),
            },
        )
        await self._repo.add_audit_log(audit_log)
        await self._session.commit()

        reloaded = await self._repo.get_quote_by_id(ctx.organization_id, quote.id)
        if reloaded is None:  # pragma: no cover
            raise ResourceNotFoundError(detail="Created quote could not be reloaded.")
        logs = await self._repo.list_audit_logs_for_entity(
            ctx.organization_id,
            "QUOTE",
            reloaded.id,
        )
        logger.info(
            "quote_created",
            quote_id=str(reloaded.id),
            organization_id=str(ctx.organization_id),
            total_sale_cents=reloaded.total_sale_cents,
        )
        return serialize_quote_for_owner(
            reloaded,
            audit_logs=logs,
        )

    async def send_quote(
        self,
        ctx: CurrentTenantContext,
        quote_id: UUID,
        *,
        actor_ip: str | None = None,
    ) -> QuoteOwnerResponse:
        """Transition a Quote from DRAFT -> SENT and enqueue QuoteSentEvent in outbox_events."""
        quote = await self._repo.get_quote_by_id(
            ctx.organization_id,
            quote_id,
            for_update=True,
        )
        if quote is None:
            raise ResourceNotFoundError(
                detail=f"Quote '{quote_id}' was not found in this organization.",
                errors=[{"quote_id": str(quote_id)}],
            )

        diff = QuoteStateMachine.transition_to_sent(
            quote.status,
            item_count=len(quote.items),
            current_version=quote.version,
        )
        quote.status = QuoteStatus.SENT

        audit_log = AuditLog(
            organization_id=ctx.organization_id,
            entity_type="QUOTE",
            entity_id=quote.id,
            action="STATE_TRANSITION",
            actor_user_id=ctx.user_id,
            actor_ip=normalize_client_ip(actor_ip),
            previous_state=diff.previous_state,
            new_state=diff.new_state,
        )
        await self._repo.add_audit_log(audit_log)

        outbox_event = OutboxEvent(
            organization_id=ctx.organization_id,
            event_type="QuoteSentEvent",
            status=OutboxStatus.PENDING,
            payload={
                "quote_id": str(quote.id),
                "organization_id": str(ctx.organization_id),
                "public_token": str(quote.public_token),
                "correlation_id": get_correlation_id(),
            },
        )
        await self._repo.add_outbox_event(outbox_event)
        await self._session.commit()
        await trigger_outbox_poll_safely()

        reloaded = await self._repo.get_quote_by_id(ctx.organization_id, quote.id)
        if reloaded is None:  # pragma: no cover
            raise ResourceNotFoundError(detail="Quote not found after send commit.")
        logs = await self._repo.list_audit_logs_for_entity(
            ctx.organization_id,
            "QUOTE",
            reloaded.id,
        )
        pdf_url = await self._resolve_pdf_url(reloaded)
        logger.info(
            "quote_sent",
            quote_id=str(reloaded.id),
            organization_id=str(ctx.organization_id),
            outbox_event_id=str(outbox_event.id),
        )
        return serialize_quote_for_owner(
            reloaded,
            pdf_download_url=pdf_url,
            audit_logs=logs,
        )

    async def _execute_atomic_approval(
        self,
        quote: Quote,
        *,
        actor_user_id: UUID | None,
        client_ip: str | None,
        client_notes: str | None = None,
    ) -> tuple[Quote, WorkOrder, OutboxEvent]:
        """Execute atomic SELECT ... FOR UPDATE stock reservation, WorkOrder, Audit, and Outbox."""
        sanitized_ip = normalize_client_ip(client_ip)
        now = datetime.now(UTC)

        diff = QuoteStateMachine.transition_to_approved(
            quote.status,
            valid_until=quote.valid_until,
            now=now,
            current_version=quote.version,
            approved_by_ip=sanitized_ip,
        )

        # Aggregate physical goods (excluding SERVICE_LABOR) and lock in ascending UUID order
        required_by_catalog_id: dict[UUID, int] = defaultdict(int)
        for line in quote.items:
            if line.catalog_item.category != CatalogCategory.SERVICE_LABOR:
                required_by_catalog_id[line.catalog_item_id] += line.quantity

        if required_by_catalog_id:
            locked_catalog_items = await self._repo.lock_catalog_items_for_update(
                quote.organization_id,
                list(required_by_catalog_id.keys()),
            )
            deficient_errors: list[ErrorDetailItem] = []
            first_deficient_detail: str | None = None

            for catalog_item in locked_catalog_items:
                requested_qty = required_by_catalog_id[catalog_item.id]
                available_qty = catalog_item.stock_quantity - catalog_item.reserved_quantity
                if available_qty < requested_qty:
                    if first_deficient_detail is None:
                        first_deficient_detail = (
                            f"Catalog item '{catalog_item.name_pt_br}' (SKU: {catalog_item.sku}) "
                            f"has {available_qty} available units (requested: {requested_qty})."
                        )
                    deficient_errors.append(
                        {
                            "catalog_item_id": str(catalog_item.id),
                            "sku": catalog_item.sku,
                            "available_quantity": available_qty,
                            "requested_quantity": requested_qty,
                        }
                    )

            if deficient_errors:
                raise InsufficientStockError(
                    detail=first_deficient_detail
                    or "Insufficient stock for one or more catalog items.",
                    errors=deficient_errors,
                )

            for catalog_item in locked_catalog_items:
                catalog_item.reserved_quantity += required_by_catalog_id[catalog_item.id]

        quote.status = QuoteStatus.APPROVED
        quote.approved_at = now
        quote.approved_by_ip = sanitized_ip
        quote.version += 1

        work_order = WorkOrder(
            organization_id=quote.organization_id,
            quote_id=quote.id,
            assigned_technician_id=None,
            status=WorkOrderStatus.PENDING,
            checklist_json=build_default_work_order_checklist(),
            installation_photos_keys=[],
            notes=client_notes,
        )
        await self._repo.add_work_order(work_order)

        new_state_payload = dict(diff.new_state)
        new_state_payload["work_order_id"] = str(work_order.id)
        if client_notes:
            new_state_payload["client_notes"] = client_notes

        audit_log = AuditLog(
            organization_id=quote.organization_id,
            entity_type="QUOTE",
            entity_id=quote.id,
            action="STATE_TRANSITION",
            actor_user_id=actor_user_id,
            actor_ip=sanitized_ip,
            previous_state=diff.previous_state,
            new_state=new_state_payload,
        )
        await self._repo.add_audit_log(audit_log)

        outbox_event = OutboxEvent(
            organization_id=quote.organization_id,
            event_type="QuoteApprovedEvent",
            status=OutboxStatus.PENDING,
            payload={
                "quote_id": str(quote.id),
                "work_order_id": str(work_order.id),
                "organization_id": str(quote.organization_id),
                "correlation_id": get_correlation_id(),
            },
        )
        await self._repo.add_outbox_event(outbox_event)
        await self._session.commit()
        await trigger_outbox_poll_safely()

        logger.info(
            "quote_approved",
            quote_id=str(quote.id),
            work_order_id=str(work_order.id),
            organization_id=str(quote.organization_id),
            outbox_event_id=str(outbox_event.id),
            approved_by_ip=sanitized_ip,
        )
        return quote, work_order, outbox_event

    async def approve_public_quote(
        self,
        public_token: UUID,
        *,
        client_ip: str | None = None,
        client_notes: str | None = None,
    ) -> QuotePublicResponse:
        """Approve a SENT quote via its public_token using pessimistic row-level locking."""
        quote = await self._repo.get_quote_by_public_token(public_token, for_update=True)
        if quote is None:
            raise ResourceNotFoundError(
                detail=f"Public proposal with token '{public_token}' was not found.",
                errors=[{"public_token": str(public_token)}],
            )

        _, work_order, _ = await self._execute_atomic_approval(
            quote,
            actor_user_id=None,
            client_ip=client_ip,
            client_notes=client_notes,
        )

        reloaded = await self._repo.get_quote_by_public_token(public_token)
        if reloaded is None:  # pragma: no cover
            raise ResourceNotFoundError(detail="Approved quote could not be reloaded.")
        pdf_url = await self._resolve_pdf_url(reloaded)
        return serialize_quote_for_public(
            reloaded,
            pdf_download_url=pdf_url,
            work_order_id=work_order.id,
        )

    async def approve_quote_by_owner(
        self,
        ctx: CurrentTenantContext,
        quote_id: UUID,
        *,
        actor_ip: str | None = None,
    ) -> QuoteOwnerResponse:
        """Allow an authenticated OWNER to approve a SENT quote with identical stock locking."""
        quote = await self._repo.get_quote_by_id(
            ctx.organization_id,
            quote_id,
            for_update=True,
        )
        if quote is None:
            raise ResourceNotFoundError(
                detail=f"Quote '{quote_id}' was not found in this organization.",
                errors=[{"quote_id": str(quote_id)}],
            )

        _, work_order, _ = await self._execute_atomic_approval(
            quote,
            actor_user_id=ctx.user_id,
            client_ip=actor_ip,
        )

        reloaded = await self._repo.get_quote_by_id(ctx.organization_id, quote_id)
        if reloaded is None:  # pragma: no cover
            raise ResourceNotFoundError(detail="Approved quote could not be reloaded.")
        logs = await self._repo.list_audit_logs_for_entity(
            ctx.organization_id,
            "QUOTE",
            reloaded.id,
        )
        pdf_url = await self._resolve_pdf_url(reloaded)
        return serialize_quote_for_owner(
            reloaded,
            pdf_download_url=pdf_url,
            work_order_id=work_order.id,
            audit_logs=logs,
        )

    async def cancel_quote(
        self,
        ctx: CurrentTenantContext,
        quote_id: UUID,
        *,
        actor_ip: str | None = None,
    ) -> QuoteOwnerResponse:
        """Cancel a DRAFT, SENT, or APPROVED quote (releasing reserved stock if APPROVED)."""
        quote = await self._repo.get_quote_by_id(
            ctx.organization_id,
            quote_id,
            for_update=True,
        )
        if quote is None:
            raise ResourceNotFoundError(
                detail=f"Quote '{quote_id}' was not found in this organization.",
                errors=[{"quote_id": str(quote_id)}],
            )

        diff = QuoteStateMachine.transition_to_canceled(
            quote.status,
            current_version=quote.version,
        )

        child_wo = await self._repo.get_work_order_by_quote_id(
            ctx.organization_id,
            quote.id,
        )
        if child_wo is not None:
            if child_wo.status in {WorkOrderStatus.IN_FIELD, WorkOrderStatus.COMPLETED}:
                raise InvalidStateTransitionError(
                    detail=(
                        f"Cannot cancel Quote '{quote.id}' because its child WorkOrder "
                        f"'{child_wo.id}' is already in status '{child_wo.status.value}'."
                    ),
                    errors=[
                        {
                            "quote_id": str(quote.id),
                            "work_order_id": str(child_wo.id),
                            "work_order_status": child_wo.status.value,
                            "reason": "child_work_order_active_or_completed",
                        }
                    ],
                )
            child_wo.status = WorkOrderStatus.CANCELED
            await self._repo.add_audit_log(
                AuditLog(
                    organization_id=ctx.organization_id,
                    entity_type="WORK_ORDER",
                    entity_id=child_wo.id,
                    action="STATE_TRANSITION",
                    actor_user_id=ctx.user_id,
                    actor_ip=normalize_client_ip(actor_ip),
                    previous_state={"status": child_wo.status.value},
                    new_state={
                        "status": WorkOrderStatus.CANCELED.value,
                        "reason": "parent_quote_canceled",
                    },
                )
            )

        if diff.requires_stock_release:
            release_by_catalog_id: dict[UUID, int] = defaultdict(int)
            for line in quote.items:
                if line.catalog_item.category != CatalogCategory.SERVICE_LABOR:
                    release_by_catalog_id[line.catalog_item_id] += line.quantity

            if release_by_catalog_id:
                locked_items = await self._repo.lock_catalog_items_for_update(
                    quote.organization_id,
                    list(release_by_catalog_id.keys()),
                )
                for cat_item in locked_items:
                    qty_to_release = release_by_catalog_id[cat_item.id]
                    cat_item.reserved_quantity = max(
                        0,
                        cat_item.reserved_quantity - qty_to_release,
                    )

        quote.status = QuoteStatus.CANCELED
        quote.version += 1

        audit_log = AuditLog(
            organization_id=ctx.organization_id,
            entity_type="QUOTE",
            entity_id=quote.id,
            action="STATE_TRANSITION",
            actor_user_id=ctx.user_id,
            actor_ip=normalize_client_ip(actor_ip),
            previous_state=diff.previous_state,
            new_state=diff.new_state,
        )
        await self._repo.add_audit_log(audit_log)
        await self._session.commit()

        reloaded = await self._repo.get_quote_by_id(ctx.organization_id, quote.id)
        if reloaded is None:  # pragma: no cover
            raise ResourceNotFoundError(detail="Canceled quote could not be reloaded.")
        logs = await self._repo.list_audit_logs_for_entity(
            ctx.organization_id,
            "QUOTE",
            reloaded.id,
        )
        pdf_url = await self._resolve_pdf_url(reloaded)
        wo_id = reloaded.work_order.id if reloaded.work_order is not None else None
        logger.info(
            "quote_canceled",
            quote_id=str(reloaded.id),
            organization_id=str(ctx.organization_id),
            released_reserved_stock=diff.requires_stock_release,
        )
        return serialize_quote_for_owner(
            reloaded,
            pdf_download_url=pdf_url,
            work_order_id=wo_id,
            audit_logs=logs,
        )

    async def revise_quote(
        self,
        ctx: CurrentTenantContext,
        quote_id: UUID,
        *,
        actor_ip: str | None = None,
    ) -> QuoteOwnerResponse:
        """Revise a SENT or EXPIRED quote back to DRAFT state for editing (OWNER only)."""
        quote = await self._repo.get_quote_by_id(
            ctx.organization_id,
            quote_id,
            for_update=True,
        )
        if quote is None:
            raise ResourceNotFoundError(
                detail=f"Quote '{quote_id}' was not found in this organization.",
                errors=[{"quote_id": str(quote_id)}],
            )

        diff = QuoteStateMachine.transition_to_draft(
            quote.status,
            current_version=quote.version,
        )
        quote.status = QuoteStatus.DRAFT
        quote.version += 1

        audit_log = AuditLog(
            organization_id=ctx.organization_id,
            entity_type="QUOTE",
            entity_id=quote.id,
            action="STATE_TRANSITION",
            actor_user_id=ctx.user_id,
            actor_ip=normalize_client_ip(actor_ip),
            previous_state=diff.previous_state,
            new_state=diff.new_state,
        )
        await self._repo.add_audit_log(audit_log)
        await self._session.commit()

        reloaded = await self._repo.get_quote_by_id(ctx.organization_id, quote.id)
        if reloaded is None:  # pragma: no cover
            raise ResourceNotFoundError(detail="Revised quote could not be reloaded.")
        logs = await self._repo.list_audit_logs_for_entity(
            ctx.organization_id,
            "QUOTE",
            reloaded.id,
        )
        pdf_url = await self._resolve_pdf_url(reloaded)
        wo_id = reloaded.work_order.id if reloaded.work_order is not None else None
        logger.info(
            "quote_revised_to_draft",
            quote_id=str(reloaded.id),
            organization_id=str(ctx.organization_id),
            new_version=reloaded.version,
        )
        return serialize_quote_for_owner(
            reloaded,
            pdf_download_url=pdf_url,
            work_order_id=wo_id,
            audit_logs=logs,
        )
