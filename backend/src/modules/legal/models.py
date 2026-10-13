"""SQLAlchemy models for legal scan history (issue #61).

The first non-user tables: one row per business/card scan with the full
report payload, plus per-document metadata rows. Retention: see
``history.LEGAL_SCAN_RETENTION_DAYS``.
"""

from uuid import UUID
from typing import Any

from sqlalchemy import JSON, BigInteger, ForeignKey, Integer, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import UUIDBase, str_255, timestamp


class LegalScan(UUIDBase):
    __tablename__ = "legal_scans"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    scope: Mapped[str_255]  # "card" | "business"
    counts: Mapped[dict[str, int]] = mapped_column(JSON, default=dict)
    result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[timestamp]

    documents: Mapped[list["LegalDocument"]] = relationship(
        back_populates="scan",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class LegalDocument(UUIDBase):
    __tablename__ = "legal_documents"

    scan_id: Mapped[UUID] = mapped_column(
        ForeignKey("legal_scans.id", ondelete="CASCADE"),
        index=True,
    )
    filename: Mapped[str_255]
    sections: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    created_at: Mapped[timestamp]

    scan: Mapped[LegalScan] = relationship(back_populates="documents")
