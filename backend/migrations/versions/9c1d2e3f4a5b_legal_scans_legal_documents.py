"""legal_scans, legal_documents

Revision ID: 9c1d2e3f4a5b
Revises: f7249c1bc003
Create Date: 2026-10-11 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "9c1d2e3f4a5b"
down_revision: Union[str, Sequence[str], None] = "f7249c1bc003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "legal_scans",
        sa.Column("chat_id", sa.BigInteger(), nullable=True),
        sa.Column("scope", sa.String(length=255), nullable=False),
        sa.Column("counts", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("TIMEZONE('UTC', now())"),
            nullable=False,
        ),
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_legal_scans_chat_id"), "legal_scans", ["chat_id"], unique=False)
    op.create_index(op.f("ix_legal_scans_user_id"), "legal_scans", ["user_id"], unique=False)
    op.create_table(
        "legal_documents",
        sa.Column("scan_id", sa.Uuid(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column(
            "sections", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("TIMEZONE('UTC', now())"),
            nullable=False,
        ),
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.ForeignKeyConstraint(["scan_id"], ["legal_scans.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_legal_documents_scan_id"), "legal_documents", ["scan_id"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_legal_documents_scan_id"), table_name="legal_documents")
    op.drop_table("legal_documents")
    op.drop_index(op.f("ix_legal_scans_user_id"), table_name="legal_scans")
    op.drop_index(op.f("ix_legal_scans_chat_id"), table_name="legal_scans")
    op.drop_table("legal_scans")
