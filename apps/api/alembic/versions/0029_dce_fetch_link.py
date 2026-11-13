"""DCE retrieval: each attempt keeps the link it was for (final review: a new link starts afresh)

Revision ID: 0029
Revises: 0028
Create Date: 2026-11-13 21:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0029"
down_revision: str | Sequence[str] | None = "0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("dce_fetches", sa.Column("source_url", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("dce_fetches", "source_url")
