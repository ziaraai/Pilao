"""Chiffrage (ADR-049): the company's rates and each price file of a dossier

Revision ID: 0031
Revises: 0030
Create Date: 2026-11-15 17:51:20.449274

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0031"
down_revision: str | Sequence[str] | None = "0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:

    op.create_table(
        "pricing_rates",
        sa.Column("hourly_rate_cents", sa.Integer(), nullable=True),
        sa.Column("night_pct", sa.Integer(), nullable=True),
        sa.Column("sunday_pct", sa.Integer(), nullable=True),
        sa.Column("holiday_pct", sa.Integer(), nullable=True),
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
            "hourly_rate_cents is null or hourly_rate_cents > 0", name=op.f("ck_pricing_rates_rate")
        ),
        sa.ForeignKeyConstraint(
            ["org_id"],
            ["organizations.id"],
            name=op.f("fk_pricing_rates_org_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pricing_rates")),
        sa.UniqueConstraint("org_id", name="uq_pricing_rates_org_id"),
    )
    op.create_index(op.f("ix_pricing_rates_org_id"), "pricing_rates", ["org_id"], unique=False)
    op.create_table(
        "price_sheets",
        sa.Column("bid_id", sa.UUID(), nullable=False),
        sa.Column("dce_file_id", sa.UUID(), nullable=False),
        sa.Column("source_file_id", sa.UUID(), nullable=True),
        sa.Column("filled_file_id", sa.UUID(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("lines", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("mirrors", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("warnings", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("notes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("entries", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("rate_cents", sa.Integer(), nullable=True),
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
            "status in ('reading','ready','error')", name=op.f("ck_price_sheets_status")
        ),
        sa.ForeignKeyConstraint(
            ["bid_id"], ["bids.id"], name=op.f("fk_price_sheets_bid_id_bids"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_price_sheets_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["dce_file_id"],
            ["dce_files.id"],
            name=op.f("fk_price_sheets_dce_file_id_dce_files"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["filled_file_id"],
            ["files.id"],
            name=op.f("fk_price_sheets_filled_file_id_files"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["org_id"],
            ["organizations.id"],
            name=op.f("fk_price_sheets_org_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_file_id"],
            ["files.id"],
            name=op.f("fk_price_sheets_source_file_id_files"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_price_sheets")),
        sa.UniqueConstraint("dce_file_id", name="uq_price_sheets_dce_file_id"),
    )
    op.create_index(op.f("ix_price_sheets_bid_id"), "price_sheets", ["bid_id"], unique=False)
    op.create_index(op.f("ix_price_sheets_org_id"), "price_sheets", ["org_id"], unique=False)


def downgrade() -> None:

    op.drop_index(op.f("ix_price_sheets_org_id"), table_name="price_sheets")
    op.drop_index(op.f("ix_price_sheets_bid_id"), table_name="price_sheets")
    op.drop_table("price_sheets")
    op.drop_index(op.f("ix_pricing_rates_org_id"), table_name="pricing_rates")
    op.drop_table("pricing_rates")
