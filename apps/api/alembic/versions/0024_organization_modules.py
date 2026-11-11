"""modules of a company (lot 3): the active module keys, both on by default

Revision ID: 0024
Revises: 0023
Create Date: 2026-11-11 16:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0024"
down_revision: str | Sequence[str] | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column(
            "modules",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default="{veille,reponse}",
        ),
    )


def downgrade() -> None:
    op.drop_column("organizations", "modules")
