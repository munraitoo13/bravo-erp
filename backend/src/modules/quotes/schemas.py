"""Role-segregated Pydantic v2 schemas for Customers and Quotes (Owner vs Technician vs Public)."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, computed_field

from src.modules.catalog.models import CatalogCategory
from src.modules.quotes.models import QuoteStatus


class CustomerCreateRequest(BaseModel):
    """Request payload for creating a tenant Customer."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=2, max_length=200)
    document_cpf_cnpj: str = Field(min_length=11, max_length=20)
    phone_whatsapp: str = Field(min_length=8, max_length=30)
    email: EmailStr
    address_json: dict[str, object] = Field(default_factory=dict)


class CustomerResponse(BaseModel):
    """Customer details embedded in Quote responses and customer listings."""

    model_config = ConfigDict(from_attributes=True, frozen=True, extra="forbid")

    id: UUID
    organization_id: UUID
    name: str
    document_cpf_cnpj: str
    phone_whatsapp: str
    email: str
    address_json: dict[str, object]
    created_at: datetime


class AuditLogResponse(BaseModel):
    """Immutable audit log entry response attached to detailed Quote views."""

    model_config = ConfigDict(from_attributes=True, frozen=True, extra="forbid")

    id: UUID
    organization_id: UUID
    entity_type: str
    entity_id: UUID
    action: str
    actor_user_id: UUID | None = None
    actor_ip: str | None = None
    previous_state: dict[str, object] | None = None
    new_state: dict[str, object]
    created_at: datetime


class QuoteItemCreateInput(BaseModel):
    """Line item input when creating a new Quote."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    catalog_item_id: UUID
    quantity: int = Field(ge=1, le=10000)
    unit_sale_cents: int | None = Field(default=None, ge=0)
    is_auto_derived: bool = False


class QuoteCreateRequest(BaseModel):
    """Request payload for creating a new Quote in DRAFT state."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    customer_id: UUID
    valid_days: int = Field(default=15, ge=1, le=180)
    valid_until: datetime | None = None
    sizing_input_json: dict[str, object] | None = None
    items: list[QuoteItemCreateInput] = Field(min_length=1)


class PublicQuoteApproveRequest(BaseModel):
    """Optional request payload when approving a Quote via the public link."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    accepted_terms: bool = True
    client_notes: str | None = Field(default=None, max_length=1000)


class QuoteItemPublicResponse(BaseModel):
    """Quote line item response for PUBLIC_CLIENT and TECHNICIAN (omits unit_cost_cents)."""

    model_config = ConfigDict(from_attributes=True, frozen=True, extra="forbid")

    id: UUID
    catalog_item_id: UUID
    sku: str
    name_pt_br: str
    category: CatalogCategory
    quantity: int
    unit_sale_cents: int
    is_auto_derived: bool

    @computed_field  # type: ignore[prop-decorator]
    @property
    def line_total_sale_cents(self) -> int:
        """Exact integer total sale price for this line item in centavos."""
        return self.quantity * self.unit_sale_cents


class QuoteItemTechnicianResponse(QuoteItemPublicResponse):
    """Quote line item response for TECHNICIAN (identical cost redaction to PUBLIC_CLIENT)."""


class QuoteItemOwnerResponse(QuoteItemPublicResponse):
    """Quote line item response for OWNER (includes unit_cost_cents and line_total_cost_cents)."""

    unit_cost_cents: int

    @computed_field  # type: ignore[prop-decorator]
    @property
    def line_total_cost_cents(self) -> int:
        """Exact integer total cost for this line item in centavos."""
        return self.quantity * self.unit_cost_cents


class QuotePublicResponse(BaseModel):
    """Commercial proposal response for PUBLIC_CLIENT (omits all cost and margin fields)."""

    model_config = ConfigDict(from_attributes=True, frozen=True, extra="forbid")

    id: UUID
    organization_id: UUID
    customer_id: UUID
    customer: CustomerResponse
    public_token: UUID
    status: QuoteStatus
    sizing_input_json: dict[str, object] | None = None
    total_sale_cents: int
    valid_until: datetime
    approved_at: datetime | None = None
    pdf_download_url: str | None = None
    pdf_sha256_hash: str | None = None
    work_order_id: UUID | None = None
    version: int
    items: list[QuoteItemPublicResponse]
    created_at: datetime
    updated_at: datetime


class QuoteTechnicianResponse(BaseModel):
    """Commercial proposal response for TECHNICIAN (omits all cost and margin fields)."""

    model_config = ConfigDict(from_attributes=True, frozen=True, extra="forbid")

    id: UUID
    organization_id: UUID
    customer_id: UUID
    customer: CustomerResponse
    public_token: UUID
    status: QuoteStatus
    sizing_input_json: dict[str, object] | None = None
    total_sale_cents: int
    valid_until: datetime
    approved_at: datetime | None = None
    pdf_download_url: str | None = None
    pdf_sha256_hash: str | None = None
    work_order_id: UUID | None = None
    version: int
    items: list[QuoteItemTechnicianResponse]
    audit_logs: list[AuditLogResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class QuoteOwnerResponse(BaseModel):
    """Full commercial proposal response for OWNER (includes cost and margin fields)."""

    model_config = ConfigDict(from_attributes=True, frozen=True, extra="forbid")

    id: UUID
    organization_id: UUID
    customer_id: UUID
    customer: CustomerResponse
    public_token: UUID
    status: QuoteStatus
    sizing_input_json: dict[str, object] | None = None
    total_cost_cents: int
    total_sale_cents: int
    margin_percent: Decimal
    valid_until: datetime
    approved_at: datetime | None = None
    approved_by_ip: str | None = None
    pdf_download_url: str | None = None
    pdf_sha256_hash: str | None = None
    work_order_id: UUID | None = None
    version: int
    items: list[QuoteItemOwnerResponse]
    audit_logs: list[AuditLogResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
