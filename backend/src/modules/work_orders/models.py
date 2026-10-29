"""SQLAlchemy 2.0 ORM models for work_orders and installed_serials."""

from datetime import date, datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base, generate_uuid7
from src.modules.catalog.models import CatalogItem
from src.modules.quotes.models import Quote
from src.modules.tenants.models import User


class WorkOrderStatus(StrEnum):
    """Lifecycle states of a field installation Work Order."""

    PENDING = "PENDING"
    SCHEDULED = "SCHEDULED"
    IN_FIELD = "IN_FIELD"
    COMPLETED = "COMPLETED"


class WorkOrder(Base):
    """Field installation work order generated atomically when a Quote is approved."""

    __tablename__ = "work_orders"
    __table_args__ = (
        UniqueConstraint("quote_id", name="uq_work_orders_quote_id"),
        Index("ix_work_orders_org_status", "organization_id", "status"),
        Index(
            "ix_work_orders_warranty_scan",
            "organization_id",
            "warranty_expires_at",
            "preventive_maintenance_alert_sent",
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
    quote_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("quotes.id", ondelete="RESTRICT"),
        nullable=False,
    )
    assigned_technician_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        default=None,
    )
    status: Mapped[WorkOrderStatus] = mapped_column(
        Enum(WorkOrderStatus, name="work_order_status_enum"),
        nullable=False,
        default=WorkOrderStatus.PENDING,
    )
    checklist_json: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    installation_photos_keys: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    cloud_p2p_id: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )
    warranty_expires_at: Mapped[date | None] = mapped_column(Date, nullable=True, default=None)
    preventive_maintenance_alert_sent: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
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

    quote: Mapped["Quote"] = relationship(
        back_populates="work_order",
        lazy="selectin",
    )
    assigned_technician: Mapped["User | None"] = relationship(
        lazy="selectin",
    )
    installed_serials: Mapped[list["InstalledSerial"]] = relationship(
        back_populates="work_order",
        lazy="selectin",
        cascade="all, delete-orphan",
    )


class InstalledSerial(Base):
    """Hardware Serial Number Vault entry registered during field work execution."""

    __tablename__ = "installed_serials"
    __table_args__ = (
        Index("ix_installed_serials_org_sn", "organization_id", "serial_number"),
        Index("ix_installed_serials_work_order", "work_order_id"),
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
    work_order_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("work_orders.id", ondelete="CASCADE"),
        nullable=False,
    )
    catalog_item_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("catalog_items.id", ondelete="RESTRICT"),
        nullable=False,
    )
    serial_number: Mapped[str] = mapped_column(Text, nullable=False)
    channel_or_slot_label: Mapped[str] = mapped_column(Text, nullable=False)
    distributor_warranty_until: Mapped[date] = mapped_column(Date, nullable=False)
    client_warranty_until: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    work_order: Mapped["WorkOrder"] = relationship(
        back_populates="installed_serials",
        lazy="raise",
    )
    catalog_item: Mapped["CatalogItem"] = relationship(
        lazy="selectin",
    )
