"""DCE deposited in several goes: pieces added to a version, analysis on the user's go

Revision ID: 0034
Revises: 0033
Create Date: 2026-11-23 18:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0034"
down_revision: str | Sequence[str] | None = "0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "dce_versions",
        sa.Column("auto_analysis", sa.Boolean(), server_default=sa.true(), nullable=False),
    )
    op.add_column(
        "dce_versions", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "dce_versions",
        sa.Column(
            "read_file_ids",
            postgresql.ARRAY(sa.UUID()),
            server_default=sa.text("'{}'::uuid[]"),
            nullable=False,
        ),
    )
    # the versions already read: their deposited files are not read again by an addition
    op.execute(
        "UPDATE dce_versions SET read_file_ids = source_file_ids WHERE status in ('ready','error')"
    )
    op.add_column("dce_files", sa.Column("source_file_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        op.f("fk_dce_files_source_file_id_files"),
        "dce_files",
        "files",
        ["source_file_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("fk_dce_files_source_file_id_files"), "dce_files", type_="foreignkey")
    op.drop_column("dce_files", "source_file_id")
    op.drop_column("dce_versions", "read_file_ids")
    op.drop_column("dce_versions", "completed_at")
    op.drop_column("dce_versions", "auto_analysis")
