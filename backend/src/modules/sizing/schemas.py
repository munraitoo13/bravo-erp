"""Pydantic v2 request and role-redacted response schemas for the CCTV Sizing Engine."""

from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, computed_field

from src.modules.catalog.models import CatalogCategory
from src.modules.sizing.domain.value_objects import (
    BomRoleLiteral,
    CablingModeLiteral,
    CameraTechnologyLiteral,
    CodecLiteral,
    FormFactorLiteral,
    FpsLiteral,
    ResolutionLiteral,
)


class CameraGroupRequest(BaseModel):
    """Input specification for a camera group in POST /api/v1/sizing/calculate."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    group_label: str = Field(min_length=1, max_length=120)
    technology: CameraTechnologyLiteral
    count: int = Field(ge=1, le=64)
    resolution: ResolutionLiteral = "1080p"
    fps: FpsLiteral = 30
    codec: CodecLiteral = "H.265+"
    retention_days: int = Field(ge=1, le=365, default=15)
    recording_hours_per_day: float = Field(gt=0.0, le=24.0, default=24.0)
    cabling_mode: CablingModeLiteral = "BALUN_UTP"
    average_cable_meters: float = Field(gt=0.0, le=500.0, default=35.0)
    form_factor: FormFactorLiteral = "BULLET"
    ir_current_draw_ma: int | None = Field(default=None, ge=100, le=3000)
    poe_power_watts: float | None = Field(default=None, gt=0.0, le=60.0)


class SizingCalculateRequest(BaseModel):
    """Request payload for POST /api/v1/sizing/calculate."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    camera_groups: list[CameraGroupRequest] = Field(min_length=1, max_length=16)


class GroupStorageBreakdownResponse(BaseModel):
    """Per-group storage and bitrate metrics."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    group_label: str
    camera_count: int
    bitrate_kbps_per_camera: int
    daily_gb_per_camera: float
    group_retention_gb: float
    group_bandwidth_mbps: float


class SelectedHddAllocationResponse(BaseModel):
    """Selected WD Purple HDD allocation summary."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    sku: str
    capacity_tb: int
    quantity: int
    total_capacity_tb: int
    total_sale_price_cents: int


class StorageSummaryResponse(BaseModel):
    """Storage calculation summary in GB and nominal TB."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    group_breakdowns: list[GroupStorageBreakdownResponse]
    raw_retention_gb: float
    total_required_gb_with_margin: float
    required_nominal_tb: int
    selected_hdds: list[SelectedHddAllocationResponse]
    total_selected_tb: int
    sata_slots_used: int


class TopologySummaryResponse(BaseModel):
    """Intelbras MHDX hybrid channel & NVR topology summary."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    selected_recorder_sku: str
    is_pure_nvr: bool
    analog_cameras_count: int
    ip_cameras_count: int
    total_cameras_count: int
    native_bnc_channels: int
    extra_ip_channels: int
    bnc_channels_used_by_analog: int
    bnc_channels_converted_to_ip: int
    total_supported_channels: int
    channel_utilization_percent: float
    total_incoming_bandwidth_mbps: float
    max_incoming_bandwidth_mbps: int
    max_sata_slots: int
    max_tb_per_slot: int


class VoltageDropWarningResponse(BaseModel):
    """Voltage drop alert when copper loop resistance lowers camera voltage below 10.8V."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    group_label: str
    cabling_mode: CablingModeLiteral
    distance_meters: float
    current_amps: float
    resistance_ohm_per_meter: float
    voltage_drop_volts: float
    voltage_at_load_volts: float
    min_operating_voltage_volts: float
    recommendation_pt_br: str


class ElectricalSummaryResponse(BaseModel):
    """12V DC current draw, PoE wattage budget, cable meters, and voltage drop warnings."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    analog_raw_current_amps: float
    analog_required_current_amps_with_headroom: float
    ip_raw_power_watts: float
    ip_required_poe_watts_with_headroom: float
    coaxial_cable_meters_with_slack: int
    coaxial_cable_rolls_100m: int
    utp_cable_meters_with_slack: int
    utp_cable_boxes_305m: int
    voltage_drop_warnings: list[VoltageDropWarningResponse]


class SizingBomLineTechnicianResponse(BaseModel):
    """Role-redacted BOM line item for TECHNICIAN (omits unit_cost_cents)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    role: BomRoleLiteral
    catalog_item_id: UUID
    sku: str
    name_pt_br: str
    category: CatalogCategory
    brand: str
    quantity: int
    unit_sale_cents: int
    available_stock_quantity: int
    is_auto_derived: bool
    notes_pt_br: str

    @computed_field
    def line_total_sale_cents(self) -> int:
        """Exact integer total sale price for this BOM line."""
        return self.quantity * self.unit_sale_cents


class SizingBomLineOwnerResponse(SizingBomLineTechnicianResponse):
    """Full BOM line item for OWNER (includes unit_cost_cents and line_total_cost_cents)."""

    unit_cost_cents: int

    @computed_field
    def line_total_cost_cents(self) -> int:
        """Exact integer total cost price for this BOM line."""
        return self.quantity * self.unit_cost_cents


class SizingCalculateTechnicianResponse(BaseModel):
    """Role-redacted sizing response for TECHNICIAN (omits total_cost_cents and margin_percent)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    topology: TopologySummaryResponse
    storage: StorageSummaryResponse
    electrical: ElectricalSummaryResponse
    bom_items: list[SizingBomLineTechnicianResponse]
    total_sale_cents: int


class SizingCalculateOwnerResponse(BaseModel):
    """Full sizing response for OWNER (includes total_cost_cents and margin_percent)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    topology: TopologySummaryResponse
    storage: StorageSummaryResponse
    electrical: ElectricalSummaryResponse
    bom_items: list[SizingBomLineOwnerResponse]
    total_cost_cents: int
    total_sale_cents: int
    margin_percent: Decimal
