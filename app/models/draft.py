from datetime import datetime
from typing import Any

from sqlalchemy import JSON, CheckConstraint, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import DraftStatus
from app.db.base import Base, CreatedAtMixin
from app.db.types import UTCDateTime, str_enum
from app.utils.time import utcnow


class DraftOrder(CreatedAtMixin, Base):
    """The one draft per `order_ref`, created from the first request that carried it."""

    __tablename__ = "draft_orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_ref: Mapped[str] = mapped_column(String(64), unique=True)
    source_request_id: Mapped[int] = mapped_column(ForeignKey("requests.id"), unique=True)
    status: Mapped[DraftStatus] = mapped_column(str_enum(DraftStatus))
    subtotal_cents: Mapped[int] = mapped_column(Integer, default=0)
    discount_cents: Mapped[int] = mapped_column(Integer, default=0)
    total_cents: Mapped[int] = mapped_column(Integer, default=0)
    # The validated model output as first proposed. Written once, never updated, so the
    # reviewer's corrections can be compared against it.
    proposal_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    # Current reasons the draft can't go straight to review (code, line, message). Derived state:
    # replaced as a whole on every validation, so a column rather than a table.
    findings: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    clarification_text: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow)
    reviewed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    lines: Mapped[list["DraftLine"]] = relationship(
        back_populates="draft_order",
        cascade="all, delete-orphan",
        lazy="raise",
        order_by="DraftLine.position",
    )
    corrections: Mapped[list["Correction"]] = relationship(
        back_populates="draft_order",
        cascade="all, delete-orphan",
        lazy="raise",
        order_by="Correction.id",
    )


class DraftLine(Base):
    """One requested item. `sku` and `quantity` stay empty when they need clarification."""

    __tablename__ = "draft_lines"
    __table_args__ = (
        UniqueConstraint("draft_order_id", "position"),
        CheckConstraint("quantity > 0", name="quantity_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    draft_order_id: Mapped[int] = mapped_column(
        ForeignKey("draft_orders.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    customer_text: Mapped[str] = mapped_column(Text)
    sku: Mapped[str | None] = mapped_column(ForeignKey("products.sku"))
    quantity: Mapped[int | None] = mapped_column(Integer)
    unit_label: Mapped[str | None] = mapped_column(String(32))
    unit_cents: Mapped[int | None] = mapped_column(Integer)
    line_cents: Mapped[int | None] = mapped_column(Integer)
    discount_cents: Mapped[int | None] = mapped_column(Integer)
    total_cents: Mapped[int | None] = mapped_column(Integer)

    draft_order: Mapped[DraftOrder] = relationship(back_populates="lines", lazy="raise")


class Correction(CreatedAtMixin, Base):
    """Append-only log of reviewer edits and the status change each one caused."""

    __tablename__ = "corrections"

    id: Mapped[int] = mapped_column(primary_key=True)
    draft_order_id: Mapped[int] = mapped_column(
        ForeignKey("draft_orders.id", ondelete="CASCADE"), index=True
    )
    draft_line_id: Mapped[int | None] = mapped_column(
        ForeignKey("draft_lines.id", ondelete="SET NULL")
    )
    field: Mapped[str] = mapped_column(String(64))
    old_value: Mapped[str | None] = mapped_column(Text)
    new_value: Mapped[str | None] = mapped_column(Text)
    status_before: Mapped[DraftStatus] = mapped_column(str_enum(DraftStatus))
    status_after: Mapped[DraftStatus] = mapped_column(str_enum(DraftStatus))

    draft_order: Mapped[DraftOrder] = relationship(back_populates="corrections", lazy="raise")
