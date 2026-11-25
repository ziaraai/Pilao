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


def downgrade() -> None:
    op.drop_constraint(op.f("ck_price_sheets_mode"), "price_sheets", type_="check")
    op.drop_column("price_sheets", "mode")
    op.drop_column("quotes", "custom_number")
    for column in ("facts_sources", "site_address", "client_address", "contact_phone"):
        op.drop_column("bids", column)
