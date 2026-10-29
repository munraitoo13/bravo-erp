"""100% branch-coverage unit tests for the pure CCTV Engineering & Sizing Engine."""

from typing import cast

import pytest

from src.core.exceptions import (
    DomainValidationError,
    StorageCapacityExceededError,
    TopologyIncompatibleError,
)
from src.modules.sizing.domain.bitrate_table import BITRATE_LOOKUP_KBPS, get_bitrate_kbps
from src.modules.sizing.domain.engine import CCTVSizingEngine
from src.modules.sizing.domain.strategies import (
    ElectricalAndBomStrategy,
    MHDXHybridTopologyStrategy,
    StorageCalculationStrategy,
)
from src.modules.sizing.domain.value_objects import (
    CameraGroupInput,
    CodecLiteral,
    FpsLiteral,
    HddCandidate,
    PoeSwitchCandidate,
    PowerSupplyCandidate,
    RecorderCandidate,
    ResolutionLiteral,
    SizingEngineInput,
)


def _sample_recorders() -> tuple[RecorderCandidate, ...]:
    """Provide reference Intelbras MHDX and NVD recorder candidates."""
    return (
        RecorderCandidate(
            sku="MHDX-1104",
            native_bnc_channels=4,
            extra_ip_channels=2,
            supports_bnc_to_ip_conversion=True,
            max_sata_slots=1,
            max_tb_per_slot=16,
            max_incoming_bandwidth_mbps=24,
            supported_codecs=("H.264", "H.265", "H.265+"),
            is_pure_nvr=False,
            sale_price_cents=64900,
        ),
        RecorderCandidate(
            sku="MHDX-1108",
            native_bnc_channels=8,
            extra_ip_channels=2,
            supports_bnc_to_ip_conversion=True,
            max_sata_slots=1,
            max_tb_per_slot=16,
            max_incoming_bandwidth_mbps=48,
            supported_codecs=("H.264", "H.265", "H.265+"),
            is_pure_nvr=False,
            sale_price_cents=89900,
        ),
        RecorderCandidate(
            sku="MHDX-1116",
            native_bnc_channels=16,
            extra_ip_channels=4,
            supports_bnc_to_ip_conversion=True,
            max_sata_slots=1,
            max_tb_per_slot=16,
            max_incoming_bandwidth_mbps=96,
            supported_codecs=("H.264", "H.265", "H.265+"),
            is_pure_nvr=False,
            sale_price_cents=149900,
        ),
        RecorderCandidate(
            sku="MHDX-3116",
            native_bnc_channels=16,
            extra_ip_channels=8,
            supports_bnc_to_ip_conversion=True,
            max_sata_slots=2,
            max_tb_per_slot=16,
            max_incoming_bandwidth_mbps=128,
            supported_codecs=("H.264", "H.265", "H.265+"),
            is_pure_nvr=False,
            sale_price_cents=239900,
        ),
        RecorderCandidate(
            sku="NVD-1408",
            native_bnc_channels=8,
            extra_ip_channels=0,
            supports_bnc_to_ip_conversion=False,
            max_sata_slots=1,
            max_tb_per_slot=16,
            max_incoming_bandwidth_mbps=80,
            supported_codecs=("H.264", "H.265", "H.265+"),
            is_pure_nvr=True,
            sale_price_cents=94900,
        ),
        RecorderCandidate(
            sku="NVD-3316-P",
            native_bnc_channels=16,
            extra_ip_channels=0,
            supports_bnc_to_ip_conversion=False,
            max_sata_slots=2,
            max_tb_per_slot=16,
            max_incoming_bandwidth_mbps=160,
            supported_codecs=("H.264", "H.265", "H.265+"),
            is_pure_nvr=True,
            sale_price_cents=289000,
        ),
    )


def _sample_hdds() -> tuple[HddCandidate, ...]:
    """Provide reference WD Purple surveillance HDD candidates."""
    return (
        HddCandidate(sku="WD10PURZ", capacity_tb=1, usable_capacity_gb=931, sale_price_cents=44900),
        HddCandidate(
            sku="WD20PURZ", capacity_tb=2, usable_capacity_gb=1862, sale_price_cents=59900
        ),
        HddCandidate(
            sku="WD42PURZ", capacity_tb=4, usable_capacity_gb=3725, sale_price_cents=96900
        ),
        HddCandidate(
            sku="WD84PURZ", capacity_tb=8, usable_capacity_gb=7450, sale_price_cents=189900
        ),
    )


def _sample_psus() -> tuple[PowerSupplyCandidate, ...]:
    """Provide reference MCM 12.8V switching power supply candidates."""
    return (
        PowerSupplyCandidate(
            sku="FONTE-MCM-5A", output_voltage_vdc=12.8, max_current_amps=5, sale_price_cents=7500
        ),
        PowerSupplyCandidate(
            sku="FONTE-MCM-10A",
            output_voltage_vdc=12.8,
            max_current_amps=10,
            sale_price_cents=11900,
        ),
        PowerSupplyCandidate(
            sku="FONTE-MCM-20A",
            output_voltage_vdc=12.8,
            max_current_amps=20,
            sale_price_cents=18900,
        ),
    )


def _sample_poe_switches() -> tuple[PoeSwitchCandidate, ...]:
    """Provide reference Intelbras PoE switch candidates."""
    return (
        PoeSwitchCandidate(
            sku="SF-500-POE", poe_ports=4, total_poe_budget_watts=58.0, sale_price_cents=31900
        ),
        PoeSwitchCandidate(
            sku="SF-900-POE", poe_ports=8, total_poe_budget_watts=92.0, sale_price_cents=52900
        ),
        PoeSwitchCandidate(
            sku="S-1124G-PA", poe_ports=24, total_poe_budget_watts=240.0, sale_price_cents=149900
        ),
    )


def test_bitrate_lookup_table_completeness_and_invalid_key_rejection() -> None:
    """Verify all 36 (Resolution x FPS x Codec) entries exist and invalid keys fail."""
    assert len(BITRATE_LOOKUP_KBPS) == 36
    assert get_bitrate_kbps("720p", 15, "H.265+") == 358
    assert get_bitrate_kbps("1080p", 30, "H.265+") == 1434
    assert get_bitrate_kbps("4MP", 30, "H.265") == 3379
    assert get_bitrate_kbps("4K", 30, "H.264") == 10240

    with pytest.raises(DomainValidationError) as exc_info:
        get_bitrate_kbps(
            cast(ResolutionLiteral, "8K"),
            cast(FpsLiteral, 60),
            cast(CodecLiteral, "AV1"),
        )
    assert exc_info.value.http_status == 422


def test_storage_calculation_formula_and_wd_purple_combination_selector() -> None:
    """Verify daily GB formula, 15% safety margin, and multi-drive WD Purple combinations."""
    # 1080p @ 30fps H.265+ = 1434 kbps
    # Daily GB = (1434 * 3600 * 24) / (8 * 1024 * 1024) = 14.769744873046875 GB/day
    daily_gb = StorageCalculationStrategy.compute_daily_gb_per_camera(1434, 24.0)
    assert abs(daily_gb - 14.769744873046875) < 1e-9

    # 8 cameras * 14.769744873... * 30 days = 3544.7388 GB raw
    # With 1.15 safety margin = 4076.4496 GB -> ceil(4076.45 / 1000) = 5 TB nominal
    group = CameraGroupInput(
        group_label="Perímetro Full HD",
        technology="ANALOG",
        count=8,
        resolution="1080p",
        fps=30,
        codec="H.265+",
        retention_days=30,
    )
    res = StorageCalculationStrategy.execute(
        camera_groups=(group,),
        max_sata_slots=1,
        max_tb_per_slot=16,
        hdd_candidates=_sample_hdds(),
    )
    assert res.required_nominal_tb == 5
    # With 1 SATA slot, must select 1x WD84PURZ (8TB) because 4TB < 5TB
    assert len(res.selected_hdds) == 1
    assert res.selected_hdds[0].sku == "WD84PURZ"
    assert res.selected_hdds[0].quantity == 1
    assert res.total_selected_tb == 8
    assert res.sata_slots_used == 1

    # When 2 SATA slots are available and 12 TB is required -> 1x 8TB + 1x 4TB = 12TB
    allocs_12tb, total_12tb, slots_12tb = StorageCalculationStrategy.select_optimal_hdd_combination(
        required_nominal_tb=12,
        max_sata_slots=2,
        max_tb_per_slot=16,
        hdd_candidates=_sample_hdds(),
    )
    assert total_12tb == 12
    assert slots_12tb == 2
    skus_12tb = {a.sku: a.quantity for a in allocs_12tb}
    assert skus_12tb == {"WD42PURZ": 1, "WD84PURZ": 1}

    # When 16 TB is required on 2 SATA slots -> 2x WD84PURZ (8TB each)
    allocs_16tb, total_16tb, slots_16tb = StorageCalculationStrategy.select_optimal_hdd_combination(
        required_nominal_tb=16,
        max_sata_slots=2,
        max_tb_per_slot=16,
        hdd_candidates=_sample_hdds(),
    )
    assert total_16tb == 16
    assert slots_16tb == 2
    assert len(allocs_16tb) == 1
    assert allocs_16tb[0].sku == "WD84PURZ"
    assert allocs_16tb[0].quantity == 2


def test_storage_validation_and_capacity_exceeded_errors() -> None:
    """Verify validation guards on invalid hours, camera count, retention days, and HDD capacity."""
    with pytest.raises(DomainValidationError):
        StorageCalculationStrategy.compute_daily_gb_per_camera(1434, 0.0)

    with pytest.raises(DomainValidationError):
        StorageCalculationStrategy.compute_daily_gb_per_camera(1434, 25.0)

    with pytest.raises(DomainValidationError):
        StorageCalculationStrategy.calculate_storage_metrics(())

    with pytest.raises(DomainValidationError):
        StorageCalculationStrategy.calculate_storage_metrics(
            (
                CameraGroupInput(
                    group_label="Zero Count",
                    technology="ANALOG",
                    count=0,
                    resolution="720p",
                    fps=15,
                    codec="H.265+",
                    retention_days=7,
                ),
            )
        )

    with pytest.raises(DomainValidationError):
        StorageCalculationStrategy.calculate_storage_metrics(
            (
                CameraGroupInput(
                    group_label="Zero Retention",
                    technology="ANALOG",
                    count=2,
                    resolution="720p",
                    fps=15,
                    codec="H.265+",
                    retention_days=0,
                ),
            )
        )

    # No HDDs fit max_tb_per_slot=0
    with pytest.raises(StorageCapacityExceededError):
        StorageCalculationStrategy.select_optimal_hdd_combination(
            required_nominal_tb=2,
            max_sata_slots=1,
            max_tb_per_slot=0,
            hdd_candidates=_sample_hdds(),
        )

    # 20 TB requested on 1-SATA DVR where max HDD is 8 TB
    with pytest.raises(StorageCapacityExceededError):
        StorageCalculationStrategy.select_optimal_hdd_combination(
            required_nominal_tb=20,
            max_sata_slots=1,
            max_tb_per_slot=16,
            hdd_candidates=_sample_hdds(),
        )


def test_mhdx_hybrid_bnc_to_ip_channel_conversion_and_nvr_selection() -> None:
    """Verify SPEC.md Section 3.2: 7 Analog + 3 IP selects MHDX-1108 via 1 converted BNC port."""
    groups_7a_3ip = (
        CameraGroupInput(
            group_label="7x Analógicas BNC",
            technology="ANALOG",
            count=7,
            resolution="1080p",
            fps=30,
            codec="H.265+",
            retention_days=15,
        ),
        CameraGroupInput(
            group_label="3x IP PoE",
            technology="IP",
            count=3,
            resolution="1080p",
            fps=30,
            codec="H.265+",
            retention_days=15,
        ),
    )

    topology = MHDXHybridTopologyStrategy.select_optimal_recorder(
        camera_groups=groups_7a_3ip,
        required_nominal_tb=2,
        recorder_candidates=_sample_recorders(),
        hdd_candidates=_sample_hdds(),
    )
    assert topology.selected_recorder_sku == "MHDX-1108"
    assert topology.analog_cameras_count == 7
    assert topology.ip_cameras_count == 3
    assert topology.total_cameras_count == 10
    assert topology.bnc_channels_used_by_analog == 7
    assert topology.bnc_channels_converted_to_ip == 1
    assert topology.total_supported_channels == 10
    assert topology.channel_utilization_percent == 100.0

    # When storage requires 12 TB (exceeds 1x 8TB slot on MHDX-1108/1116),
    # automatically upgrades to MHDX-3116 (2 SATA slots)!
    topology_multi_sata = MHDXHybridTopologyStrategy.select_optimal_recorder(
        camera_groups=groups_7a_3ip,
        required_nominal_tb=12,
        recorder_candidates=_sample_recorders(),
        hdd_candidates=_sample_hdds(),
    )
    assert topology_multi_sata.selected_recorder_sku == "MHDX-3116"
    assert topology_multi_sata.max_sata_slots == 2

    # Pure IP system (8x IP cameras) when pure NVR is cheapest
    nvr_only_candidates = (
        RecorderCandidate(
            sku="NVD-1408",
            native_bnc_channels=8,
            extra_ip_channels=0,
            supports_bnc_to_ip_conversion=False,
            max_sata_slots=1,
            max_tb_per_slot=16,
            max_incoming_bandwidth_mbps=80,
            supported_codecs=("H.264", "H.265", "H.265+"),
            is_pure_nvr=True,
            sale_price_cents=85000,
        ),
        RecorderCandidate(
            sku="MHDX-1108",
            native_bnc_channels=8,
            extra_ip_channels=2,
            supports_bnc_to_ip_conversion=True,
            max_sata_slots=1,
            max_tb_per_slot=16,
            max_incoming_bandwidth_mbps=48,
            supported_codecs=("H.264", "H.265", "H.265+"),
            is_pure_nvr=False,
            sale_price_cents=85000,
        ),
    )
    pure_ip_group = (
        CameraGroupInput(
            group_label="8x IP PoE",
            technology="IP",
            count=8,
            resolution="1080p",
            fps=30,
            codec="H.265+",
            retention_days=15,
        ),
    )
    pure_ip_top = MHDXHybridTopologyStrategy.select_optimal_recorder(
        camera_groups=pure_ip_group,
        required_nominal_tb=2,
        recorder_candidates=nvr_only_candidates,
        hdd_candidates=_sample_hdds(),
    )
    assert pure_ip_top.selected_recorder_sku == "NVD-1408"
    assert pure_ip_top.is_pure_nvr is True
    assert pure_ip_top.bnc_channels_used_by_analog == 0
    assert pure_ip_top.bnc_channels_converted_to_ip == 0


def test_topology_compatibility_edge_cases_and_errors() -> None:
    """Verify topology rejection for zero cameras, bandwidth, non-convertible BNC, and storage."""
    non_hybrid_dvr = RecorderCandidate(
        sku="LEGACY-DVR-04",
        native_bnc_channels=4,
        extra_ip_channels=1,
        supports_bnc_to_ip_conversion=False,
        max_sata_slots=1,
        max_tb_per_slot=8,
        max_incoming_bandwidth_mbps=16,
        supported_codecs=("H.264",),
        is_pure_nvr=False,
        sale_price_cents=40000,
    )
    # Zero cameras -> False
    assert (
        MHDXHybridTopologyStrategy.is_recorder_topology_compatible(non_hybrid_dvr, 0, 0, 0.0)
        is False
    )
    # Exceeds bandwidth -> False
    assert (
        MHDXHybridTopologyStrategy.is_recorder_topology_compatible(non_hybrid_dvr, 2, 0, 20.0)
        is False
    )
    # Without BNC-to-IP conversion, 2 analog + 2 IP fails because extra_ip_channels is only 1
    assert (
        MHDXHybridTopologyStrategy.is_recorder_topology_compatible(non_hybrid_dvr, 2, 2, 10.0)
        is False
    )

    # Empty recorder candidates
    with pytest.raises(TopologyIncompatibleError):
        MHDXHybridTopologyStrategy.select_optimal_recorder(
            camera_groups=(
                CameraGroupInput(
                    group_label="Cam",
                    technology="ANALOG",
                    count=1,
                    resolution="720p",
                    fps=15,
                    codec="H.265+",
                    retention_days=7,
                ),
            ),
            required_nominal_tb=1,
            recorder_candidates=(),
            hdd_candidates=_sample_hdds(),
        )

    # 32 Analog cameras when largest DVR in catalog has 16 BNC channels
    with pytest.raises(TopologyIncompatibleError):
        MHDXHybridTopologyStrategy.select_optimal_recorder(
            camera_groups=(
                CameraGroupInput(
                    group_label="32x Analog",
                    technology="ANALOG",
                    count=32,
                    resolution="1080p",
                    fps=30,
                    codec="H.265+",
                    retention_days=15,
                ),
            ),
            required_nominal_tb=2,
            recorder_candidates=_sample_recorders(),
            hdd_candidates=_sample_hdds(),
        )

    # Storage exceeds even the 2-SATA DVR (e.g., 40 TB required when max is 2 * 8TB = 16TB)
    with pytest.raises(StorageCapacityExceededError):
        MHDXHybridTopologyStrategy.select_optimal_recorder(
            camera_groups=(
                CameraGroupInput(
                    group_label="4x Analog",
                    technology="ANALOG",
                    count=4,
                    resolution="1080p",
                    fps=30,
                    codec="H.265+",
                    retention_days=15,
                ),
            ),
            required_nominal_tb=40,
            recorder_candidates=_sample_recorders(),
            hdd_candidates=_sample_hdds(),
        )


def test_electrical_voltage_drop_warnings_and_auto_bom_derivation() -> None:
    """Verify 1.3x current headroom, copper voltage drop < 10.8V warning, and exact BOM counts."""
    # Group 1: 4x Analog 4MP cameras (0.50A each) over 120m CAT5e Balun UTP
    # Delta_V = 2 * 120m * 0.50A * 0.0839 Ohm/m = 10.07V -> V_load = 1.93V < 10.8V (Warning!)
    # Group 2: 2x Analog 720p cameras (0.30A each) over 40m Coaxial Bipolar
    # Delta_V = 2 * 40m * 0.30A * 0.0344 Ohm/m = 0.83V -> V_load = 11.17V >= 10.8V (OK)
    # Group 3: 2x IP 1080p cameras (6.5W each) over 50m CAT6 UTP
    engine_input = SizingEngineInput(
        camera_groups=(
            CameraGroupInput(
                group_label="Galpão Externo 4MP Longa Distância",
                technology="ANALOG",
                count=4,
                resolution="4MP",
                fps=30,
                codec="H.265+",
                retention_days=15,
                cabling_mode="BALUN_UTP",
                average_cable_meters=120.0,
            ),
            CameraGroupInput(
                group_label="Portaria Coaxial",
                technology="ANALOG",
                count=2,
                resolution="720p",
                fps=30,
                codec="H.265+",
                retention_days=15,
                cabling_mode="COAXIAL",
                average_cable_meters=40.0,
            ),
            CameraGroupInput(
                group_label="Pátio IP PoE",
                technology="IP",
                count=2,
                resolution="1080p",
                fps=30,
                codec="H.265+",
                retention_days=15,
                cabling_mode="UTP_CAT6",
                average_cable_meters=50.0,
            ),
        )
    )

    result = CCTVSizingEngine.calculate(
        engine_input=engine_input,
        recorder_candidates=_sample_recorders(),
        hdd_candidates=_sample_hdds(),
        psu_candidates=_sample_psus(),
        poe_candidates=_sample_poe_switches(),
    )

    # 6 Analog + 2 IP = 8 total -> MHDX-1108
    assert result.topology.selected_recorder_sku == "MHDX-1108"

    # Analog current: (4 * 0.5A) + (2 * 0.3A) = 2.60A raw * 1.30 = 3.38A -> FONTE-MCM-5A (5A)
    elec = result.electrical_and_bom
    assert elec.analog_raw_current_amps == 2.60
    assert elec.analog_required_current_amps_with_headroom == 3.38
    assert len(elec.selected_power_supplies) == 1
    assert elec.selected_power_supplies[0].sku == "FONTE-MCM-5A"

    # IP PoE: 2 * 6.5W = 13.0W raw * 1.25 = 16.25W -> SF-500-POE (4 ports, 58W)
    assert elec.ip_raw_power_watts == 13.0
    assert elec.ip_required_poe_watts_with_headroom == 16.25
    assert len(elec.selected_poe_switches) == 1
    assert elec.selected_poe_switches[0].sku == "SF-500-POE"

    # Voltage drop warnings: only the 120m 4MP group triggers V_load < 10.8V
    assert len(elec.voltage_drop_warnings) == 1
    warn = elec.voltage_drop_warnings[0]
    assert warn.group_label == "Galpão Externo 4MP Longa Distância"
    assert warn.voltage_at_load_volts < 10.8

    # Cable calculations with 1.15 slack:
    # Analog UTP: ceil(4 * 120 * 1.15) = ceil(552) = 552m
    # IP UTP: ceil(2 * 50 * 1.15) = ceil(115) = 115m
    # Total UTP = 667m -> ceil(667 / 305) = 3 boxes
    assert elec.utp_cable_meters_with_slack == 667
    assert elec.utp_cable_boxes_305m == 3

    # Coaxial: ceil(2 * 40 * 1.15) = ceil(92) = 92m -> ceil(92 / 100) = 1 roll
    assert elec.coaxial_cable_meters_with_slack == 92
    assert elec.coaxial_cable_rolls_100m == 1

    # Verify BOM quantities by role
    bom_by_role = {
        item.role: sum(b.quantity for b in elec.derived_bom if b.role == item.role)
        for item in elec.derived_bom
    }
    assert bom_by_role["RECORDER"] == 1
    assert bom_by_role["CAMERA_ANALOG"] == 6
    assert bom_by_role["CAMERA_IP"] == 2
    assert bom_by_role["BALUN"] == 4  # 4 analog cameras on UTP
    assert bom_by_role["CONNECTOR_BNC"] == 4  # 2 analog cameras on Coax * 2
    assert bom_by_role["CONNECTOR_P4"] == 6  # All 6 analog cameras
    assert bom_by_role["CONNECTOR_RJ45"] == 4  # 2 IP cameras * 2
    assert bom_by_role["JUNCTION_BOX"] == 8  # All 8 cameras
    assert bom_by_role["CABLE_COAXIAL"] == 1
    assert bom_by_role["CABLE_UTP"] == 3
    assert bom_by_role["LABOR"] == 8


def test_electrical_multi_unit_psu_and_poe_switch_fallbacks() -> None:
    """Verify multi-unit PSU/PoE switch selection, explicit overrides, and error paths."""
    # Test CAT6 resistance lookup directly
    assert ElectricalAndBomStrategy.get_conductor_resistance_ohm_per_meter("UTP_CAT6") == 0.0660

    # Zero amps / ports return empty tuples
    assert ElectricalAndBomStrategy.select_power_supplies(0.0, _sample_psus()) == ()
    assert ElectricalAndBomStrategy.select_poe_switches(0, 0.0, _sample_poe_switches()) == ()

    # Missing PSU or PoE candidates when required > 0 raises DomainValidationError
    with pytest.raises(DomainValidationError):
        ElectricalAndBomStrategy.select_power_supplies(5.0, ())

    with pytest.raises(DomainValidationError):
        ElectricalAndBomStrategy.select_poe_switches(4, 30.0, ())

    # Multi-unit PSU combination: 35A required -> 1x 20A + 1x 20A (or 20A + 10A + 5A)
    psus_35a = ElectricalAndBomStrategy.select_power_supplies(35.0, _sample_psus())
    total_psu_cap = sum(p.quantity * p.capacity_per_unit for p in psus_35a)
    assert total_psu_cap >= 35.0

    # Extreme current (> 4 * 20A = 80A) triggers fallback to ceiling of largest PSU
    psus_100a = ElectricalAndBomStrategy.select_power_supplies(100.0, _sample_psus())
    assert len(psus_100a) == 1
    assert psus_100a[0].sku == "FONTE-MCM-20A"
    assert psus_100a[0].quantity == 5

    # Multi-unit PoE switch combination: 12 ports, 100W -> 1x 8p (SF-900-POE) + 1x 4p (SF-500-POE)
    poe_12p = ElectricalAndBomStrategy.select_poe_switches(12, 100.0, _sample_poe_switches())
    total_poe_ports = sum(int(s.quantity * s.capacity_per_unit) for s in poe_12p)
    assert total_poe_ports >= 12

    # Multi-unit identical PoE switch combination: 16 ports, 160W -> 2x 8p (SF-900-POE)
    poe_16p = ElectricalAndBomStrategy.select_poe_switches(16, 160.0, _sample_poe_switches())
    assert len(poe_16p) == 1
    assert poe_16p[0].sku == "SF-900-POE"
    assert poe_16p[0].quantity == 2

    # Extreme PoE port count (> 4 * 24 = 96 ports) triggers fallback to ceiling of largest switch
    poe_120p = ElectricalAndBomStrategy.select_poe_switches(120, 800.0, _sample_poe_switches())
    assert len(poe_120p) == 1
    assert poe_120p[0].sku == "S-1124G-PA"
    assert poe_120p[0].quantity == 5

    # Invalid average_cable_meters <= 0 raises DomainValidationError
    bad_group = CameraGroupInput(
        group_label="Invalid Cable",
        technology="IP",
        count=2,
        resolution="1080p",
        fps=30,
        codec="H.265+",
        retention_days=7,
        average_cable_meters=0.0,
        poe_power_watts=8.0,
    )
    with pytest.raises(DomainValidationError):
        CCTVSizingEngine.calculate(
            engine_input=SizingEngineInput(camera_groups=(bad_group,)),
            recorder_candidates=_sample_recorders(),
            hdd_candidates=_sample_hdds(),
            psu_candidates=_sample_psus(),
            poe_candidates=_sample_poe_switches(),
        )

    # Explicit ir_current_draw_ma and poe_power_watts overrides
    override_input = SizingEngineInput(
        camera_groups=(
            CameraGroupInput(
                group_label="Custom Analog",
                technology="ANALOG",
                count=2,
                resolution="1080p",
                fps=15,
                codec="H.265+",
                retention_days=7,
                cabling_mode="COAXIAL",
                average_cable_meters=25.0,
                ir_current_draw_ma=400,
            ),
            CameraGroupInput(
                group_label="Custom IP",
                technology="IP",
                count=2,
                resolution="1080p",
                fps=15,
                codec="H.265+",
                retention_days=7,
                cabling_mode="UTP_CAT5E",
                average_cable_meters=25.0,
                poe_power_watts=10.0,
            ),
        )
    )
    override_res = CCTVSizingEngine.calculate(
        engine_input=override_input,
        recorder_candidates=_sample_recorders(),
        hdd_candidates=_sample_hdds(),
        psu_candidates=_sample_psus(),
        poe_candidates=_sample_poe_switches(),
    )
    assert override_res.electrical_and_bom.analog_raw_current_amps == 0.80
    assert override_res.electrical_and_bom.ip_raw_power_watts == 20.0
