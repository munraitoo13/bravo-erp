"""Pydantic v2 schemas for equipment catalog items, category specs, and role-redacted responses."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError, computed_field, model_validator

from src.core.exceptions import DomainValidationError, ErrorDetailItem
from src.modules.catalog.models import CatalogCategory


class DvrSpecs(BaseModel):
    """Technical specifications for Digital Video Recorders (Intelbras MHDX / NVD)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    native_bnc_channels: Literal[4, 8, 16, 32]
    extra_ip_channels: int = Field(ge=0, le=16)
    supports_bnc_to_ip_conversion: bool = True
    max_sata_slots: int = Field(ge=1, le=8)
    max_tb_per_slot: int = Field(ge=6, le=20)
    max_incoming_bandwidth_mbps: int = Field(ge=16, le=512)
    supported_codecs: list[Literal["H.264", "H.265", "H.265+"]]
    is_pure_nvr: bool = False
    requires_serial_number: bool = True
    distributor_warranty_months: int = 12


class AnalogCameraSpecs(BaseModel):
    """Technical specifications for Multi-HD / HDCVI Analog Cameras."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    resolution: Literal["720p", "1080p", "4MP", "4K"]
    max_fps: Literal[15, 20, 30] = 30
    ir_range_meters: int = Field(ge=10, le=100)
    ir_current_draw_ma: int = Field(ge=150, le=2000)
    nominal_voltage_vdc: float = 12.0
    min_operating_voltage_vdc: float = 10.8
    form_factor: Literal["BULLET", "DOME"]
    requires_serial_number: bool = True
    distributor_warranty_months: int = 12


class IpCameraSpecs(BaseModel):
    """Technical specifications for PoE IP Cameras."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    resolution: Literal["720p", "1080p", "4MP", "4K"]
    max_fps: Literal[15, 20, 30] = 30
    supported_codecs: list[Literal["H.264", "H.265", "H.265+"]]
    poe_standard: Literal["802.3af", "802.3at"] = "802.3af"
    max_power_watts: float = Field(gt=0, le=30.0)
    ir_current_draw_ma: int = Field(ge=200, le=2000)
    ir_range_meters: int = Field(ge=20, le=100)
    form_factor: Literal["BULLET", "DOME", "SPEED_DOME"]
    requires_serial_number: bool = True
    distributor_warranty_months: int = 12


class HddSpecs(BaseModel):
    """Technical specifications for 24x7 Surveillance Hard Drives (WD Purple)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    capacity_tb: Literal[1, 2, 4, 6, 8, 10, 12, 16]
    usable_capacity_gb: int = Field(gt=0)
    surveillance_grade: bool = True
    requires_serial_number: bool = True
    distributor_warranty_months: int = 36


class PowerSupplySpecs(BaseModel):
    """Technical specifications for 12V DC Switching Power Supplies."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    output_voltage_vdc: float = 12.8
    max_current_amps: Literal[5, 10, 20, 30]
    requires_serial_number: bool = False
    distributor_warranty_months: int = 12


class PoeSwitchSpecs(BaseModel):
    """Technical specifications for PoE Network Switches."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    poe_ports: Literal[4, 8, 16, 24]
    uplink_ports: int = 2
    total_poe_budget_watts: float = Field(gt=0, le=500.0)
    supports_extend_250m: bool = True
    requires_serial_number: bool = True
    distributor_warranty_months: int = 12


class CableSpecs(BaseModel):
    """Technical specifications for Coaxial Bipolar and UTP Copper Cables."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    cable_type: Literal["UTP_CAT5E", "UTP_CAT6", "COAXIAL_BIPOLAR_4MM"]
    roll_length_meters: Literal[100, 305]
    dc_resistance_ohm_per_meter: float = Field(gt=0)
    is_pure_copper: bool = True
    requires_serial_number: bool = False


class GenericAccessorySpecs(BaseModel):
    """Technical specifications for Baluns, Connectors, VBOX Junction Boxes, and Labor."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    sub_type: Literal[
        "PASSIVE_BALUN_PAIR",
        "CONNECTOR_BNC_MALE",
        "CONNECTOR_P4_MALE",
        "CONNECTOR_RJ45",
        "JUNCTION_BOX_VBOX",
        "LABOR_POINT_INSTALL",
    ]
    units_per_package: int = Field(default=1, ge=1)
    requires_serial_number: bool = False


_CATEGORY_SPEC_MODELS: dict[CatalogCategory, type[BaseModel]] = {
    CatalogCategory.DVR: DvrSpecs,
    CatalogCategory.CAMERA_ANALOG: AnalogCameraSpecs,
    CatalogCategory.CAMERA_IP: IpCameraSpecs,
    CatalogCategory.HDD: HddSpecs,
    CatalogCategory.POWER_SUPPLY: PowerSupplySpecs,
    CatalogCategory.POE_SWITCH: PoeSwitchSpecs,
    CatalogCategory.CABLE: CableSpecs,
    CatalogCategory.BALUN: GenericAccessorySpecs,
    CatalogCategory.CONNECTOR: GenericAccessorySpecs,
    CatalogCategory.ACCESSORY: GenericAccessorySpecs,
    CatalogCategory.SERVICE_LABOR: GenericAccessorySpecs,
}


def validate_specs_for_category(
    category: CatalogCategory,
    specs: dict[str, object],
) -> dict[str, object]:
    """Validate raw specs dictionary against the category's strict Pydantic v2 schema."""
    spec_model = _CATEGORY_SPEC_MODELS[category]
    try:
        validated = spec_model.model_validate(specs)
        return validated.model_dump()
    except ValidationError as exc:
        formatted_errors: list[ErrorDetailItem] = [
            {
                "field": "specs." + ".".join(str(loc) for loc in err.get("loc", ())),
                "message": str(err.get("msg", "Invalid specification attribute")),
                "type": str(err.get("type", "value_error")),
            }
            for err in exc.errors()
        ]
        raise DomainValidationError(
            detail=f"Invalid technical specifications for category '{category.value}'.",
            errors=formatted_errors,
        ) from exc


class CatalogItemCreateRequest(BaseModel):
    """Payload to create a new CatalogItem."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    sku: str = Field(min_length=2, max_length=64)
    name_pt_br: str = Field(min_length=3, max_length=255)
    category: CatalogCategory
    brand: str = Field(min_length=1, max_length=80)
    cost_price_cents: int = Field(ge=0)
    sale_price_cents: int = Field(ge=0)
    stock_quantity: int = Field(default=0, ge=0)
    specs: dict[str, object]
    is_active: bool = True

    @model_validator(mode="after")
    def _validate_category_specs(self) -> "CatalogItemCreateRequest":
        validate_specs_for_category(self.category, self.specs)
        return self


class CatalogItemUpdateRequest(BaseModel):
    """Payload to partially update an existing CatalogItem."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name_pt_br: str | None = Field(default=None, min_length=3, max_length=255)
    brand: str | None = Field(default=None, min_length=1, max_length=80)
    cost_price_cents: int | None = Field(default=None, ge=0)
    sale_price_cents: int | None = Field(default=None, ge=0)
    stock_quantity: int | None = Field(default=None, ge=0)
    specs: dict[str, object] | None = None
    is_active: bool | None = None


class CatalogItemTechnicianResponse(BaseModel):
    """Role-segregated catalog response for TECHNICIAN (strictly omits cost_price_cents)."""

    model_config = ConfigDict(from_attributes=True, frozen=True, extra="forbid")

    id: UUID
    organization_id: UUID
    sku: str
    name_pt_br: str
    category: CatalogCategory
    brand: str
    sale_price_cents: int
    stock_quantity: int
    reserved_quantity: int
    specs: dict[str, object]
    is_seed_protected: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime

    @computed_field  # type: ignore[prop-decorator]
    @property
    def available_quantity(self) -> int:
        """Compute physical stock minus reserved stock."""
        return self.stock_quantity - self.reserved_quantity


class CatalogItemOwnerResponse(CatalogItemTechnicianResponse):
    """Full catalog response for OWNER (includes cost_price_cents)."""

    cost_price_cents: int
