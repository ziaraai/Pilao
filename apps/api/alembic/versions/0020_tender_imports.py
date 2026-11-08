"""tender imports: one row per pass of the BOAMP / TED readers

Revision ID: 0020
Revises: 0019
Create Date: 2026-11-08 09:30:00

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0020"
down_revision: str | Sequence[str] | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """The cursor and the log of the scheduled notice imports (P3-01, P3-02)."""
    op.create_table(
        "tender_imports",
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("since", sa.Date(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fetched", sa.Integer(), nullable=False),
        sa.Column("skipped", sa.Integer(), nullable=False),
        sa.Column("created", sa.Integer(), nullable=False),
        sa.Column("updated", sa.Integer(), nullable=False),
        sa.Column("corrected", sa.Integer(), nullable=False),
        sa.Column("matched", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
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
        sa.CheckConstraint("source in ('boamp','ted')", name=op.f("ck_tender_imports_source")),
        sa.CheckConstraint(
            "status in ('running','done','error')", name=op.f("ck_tender_imports_status")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tender_imports")),
    )
    op.create_index(
        "ix_tender_imports_source_created_at",
        "tender_imports",
        ["source", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_tender_imports_source_created_at", table_name="tender_imports")
    op.drop_table("tender_imports")
