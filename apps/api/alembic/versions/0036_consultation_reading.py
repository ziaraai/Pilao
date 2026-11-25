"""Consultations read from their documents: the quote's own number, price files read from
a PDF or Word document (25/11)

Revision ID: 0036
Revises: 0035
Create Date: 2026-11-25 10:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0036"
down_revision: str | Sequence[str] | None = "0035"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("bids", sa.Column("contact_phone", sa.Text(), nullable=True))
    op.add_column("bids", sa.Column("client_address", sa.Text(), nullable=True))
    op.add_column("bids", sa.Column("site_address", sa.Text(), nullable=True))
    op.add_column(
        "bids",
        sa.Column(
            "facts_sources",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
    )
    op.add_column("quotes", sa.Column("custom_number", sa.Text(), nullable=True))
    op.add_column(
        "price_sheets", sa.Column("mode", sa.Text(), server_default="grid", nullable=False)
    )
    op.create_check_constraint(
        op.f("ck_price_sheets_mode"), "price_sheets", "mode in ('grid','document')"
    )
    op.add_column(
        "price_sheets",
        sa.Column("included", sa.Boolean(), server_default=sa.false(), nullable=False),
    )

    op.create_table(
        "consultation_reads",
        sa.Column("bid_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("found", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("price_files", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("org_id", sa.UUID(), nullable=False),
        sa.CheckConstraint(
            "status in ('reading','ready','error','waiting_credits')",
            name=op.f("ck_consultation_reads_status"),
        ),
        sa.ForeignKeyConstraint(
            ["bid_id"],
            ["bids.id"],
            name=op.f("fk_consultation_reads_bid_id_bids"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_consultation_reads_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["org_id"],
            ["organizations.id"],
            name=op.f("fk_consultation_reads_org_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_consultation_reads")),
        sa.UniqueConstraint("bid_id", name="uq_consultation_reads_bid_id"),
    )
    op.create_index(
        op.f("ix_consultation_reads_org_id"), "consultation_reads", ["org_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_consultation_reads_org_id"), table_name="consultation_reads")
    op.drop_table("consultation_reads")
    op.drop_column("price_sheets", "included")
    op.drop_constraint(op.f("ck_price_sheets_mode"), "price_sheets", type_="check")
    op.drop_column("price_sheets", "mode")
    op.drop_column("quotes", "custom_number")
    for column in ("facts_sources", "site_address", "client_address", "contact_phone"):
        op.drop_column("bids", column)
