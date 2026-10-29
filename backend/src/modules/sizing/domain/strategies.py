"""Pure domain strategies for Storage, Intelbras MHDX Hybrid Topology, and Electrical/Auto-BOM."""

import math
from collections.abc import Sequence
from itertools import combinations_with_replacement

from src.core.exceptions import (
    DomainValidationError,
    StorageCapacityExceededError,
    TopologyIncompatibleError,
)
from src.modules.sizing.domain.bitrate_table import get_bitrate_kbps
from src.modules.sizing.domain.value_objects import (
    CablingModeLiteral,
    CameraGroupInput,
    DerivedBomRequirement,
    ElectricalAndBomResult,
    GroupStorageBreakdown,
    HddCandidate,
    PoeSwitchCandidate,
    PowerSupplyCandidate,
    RecorderCandidate,
    ResolutionLiteral,
    SelectedEquipmentQuantity,
    SelectedHddAllocation,
    StorageCalculationResult,
    TopologySelectionResult,
    VoltageDropWarning,
)

# Default reference values from SPEC.md Section 3.3
STORAGE_SAFETY_MARGIN_MULTIPLIER: float = 1.15
CURRENT_HEADROOM_MULTIPLIER: float = 1.30
POE_HEADROOM_MULTIPLIER: float = 1.25
CABLE_SLACK_MULTIPLIER: float = 1.15
NOMINAL_SOURCE_VOLTAGE_VDC: float = 12.0
MIN_OPERATING_VOLTAGE_VDC: float = 10.8

# Reference conductor DC resistance (Ohm/meter at 20°C pure copper)
RESISTANCE_COAX_BIPOLAR_OHM_M: float = 0.0344
RESISTANCE_CAT5E_SINGLE_OHM_M: float = 0.0839
RESISTANCE_CAT6_SINGLE_OHM_M: float = 0.0660

DEFAULT_ANALOG_CURRENT_MA: dict[ResolutionLiteral, int] = {
    "720p": 300,
    "1080p": 350,
    "4MP": 500,
    "4K": 650,
}

DEFAULT_IP_POWER_WATTS: dict[ResolutionLiteral, float] = {
    "720p": 5.5,
    "1080p": 6.5,
    "4MP": 7.5,
    "4K": 9.5,
}


class StorageCalculationStrategy:
    """Calculates CCTV retention storage in GB/TB and selects optimal WD Purple HDD combinations."""

    @staticmethod
    def compute_daily_gb_per_camera(
        bitrate_kbps: int,
        recording_hours_per_day: float = 24.0,
    ) -> float:
        """Compute daily storage per camera: (Bitrate_kbps * 3600 * Hours) / (8 * 1024 * 1024)."""
        if recording_hours_per_day <= 0 or recording_hours_per_day > 24.0:
            raise DomainValidationError(detail="recording_hours_per_day must be in (0, 24].")
        return (bitrate_kbps * 3600.0 * recording_hours_per_day) / (8.0 * 1024.0 * 1024.0)

    @classmethod
    def calculate_storage_metrics(
        cls,
        camera_groups: Sequence[CameraGroupInput],
    ) -> tuple[tuple[GroupStorageBreakdown, ...], float, float, int]:
        """Compute group breakdowns, raw GB, 15% safety margin GB, and required nominal TB."""
        if not camera_groups:
            raise DomainValidationError(detail="At least one camera group is required.")

        breakdowns: list[GroupStorageBreakdown] = []
        raw_retention_gb = 0.0

        for group in camera_groups:
            if group.count <= 0:
                raise DomainValidationError(
                    detail=f"Camera group '{group.group_label}' must have count >= 1."
                )
            if group.retention_days <= 0:
                raise DomainValidationError(
                    detail=f"Camera group '{group.group_label}' must have retention_days >= 1."
                )
            bitrate_kbps = get_bitrate_kbps(group.resolution, group.fps, group.codec)
            daily_gb = cls.compute_daily_gb_per_camera(
                bitrate_kbps=bitrate_kbps,
                recording_hours_per_day=group.recording_hours_per_day,
            )
            group_gb = group.count * daily_gb * group.retention_days
            bandwidth_mbps = (group.count * bitrate_kbps) / 1000.0
            raw_retention_gb += group_gb

            breakdowns.append(
                GroupStorageBreakdown(
                    group_label=group.group_label,
                    camera_count=group.count,
                    bitrate_kbps_per_camera=bitrate_kbps,
                    daily_gb_per_camera=round(daily_gb, 4),
                    group_retention_gb=round(group_gb, 4),
                    group_bandwidth_mbps=round(bandwidth_mbps, 3),
                )
            )

        total_gb_with_margin = raw_retention_gb * STORAGE_SAFETY_MARGIN_MULTIPLIER
        required_nominal_tb = max(1, math.ceil(total_gb_with_margin / 1000.0))

        return (
            tuple(breakdowns),
            round(raw_retention_gb, 4),
            round(total_gb_with_margin, 4),
            required_nominal_tb,
        )

    @staticmethod
    def select_optimal_hdd_combination(
        required_nominal_tb: int,
        max_sata_slots: int,
        max_tb_per_slot: int,
        hdd_candidates: Sequence[HddCandidate],
    ) -> tuple[tuple[SelectedHddAllocation, ...], int, int]:
        """Select lowest-cost WD Purple HDD combination within max_sata_slots & max_tb_per_slot."""
        eligible_hdds = [hdd for hdd in hdd_candidates if 0 < hdd.capacity_tb <= max_tb_per_slot]
        if not eligible_hdds:
            raise StorageCapacityExceededError(
                detail="No eligible surveillance HDDs available within recorder slot capacity.",
                errors=[
                    {
                        "required_nominal_tb": required_nominal_tb,
                        "max_sata_slots": max_sata_slots,
                        "max_tb_per_slot": max_tb_per_slot,
                    }
                ],
            )

        best_combo: tuple[HddCandidate, ...] | None = None
        best_sort_key: tuple[int, int, int, tuple[str, ...]] | None = None

        for num_drives in range(1, max_sata_slots + 1):
            for combo in combinations_with_replacement(eligible_hdds, num_drives):
                total_tb = sum(h.capacity_tb for h in combo)
                if total_tb < required_nominal_tb:
                    continue
                total_price_cents = sum(h.sale_price_cents for h in combo)
                sku_tuple = tuple(sorted(h.sku for h in combo))
                # Sort by: 1) lowest price, 2) fewest SATA slots, 3) least excess TB, 4) SKU
                sort_key = (total_price_cents, num_drives, total_tb, sku_tuple)
                if best_sort_key is None or sort_key < best_sort_key:
                    best_sort_key = sort_key
                    best_combo = combo

        if best_combo is None:
            max_possible_tb = max_sata_slots * max(h.capacity_tb for h in eligible_hdds)
            raise StorageCapacityExceededError(
                detail=(
                    f"Required storage ({required_nominal_tb} TB) exceeds recorder capacity "
                    f"({max_possible_tb} TB across {max_sata_slots} SATA slot(s))."
                ),
                errors=[
                    {
                        "required_nominal_tb": required_nominal_tb,
                        "max_sata_slots": max_sata_slots,
                        "max_tb_per_slot": max_tb_per_slot,
                        "max_possible_tb": max_possible_tb,
                    }
                ],
            )

        grouped_counts: dict[str, tuple[HddCandidate, int]] = {}
        for hdd in best_combo:
            if hdd.sku in grouped_counts:
                cand, current_qty = grouped_counts[hdd.sku]
                grouped_counts[hdd.sku] = (cand, current_qty + 1)
            else:
                grouped_counts[hdd.sku] = (hdd, 1)

        allocations: list[SelectedHddAllocation] = []
        for sku in sorted(grouped_counts.keys()):
            cand, qty = grouped_counts[sku]
            allocations.append(
                SelectedHddAllocation(
                    sku=cand.sku,
                    capacity_tb=cand.capacity_tb,
                    quantity=qty,
                    total_capacity_tb=cand.capacity_tb * qty,
                    total_sale_price_cents=cand.sale_price_cents * qty,
                )
            )

        total_selected_tb = sum(a.total_capacity_tb for a in allocations)
        sata_slots_used = sum(a.quantity for a in allocations)
        return tuple(allocations), total_selected_tb, sata_slots_used

    @classmethod
    def execute(
        cls,
        camera_groups: Sequence[CameraGroupInput],
        max_sata_slots: int,
        max_tb_per_slot: int,
        hdd_candidates: Sequence[HddCandidate],
    ) -> StorageCalculationResult:
        """Execute full storage calculation and WD Purple HDD allocation."""
        breakdowns, raw_gb, margin_gb, req_tb = cls.calculate_storage_metrics(camera_groups)
        allocations, total_tb, slots_used = cls.select_optimal_hdd_combination(
            required_nominal_tb=req_tb,
            max_sata_slots=max_sata_slots,
            max_tb_per_slot=max_tb_per_slot,
            hdd_candidates=hdd_candidates,
        )
        return StorageCalculationResult(
            group_breakdowns=breakdowns,
            raw_retention_gb=raw_gb,
            total_required_gb_with_margin=margin_gb,
            required_nominal_tb=req_tb,
            selected_hdds=allocations,
            total_selected_tb=total_tb,
            sata_slots_used=slots_used,
        )


class MHDXHybridTopologyStrategy:
    """Validates Intelbras Multi-HD MHDX hybrid BNC-to-IP conversion and selects optimal DVR/NVR."""

    @staticmethod
    def is_recorder_topology_compatible(
        recorder: RecorderCandidate,
        analog_count: int,
        ip_count: int,
        total_bandwidth_mbps: float,
    ) -> bool:
        """Check if a recorder satisfies BNC, hybrid IP conversion, channels, and bandwidth."""
        total_cameras = analog_count + ip_count
        if total_cameras <= 0:
            return False

        if total_bandwidth_mbps > recorder.max_incoming_bandwidth_mbps:
            return False

        if recorder.is_pure_nvr:
            if analog_count > 0:
                return False
            max_ip_channels = recorder.native_bnc_channels + recorder.extra_ip_channels
            return ip_count <= max_ip_channels

        # Hybrid / Analog DVR (Intelbras MHDX series)
        if analog_count > recorder.native_bnc_channels:
            return False

        converted_bnc_ports = (
            recorder.native_bnc_channels - analog_count
            if recorder.supports_bnc_to_ip_conversion
            else 0
        )
        max_ip_supported = recorder.extra_ip_channels + converted_bnc_ports
        if ip_count > max_ip_supported:
            return False

        total_max_channels = recorder.native_bnc_channels + recorder.extra_ip_channels
        return total_cameras <= total_max_channels

    @classmethod
    def select_optimal_recorder(
        cls,
        camera_groups: Sequence[CameraGroupInput],
        required_nominal_tb: int,
        recorder_candidates: Sequence[RecorderCandidate],
        hdd_candidates: Sequence[HddCandidate],
    ) -> TopologySelectionResult:
        """Select lowest-cost compatible Intelbras MHDX DVR or NVD NVR supporting required TB."""
        if not recorder_candidates:
            raise TopologyIncompatibleError(
                detail="No active DVR/NVR recorders available in the catalog."
            )

        analog_count = sum(g.count for g in camera_groups if g.technology == "ANALOG")
        ip_count = sum(g.count for g in camera_groups if g.technology == "IP")
        total_cameras = analog_count + ip_count

        total_kbps = sum(
            g.count * get_bitrate_kbps(g.resolution, g.fps, g.codec) for g in camera_groups
        )
        total_bandwidth_mbps = round(total_kbps / 1000.0, 3)

        topology_compatible = [
            rec
            for rec in recorder_candidates
            if cls.is_recorder_topology_compatible(
                recorder=rec,
                analog_count=analog_count,
                ip_count=ip_count,
                total_bandwidth_mbps=total_bandwidth_mbps,
            )
        ]

        if not topology_compatible:
            raise TopologyIncompatibleError(
                detail=(
                    f"No recorder supports {analog_count} analog + {ip_count} IP cameras "
                    f"({total_cameras} total channels) at {total_bandwidth_mbps} Mbps."
                ),
                errors=[
                    {
                        "analog_cameras": analog_count,
                        "ip_cameras": ip_count,
                        "total_cameras": total_cameras,
                        "total_bandwidth_mbps": total_bandwidth_mbps,
                    }
                ],
            )

        max_available_hdd_tb = max(
            (h.capacity_tb for h in hdd_candidates),
            default=0,
        )

        storage_and_topology_compatible: list[RecorderCandidate] = []
        for rec in topology_compatible:
            effective_slot_tb = min(rec.max_tb_per_slot, max_available_hdd_tb)
            if rec.max_sata_slots * effective_slot_tb >= required_nominal_tb:
                storage_and_topology_compatible.append(rec)

        if not storage_and_topology_compatible:
            max_possible_tb = max(
                rec.max_sata_slots * min(rec.max_tb_per_slot, max_available_hdd_tb)
                for rec in topology_compatible
            )
            raise StorageCapacityExceededError(
                detail=(
                    f"Required storage ({required_nominal_tb} TB) exceeds maximum capacity "
                    f"({max_possible_tb} TB) of all topology-compatible recorders."
                ),
                errors=[
                    {
                        "required_nominal_tb": required_nominal_tb,
                        "max_possible_tb": max_possible_tb,
                        "analog_cameras": analog_count,
                        "ip_cameras": ip_count,
                    }
                ],
            )

        def _recorder_sort_key(rec: RecorderCandidate) -> tuple[int, int, int, str]:
            # Pure IP systems prefer pure NVR if cheaper or equal; lowest sale_price_cents wins
            pure_nvr_preference = (
                0 if (analog_count == 0 and ip_count > 0 and rec.is_pure_nvr) else 1
            )
            total_cap = rec.native_bnc_channels + rec.extra_ip_channels
            return (rec.sale_price_cents, pure_nvr_preference, total_cap, rec.sku)

        chosen = min(storage_and_topology_compatible, key=_recorder_sort_key)

        if chosen.is_pure_nvr:
            bnc_used = 0
            bnc_converted = 0
            total_supported = chosen.native_bnc_channels + chosen.extra_ip_channels
        else:
            bnc_used = analog_count
            bnc_converted = max(0, ip_count - chosen.extra_ip_channels)
            total_supported = chosen.native_bnc_channels + chosen.extra_ip_channels

        utilization_pct = round((total_cameras / total_supported) * 100.0, 2)

        return TopologySelectionResult(
            selected_recorder_sku=chosen.sku,
            is_pure_nvr=chosen.is_pure_nvr,
            analog_cameras_count=analog_count,
            ip_cameras_count=ip_count,
            total_cameras_count=total_cameras,
            native_bnc_channels=chosen.native_bnc_channels,
            extra_ip_channels=chosen.extra_ip_channels,
            bnc_channels_used_by_analog=bnc_used,
            bnc_channels_converted_to_ip=bnc_converted,
            total_supported_channels=total_supported,
            channel_utilization_percent=utilization_pct,
            total_incoming_bandwidth_mbps=total_bandwidth_mbps,
            max_incoming_bandwidth_mbps=chosen.max_incoming_bandwidth_mbps,
            max_sata_slots=chosen.max_sata_slots,
            max_tb_per_slot=chosen.max_tb_per_slot,
        )


class ElectricalAndBomStrategy:
    """Computes 12V current draw, PoE budget, copper voltage drop, and auto-derived BOM items."""

    @staticmethod
    def get_conductor_resistance_ohm_per_meter(cabling_mode: CablingModeLiteral) -> float:
        """Return reference copper resistance per meter (Ohm/m) at 20°C."""
        if cabling_mode == "COAXIAL":
            return RESISTANCE_COAX_BIPOLAR_OHM_M
        if cabling_mode == "UTP_CAT6":
            return RESISTANCE_CAT6_SINGLE_OHM_M
        return RESISTANCE_CAT5E_SINGLE_OHM_M

    @classmethod
    def compute_voltage_drop(
        cls,
        distance_meters: float,
        current_amps: float,
        cabling_mode: CablingModeLiteral,
        source_voltage_vdc: float = NOMINAL_SOURCE_VOLTAGE_VDC,
    ) -> tuple[float, float, float]:
        """Compute round-trip copper voltage drop: delta_V = 2 * L * I * R_meter."""
        r_meter = cls.get_conductor_resistance_ohm_per_meter(cabling_mode)
        delta_v = 2.0 * distance_meters * current_amps * r_meter
        v_load = source_voltage_vdc - delta_v
        return round(r_meter, 4), round(delta_v, 2), round(v_load, 2)

    @staticmethod
    def select_power_supplies(
        required_current_amps: float,
        psu_candidates: Sequence[PowerSupplyCandidate],
    ) -> tuple[SelectedEquipmentQuantity, ...]:
        """Select lowest-cost 12V switching PSU combination satisfying required_current_amps."""
        if required_current_amps <= 0:
            return ()
        if not psu_candidates:
            raise DomainValidationError(
                detail="No active 12V POWER_SUPPLY items available in the catalog."
            )

        # Single unit check first, otherwise multi-unit combinations up to 4 PSUs
        best_combo: tuple[PowerSupplyCandidate, ...] | None = None
        best_key: tuple[int, int, int, tuple[str, ...]] | None = None

        for count in range(1, 5):
            for combo in combinations_with_replacement(psu_candidates, count):
                total_amps = sum(p.max_current_amps for p in combo)
                if total_amps < required_current_amps:
                    continue
                total_price = sum(p.sale_price_cents for p in combo)
                skus = tuple(sorted(p.sku for p in combo))
                key = (total_price, count, total_amps, skus)
                if best_key is None or key < best_key:
                    best_key = key
                    best_combo = combo

        if best_combo is None:
            largest_psu = max(psu_candidates, key=lambda p: p.max_current_amps)
            qty = math.ceil(required_current_amps / largest_psu.max_current_amps)
            return (
                SelectedEquipmentQuantity(
                    sku=largest_psu.sku,
                    quantity=qty,
                    capacity_per_unit=float(largest_psu.max_current_amps),
                    sale_price_cents=largest_psu.sale_price_cents,
                ),
            )

        grouped: dict[str, tuple[PowerSupplyCandidate, int]] = {}
        for psu in best_combo:
            if psu.sku in grouped:
                cand, q = grouped[psu.sku]
                grouped[psu.sku] = (cand, q + 1)
            else:
                grouped[psu.sku] = (psu, 1)

        return tuple(
            SelectedEquipmentQuantity(
                sku=cand.sku,
                quantity=q,
                capacity_per_unit=float(cand.max_current_amps),
                sale_price_cents=cand.sale_price_cents,
            )
            for _, (cand, q) in sorted(grouped.items())
        )

    @staticmethod
    def select_poe_switches(
        required_ports: int,
        required_watts: float,
        poe_candidates: Sequence[PoeSwitchCandidate],
    ) -> tuple[SelectedEquipmentQuantity, ...]:
        """Select lowest-cost PoE switch combination satisfying both ports and wattage budget."""
        if required_ports <= 0:
            return ()
        if not poe_candidates:
            raise DomainValidationError(
                detail="No active POE_SWITCH items available in the catalog."
            )

        best_combo: tuple[PoeSwitchCandidate, ...] | None = None
        best_key: tuple[int, int, int, tuple[str, ...]] | None = None

        for count in range(1, 5):
            for combo in combinations_with_replacement(poe_candidates, count):
                total_ports = sum(sw.poe_ports for sw in combo)
                total_watts = sum(sw.total_poe_budget_watts for sw in combo)
                if total_ports < required_ports or total_watts < required_watts:
                    continue
                total_price = sum(sw.sale_price_cents for sw in combo)
                skus = tuple(sorted(sw.sku for sw in combo))
                key = (total_price, count, total_ports, skus)
                if best_key is None or key < best_key:
                    best_key = key
                    best_combo = combo

        if best_combo is None:
            largest_sw = max(poe_candidates, key=lambda s: (s.poe_ports, s.total_poe_budget_watts))
            qty_by_ports = math.ceil(required_ports / largest_sw.poe_ports)
            qty_by_watts = math.ceil(required_watts / largest_sw.total_poe_budget_watts)
            qty = max(qty_by_ports, qty_by_watts)
            return (
                SelectedEquipmentQuantity(
                    sku=largest_sw.sku,
                    quantity=qty,
                    capacity_per_unit=float(largest_sw.poe_ports),
                    sale_price_cents=largest_sw.sale_price_cents,
                ),
            )

        grouped: dict[str, tuple[PoeSwitchCandidate, int]] = {}
        for sw in best_combo:
            if sw.sku in grouped:
                cand, q = grouped[sw.sku]
                grouped[sw.sku] = (cand, q + 1)
            else:
                grouped[sw.sku] = (sw, 1)

        return tuple(
            SelectedEquipmentQuantity(
                sku=cand.sku,
                quantity=q,
                capacity_per_unit=float(cand.poe_ports),
                sale_price_cents=cand.sale_price_cents,
            )
            for _, (cand, q) in sorted(grouped.items())
        )

    @classmethod
    def execute(
        cls,
        camera_groups: Sequence[CameraGroupInput],
        topology: TopologySelectionResult,
        storage: StorageCalculationResult,
        psu_candidates: Sequence[PowerSupplyCandidate],
        poe_candidates: Sequence[PoeSwitchCandidate],
        utp_roll_length_meters: int = 305,
        coax_roll_length_meters: int = 100,
    ) -> ElectricalAndBomResult:
        """Compute electrical load, voltage drops, and full deterministic auto-BOM."""
        analog_raw_amps = 0.0
        ip_raw_watts = 0.0
        warnings: list[VoltageDropWarning] = []

        balun_pairs_qty = 0
        bnc_connectors_qty = 0
        p4_connectors_qty = 0
        rj45_connectors_qty = 0
        junction_boxes_qty = 0

        analog_utp_raw_meters = 0.0
        coax_raw_meters = 0.0
        ip_utp_raw_meters = 0.0

        for group in camera_groups:
            if group.average_cable_meters <= 0:
                raise DomainValidationError(
                    detail=f"Camera group '{group.group_label}' must have average_cable_meters > 0."
                )

            junction_boxes_qty += group.count

            if group.technology == "ANALOG":
                cam_ma = (
                    group.ir_current_draw_ma
                    if group.ir_current_draw_ma is not None
                    else DEFAULT_ANALOG_CURRENT_MA[group.resolution]
                )
                cam_amps = cam_ma / 1000.0
                analog_raw_amps += group.count * cam_amps

                r_meter, delta_v, v_load = cls.compute_voltage_drop(
                    distance_meters=group.average_cable_meters,
                    current_amps=cam_amps,
                    cabling_mode=group.cabling_mode,
                )
                if v_load < MIN_OPERATING_VOLTAGE_VDC:
                    warnings.append(
                        VoltageDropWarning(
                            group_label=group.group_label,
                            cabling_mode=group.cabling_mode,
                            distance_meters=group.average_cable_meters,
                            current_amps=round(cam_amps, 3),
                            resistance_ohm_per_meter=r_meter,
                            voltage_drop_volts=delta_v,
                            voltage_at_load_volts=v_load,
                            min_operating_voltage_volts=MIN_OPERATING_VOLTAGE_VDC,
                            recommendation_pt_br=(
                                f"Queda de tensão crítica ({delta_v:.2f}V -> {v_load:.2f}V "
                                f"< 10.8V) em {group.average_cable_meters:.0f}m. "
                                "Recomenda-se par UTP duplo em paralelo, fonte ajustável "
                                "MCM 12.8V/13.8V ou fonte local próxima às câmeras."
                            ),
                        )
                    )

                p4_connectors_qty += group.count
                if group.cabling_mode == "COAXIAL":
                    bnc_connectors_qty += group.count * 2
                    coax_raw_meters += group.count * group.average_cable_meters
                else:
                    balun_pairs_qty += group.count
                    analog_utp_raw_meters += group.count * group.average_cable_meters
            else:
                cam_watts = (
                    group.poe_power_watts
                    if group.poe_power_watts is not None
                    else DEFAULT_IP_POWER_WATTS[group.resolution]
                )
                ip_raw_watts += group.count * cam_watts
                rj45_connectors_qty += group.count * 2
                ip_utp_raw_meters += group.count * group.average_cable_meters

        analog_req_amps = round(analog_raw_amps * CURRENT_HEADROOM_MULTIPLIER, 2)
        selected_psus = cls.select_power_supplies(analog_req_amps, psu_candidates)

        ip_req_watts = round(ip_raw_watts * POE_HEADROOM_MULTIPLIER, 2)
        selected_poe = cls.select_poe_switches(
            required_ports=topology.ip_cameras_count,
            required_watts=ip_req_watts,
            poe_candidates=poe_candidates,
        )

        analog_utp_meters = (
            math.ceil(analog_utp_raw_meters * CABLE_SLACK_MULTIPLIER)
            if analog_utp_raw_meters > 0
            else 0
        )
        ip_utp_meters = (
            math.ceil(ip_utp_raw_meters * CABLE_SLACK_MULTIPLIER) if ip_utp_raw_meters > 0 else 0
        )
        total_utp_meters = analog_utp_meters + ip_utp_meters
        utp_boxes = (
            math.ceil(total_utp_meters / utp_roll_length_meters) if total_utp_meters > 0 else 0
        )

        coax_meters = (
            math.ceil(coax_raw_meters * CABLE_SLACK_MULTIPLIER) if coax_raw_meters > 0 else 0
        )
        coax_rolls = math.ceil(coax_meters / coax_roll_length_meters) if coax_meters > 0 else 0

        derived_bom: list[DerivedBomRequirement] = [
            DerivedBomRequirement(
                role="RECORDER",
                quantity=1,
                is_auto_derived=True,
                sku_hint=topology.selected_recorder_sku,
                notes_pt_br=(
                    f"Gravador selecionado ({topology.total_cameras_count}/"
                    f"{topology.total_supported_channels} canais utilizados)"
                ),
            )
        ]

        # Camera groups (explicitly requested by user -> is_auto_derived=False)
        for group in camera_groups:
            derived_bom.append(
                DerivedBomRequirement(
                    role="CAMERA_ANALOG" if group.technology == "ANALOG" else "CAMERA_IP",
                    quantity=group.count,
                    is_auto_derived=False,
                    resolution_hint=group.resolution,
                    form_factor_hint=group.form_factor,
                    notes_pt_br=(
                        f"Grupo: {group.group_label} ({group.resolution} @ {group.fps} FPS)"
                    ),
                )
            )

        # Surveillance HDDs
        for hdd_alloc in storage.selected_hdds:
            derived_bom.append(
                DerivedBomRequirement(
                    role="HDD",
                    quantity=hdd_alloc.quantity,
                    is_auto_derived=True,
                    sku_hint=hdd_alloc.sku,
                    notes_pt_br=(
                        f"Armazenamento CFTV 24x7 ({hdd_alloc.total_capacity_tb} TB nominal)"
                    ),
                )
            )

        # 12V Power Supplies
        for psu_alloc in selected_psus:
            derived_bom.append(
                DerivedBomRequirement(
                    role="POWER_SUPPLY",
                    quantity=psu_alloc.quantity,
                    is_auto_derived=True,
                    sku_hint=psu_alloc.sku,
                    notes_pt_br=(
                        f"Alimentação 12V CFTV (Carga c/ 30% folga: {analog_req_amps:.2f}A)"
                    ),
                )
            )

        # PoE Switches
        for poe_alloc in selected_poe:
            derived_bom.append(
                DerivedBomRequirement(
                    role="POE_SWITCH",
                    quantity=poe_alloc.quantity,
                    is_auto_derived=True,
                    sku_hint=poe_alloc.sku,
                    notes_pt_br=f"Alimentação e Rede PoE ({ip_req_watts:.1f}W c/ 25% folga)",
                )
            )

        if balun_pairs_qty > 0:
            derived_bom.append(
                DerivedBomRequirement(
                    role="BALUN",
                    quantity=balun_pairs_qty,
                    is_auto_derived=True,
                    sub_type_hint="PASSIVE_BALUN_PAIR",
                    notes_pt_br="1x Par de Vídeo Balun Passivo por câmera analógica em UTP",
                )
            )

        if bnc_connectors_qty > 0:
            derived_bom.append(
                DerivedBomRequirement(
                    role="CONNECTOR_BNC",
                    quantity=bnc_connectors_qty,
                    is_auto_derived=True,
                    sub_type_hint="CONNECTOR_BNC_MALE",
                    notes_pt_br="2x Conectores BNC Macho por câmera analógica em cabo coaxial",
                )
            )

        if p4_connectors_qty > 0:
            derived_bom.append(
                DerivedBomRequirement(
                    role="CONNECTOR_P4",
                    quantity=p4_connectors_qty,
                    is_auto_derived=True,
                    sub_type_hint="CONNECTOR_P4_MALE",
                    notes_pt_br="1x Conector P4 Macho de alimentação por câmera analógica",
                )
            )

        if rj45_connectors_qty > 0:
            derived_bom.append(
                DerivedBomRequirement(
                    role="CONNECTOR_RJ45",
                    quantity=rj45_connectors_qty,
                    is_auto_derived=True,
                    sub_type_hint="CONNECTOR_RJ45",
                    notes_pt_br="2x Conectores RJ45 por câmera IP",
                )
            )

        if junction_boxes_qty > 0:
            derived_bom.append(
                DerivedBomRequirement(
                    role="JUNCTION_BOX",
                    quantity=junction_boxes_qty,
                    is_auto_derived=True,
                    sub_type_hint="JUNCTION_BOX_VBOX",
                    notes_pt_br="1x Caixa de passagem e acabamento VBOX por câmera",
                )
            )

        if coax_rolls > 0:
            derived_bom.append(
                DerivedBomRequirement(
                    role="CABLE_COAXIAL",
                    quantity=coax_rolls,
                    is_auto_derived=True,
                    cable_type_hint="COAXIAL_BIPOLAR_4MM",
                    notes_pt_br=(
                        f"{coax_meters}m estimados (c/ 15% folga) -> {coax_rolls} rolo(s) de 100m"
                    ),
                )
            )

        if utp_boxes > 0:
            derived_bom.append(
                DerivedBomRequirement(
                    role="CABLE_UTP",
                    quantity=utp_boxes,
                    is_auto_derived=True,
                    cable_type_hint="UTP_CAT5E",
                    notes_pt_br=(
                        f"{total_utp_meters}m estimados (c/ 15% folga) -> "
                        f"{utp_boxes} caixa(s) de 305m"
                    ),
                )
            )

        if topology.total_cameras_count > 0:
            derived_bom.append(
                DerivedBomRequirement(
                    role="LABOR",
                    quantity=topology.total_cameras_count,
                    is_auto_derived=True,
                    sub_type_hint="LABOR_POINT_INSTALL",
                    notes_pt_br="1x Ponto de instalação técnica por câmera",
                )
            )

        return ElectricalAndBomResult(
            analog_raw_current_amps=round(analog_raw_amps, 2),
            analog_required_current_amps_with_headroom=analog_req_amps,
            selected_power_supplies=selected_psus,
            ip_raw_power_watts=round(ip_raw_watts, 2),
            ip_required_poe_watts_with_headroom=ip_req_watts,
            selected_poe_switches=selected_poe,
            voltage_drop_warnings=tuple(warnings),
            coaxial_cable_meters_with_slack=coax_meters,
            coaxial_cable_rolls_100m=coax_rolls,
            utp_cable_meters_with_slack=total_utp_meters,
            utp_cable_boxes_305m=utp_boxes,
            derived_bom=tuple(derived_bom),
        )
