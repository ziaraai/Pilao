"""account management from the administration: suspension, deletion scheduled by Pilao

Revision ID: 0023
Revises: 0022
Create Date: 2026-11-11 10:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0023"
down_revision: str | Sequence[str] | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("organizations", sa.Column("suspended_at", sa.DateTime(timezone=True)))
    op.add_column("organizations", sa.Column("suspension_reason", sa.Text()))
    op.add_column(
        "data_requests",
        sa.Column(
            "platform_admin_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("platform_admins.id", ondelete="SET NULL"),
        ),
    )


def downgrade() -> None:
    op.drop_column("data_requests", "platform_admin_id")
    op.drop_column("organizations", "suspension_reason")
    op.drop_column("organizations", "suspended_at")
