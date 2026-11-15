"""« Ce qu'il manque » (ADR-048): each request to complete a missing item with the AI

Revision ID: 0030
Revises: 0029
Create Date: 2026-11-15 12:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0030"
down_revision: str | Sequence[str] | None = "0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "marker_fills",
        sa.Column("memoir_id", sa.UUID(), nullable=False),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("marker_text", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("outcome", sa.Text(), nullable=True),
        sa.Column("sections_filled", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("org_id", sa.UUID(), nullable=False),
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
        sa.CheckConstraint(
            "status in ('pending','running','done','error')", name=op.f("ck_marker_fills_status")
        ),
        sa.CheckConstraint(
            "outcome is null or outcome in ('filled','not_enough')",
            name=op.f("ck_marker_fills_outcome"),
        ),
        sa.ForeignKeyConstraint(
            ["memoir_id"],
            ["memoirs.id"],
            name=op.f("fk_marker_fills_memoir_id_memoirs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_marker_fills_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["org_id"],
            ["organizations.id"],
            name=op.f("fk_marker_fills_org_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_marker_fills")),
    )
    op.create_index("ix_marker_fills_memoir_key", "marker_fills", ["memoir_id", "key"])
    op.create_index(op.f("ix_marker_fills_org_id"), "marker_fills", ["org_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_marker_fills_org_id"), table_name="marker_fills")
    op.drop_index("ix_marker_fills_memoir_key", table_name="marker_fills")
    op.drop_table("marker_fills")
