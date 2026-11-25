"""Consultations read from their documents: the quote's own number (25/11)

Revision ID: 0036
Revises: 0035
Create Date: 2026-11-25 10:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0036"
down_revision: str | Sequence[str] | None = "0035"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("quotes", sa.Column("custom_number", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("quotes", "custom_number")
