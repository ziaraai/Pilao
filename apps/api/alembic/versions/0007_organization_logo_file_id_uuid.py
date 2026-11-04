"""organizations.logo_file_id as uuid

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-04 15:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007"
down_revision: str | Sequence[str] | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column(
        "organizations",
        "logo_file_id",
        existing_type=sa.Text(),
        type_=sa.UUID(),
        existing_nullable=True,
        postgresql_using="logo_file_id::uuid",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column(
        "organizations",
        "logo_file_id",
        existing_type=sa.UUID(),
        type_=sa.Text(),
        existing_nullable=True,
        postgresql_using="logo_file_id::text",
    )
