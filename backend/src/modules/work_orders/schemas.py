"""Pydantic v2 schemas for Work Orders, Serial Vault, Warranties, and SHA-256 Verification."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.modules.catalog.models import CatalogCategory
from src.modules.quotes.models import QuoteStatus
from src.modules.quotes.schemas import CustomerResponse
from src.modules.work_orders.models import WorkOrderStatus


class ChecklistStepItem(BaseModel):
    """Single step inside work_orders.checklist_json."""

    model_config = ConfigDict(from_attributes=True, frozen=True, extra="forbid")

    step_id: str
    label_pt_br: str
    is_checked: bool
    checked_at: str | None = None


class ChecklistStepPatchItem(BaseModel):
    """Patch input for toggling a single checklist step."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    step_id: str = Field(min_length=1, max_length=64)
    is_checked: bool


class WorkOrderChecklistUpdateRequest(BaseModel):
    """Request payload for PATCH /api/v1/work-orders/{id}/checklist."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    step_id: str | None = Field(default=None, min_length=1, max_length=64)
    is_checked: bool | None = None
    steps: list[ChecklistStepPatchItem] | None = None
    cloud_p2p_id: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=2000)


class WorkOrderScheduleRequest(BaseModel):
    """Request payload for scheduling a technician on a WorkOrder (PENDING -> SCHEDULED)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    assigned_technician_id: UUID | None = None
    notes: str | None = Field(default=None, max_length=2000)


class WorkOrderStartRequest(BaseModel):
    """Optional request payload when starting a WorkOrder in the field."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    assigned_technician_id: UUID | None = None
    notes: str | None = Field(default=None, max_length=2000)


class WorkOrderPhotoJsonUploadRequest(BaseModel):
    """JSON alternative payload for uploading an installation photo or registering its key."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    filename: str = Field(default="instalacao_cftv.jpg", min_length=1, max_length=255)
    content_base64: str | None = None
    content_type: str = Field(default="image/jpeg", min_length=3, max_length=100)
    photo_key: str | None = Field(default=None, min_length=3, max_length=500)


class InstalledSerialCreateRequest(BaseModel):
    """Request payload for registering a hardware serial number in the Serial Vault."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    catalog_item_id: UUID
    serial_number: str = Field(min_length=3, max_length=120)
    channel_or_slot_label: str = Field(min_length=1, max_length=120)
    distributor_warranty_until: date | None = None
    client_warranty_until: date | None = None


class InstalledSerialResponse(BaseModel):
    """Registered hardware Serial Number Vault record."""

    model_config = ConfigDict(from_attributes=True, frozen=True, extra="forbid")

    id: UUID
    organization_id: UUID
    work_order_id: UUID
    catalog_item_id: UUID
    sku: str
    name_pt_br: str
    category: CatalogCategory
    serial_number: str
    channel_or_slot_label: str
    distributor_warranty_until: date
    client_warranty_until: date
    created_at: datetime


class RequiredSerialItemSummary(BaseModel):
    """Progress summary of required vs registered serial numbers per hardware SKU."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    catalog_item_id: UUID
    sku: str
    name_pt_br: str
    category: CatalogCategory
    required_quantity: int
    registered_quantity: int
    is_satisfied: bool


class WorkOrderCompleteRequest(BaseModel):
    """Optional request payload when completing a field WorkOrder (IN_FIELD -> COMPLETED)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    cloud_p2p_id: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=2000)


class WorkOrderResponse(BaseModel):
    """Detailed WorkOrder response (role-safe for both OWNER and TECHNICIAN)."""

    model_config = ConfigDict(from_attributes=True, frozen=True, extra="forbid")

    id: UUID
    organization_id: UUID
    quote_id: UUID
    quote_status: QuoteStatus
    customer: CustomerResponse
    assigned_technician_id: UUID | None = None
    assigned_technician_name: str | None = None
    status: WorkOrderStatus
    checklist_json: list[ChecklistStepItem]
    installation_photos_keys: list[str]
    installation_photo_urls: list[str] = Field(default_factory=list)
    cloud_p2p_id: str | None = None
    notes: str | None = None
    completed_at: datetime | None = None
    warranty_expires_at: date | None = None
    preventive_maintenance_alert_sent: bool
    installed_serials: list[InstalledSerialResponse]
    required_serials_summary: list[RequiredSerialItemSummary]
    created_at: datetime
    updated_at: datetime


class ExpiringWarrantyItemResponse(BaseModel):
    """11-month preventive maintenance & expiring warranty radar item for OWNER dashboard."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    work_order_id: UUID
    quote_id: UUID
    organization_id: UUID
    customer_id: UUID
    customer_name: str
    customer_phone_whatsapp: str
    customer_email: str
    completed_at: datetime | None = None
    warranty_expires_at: date
    days_until_expiration: int
    preventive_maintenance_alert_sent: bool
    cloud_p2p_id: str | None = None
    installed_serials_count: int
    installed_serials: list[InstalledSerialResponse]


class DocumentVerificationResponse(BaseModel):
    """Public cryptographic verification response for GET /api/v1/verify/{pdf_sha256_hash}."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    verified: bool = True
    pdf_sha256_hash: str
    organization_name: str
    organization_cnpj: str
    quote_id: UUID
    quote_status: QuoteStatus
    quote_version: int
    customer_name: str
    customer_document_masked: str
    total_sale_cents: int
    approved_at: datetime | None = None
    approved_by_ip: str | None = None
    work_order_id: UUID | None = None
    work_order_status: WorkOrderStatus | None = None
    completed_at: datetime | None = None
    cloud_p2p_id: str | None = None
    warranty_expires_at: date | None = None
    is_warranty_active: bool
    installed_serials: list[InstalledSerialResponse]
