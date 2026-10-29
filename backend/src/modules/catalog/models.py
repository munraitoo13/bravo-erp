"""SQLAlchemy 2.0 ORM model for catalog_items and CatalogCategory enum."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base, generate_uuid7


class CatalogCategory(StrEnum):
    """Hardware and service categories supported by the CCTV Sizing Engine and Catalog."""

    DVR = "DVR"
    CAMERA_ANALOG = "CAMERA_ANALOG"
    CAMERA_IP = "CAMERA_IP"
    HDD = "HDD"
    POWER_SUPPLY = "POWER_SUPPLY"
    POE_SWITCH = "POE_SWITCH"
    CABLE = "CABLE"
    BALUN = "BALUN"
    CONNECTOR = "CONNECTOR"
    ACCESSORY = "ACCESSORY"
    SERVICE_LABOR = "SERVICE_LABOR"


class CatalogItem(Base):
    """Equipment or labor SKU belonging to a tenant's catalog with stock tracking."""

    __tablename__ = "catalog_items"
    __table_args__ = (
        UniqueConstraint("organization_id", "sku", name="uq_catalog_items_org_sku"),
        Index("ix_catalog_items_org_category", "organization_id", "category", "is_active"),
        CheckConstraint("cost_price_cents >= 0", name="cost_price_cents_non_negative"),
        CheckConstraint("sale_price_cents >= 0", name="sale_price_cents_non_negative"),
        CheckConstraint("stock_quantity >= 0", name="stock_quantity_non_negative"),
        CheckConstraint(
            "reserved_quantity >= 0 AND stock_quantity - reserved_quantity >= 0",
            name="reserved_within_stock",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=generate_uuid7,
    )
    organization_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    sku: Mapped[str] = mapped_column(String(64), nullable=False)
    name_pt_br: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[CatalogCategory] = mapped_column(
        Enum(CatalogCategory, name="catalog_category_enum"),
        nullable=False,
    )
    brand: Mapped[str] = mapped_column(String(80), nullable=False)
    cost_price_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    sale_price_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    stock_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reserved_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    specs: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    is_seed_protected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
