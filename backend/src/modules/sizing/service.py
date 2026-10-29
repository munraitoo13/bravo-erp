"""Application service connecting the pure CCTV Sizing Engine to the tenant's CatalogItems."""

from collections.abc import Sequence
from decimal import Decimal

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import CurrentTenantContext
from src.core.exceptions import DomainValidationError, ResourceNotFoundError
from src.core.security import UserRole
from src.modules.catalog.models import CatalogCategory, CatalogItem
from src.modules.catalog.repository import CatalogRepository
from src.modules.catalog.schemas import (
    DvrSpecs,
    HddSpecs,
    PoeSwitchSpecs,
    PowerSupplySpecs,
)
from src.modules.sizing.domain.engine import CCTVSizingEngine
from src.modules.sizing.domain.value_objects import (
    CameraGroupInput,
    DerivedBomRequirement,
    HddCandidate,
    PoeSwitchCandidate,
    PowerSupplyCandidate,
    RecorderCandidate,
    SizingEngineInput,
)
from src.modules.sizing.schemas import (
    ElectricalSummaryResponse,
    GroupStorageBreakdownResponse,
    SelectedHddAllocationResponse,
    SizingBomLineOwnerResponse,
    SizingBomLineTechnicianResponse,
    SizingCalculateOwnerResponse,
    SizingCalculateRequest,
    SizingCalculateTechnicianResponse,
    StorageSummaryResponse,
    TopologySummaryResponse,
    VoltageDropWarningResponse,
)

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

type SizingRoleResponse = SizingCalculateOwnerResponse | SizingCalculateTechnicianResponse


class SizingService:
    """Orchestrates CCTV sizing calculations and maps BOM requirements to live tenant SKUs."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._catalog_repo = CatalogRepository(session)

    @staticmethod
    def _extract_candidates(
        active_items: Sequence[CatalogItem],
    ) -> tuple[
        list[RecorderCandidate],
        list[HddCandidate],
        list[PowerSupplyCandidate],
        list[PoeSwitchCandidate],
    ]:
        """Convert active ORM CatalogItems into pure domain candidate value objects."""
        recorders: list[RecorderCandidate] = []
        hdds: list[HddCandidate] = []
        psus: list[PowerSupplyCandidate] = []
        poe_switches: list[PoeSwitchCandidate] = []

        for item in active_items:
            if item.category == CatalogCategory.DVR:
                dvr_specs = DvrSpecs.model_validate(item.specs)
                recorders.append(
                    RecorderCandidate(
                        sku=item.sku,
                        native_bnc_channels=dvr_specs.native_bnc_channels,
                        extra_ip_channels=dvr_specs.extra_ip_channels,
                        supports_bnc_to_ip_conversion=dvr_specs.supports_bnc_to_ip_conversion,
                        max_sata_slots=dvr_specs.max_sata_slots,
                        max_tb_per_slot=dvr_specs.max_tb_per_slot,
                        max_incoming_bandwidth_mbps=dvr_specs.max_incoming_bandwidth_mbps,
                        supported_codecs=tuple(dvr_specs.supported_codecs),
                        is_pure_nvr=dvr_specs.is_pure_nvr,
                        sale_price_cents=item.sale_price_cents,
                    )
                )
            elif item.category == CatalogCategory.HDD:
                hdd_specs = HddSpecs.model_validate(item.specs)
                hdds.append(
                    HddCandidate(
                        sku=item.sku,
                        capacity_tb=hdd_specs.capacity_tb,
                        usable_capacity_gb=hdd_specs.usable_capacity_gb,
                        sale_price_cents=item.sale_price_cents,
                    )
                )
            elif item.category == CatalogCategory.POWER_SUPPLY:
                psu_specs = PowerSupplySpecs.model_validate(item.specs)
                psus.append(
                    PowerSupplyCandidate(
                        sku=item.sku,
                        output_voltage_vdc=psu_specs.output_voltage_vdc,
                        max_current_amps=psu_specs.max_current_amps,
                        sale_price_cents=item.sale_price_cents,
                    )
                )
            elif item.category == CatalogCategory.POE_SWITCH:
                poe_specs = PoeSwitchSpecs.model_validate(item.specs)
                poe_switches.append(
                    PoeSwitchCandidate(
                        sku=item.sku,
                        poe_ports=poe_specs.poe_ports,
                        total_poe_budget_watts=poe_specs.total_poe_budget_watts,
                        sale_price_cents=item.sale_price_cents,
                    )
                )

        return recorders, hdds, psus, poe_switches

    @staticmethod
    def _match_bom_requirement_to_catalog_item(
        req: DerivedBomRequirement,
        active_items: Sequence[CatalogItem],
        sku_lookup: dict[str, CatalogItem],
    ) -> CatalogItem:
        """Resolve an abstract DerivedBomRequirement to the best matching tenant CatalogItem."""
        if req.sku_hint is not None and req.sku_hint in sku_lookup:
            return sku_lookup[req.sku_hint]

        if req.role in ("CAMERA_ANALOG", "CAMERA_IP"):
            target_cat = (
                CatalogCategory.CAMERA_ANALOG
                if req.role == "CAMERA_ANALOG"
                else CatalogCategory.CAMERA_IP
            )
            cam_matches = [
                item
                for item in active_items
                if item.category == target_cat
                and item.specs.get("resolution") == req.resolution_hint
                and item.specs.get("form_factor") == req.form_factor_hint
            ]
            if not cam_matches:
                # Fallback to resolution match regardless of form factor
                cam_matches = [
                    item
                    for item in active_items
                    if item.category == target_cat
                    and item.specs.get("resolution") == req.resolution_hint
                ]
            if not cam_matches:
                # Fallback to any camera in that technology category
                cam_matches = [item for item in active_items if item.category == target_cat]
            if cam_matches:
                return min(cam_matches, key=lambda c: (c.sale_price_cents, c.sku))

        if req.sub_type_hint is not None:
            sub_matches = [
                item for item in active_items if item.specs.get("sub_type") == req.sub_type_hint
            ]
            if sub_matches:
                return min(sub_matches, key=lambda c: (c.sale_price_cents, c.sku))

        if req.cable_type_hint is not None:
            cable_matches = [
                item
                for item in active_items
                if item.category == CatalogCategory.CABLE
                and item.specs.get("cable_type") == req.cable_type_hint
            ]
            if not cable_matches and req.role == "CABLE_UTP":
                cable_matches = [
                    item
                    for item in active_items
                    if item.category == CatalogCategory.CABLE
                    and str(item.specs.get("cable_type", "")).startswith("UTP_")
                ]
            if cable_matches:
                return min(cable_matches, key=lambda c: (c.sale_price_cents, c.sku))

        raise ResourceNotFoundError(
            detail=f"No active catalog SKU found matching BOM role '{req.role}'.",
            errors=[
                {
                    "bom_role": req.role,
                    "sku_hint": req.sku_hint,
                    "sub_type_hint": req.sub_type_hint,
                    "cable_type_hint": req.cable_type_hint,
                }
            ],
        )

    async def calculate_sizing(
        self,
        ctx: CurrentTenantContext,
        payload: SizingCalculateRequest,
    ) -> SizingRoleResponse:
        """Run the pure CCTV Sizing Engine and map results to role-redacted tenant CatalogItems."""
        active_items = await self._catalog_repo.list_items(
            ctx.organization_id,
            active_only=True,
        )
        if not active_items:
            raise DomainValidationError(
                detail="Organization catalog has no active items to perform CCTV sizing."
            )

        recorders, hdds, psus, poe_switches = self._extract_candidates(active_items)
        sku_lookup = {item.sku: item for item in active_items}

        domain_groups = tuple(
            CameraGroupInput(
                group_label=g.group_label,
                technology=g.technology,
                count=g.count,
                resolution=g.resolution,
                fps=g.fps,
                codec=g.codec,
                retention_days=g.retention_days,
                recording_hours_per_day=g.recording_hours_per_day,
                cabling_mode=g.cabling_mode,
                average_cable_meters=g.average_cable_meters,
                form_factor=g.form_factor,
                ir_current_draw_ma=g.ir_current_draw_ma,
                poe_power_watts=g.poe_power_watts,
            )
            for g in payload.camera_groups
        )

        engine_result = CCTVSizingEngine.calculate(
            engine_input=SizingEngineInput(camera_groups=domain_groups),
            recorder_candidates=recorders,
            hdd_candidates=hdds,
            psu_candidates=psus,
            poe_candidates=poe_switches,
        )

        topology_resp = TopologySummaryResponse(
            selected_recorder_sku=engine_result.topology.selected_recorder_sku,
            is_pure_nvr=engine_result.topology.is_pure_nvr,
            analog_cameras_count=engine_result.topology.analog_cameras_count,
            ip_cameras_count=engine_result.topology.ip_cameras_count,
            total_cameras_count=engine_result.topology.total_cameras_count,
            native_bnc_channels=engine_result.topology.native_bnc_channels,
            extra_ip_channels=engine_result.topology.extra_ip_channels,
            bnc_channels_used_by_analog=engine_result.topology.bnc_channels_used_by_analog,
            bnc_channels_converted_to_ip=engine_result.topology.bnc_channels_converted_to_ip,
            total_supported_channels=engine_result.topology.total_supported_channels,
            channel_utilization_percent=engine_result.topology.channel_utilization_percent,
            total_incoming_bandwidth_mbps=engine_result.topology.total_incoming_bandwidth_mbps,
            max_incoming_bandwidth_mbps=engine_result.topology.max_incoming_bandwidth_mbps,
            max_sata_slots=engine_result.topology.max_sata_slots,
            max_tb_per_slot=engine_result.topology.max_tb_per_slot,
        )

        storage_resp = StorageSummaryResponse(
            group_breakdowns=[
                GroupStorageBreakdownResponse(
                    group_label=b.group_label,
                    camera_count=b.camera_count,
                    bitrate_kbps_per_camera=b.bitrate_kbps_per_camera,
                    daily_gb_per_camera=b.daily_gb_per_camera,
                    group_retention_gb=b.group_retention_gb,
                    group_bandwidth_mbps=b.group_bandwidth_mbps,
                )
                for b in engine_result.storage.group_breakdowns
            ],
            raw_retention_gb=engine_result.storage.raw_retention_gb,
            total_required_gb_with_margin=engine_result.storage.total_required_gb_with_margin,
            required_nominal_tb=engine_result.storage.required_nominal_tb,
            selected_hdds=[
                SelectedHddAllocationResponse(
                    sku=h.sku,
                    capacity_tb=h.capacity_tb,
                    quantity=h.quantity,
                    total_capacity_tb=h.total_capacity_tb,
                    total_sale_price_cents=h.total_sale_price_cents,
                )
                for h in engine_result.storage.selected_hdds
            ],
            total_selected_tb=engine_result.storage.total_selected_tb,
            sata_slots_used=engine_result.storage.sata_slots_used,
        )

        elec = engine_result.electrical_and_bom
        electrical_resp = ElectricalSummaryResponse(
            analog_raw_current_amps=elec.analog_raw_current_amps,
            analog_required_current_amps_with_headroom=(
                elec.analog_required_current_amps_with_headroom
            ),
            ip_raw_power_watts=elec.ip_raw_power_watts,
            ip_required_poe_watts_with_headroom=elec.ip_required_poe_watts_with_headroom,
            coaxial_cable_meters_with_slack=elec.coaxial_cable_meters_with_slack,
            coaxial_cable_rolls_100m=elec.coaxial_cable_rolls_100m,
            utp_cable_meters_with_slack=elec.utp_cable_meters_with_slack,
            utp_cable_boxes_305m=elec.utp_cable_boxes_305m,
            voltage_drop_warnings=[
                VoltageDropWarningResponse(
                    group_label=w.group_label,
                    cabling_mode=w.cabling_mode,
                    distance_meters=w.distance_meters,
                    current_amps=w.current_amps,
                    resistance_ohm_per_meter=w.resistance_ohm_per_meter,
                    voltage_drop_volts=w.voltage_drop_volts,
                    voltage_at_load_volts=w.voltage_at_load_volts,
                    min_operating_voltage_volts=w.min_operating_voltage_volts,
                    recommendation_pt_br=w.recommendation_pt_br,
                )
                for w in elec.voltage_drop_warnings
            ],
        )

        owner_bom_lines: list[SizingBomLineOwnerResponse] = []
        tech_bom_lines: list[SizingBomLineTechnicianResponse] = []
        total_cost_cents = 0
        total_sale_cents = 0

        for req in elec.derived_bom:
            matched_item = self._match_bom_requirement_to_catalog_item(
                req=req,
                active_items=active_items,
                sku_lookup=sku_lookup,
            )
            avail_qty = matched_item.stock_quantity - matched_item.reserved_quantity
            total_cost_cents += req.quantity * matched_item.cost_price_cents
            total_sale_cents += req.quantity * matched_item.sale_price_cents

            owner_bom_lines.append(
                SizingBomLineOwnerResponse(
                    role=req.role,
                    catalog_item_id=matched_item.id,
                    sku=matched_item.sku,
                    name_pt_br=matched_item.name_pt_br,
                    category=matched_item.category,
                    brand=matched_item.brand,
                    quantity=req.quantity,
                    unit_cost_cents=matched_item.cost_price_cents,
                    unit_sale_cents=matched_item.sale_price_cents,
                    available_stock_quantity=avail_qty,
                    is_auto_derived=req.is_auto_derived,
                    notes_pt_br=req.notes_pt_br,
                )
            )
            tech_bom_lines.append(
                SizingBomLineTechnicianResponse(
                    role=req.role,
                    catalog_item_id=matched_item.id,
                    sku=matched_item.sku,
                    name_pt_br=matched_item.name_pt_br,
                    category=matched_item.category,
                    brand=matched_item.brand,
                    quantity=req.quantity,
                    unit_sale_cents=matched_item.sale_price_cents,
                    available_stock_quantity=avail_qty,
                    is_auto_derived=req.is_auto_derived,
                    notes_pt_br=req.notes_pt_br,
                )
            )

        logger.info(
            "cctv_sizing_calculated",
            organization_id=str(ctx.organization_id),
            selected_recorder_sku=topology_resp.selected_recorder_sku,
            total_cameras=topology_resp.total_cameras_count,
            required_nominal_tb=storage_resp.required_nominal_tb,
            warnings_count=len(electrical_resp.voltage_drop_warnings),
        )

        if ctx.role == UserRole.OWNER:
            margin_pct = (
                (
                    (Decimal(total_sale_cents - total_cost_cents) / Decimal(total_sale_cents))
                    * Decimal("100.00")
                ).quantize(Decimal("0.01"))
                if total_sale_cents > 0
                else Decimal("0.00")
            )
            return SizingCalculateOwnerResponse(
                topology=topology_resp,
                storage=storage_resp,
                electrical=electrical_resp,
                bom_items=owner_bom_lines,
                total_cost_cents=total_cost_cents,
                total_sale_cents=total_sale_cents,
                margin_percent=margin_pct,
            )

        return SizingCalculateTechnicianResponse(
            topology=topology_resp,
            storage=storage_resp,
            electrical=electrical_resp,
            bom_items=tech_bom_lines,
            total_sale_cents=total_sale_cents,
        )
