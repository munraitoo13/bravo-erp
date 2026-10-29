"""SQLAlchemy 2.0 ORM models for customers, quotes, quote_items, audit_logs, and outbox_events."""

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    CHAR,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base, generate_uuid7
from src.modules.catalog.models import CatalogItem

if TYPE_CHECKING:
    from src.modules.work_orders.models import WorkOrder


class QuoteStatus(StrEnum):
    """Lifecycle states of a commercial proposal (Quote)."""

    DRAFT = "DRAFT"
    SENT = "SENT"
    APPROVED = "APPROVED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELED = "CANCELED"
    EXPIRED = "EXPIRED"


class OutboxStatus(StrEnum):
    """Processing states of a transactional outbox event."""

    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    PROCESSED = "PROCESSED"
    FAILED = "FAILED"


class Customer(Base):
    """Client receiving commercial proposals and CCTV installations."""

    __tablename__ = "customers"
    __table_args__ = (Index("ix_customers_org_doc", "organization_id", "document_cpf_cnpj"),)

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
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    document_cpf_cnpj: Mapped[str] = mapped_column(String(20), nullable=False)
    phone_whatsapp: Mapped[str] = mapped_column(String(30), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    address_json: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    quotes: Mapped[list["Quote"]] = relationship(
        back_populates="customer",
        lazy="raise",
    )


class Quote(Base):
    """Commercial proposal containing sized CCTV BOM items and cryptographic PDF metadata."""

    __tablename__ = "quotes"
    __table_args__ = (
        UniqueConstraint("public_token", name="uq_quotes_public_token"),
        UniqueConstraint("pdf_sha256_hash", name="uq_quotes_pdf_sha256_hash"),
        Index(
            "ix_quotes_org_status_created",
            "organization_id",
            "status",
            text("created_at DESC"),
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
    customer_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="RESTRICT"),
        nullable=False,
    )
    public_token: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=False,
        default=uuid.uuid4,
    )
    status: Mapped[QuoteStatus] = mapped_column(
        Enum(QuoteStatus, name="quote_status_enum"),
        nullable=False,
        default=QuoteStatus.DRAFT,
    )
    sizing_input_json: Mapped[dict[str, object] | None] = mapped_column(
        JSONB,
        nullable=True,
        default=None,
    )
    total_cost_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_sale_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    margin_percent: Mapped[Decimal] = mapped_column(
        Numeric(6, 2),
        nullable=False,
        default=Decimal("0.00"),
    )
    valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )
    approved_by_ip: Mapped[str | None] = mapped_column(INET, nullable=True, default=None)
    pdf_storage_key: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    pdf_sha256_hash: Mapped[str | None] = mapped_column(CHAR(64), nullable=True, default=None)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
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

    customer: Mapped["Customer"] = relationship(
        back_populates="quotes",
        lazy="selectin",
    )
    items: Mapped[list["QuoteItem"]] = relationship(
        back_populates="quote",
        lazy="selectin",
        cascade="all, delete-orphan",
    )
    work_order: Mapped["WorkOrder | None"] = relationship(
        back_populates="quote",
        lazy="raise",
        uselist=False,
    )


class QuoteItem(Base):
    """Line item inside a Quote referencing a CatalogItem with frozen unit cost and sale cents."""

    __tablename__ = "quote_items"
    __table_args__ = (
        Index("ix_quote_items_quote_id", "quote_id"),
        Index("ix_quote_items_org_catalog", "organization_id", "catalog_item_id"),
        CheckConstraint("quantity > 0", name="quantity_positive"),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=generate_uuid7,
    )
    quote_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("quotes.id", ondelete="CASCADE"),
        nullable=False,
    )
    organization_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    catalog_item_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("catalog_items.id", ondelete="RESTRICT"),
        nullable=False,
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_cost_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_sale_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    is_auto_derived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    quote: Mapped["Quote"] = relationship(
        back_populates="items",
        lazy="raise",
    )
    catalog_item: Mapped["CatalogItem"] = relationship(
        lazy="selectin",
    )


class AuditLog(Base):
    """Immutable audit log recording state transitions and critical entity mutations."""

    __tablename__ = "audit_logs"
    __table_args__ = (
        Index(
            "ix_audit_logs_org_entity",
            "organization_id",
            "entity_type",
            "entity_id",
            text("created_at DESC"),
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
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    actor_user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
        default=None,
    )
    actor_ip: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    previous_state: Mapped[dict[str, object] | None] = mapped_column(
        JSONB,
        nullable=True,
        default=None,
    )
    new_state: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class OutboxEvent(Base):
    """Transactional Outbox table for reliable asynchronous Taskiq event dispatch."""

    __tablename__ = "outbox_events"
    __table_args__ = (
        Index(
            "ix_outbox_events_poll",
            "status",
            "next_retry_at",
            "created_at",
            postgresql_where=text("status = 'PENDING'"),
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
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    status: Mapped[OutboxStatus] = mapped_column(
        Enum(OutboxStatus, name="outbox_status_enum"),
        nullable=False,
        default=OutboxStatus.PENDING,
    )
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_retry_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
