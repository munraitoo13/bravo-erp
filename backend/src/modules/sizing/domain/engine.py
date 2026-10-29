"""Pure domain orchestrator for the CCTV Engineering & Sizing Engine."""

from collections.abc import Sequence

from src.modules.sizing.domain.strategies import (
    ElectricalAndBomStrategy,
    MHDXHybridTopologyStrategy,
    StorageCalculationStrategy,
)
from src.modules.sizing.domain.value_objects import (
    HddCandidate,
    PoeSwitchCandidate,
    PowerSupplyCandidate,
    RecorderCandidate,
    SizingEngineInput,
    SizingEngineResult,
    StorageCalculationResult,
)


class CCTVSizingEngine:
    """Stateless pure Python orchestrator executing Storage, MHDX Topology, and Electrical rules."""

    @staticmethod
    def calculate(
        engine_input: SizingEngineInput,
        recorder_candidates: Sequence[RecorderCandidate],
        hdd_candidates: Sequence[HddCandidate],
        psu_candidates: Sequence[PowerSupplyCandidate],
        poe_candidates: Sequence[PoeSwitchCandidate],
        utp_roll_length_meters: int = 305,
        coax_roll_length_meters: int = 100,
    ) -> SizingEngineResult:
        """Execute end-to-end CCTV engineering calculations and derive optimal equipment BOM."""
        # 1. Calculate storage requirement metrics (GB/day, retention GB, 15% safety margin, TB)
        breakdowns, raw_gb, margin_gb, required_nominal_tb = (
            StorageCalculationStrategy.calculate_storage_metrics(engine_input.camera_groups)
        )

        # 2. Select optimal Intelbras MHDX / NVD recorder supporting channel topology and SATA bays
        topology = MHDXHybridTopologyStrategy.select_optimal_recorder(
            camera_groups=engine_input.camera_groups,
            required_nominal_tb=required_nominal_tb,
            recorder_candidates=recorder_candidates,
            hdd_candidates=hdd_candidates,
        )

        # 3. Select optimal WD Purple HDD combination constrained by the chosen recorder's SATA bays
        selected_hdds, total_selected_tb, sata_slots_used = (
            StorageCalculationStrategy.select_optimal_hdd_combination(
                required_nominal_tb=required_nominal_tb,
                max_sata_slots=topology.max_sata_slots,
                max_tb_per_slot=topology.max_tb_per_slot,
                hdd_candidates=hdd_candidates,
            )
        )
        storage = StorageCalculationResult(
            group_breakdowns=breakdowns,
            raw_retention_gb=raw_gb,
            total_required_gb_with_margin=margin_gb,
            required_nominal_tb=required_nominal_tb,
            selected_hdds=selected_hdds,
            total_selected_tb=total_selected_tb,
            sata_slots_used=sata_slots_used,
        )

        # 4. Compute electrical load, copper cable voltage drops, and deterministic BOM items
        electrical_and_bom = ElectricalAndBomStrategy.execute(
            camera_groups=engine_input.camera_groups,
            topology=topology,
            storage=storage,
            psu_candidates=psu_candidates,
            poe_candidates=poe_candidates,
            utp_roll_length_meters=utp_roll_length_meters,
            coax_roll_length_meters=coax_roll_length_meters,
        )

        return SizingEngineResult(
            topology=topology,
            storage=storage,
            electrical_and_bom=electrical_and_bom,
        )
