"""Role-segregated Pydantic v2 schemas for Customers and Quotes (Owner vs Technician vs Public)."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, computed_field

from src.modules.catalog.models import CatalogCategory
from src.modules.quotes.models import QuoteStatus


class CustomerResponse(BaseModel):
    """Customer details embedded in Quote responses."""

    model_config = ConfigDict(from_attributes=True, frozen=True, extra="forbid")

    id: UUID
    organization_id: UUID
    name: str
    document_cpf_cnpj: str
    phone_whatsapp: str
    email: str
    address_json: dict[str, object]
    created_at: datetime


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
    version: int
    items: list[QuoteItemTechnicianResponse]
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
    version: int
    items: list[QuoteItemOwnerResponse]
    created_at: datetime
    updated_at: datetime
