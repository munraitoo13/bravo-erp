"""Idempotent PT-BR Demo Tenant Seeder (Intelbras, WD Purple, MCM, Condutti, Furukawa)."""

import asyncio
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import structlog
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import async_session_factory
from src.core.logging import configure_logging
from src.core.security import UserRole, hash_password
from src.core.storage import StorageClient
from src.modules.catalog.models import CatalogCategory, CatalogItem
from src.modules.catalog.schemas import validate_specs_for_category
from src.modules.quotes.models import (
    AuditLog,
    Customer,
    OutboxEvent,
    Quote,
    QuoteItem,
    QuoteStatus,
)
from src.modules.tenants.models import Organization, User
from src.modules.work_orders.models import InstalledSerial, WorkOrder, WorkOrderStatus

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

DEMO_ORG_ID = UUID("0192d4a0-0000-7000-8000-000000000001")
DEMO_ORG_SLUG = "bravo-seguranca-demo"
DEMO_ORG_NAME = "Bravo Segurança Eletrônica Ltda"
DEMO_ORG_CNPJ = "14.582.901/0001-73"

DEMO_OWNER_USER_ID = UUID("0192d4a0-0000-7000-8000-000000000011")
DEMO_OWNER_EMAIL = "carlos.mendes@bravoseguranca.com.br"
DEMO_OWNER_NAME = "Carlos Eduardo Mendes"

DEMO_TECH_USER_ID = UUID("0192d4a0-0000-7000-8000-000000000012")
DEMO_TECH_EMAIL = "rafael.silva@bravoseguranca.com.br"
DEMO_TECH_NAME = "Rafael Oliveira Silva"

DEMO_DEFAULT_PASSWORD = "BravoDemo@2026"

DEMO_SENT_QUOTE_ID = UUID("0192d4a0-7c10-7000-8000-000000000101")
DEMO_SENT_QUOTE_PUBLIC_TOKEN = UUID("0192d4a0-7c10-7000-8000-000000000001")

DEMO_IN_PROGRESS_QUOTE_ID = UUID("0192d4a0-7c10-7000-8000-000000000102")
DEMO_IN_PROGRESS_QUOTE_PUBLIC_TOKEN = UUID("0192d4a0-7c10-7000-8000-000000000002")
DEMO_ACTIVE_WORK_ORDER_ID = UUID("0192d4a0-7c10-7000-8000-000000000202")

DEMO_COMPLETED_QUOTE_ID = UUID("0192d4a0-7c10-7000-8000-000000000103")
DEMO_COMPLETED_QUOTE_PUBLIC_TOKEN = UUID("0192d4a0-7c10-7000-8000-000000000003")
DEMO_COMPLETED_WORK_ORDER_ID = UUID("0192d4a0-7c10-7000-8000-000000000203")
DEMO_COMPLETED_PDF_SHA256 = "a3f5c8e9d1b20476589a1c3e5f7b9d0e2a4c6e8f0b1d3f5a7c9e1b3d5f7a9c1e"

_SAMPLE_JPEG_BYTES = (
    b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00\xff\xdb\x00C\x00"
    b"\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19"
    b"\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c $.' \",#\x1c\x1c(7),01444\x1f'9=82<.342"
    b"\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xda\x00\x08\x01\x01\x00\x00"
    b"?\x00\xbf\x00\xff\xd9"
)

_CACHED_DEMO_PASSWORD_HASH: str | None = None


def get_demo_password_hash() -> str:
    """Return cached Argon2id password hash for DEMO_DEFAULT_PASSWORD."""
    global _CACHED_DEMO_PASSWORD_HASH
    if _CACHED_DEMO_PASSWORD_HASH is None:
        _CACHED_DEMO_PASSWORD_HASH = hash_password(DEMO_DEFAULT_PASSWORD)
    return _CACHED_DEMO_PASSWORD_HASH


@dataclass(frozen=True)
class SeedCatalogSkuDefinition:
    """Immutable definition for a protected PT-BR Demo Catalog item."""

    sku: str
    name_pt_br: str
    category: CatalogCategory
    brand: str
    cost_price_cents: int
    sale_price_cents: int
    stock_quantity: int
    reserved_quantity: int
    specs: dict[str, object]


@dataclass(frozen=True)
class DemoSeedSummary:
    """Summary returned after seeding or resetting the Demo Tenant."""

    organization_id: UUID
    owner_user_id: UUID
    technician_user_id: UUID
    sent_quote_public_token: UUID
    active_work_order_id: UUID
    catalog_items_count: int
    quotes_count: int


SEED_CATALOG_DEFINITIONS: tuple[SeedCatalogSkuDefinition, ...] = (
    # 1. DVRs / NVRs (Intelbras Multi-HD MHDX & NVD)
    SeedCatalogSkuDefinition(
        sku="MHDX-1104",
        name_pt_br="DVR Intelbras Multi-HD MHDX 1104 4 Canais (+2 IP)",
        category=CatalogCategory.DVR,
        brand="Intelbras",
        cost_price_cents=42000,
        sale_price_cents=64900,
        stock_quantity=10,
        reserved_quantity=1,
        specs={
            "native_bnc_channels": 4,
            "extra_ip_channels": 2,
            "supports_bnc_to_ip_conversion": True,
            "max_sata_slots": 1,
            "max_tb_per_slot": 16,
            "max_incoming_bandwidth_mbps": 24,
            "supported_codecs": ["H.264", "H.265", "H.265+"],
            "is_pure_nvr": False,
            "requires_serial_number": True,
            "distributor_warranty_months": 12,
        },
    ),
    SeedCatalogSkuDefinition(
        sku="MHDX-1108",
        name_pt_br="DVR Intelbras Multi-HD MHDX 1108 8 Canais (+2 IP)",
        category=CatalogCategory.DVR,
        brand="Intelbras",
        cost_price_cents=59000,
        sale_price_cents=89900,
        stock_quantity=8,
        reserved_quantity=0,
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
    ),
    SeedCatalogSkuDefinition(
        sku="MHDX-1116",
        name_pt_br="DVR Intelbras Multi-HD MHDX 1116 16 Canais (+4 IP, 1 SATA)",
        category=CatalogCategory.DVR,
        brand="Intelbras",
        cost_price_cents=98000,
        sale_price_cents=149900,
        stock_quantity=5,
        reserved_quantity=0,
        specs={
            "native_bnc_channels": 16,
            "extra_ip_channels": 4,
            "supports_bnc_to_ip_conversion": True,
            "max_sata_slots": 1,
            "max_tb_per_slot": 16,
            "max_incoming_bandwidth_mbps": 96,
            "supported_codecs": ["H.264", "H.265", "H.265+"],
            "is_pure_nvr": False,
            "requires_serial_number": True,
            "distributor_warranty_months": 12,
        },
    ),
    SeedCatalogSkuDefinition(
        sku="MHDX-3116",
        name_pt_br="DVR Intelbras Multi-HD MHDX 3116 16 Canais (+8 IP, 2 SATA)",
        category=CatalogCategory.DVR,
        brand="Intelbras",
        cost_price_cents=158000,
        sale_price_cents=239900,
        stock_quantity=4,
        reserved_quantity=0,
        specs={
            "native_bnc_channels": 16,
            "extra_ip_channels": 8,
            "supports_bnc_to_ip_conversion": True,
            "max_sata_slots": 2,
            "max_tb_per_slot": 16,
            "max_incoming_bandwidth_mbps": 128,
            "supported_codecs": ["H.264", "H.265", "H.265+"],
            "is_pure_nvr": False,
            "requires_serial_number": True,
            "distributor_warranty_months": 12,
        },
    ),
    SeedCatalogSkuDefinition(
        sku="NVD-1408",
        name_pt_br="Gravador Digital IP NVR Intelbras NVD 1408 8 Canais H.265+",
        category=CatalogCategory.DVR,
        brand="Intelbras",
        cost_price_cents=62000,
        sale_price_cents=94900,
        stock_quantity=6,
        reserved_quantity=0,
        specs={
            "native_bnc_channels": 8,
            "extra_ip_channels": 0,
            "supports_bnc_to_ip_conversion": False,
            "max_sata_slots": 1,
            "max_tb_per_slot": 16,
            "max_incoming_bandwidth_mbps": 80,
            "supported_codecs": ["H.264", "H.265", "H.265+"],
            "is_pure_nvr": True,
            "requires_serial_number": True,
            "distributor_warranty_months": 12,
        },
    ),
    SeedCatalogSkuDefinition(
        sku="NVD-3316-P",
        name_pt_br="Gravador Digital IP NVR Intelbras NVD 3316 P 16 Canais PoE (2 SATA)",
        category=CatalogCategory.DVR,
        brand="Intelbras",
        cost_price_cents=189000,
        sale_price_cents=289000,
        stock_quantity=3,
        reserved_quantity=0,
        specs={
            "native_bnc_channels": 16,
            "extra_ip_channels": 0,
            "supports_bnc_to_ip_conversion": False,
            "max_sata_slots": 2,
            "max_tb_per_slot": 16,
            "max_incoming_bandwidth_mbps": 160,
            "supported_codecs": ["H.264", "H.265", "H.265+"],
            "is_pure_nvr": True,
            "requires_serial_number": True,
            "distributor_warranty_months": 12,
        },
    ),
    # 2. Analog Cameras (Intelbras VHL / VHD)
    SeedCatalogSkuDefinition(
        sku="VHL-1120-B",
        name_pt_br="Câmera Bullet HDCVI Intelbras VHL 1120 B HD 720p IR 20m",
        category=CatalogCategory.CAMERA_ANALOG,
        brand="Intelbras",
        cost_price_cents=8900,
        sale_price_cents=14900,
        stock_quantity=40,
        reserved_quantity=4,
        specs={
            "resolution": "720p",
            "max_fps": 30,
            "ir_range_meters": 20,
            "ir_current_draw_ma": 300,
            "nominal_voltage_vdc": 12.0,
            "min_operating_voltage_vdc": 10.8,
            "form_factor": "BULLET",
            "requires_serial_number": True,
            "distributor_warranty_months": 12,
        },
    ),
    SeedCatalogSkuDefinition(
        sku="VHD-1220-B",
        name_pt_br="Câmera Bullet Multi-HD Intelbras VHD 1220 B Full HD 1080p IR 20m",
        category=CatalogCategory.CAMERA_ANALOG,
        brand="Intelbras",
        cost_price_cents=12900,
        sale_price_cents=21900,
        stock_quantity=50,
        reserved_quantity=0,
        specs={
            "resolution": "1080p",
            "max_fps": 30,
            "ir_range_meters": 20,
            "ir_current_draw_ma": 350,
            "nominal_voltage_vdc": 12.0,
            "min_operating_voltage_vdc": 10.8,
            "form_factor": "BULLET",
            "requires_serial_number": True,
            "distributor_warranty_months": 12,
        },
    ),
    SeedCatalogSkuDefinition(
        sku="VHD-3220-D-FC",
        name_pt_br="Câmera Dome Multi-HD Intelbras VHD 3220 D Full Color 1080p LED 20m",
        category=CatalogCategory.CAMERA_ANALOG,
        brand="Intelbras",
        cost_price_cents=18500,
        sale_price_cents=29900,
        stock_quantity=30,
        reserved_quantity=0,
        specs={
            "resolution": "1080p",
            "max_fps": 30,
            "ir_range_meters": 20,
            "ir_current_draw_ma": 450,
            "nominal_voltage_vdc": 12.0,
            "min_operating_voltage_vdc": 10.8,
            "form_factor": "DOME",
            "requires_serial_number": True,
            "distributor_warranty_months": 12,
        },
    ),
    SeedCatalogSkuDefinition(
        sku="VHD-3430-B",
        name_pt_br="Câmera Bullet Multi-HD Intelbras VHD 3430 B 4MP (2K) IR 30m",
        category=CatalogCategory.CAMERA_ANALOG,
        brand="Intelbras",
        cost_price_cents=23000,
        sale_price_cents=36900,
        stock_quantity=25,
        reserved_quantity=0,
        specs={
            "resolution": "4MP",
            "max_fps": 30,
            "ir_range_meters": 30,
            "ir_current_draw_ma": 500,
            "nominal_voltage_vdc": 12.0,
            "min_operating_voltage_vdc": 10.8,
            "form_factor": "BULLET",
            "requires_serial_number": True,
            "distributor_warranty_months": 12,
        },
    ),
    # 3. IP Cameras (Intelbras VIP)
    SeedCatalogSkuDefinition(
        sku="VIP-1230-B-G4",
        name_pt_br="Câmera IP Bullet Intelbras VIP 1230 B G4 Full HD 1080p PoE IR 30m",
        category=CatalogCategory.CAMERA_IP,
        brand="Intelbras",
        cost_price_cents=24500,
        sale_price_cents=38900,
        stock_quantity=30,
        reserved_quantity=0,
        specs={
            "resolution": "1080p",
            "max_fps": 30,
            "supported_codecs": ["H.264", "H.265", "H.265+"],
            "poe_standard": "802.3af",
            "max_power_watts": 6.5,
            "ir_current_draw_ma": 540,
            "ir_range_meters": 30,
            "form_factor": "BULLET",
            "requires_serial_number": True,
            "distributor_warranty_months": 12,
        },
    ),
    SeedCatalogSkuDefinition(
        sku="VIP-3430-B",
        name_pt_br="Câmera IP Bullet Intelbras VIP 3430 B 4MP PoE H.265+ IR 30m",
        category=CatalogCategory.CAMERA_IP,
        brand="Intelbras",
        cost_price_cents=39000,
        sale_price_cents=59900,
        stock_quantity=20,
        reserved_quantity=0,
        specs={
            "resolution": "4MP",
            "max_fps": 30,
            "supported_codecs": ["H.264", "H.265", "H.265+"],
            "poe_standard": "802.3af",
            "max_power_watts": 7.5,
            "ir_current_draw_ma": 625,
            "ir_range_meters": 30,
            "form_factor": "BULLET",
            "requires_serial_number": True,
            "distributor_warranty_months": 12,
        },
    ),
    SeedCatalogSkuDefinition(
        sku="VIP-3830-B",
        name_pt_br="Câmera IP Bullet Intelbras VIP 3830 B 4K Ultra HD PoE IR 30m",
        category=CatalogCategory.CAMERA_IP,
        brand="Intelbras",
        cost_price_cents=64000,
        sale_price_cents=98900,
        stock_quantity=12,
        reserved_quantity=0,
        specs={
            "resolution": "4K",
            "max_fps": 30,
            "supported_codecs": ["H.264", "H.265", "H.265+"],
            "poe_standard": "802.3af",
            "max_power_watts": 9.5,
            "ir_current_draw_ma": 790,
            "ir_range_meters": 30,
            "form_factor": "BULLET",
            "requires_serial_number": True,
            "distributor_warranty_months": 12,
        },
    ),
    # 4. Surveillance HDDs (Western Digital WD Purple)
    SeedCatalogSkuDefinition(
        sku="WD10PURZ",
        name_pt_br="HD para CFTV Western Digital WD Purple 1TB SATA 24x7 (WD10PURZ)",
        category=CatalogCategory.HDD,
        brand="Western Digital",
        cost_price_cents=29000,
        sale_price_cents=44900,
        stock_quantity=15,
        reserved_quantity=1,
        specs={
            "capacity_tb": 1,
            "usable_capacity_gb": 931,
            "surveillance_grade": True,
            "requires_serial_number": True,
            "distributor_warranty_months": 36,
        },
    ),
    SeedCatalogSkuDefinition(
        sku="WD20PURZ",
        name_pt_br="HD para CFTV Western Digital WD Purple 2TB SATA 24x7 (WD20PURZ)",
        category=CatalogCategory.HDD,
        brand="Western Digital",
        cost_price_cents=39500,
        sale_price_cents=59900,
        stock_quantity=15,
        reserved_quantity=0,
        specs={
            "capacity_tb": 2,
            "usable_capacity_gb": 1862,
            "surveillance_grade": True,
            "requires_serial_number": True,
            "distributor_warranty_months": 36,
        },
    ),
    SeedCatalogSkuDefinition(
        sku="WD42PURZ",
        name_pt_br="HD para CFTV Western Digital WD Purple 4TB SATA 24x7 (WD42PURZ)",
        category=CatalogCategory.HDD,
        brand="Western Digital",
        cost_price_cents=64000,
        sale_price_cents=96900,
        stock_quantity=10,
        reserved_quantity=0,
        specs={
            "capacity_tb": 4,
            "usable_capacity_gb": 3725,
            "surveillance_grade": True,
            "requires_serial_number": True,
            "distributor_warranty_months": 36,
        },
    ),
    SeedCatalogSkuDefinition(
        sku="WD84PURZ",
        name_pt_br="HD para CFTV Western Digital WD Purple 8TB SATA 24x7 (WD84PURZ)",
        category=CatalogCategory.HDD,
        brand="Western Digital",
        cost_price_cents=129000,
        sale_price_cents=189900,
        stock_quantity=6,
        reserved_quantity=0,
        specs={
            "capacity_tb": 8,
            "usable_capacity_gb": 7450,
            "surveillance_grade": True,
            "requires_serial_number": True,
            "distributor_warranty_months": 36,
        },
    ),
    # 5. Power Supplies (MCM)
    SeedCatalogSkuDefinition(
        sku="FONTE-MCM-5A",
        name_pt_br="Fonte Chaveada Colmeia MCM 12.8V 5A Estabilizada CFTV",
        category=CatalogCategory.POWER_SUPPLY,
        brand="MCM",
        cost_price_cents=4200,
        sale_price_cents=7500,
        stock_quantity=20,
        reserved_quantity=1,
        specs={
            "output_voltage_vdc": 12.8,
            "max_current_amps": 5,
            "requires_serial_number": False,
            "distributor_warranty_months": 12,
        },
    ),
    SeedCatalogSkuDefinition(
        sku="FONTE-MCM-10A",
        name_pt_br="Fonte Chaveada Colmeia MCM 12.8V 10A Estabilizada CFTV",
        category=CatalogCategory.POWER_SUPPLY,
        brand="MCM",
        cost_price_cents=6800,
        sale_price_cents=11900,
        stock_quantity=20,
        reserved_quantity=0,
        specs={
            "output_voltage_vdc": 12.8,
            "max_current_amps": 10,
            "requires_serial_number": False,
            "distributor_warranty_months": 12,
        },
    ),
    SeedCatalogSkuDefinition(
        sku="FONTE-MCM-20A",
        name_pt_br="Fonte Chaveada Colmeia MCM 12.8V 20A Estabilizada CFTV",
        category=CatalogCategory.POWER_SUPPLY,
        brand="MCM",
        cost_price_cents=11500,
        sale_price_cents=18900,
        stock_quantity=15,
        reserved_quantity=0,
        specs={
            "output_voltage_vdc": 12.8,
            "max_current_amps": 20,
            "requires_serial_number": False,
            "distributor_warranty_months": 12,
        },
    ),
    # 6. PoE Switches (Intelbras)
    SeedCatalogSkuDefinition(
        sku="SF-500-POE",
        name_pt_br="Switch PoE Intelbras SF 500 PoE 4 Portas PoE + 1 Uplink (58W)",
        category=CatalogCategory.POE_SWITCH,
        brand="Intelbras",
        cost_price_cents=19500,
        sale_price_cents=31900,
        stock_quantity=12,
        reserved_quantity=0,
        specs={
            "poe_ports": 4,
            "uplink_ports": 1,
            "total_poe_budget_watts": 58.0,
            "supports_extend_250m": True,
            "requires_serial_number": True,
            "distributor_warranty_months": 12,
        },
    ),
    SeedCatalogSkuDefinition(
        sku="SF-900-POE",
        name_pt_br="Switch PoE Intelbras SF 900 PoE 8 Portas PoE + 1 Uplink (92W)",
        category=CatalogCategory.POE_SWITCH,
        brand="Intelbras",
        cost_price_cents=34000,
        sale_price_cents=52900,
        stock_quantity=10,
        reserved_quantity=0,
        specs={
            "poe_ports": 8,
            "uplink_ports": 1,
            "total_poe_budget_watts": 92.0,
            "supports_extend_250m": True,
            "requires_serial_number": True,
            "distributor_warranty_months": 12,
        },
    ),
    SeedCatalogSkuDefinition(
        sku="S-1124G-PA",
        name_pt_br="Switch Gigabit PoE Intelbras S 1124G-PA 24 Portas PoE + 2 SFP (240W)",
        category=CatalogCategory.POE_SWITCH,
        brand="Intelbras",
        cost_price_cents=98000,
        sale_price_cents=149900,
        stock_quantity=5,
        reserved_quantity=0,
        specs={
            "poe_ports": 24,
            "uplink_ports": 2,
            "total_poe_budget_watts": 240.0,
            "supports_extend_250m": True,
            "requires_serial_number": True,
            "distributor_warranty_months": 12,
        },
    ),
    # 7. Cables, Baluns, Connectors, Accessories & Labor
    SeedCatalogSkuDefinition(
        sku="CABO-COAX-CONDUTTI-100M",
        name_pt_br="Cabo Coaxial Bipolar Condutti 4mm 80% Malha Cobre (Rolo 100m)",
        category=CatalogCategory.CABLE,
        brand="Condutti",
        cost_price_cents=8900,
        sale_price_cents=14900,
        stock_quantity=30,
        reserved_quantity=1,
        specs={
            "cable_type": "COAXIAL_BIPOLAR_4MM",
            "roll_length_meters": 100,
            "dc_resistance_ohm_per_meter": 0.0344,
            "is_pure_copper": True,
            "requires_serial_number": False,
        },
    ),
    SeedCatalogSkuDefinition(
        sku="CABO-UTP-FURUKAWA-305M",
        name_pt_br="Cabo de Rede Furukawa SohoPlus UTP Cat5e 100% Cobre (Caixa 305m)",
        category=CatalogCategory.CABLE,
        brand="Furukawa",
        cost_price_cents=42000,
        sale_price_cents=64900,
        stock_quantity=20,
        reserved_quantity=0,
        specs={
            "cable_type": "UTP_CAT5E",
            "roll_length_meters": 305,
            "dc_resistance_ohm_per_meter": 0.0839,
            "is_pure_copper": True,
            "requires_serial_number": False,
        },
    ),
    SeedCatalogSkuDefinition(
        sku="BALUN-XBP-502",
        name_pt_br="Par de Vídeo Balun Passivo Intelbras XBP 502 HD/Full HD/4MP",
        category=CatalogCategory.BALUN,
        brand="Intelbras",
        cost_price_cents=1800,
        sale_price_cents=3500,
        stock_quantity=150,
        reserved_quantity=0,
        specs={
            "sub_type": "PASSIVE_BALUN_PAIR",
            "units_per_package": 1,
            "requires_serial_number": False,
        },
    ),
    SeedCatalogSkuDefinition(
        sku="CONN-BNC-MOLA",
        name_pt_br="Conector BNC Macho com Mola e Parafuso CFTV",
        category=CatalogCategory.CONNECTOR,
        brand="Condutti",
        cost_price_cents=250,
        sale_price_cents=600,
        stock_quantity=300,
        reserved_quantity=8,
        specs={
            "sub_type": "CONNECTOR_BNC_MALE",
            "units_per_package": 1,
            "requires_serial_number": False,
        },
    ),
    SeedCatalogSkuDefinition(
        sku="CONN-P4-BORNE",
        name_pt_br="Conector P4 Macho com Borne para Alimentação 12V",
        category=CatalogCategory.CONNECTOR,
        brand="Condutti",
        cost_price_cents=250,
        sale_price_cents=600,
        stock_quantity=300,
        reserved_quantity=4,
        specs={
            "sub_type": "CONNECTOR_P4_MALE",
            "units_per_package": 1,
            "requires_serial_number": False,
        },
    ),
    SeedCatalogSkuDefinition(
        sku="CONN-RJ45-CAT5E",
        name_pt_br="Conector RJ45 Macho Cat5e Furukawa SohoPlus",
        category=CatalogCategory.CONNECTOR,
        brand="Furukawa",
        cost_price_cents=180,
        sale_price_cents=450,
        stock_quantity=400,
        reserved_quantity=0,
        specs={
            "sub_type": "CONNECTOR_RJ45",
            "units_per_package": 1,
            "requires_serial_number": False,
        },
    ),
    SeedCatalogSkuDefinition(
        sku="VBOX-1100E",
        name_pt_br="Caixa de Sobrepor e Passagem Intelbras VBOX 1100E CFTV",
        category=CatalogCategory.ACCESSORY,
        brand="Intelbras",
        cost_price_cents=1100,
        sale_price_cents=2200,
        stock_quantity=200,
        reserved_quantity=4,
        specs={
            "sub_type": "JUNCTION_BOX_VBOX",
            "units_per_package": 1,
            "requires_serial_number": False,
        },
    ),
    SeedCatalogSkuDefinition(
        sku="SRV-INST-PONTO",
        name_pt_br="Mão de Obra de Instalação, Cabeamento e Configuração por Ponto de Câmera",
        category=CatalogCategory.SERVICE_LABOR,
        brand="Bravo Engenharia",
        cost_price_cents=6000,
        sale_price_cents=14000,
        stock_quantity=9999,
        reserved_quantity=0,
        specs={
            "sub_type": "LABOR_POINT_INSTALL",
            "units_per_package": 1,
            "requires_serial_number": False,
        },
    ),
)


def _compute_quote_totals(
    line_defs: list[tuple[CatalogItem, int, bool]],
) -> tuple[int, int, Decimal]:
    """Compute exact integer cost_cents, sale_cents, and Decimal margin_percent."""
    total_cost = sum(item.cost_price_cents * qty for item, qty, _ in line_defs)
    total_sale = sum(item.sale_price_cents * qty for item, qty, _ in line_defs)
    if total_sale <= 0:
        return total_cost, total_sale, Decimal("0.00")
    margin = (Decimal(total_sale - total_cost) / Decimal(total_sale)) * Decimal("100.00")
    return total_cost, total_sale, margin.quantize(Decimal("0.01"))


async def seed_demo_tenant(
    session: AsyncSession,
    *,
    force_reset: bool = False,
    storage_client: StorageClient | None = None,
) -> DemoSeedSummary:
    """Idempotently seed or reset the Demo Tenant with PT-BR catalog, quotes, and work orders."""
    existing_org = await session.scalar(
        select(Organization).where(Organization.slug == DEMO_ORG_SLUG)
    )

    if existing_org is not None and not force_reset:
        # Verify demo quotes exist; if already seeded, return summary immediately
        existing_sent_quote = await session.scalar(
            select(Quote).where(Quote.public_token == DEMO_SENT_QUOTE_PUBLIC_TOKEN)
        )
        if existing_sent_quote is not None:
            return DemoSeedSummary(
                organization_id=existing_org.id,
                owner_user_id=DEMO_OWNER_USER_ID,
                technician_user_id=DEMO_TECH_USER_ID,
                sent_quote_public_token=DEMO_SENT_QUOTE_PUBLIC_TOKEN,
                active_work_order_id=DEMO_ACTIVE_WORK_ORDER_ID,
                catalog_items_count=len(SEED_CATALOG_DEFINITIONS),
                quotes_count=3,
            )

    if existing_org is not None:
        # Clean transactional children in topological FK order for deterministic reset
        org_id = existing_org.id
        await session.execute(
            delete(InstalledSerial).where(InstalledSerial.organization_id == org_id)
        )
        await session.execute(delete(WorkOrder).where(WorkOrder.organization_id == org_id))
        await session.execute(delete(QuoteItem).where(QuoteItem.organization_id == org_id))
        await session.execute(delete(Quote).where(Quote.organization_id == org_id))
        await session.execute(delete(Customer).where(Customer.organization_id == org_id))
        await session.execute(delete(AuditLog).where(AuditLog.organization_id == org_id))
        await session.execute(delete(OutboxEvent).where(OutboxEvent.organization_id == org_id))
        await session.flush()
    else:
        existing_org = Organization(
            id=DEMO_ORG_ID,
            name=DEMO_ORG_NAME,
            slug=DEMO_ORG_SLUG,
            document_cnpj=DEMO_ORG_CNPJ,
            is_demo=True,
        )
        session.add(existing_org)
        await session.flush()

    org_id = existing_org.id
    password_hash = get_demo_password_hash()

    # Upsert Demo OWNER and TECHNICIAN users
    owner_user = await session.scalar(
        select(User).where(User.organization_id == org_id, User.email == DEMO_OWNER_EMAIL)
    )
    if owner_user is None:
        owner_user = User(
            id=DEMO_OWNER_USER_ID,
            organization_id=org_id,
            email=DEMO_OWNER_EMAIL,
            password_hash=password_hash,
            full_name=DEMO_OWNER_NAME,
            role=UserRole.OWNER,
            is_active=True,
        )
        session.add(owner_user)
    else:
        owner_user.full_name = DEMO_OWNER_NAME
        owner_user.role = UserRole.OWNER
        owner_user.is_active = True

    tech_user = await session.scalar(
        select(User).where(User.organization_id == org_id, User.email == DEMO_TECH_EMAIL)
    )
    if tech_user is None:
        tech_user = User(
            id=DEMO_TECH_USER_ID,
            organization_id=org_id,
            email=DEMO_TECH_EMAIL,
            password_hash=password_hash,
            full_name=DEMO_TECH_NAME,
            role=UserRole.TECHNICIAN,
            is_active=True,
        )
        session.add(tech_user)
    else:
        tech_user.full_name = DEMO_TECH_NAME
        tech_user.role = UserRole.TECHNICIAN
        tech_user.is_active = True

    await session.flush()

    # Upsert Protected PT-BR Catalog Items
    sku_map: dict[str, CatalogItem] = {}
    for sku_def in SEED_CATALOG_DEFINITIONS:
        validated_specs = validate_specs_for_category(sku_def.category, sku_def.specs)
        catalog_item = await session.scalar(
            select(CatalogItem).where(
                CatalogItem.organization_id == org_id,
                CatalogItem.sku == sku_def.sku,
            )
        )
        if catalog_item is None:
            catalog_item = CatalogItem(
                organization_id=org_id,
                sku=sku_def.sku,
                name_pt_br=sku_def.name_pt_br,
                category=sku_def.category,
                brand=sku_def.brand,
                cost_price_cents=sku_def.cost_price_cents,
                sale_price_cents=sku_def.sale_price_cents,
                stock_quantity=sku_def.stock_quantity,
                reserved_quantity=sku_def.reserved_quantity,
                specs=validated_specs,
                is_seed_protected=True,
                is_active=True,
            )
            session.add(catalog_item)
        else:
            catalog_item.name_pt_br = sku_def.name_pt_br
            catalog_item.category = sku_def.category
            catalog_item.brand = sku_def.brand
            catalog_item.cost_price_cents = sku_def.cost_price_cents
            catalog_item.sale_price_cents = sku_def.sale_price_cents
            catalog_item.stock_quantity = sku_def.stock_quantity
            catalog_item.reserved_quantity = sku_def.reserved_quantity
            catalog_item.specs = validated_specs
            catalog_item.is_seed_protected = True
            catalog_item.is_active = True

        sku_map[sku_def.sku] = catalog_item

    await session.flush()

    # Create 3 PT-BR Customers
    cust_condominio = Customer(
        organization_id=org_id,
        name="Condomínio Residencial Jardim das Acácias",
        document_cpf_cnpj="45.123.890/0001-12",
        phone_whatsapp="+5511998123456",
        email="sindico@jardimdasacacias.com.br",
        address_json={
            "street": "Rua das Palmeiras",
            "number": "450",
            "complement": "Portaria Central",
            "district": "Moema",
            "city": "São Paulo",
            "state": "SP",
            "zip_code": "04520-001",
        },
    )
    cust_mercado = Customer(
        organization_id=org_id,
        name="Supermercado Bom Preço Matriz Ltda",
        document_cpf_cnpj="22.876.543/0001-88",
        phone_whatsapp="+5511987654321",
        email="gerencia@superbompreco.com.br",
        address_json={
            "street": "Avenida Brasil",
            "number": "1820",
            "complement": "Galpão A",
            "district": "Centro",
            "city": "Campinas",
            "state": "SP",
            "zip_code": "13015-100",
        },
    )
    cust_clinica = Customer(
        organization_id=org_id,
        name="Clínica Médica São Lucas S/A",
        document_cpf_cnpj="33.445.667/0001-09",
        phone_whatsapp="+5511976543210",
        email="infraestrutura@clinicasaolucas.com.br",
        address_json={
            "street": "Alameda Santos",
            "number": "905",
            "complement": "Conjunto 41",
            "district": "Cerqueira César",
            "city": "São Paulo",
            "state": "SP",
            "zip_code": "01419-001",
        },
    )
    session.add_all([cust_condominio, cust_mercado, cust_clinica])
    await session.flush()

    now = datetime.now(UTC)

    # Scenario 1: Quote #1 (SENT) — Ready for 1-Click Public Client Approval
    q1_lines: list[tuple[CatalogItem, int, bool]] = [
        (sku_map["MHDX-1108"], 1, True),
        (sku_map["VHD-1220-B"], 6, False),
        (sku_map["VIP-1230-B-G4"], 2, False),
        (sku_map["WD20PURZ"], 1, True),
        (sku_map["FONTE-MCM-10A"], 1, True),
        (sku_map["SF-500-POE"], 1, True),
        (sku_map["BALUN-XBP-502"], 6, True),
        (sku_map["CONN-P4-BORNE"], 6, True),
        (sku_map["CONN-RJ45-CAT5E"], 4, True),
        (sku_map["VBOX-1100E"], 8, True),
        (sku_map["CABO-UTP-FURUKAWA-305M"], 1, True),
        (sku_map["SRV-INST-PONTO"], 8, True),
    ]
    q1_cost, q1_sale, q1_margin = _compute_quote_totals(q1_lines)
    quote_1 = Quote(
        id=DEMO_SENT_QUOTE_ID,
        organization_id=org_id,
        customer_id=cust_condominio.id,
        public_token=DEMO_SENT_QUOTE_PUBLIC_TOKEN,
        status=QuoteStatus.SENT,
        sizing_input_json={
            "scenario_label": "Híbrido 6x Analógicas 1080p + 2x IP PoE (MHDX 1108 10ch Total)",
            "retention_days": 15,
            "codec": "H.265+",
        },
        total_cost_cents=q1_cost,
        total_sale_cents=q1_sale,
        margin_percent=q1_margin,
        valid_until=now + timedelta(days=15),
        version=1,
    )
    session.add(quote_1)
    await session.flush()
    for item, qty, is_auto in q1_lines:
        session.add(
            QuoteItem(
                quote_id=quote_1.id,
                organization_id=org_id,
                catalog_item_id=item.id,
                quantity=qty,
                unit_cost_cents=item.cost_price_cents,
                unit_sale_cents=item.sale_price_cents,
                is_auto_derived=is_auto,
            )
        )

    # Scenario 2: Quote #2 (IN_PROGRESS) + WorkOrder (IN_FIELD) — Ready for Technician Completion
    q2_lines: list[tuple[CatalogItem, int, bool]] = [
        (sku_map["MHDX-1104"], 1, True),
        (sku_map["VHL-1120-B"], 4, False),
        (sku_map["WD10PURZ"], 1, True),
        (sku_map["FONTE-MCM-5A"], 1, True),
        (sku_map["CONN-BNC-MOLA"], 8, True),
        (sku_map["CONN-P4-BORNE"], 4, True),
        (sku_map["VBOX-1100E"], 4, True),
        (sku_map["CABO-COAX-CONDUTTI-100M"], 1, True),
        (sku_map["SRV-INST-PONTO"], 4, True),
    ]
    q2_cost, q2_sale, q2_margin = _compute_quote_totals(q2_lines)
    quote_2 = Quote(
        id=DEMO_IN_PROGRESS_QUOTE_ID,
        organization_id=org_id,
        customer_id=cust_mercado.id,
        public_token=DEMO_IN_PROGRESS_QUOTE_PUBLIC_TOKEN,
        status=QuoteStatus.IN_PROGRESS,
        sizing_input_json={
            "scenario_label": "Kit 4 Câmeras HDCVI 720p + DVR MHDX 1104 + WD Purple 1TB",
            "retention_days": 15,
            "codec": "H.265+",
        },
        total_cost_cents=q2_cost,
        total_sale_cents=q2_sale,
        margin_percent=q2_margin,
        valid_until=now + timedelta(days=10),
        approved_at=now - timedelta(days=1),
        approved_by_ip="189.40.112.84",
        version=2,
    )
    session.add(quote_2)
    await session.flush()
    for item, qty, is_auto in q2_lines:
        session.add(
            QuoteItem(
                quote_id=quote_2.id,
                organization_id=org_id,
                catalog_item_id=item.id,
                quantity=qty,
                unit_cost_cents=item.cost_price_cents,
                unit_sale_cents=item.sale_price_cents,
                is_auto_derived=is_auto,
            )
        )

    wo_2 = WorkOrder(
        id=DEMO_ACTIVE_WORK_ORDER_ID,
        organization_id=org_id,
        quote_id=quote_2.id,
        assigned_technician_id=tech_user.id,
        status=WorkOrderStatus.IN_FIELD,
        checklist_json=[
            {
                "step_id": "step_1",
                "label_pt_br": "Fixação e alinhamento das câmeras",
                "is_checked": True,
                "checked_at": (now - timedelta(hours=3)).isoformat(),
            },
            {
                "step_id": "step_2",
                "label_pt_br": "Crimpagem e teste de cabos/baluns",
                "is_checked": True,
                "checked_at": (now - timedelta(hours=2)).isoformat(),
            },
            {
                "step_id": "step_3",
                "label_pt_br": "Instalação do HD WD Purple e formatação no DVR",
                "is_checked": True,
                "checked_at": (now - timedelta(hours=1)).isoformat(),
            },
            {
                "step_id": "step_4",
                "label_pt_br": "Configuração Intelbras Cloud P2P e aplicativo cliente",
                "is_checked": False,
                "checked_at": None,
            },
            {
                "step_id": "step_5",
                "label_pt_br": "Limpeza do local e termo de aceite",
                "is_checked": False,
                "checked_at": None,
            },
        ],
        installation_photos_keys=[
            f"photos/{org_id}/{DEMO_ACTIVE_WORK_ORDER_ID}/rack-mhdx-1104-instalado.jpg"
        ],
        cloud_p2p_id="ITB-P2P-994821BR",
        notes=(
            "3 de 4 câmeras já registradas no Cofre de Seriais. "
            "Falta registrar BNC-04 (Estacionamento)."
        ),
    )
    session.add(wo_2)
    await session.flush()

    today = date.today()
    # Register 5 of the 6 required serials for Work Order #2 (leaving 1 camera BNC-04 for demo)
    wo2_serials = [
        (sku_map["MHDX-1104"], "ITB-MHDX1104-882910", "RACK-DVR-01", 365),
        (sku_map["WD10PURZ"], "WCC6Y7P94821", "SATA-01", 1095),
        (sku_map["VHL-1120-B"], "ITB-VHL1120-004911", "BNC-01 (Caixa 01)", 365),
        (sku_map["VHL-1120-B"], "ITB-VHL1120-004912", "BNC-02 (Corredor Central)", 365),
        (sku_map["VHL-1120-B"], "ITB-VHL1120-004913", "BNC-03 (Doca Recebimento)", 365),
    ]
    for item_obj, sn, label, dist_days in wo2_serials:
        session.add(
            InstalledSerial(
                organization_id=org_id,
                work_order_id=wo_2.id,
                catalog_item_id=item_obj.id,
                serial_number=sn,
                channel_or_slot_label=label,
                distributor_warranty_until=today + timedelta(days=dist_days),
                client_warranty_until=today + timedelta(days=365),
            )
        )

    # Scenario 3: Quote #3 (COMPLETED 11 months ago) — Flagged on 11-Month Warranty Radar
    q3_lines: list[tuple[CatalogItem, int, bool]] = [
        (sku_map["MHDX-1108"], 1, True),
        (sku_map["VHD-3220-D-FC"], 4, False),
        (sku_map["WD42PURZ"], 1, True),
        (sku_map["FONTE-MCM-10A"], 1, True),
        (sku_map["SRV-INST-PONTO"], 4, True),
    ]
    q3_cost, q3_sale, q3_margin = _compute_quote_totals(q3_lines)
    completed_11m_ago = now - timedelta(days=340)
    quote_3 = Quote(
        id=DEMO_COMPLETED_QUOTE_ID,
        organization_id=org_id,
        customer_id=cust_clinica.id,
        public_token=DEMO_COMPLETED_QUOTE_PUBLIC_TOKEN,
        status=QuoteStatus.COMPLETED,
        sizing_input_json={
            "scenario_label": "CFTV Full Color Recepção & Acesso — Clínica São Lucas",
            "retention_days": 30,
            "codec": "H.265+",
        },
        total_cost_cents=q3_cost,
        total_sale_cents=q3_sale,
        margin_percent=q3_margin,
        valid_until=completed_11m_ago + timedelta(days=15),
        approved_at=completed_11m_ago - timedelta(days=2),
        approved_by_ip="200.155.80.19",
        pdf_storage_key=f"proposals/{org_id}/{DEMO_COMPLETED_QUOTE_ID}.pdf",
        pdf_sha256_hash=DEMO_COMPLETED_PDF_SHA256,
        version=3,
    )
    session.add(quote_3)
    await session.flush()
    for item, qty, is_auto in q3_lines:
        session.add(
            QuoteItem(
                quote_id=quote_3.id,
                organization_id=org_id,
                catalog_item_id=item.id,
                quantity=qty,
                unit_cost_cents=item.cost_price_cents,
                unit_sale_cents=item.sale_price_cents,
                is_auto_derived=is_auto,
            )
        )

    wo_3 = WorkOrder(
        id=DEMO_COMPLETED_WORK_ORDER_ID,
        organization_id=org_id,
        quote_id=quote_3.id,
        assigned_technician_id=tech_user.id,
        status=WorkOrderStatus.COMPLETED,
        checklist_json=[
            {
                "step_id": "step_1",
                "label_pt_br": "Fixação e alinhamento das câmeras",
                "is_checked": True,
                "checked_at": completed_11m_ago.isoformat(),
            },
            {
                "step_id": "step_2",
                "label_pt_br": "Crimpagem e teste de cabos/baluns",
                "is_checked": True,
                "checked_at": completed_11m_ago.isoformat(),
            },
            {
                "step_id": "step_3",
                "label_pt_br": "Instalação do HD WD Purple e formatação no DVR",
                "is_checked": True,
                "checked_at": completed_11m_ago.isoformat(),
            },
            {
                "step_id": "step_4",
                "label_pt_br": "Configuração Intelbras Cloud P2P e aplicativo cliente",
                "is_checked": True,
                "checked_at": completed_11m_ago.isoformat(),
            },
            {
                "step_id": "step_5",
                "label_pt_br": "Limpeza do local e termo de aceite",
                "is_checked": True,
                "checked_at": completed_11m_ago.isoformat(),
            },
        ],
        installation_photos_keys=[
            f"photos/{org_id}/{DEMO_COMPLETED_WORK_ORDER_ID}/clinica-sao-lucas-recepcao.jpg",
            f"photos/{org_id}/{DEMO_COMPLETED_WORK_ORDER_ID}/clinica-sao-lucas-rack.jpg",
        ],
        cloud_p2p_id="ITB-P2P-771204BR",
        notes=(
            "Instalação concluída com sucesso. "
            "Garantia de 12 meses próxima do vencimento (11º mês)."
        ),
        completed_at=completed_11m_ago,
        warranty_expires_at=today + timedelta(days=25),
        preventive_maintenance_alert_sent=True,
    )
    session.add(wo_3)
    await session.flush()

    install_date_3 = completed_11m_ago.date()
    wo3_serials = [
        (sku_map["MHDX-1108"], "ITB-MHDX1108-551029", "RACK-DVR-01", 365),
        (sku_map["WD42PURZ"], "WD-WCC7K2L09182", "SATA-01", 1095),
        (sku_map["VHD-3220-D-FC"], "ITB-VHD3220FC-110201", "BNC-01 (Recepção Principal)", 365),
        (sku_map["VHD-3220-D-FC"], "ITB-VHD3220FC-110202", "BNC-02 (Sala de Espera)", 365),
        (sku_map["VHD-3220-D-FC"], "ITB-VHD3220FC-110203", "BNC-03 (Acesso Triagem)", 365),
        (sku_map["VHD-3220-D-FC"], "ITB-VHD3220FC-110204", "BNC-04 (Estacionamento Médicos)", 365),
    ]
    for item_obj, sn, label, dist_days in wo3_serials:
        session.add(
            InstalledSerial(
                organization_id=org_id,
                work_order_id=wo_3.id,
                catalog_item_id=item_obj.id,
                serial_number=sn,
                channel_or_slot_label=label,
                distributor_warranty_until=install_date_3 + timedelta(days=dist_days),
                client_warranty_until=today + timedelta(days=25),
            )
        )

    session.add(
        AuditLog(
            organization_id=org_id,
            entity_type="QUOTE",
            entity_id=quote_1.id,
            action="STATE_TRANSITION",
            actor_user_id=owner_user.id,
            actor_ip="127.0.0.1",
            previous_state={"status": "DRAFT"},
            new_state={"status": "SENT"},
        )
    )

    await session.flush()

    await _seed_minio_assets_if_reachable(
        session,
        org_id=org_id,
        quote_1_id=quote_1.id,
        quote_3_id=quote_3.id,
        wo_2_photos=wo_2.installation_photos_keys,
        wo_3_photos=wo_3.installation_photos_keys,
        storage_client=storage_client,
    )

    logger.info(
        "demo_tenant_seeded",
        organization_id=str(org_id),
        catalog_items=len(SEED_CATALOG_DEFINITIONS),
        force_reset=force_reset,
    )
    return DemoSeedSummary(
        organization_id=org_id,
        owner_user_id=owner_user.id,
        technician_user_id=tech_user.id,
        sent_quote_public_token=DEMO_SENT_QUOTE_PUBLIC_TOKEN,
        active_work_order_id=DEMO_ACTIVE_WORK_ORDER_ID,
        catalog_items_count=len(SEED_CATALOG_DEFINITIONS),
        quotes_count=3,
    )


async def _seed_minio_assets_if_reachable(
    session: AsyncSession,
    *,
    org_id: UUID,
    quote_1_id: UUID,
    quote_3_id: UUID,
    wo_2_photos: list[str],
    wo_3_photos: list[str],
    storage_client: StorageClient | None = None,
) -> None:
    """Upload sample photo JPEGs and generate real WeasyPrint PDFs if storage is reachable."""
    try:
        storage = storage_client or StorageClient()
        # 1. Upload sample photos for WO #2 and WO #3
        for photo_key in [*wo_2_photos, *wo_3_photos]:
            await storage.upload_bytes(
                object_key=photo_key,
                data=_SAMPLE_JPEG_BYTES,
                content_type="image/jpeg",
            )

        # 2. Render real WeasyPrint PDFs for Quote #1 (SENT) and Quote #3 (COMPLETED)
        from src.modules.tasks.pdf_generator import generate_and_store_quote_pdf

        await generate_and_store_quote_pdf(session, quote_1_id, storage_client=storage)
        await generate_and_store_quote_pdf(session, quote_3_id, storage_client=storage)
        logger.info("demo_minio_assets_seeded_successfully", organization_id=str(org_id))
    except Exception as exc:
        logger.warning(
            "demo_minio_assets_seeding_skipped_or_failed",
            error=str(exc),
            organization_id=str(org_id),
        )


async def _run_cli_seeder() -> None:
    """Entrypoint when invoked via `python -m src.seed.demo_seeder`."""
    configure_logging(json_logs=False)
    async with async_session_factory() as session:
        summary = await seed_demo_tenant(session, force_reset=True)
        await session.commit()
        logger.info(
            "demo_seeder_cli_completed",
            organization_id=str(summary.organization_id),
            catalog_items_count=summary.catalog_items_count,
            quotes_count=summary.quotes_count,
            sent_quote_public_token=str(summary.sent_quote_public_token),
        )


if __name__ == "__main__":
    asyncio.run(_run_cli_seeder())
