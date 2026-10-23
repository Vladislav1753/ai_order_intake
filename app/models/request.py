from datetime import datetime
from typing import Any

from sqlalchemy import JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import RequestStatus
from app.db.base import Base, CreatedAtMixin
from app.db.types import UTCDateTime, str_enum


class IncomingRequest(CreatedAtMixin, Base):
    """One customer message as received. Linked to its draft through `order_ref`."""

    __tablename__ = "requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[str] = mapped_column(String(64), unique=True)
    order_ref: Mapped[str] = mapped_column(String(64), index=True)
    text: Mapped[str] = mapped_column(Text)
    source_path: Mapped[str | None] = mapped_column(String(500))
    content_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[RequestStatus] = mapped_column(
        str_enum(RequestStatus), default=RequestStatus.PENDING
    )
    error: Mapped[str | None] = mapped_column(Text)
    processed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    # Every provider round trip of the extraction loop, raw, in order:
    # step, source (live | cached | simulated-failure), prompt version and hash, request,
    # response or error. Includes the catalog searches the model made and what they returned.
    model_calls: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
