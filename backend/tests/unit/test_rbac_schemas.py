"""Unit tests verifying RBAC cost/margin redaction and category JSONB specification schemas."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from src.core.database import generate_uuid7
from src.core.exceptions import DomainValidationError
from src.core.security import UserRole
from src.modules.catalog.models import CatalogCategory, CatalogItem
from src.modules.catalog.schemas import (
    CatalogItemOwnerResponse,
    CatalogItemTechnicianResponse,
    validate_specs_for_category,
)
from src.modules.catalog.service import serialize_catalog_item_for_role
from src.modules.quotes.models import QuoteStatus
from src.modules.quotes.schemas import (
    CustomerResponse,
    QuoteItemOwnerResponse,
    QuoteItemPublicResponse,
    QuoteItemTechnicianResponse,
    QuoteOwnerResponse,
    QuotePublicResponse,
    QuoteTechnicianResponse,
)


def _build_sample_catalog_item() -> CatalogItem:
    """Construct an in-memory CatalogItem instance for RBAC serialization tests."""
    now = datetime.now(UTC)
    return CatalogItem(
        id=generate_uuid7(),
        organization_id=generate_uuid7(),
        sku="MHDX-1108",
        name_pt_br="DVR Intelbras Multi-HD MHDX 1108 8 Canais (+2 IP)",
        category=CatalogCategory.DVR,
        brand="Intelbras",
        cost_price_cents=59000,
        sale_price_cents=89900,
        stock_quantity=8,
        reserved_quantity=2,
        specs={
            "native_bnc_channels": 8,
            "extra_ip_channels": 2,
            "supports_bnc_to_ip_conversion": True,
            "max_sata_slots": 1,
            "max_tb_per_slot": 16,
            "max_incoming_bandwidth_mbps": 48,
            "supported_codecs": ["H.264", "H.265", "H.265+"],
            "is_pure_nvr": False,
            "requires_serial_number": True,
            "distributor_warranty_months": 12,
        },
        is_seed_protected=True,
        is_active=True,
        created_at=now,
        updated_at=now,
    )


def test_catalog_item_rbac_serialization_strips_cost_for_technician() -> None:
    """Verify TECHNICIAN catalog response omits cost_price_cents while OWNER includes it."""
    item = _build_sample_catalog_item()

    owner_dto = serialize_catalog_item_for_role(item, UserRole.OWNER)
    assert isinstance(owner_dto, CatalogItemOwnerResponse)
    owner_dump = owner_dto.model_dump()
    assert owner_dump["cost_price_cents"] == 59000
    assert owner_dump["sale_price_cents"] == 89900
    assert owner_dump["available_quantity"] == 6

    tech_dto = serialize_catalog_item_for_role(item, UserRole.TECHNICIAN)
    assert isinstance(tech_dto, CatalogItemTechnicianResponse)
    assert not isinstance(tech_dto, CatalogItemOwnerResponse)
    tech_dump = tech_dto.model_dump()
    assert "cost_price_cents" not in tech_dump
    assert "cost" not in tech_dto.model_dump_json()
    assert tech_dump["sale_price_cents"] == 89900
    assert tech_dump["available_quantity"] == 6


def test_quote_rbac_schemas_strip_cost_and_margin_for_technician_and_public_client() -> None:
    """Verify QuoteTechnicianResponse and QuotePublicResponse omit all cost and margin fields."""
    now = datetime.now(UTC)
    org_id = generate_uuid7()
    customer_id = generate_uuid7()
    quote_id = generate_uuid7()
    public_token = generate_uuid7()
    catalog_item_id = generate_uuid7()
    line_id = generate_uuid7()

    customer = CustomerResponse(
        id=customer_id,
        organization_id=org_id,
        name="Condomínio Residencial Jardim das Acácias",
        document_cpf_cnpj="45.123.890/0001-12",
        phone_whatsapp="+5511998123456",
        email="sindico@jardimdasacacias.com.br",
        address_json={"city": "São Paulo", "state": "SP"},
        created_at=now,
    )

    owner_item = QuoteItemOwnerResponse(
        id=line_id,
        catalog_item_id=catalog_item_id,
        sku="MHDX-1108",
        name_pt_br="DVR Intelbras Multi-HD MHDX 1108",
        category=CatalogCategory.DVR,
        quantity=2,
        unit_cost_cents=59000,
        unit_sale_cents=89900,
        is_auto_derived=True,
    )
    owner_quote = QuoteOwnerResponse(
        id=quote_id,
        organization_id=org_id,
        customer_id=customer_id,
        customer=customer,
        public_token=public_token,
        status=QuoteStatus.SENT,
        sizing_input_json={"retention_days": 15},
        total_cost_cents=118000,
        total_sale_cents=179800,
        margin_percent=Decimal("34.37"),
        valid_until=now + timedelta(days=15),
        version=1,
        items=[owner_item],
        created_at=now,
        updated_at=now,
    )
    owner_json = owner_quote.model_dump()
    assert owner_json["total_cost_cents"] == 118000
    assert owner_json["margin_percent"] == Decimal("34.37")
    assert owner_json["items"][0]["unit_cost_cents"] == 59000
    assert owner_json["items"][0]["line_total_cost_cents"] == 118000
    assert owner_json["items"][0]["line_total_sale_cents"] == 179800

    tech_item = QuoteItemTechnicianResponse(
        id=line_id,
        catalog_item_id=catalog_item_id,
        sku="MHDX-1108",
        name_pt_br="DVR Intelbras Multi-HD MHDX 1108",
        category=CatalogCategory.DVR,
        quantity=2,
        unit_sale_cents=89900,
        is_auto_derived=True,
    )
    tech_quote = QuoteTechnicianResponse(
        id=quote_id,
        organization_id=org_id,
        customer_id=customer_id,
        customer=customer,
        public_token=public_token,
        status=QuoteStatus.SENT,
        sizing_input_json={"retention_days": 15},
        total_sale_cents=179800,
        valid_until=now + timedelta(days=15),
        version=1,
        items=[tech_item],
        created_at=now,
        updated_at=now,
    )
    tech_dump = tech_quote.model_dump()
    assert "total_cost_cents" not in tech_dump
    assert "margin_percent" not in tech_dump
    assert "unit_cost_cents" not in tech_dump["items"][0]
    assert "line_total_cost_cents" not in tech_dump["items"][0]
    assert "cost" not in tech_quote.model_dump_json()
    assert "margin" not in tech_quote.model_dump_json()

    public_item = QuoteItemPublicResponse(
        id=line_id,
        catalog_item_id=catalog_item_id,
        sku="MHDX-1108",
        name_pt_br="DVR Intelbras Multi-HD MHDX 1108",
        category=CatalogCategory.DVR,
        quantity=2,
        unit_sale_cents=89900,
        is_auto_derived=True,
    )
    public_quote = QuotePublicResponse(
        id=quote_id,
        organization_id=org_id,
        customer_id=customer_id,
        customer=customer,
        public_token=public_token,
        status=QuoteStatus.SENT,
        sizing_input_json={"retention_days": 15},
        total_sale_cents=179800,
        valid_until=now + timedelta(days=15),
        version=1,
        items=[public_item],
        created_at=now,
        updated_at=now,
    )
    public_dump = public_quote.model_dump()
    assert "total_cost_cents" not in public_dump
    assert "margin_percent" not in public_dump
    assert "unit_cost_cents" not in public_dump["items"][0]
    assert "line_total_cost_cents" not in public_dump["items"][0]
    assert "cost" not in public_quote.model_dump_json()
    assert "margin" not in public_quote.model_dump_json()


def test_category_specs_validation_rejects_invalid_channel_count_or_extra_fields() -> None:
    """Verify validate_specs_for_category enforces strict Pydantic v2 category rules."""
    valid_hdd = validate_specs_for_category(
        CatalogCategory.HDD,
        {
            "capacity_tb": 4,
            "usable_capacity_gb": 3725,
            "surveillance_grade": True,
            "requires_serial_number": True,
            "distributor_warranty_months": 36,
        },
    )
    assert valid_hdd["capacity_tb"] == 4

    with pytest.raises(DomainValidationError) as exc_info:
        validate_specs_for_category(
            CatalogCategory.DVR,
            {
                "native_bnc_channels": 6,  # Invalid: must be 4, 8, 16, or 32
                "extra_ip_channels": 2,
                "max_sata_slots": 1,
                "max_tb_per_slot": 16,
                "max_incoming_bandwidth_mbps": 48,
                "supported_codecs": ["H.265+"],
            },
        )
    assert exc_info.value.http_status == 422
    assert exc_info.value.errors is not None
