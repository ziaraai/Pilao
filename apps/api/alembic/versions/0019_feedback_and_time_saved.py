"""feedback from users, time spent per bid

Revision ID: 0019
Revises: 0018
Create Date: 2026-11-05 13:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0019"
down_revision: str | Sequence[str] | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Feedback from inside the application, and the time saved on each bid (P4-02)."""
    op.create_table(
        "feedback",
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("page", sa.Text(), nullable=True),
        sa.Column("bid_id", sa.UUID(), nullable=True),
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
        sa.CheckConstraint("kind in ('idea','problem','question')", name=op.f("ck_feedback_kind")),
        sa.ForeignKeyConstraint(
            ["bid_id"], ["bids.id"], name=op.f("fk_feedback_bid_id_bids"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["org_id"],
            ["organizations.id"],
            name=op.f("fk_feedback_org_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_feedback_user_id_users"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_feedback")),
    )
    op.create_index(op.f("ix_feedback_org_id"), "feedback", ["org_id"], unique=False)
    op.add_column("bids", sa.Column("minutes_with_pilao", sa.Integer()))
    op.add_column("bids", sa.Column("minutes_usual", sa.Integer()))


def downgrade() -> None:
    op.drop_column("bids", "minutes_usual")
    op.drop_column("bids", "minutes_with_pilao")
    op.drop_index(op.f("ix_feedback_org_id"), table_name="feedback")
    op.drop_table("feedback")
