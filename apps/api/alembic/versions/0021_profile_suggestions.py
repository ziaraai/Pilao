"""profile suggestions: profile lines proposed from the company's documents

Revision ID: 0021
Revises: 0020
Create Date: 2026-11-09 10:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0021"
down_revision: str | Sequence[str] | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Proposals read from the knowledge base, waiting for the user's decision (US-1.6)."""
    op.create_table(
        "profile_suggestions",
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("missing", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("page", sa.SmallInteger(), nullable=True),
        sa.Column("heading", sa.Text(), nullable=True),
        sa.Column("excerpt", sa.Text(), nullable=False),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
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
        sa.CheckConstraint(
            "kind in ('human_resource','equipment','certification','reference')",
            name=op.f("ck_profile_suggestions_kind"),
        ),
        sa.CheckConstraint(
            "status in ('pending','accepted','dismissed')",
            name=op.f("ck_profile_suggestions_status"),
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["knowledge_documents.id"],
            name=op.f("fk_profile_suggestions_document_id_knowledge_documents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["org_id"],
            ["organizations.id"],
            name=op.f("fk_profile_suggestions_org_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_profile_suggestions")),
    )
    op.create_index(
        op.f("ix_profile_suggestions_org_id"), "profile_suggestions", ["org_id"], unique=False
    )
    op.create_index(
        "ix_profile_suggestions_org_id_status",
        "profile_suggestions",
        ["org_id", "status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_profile_suggestions_org_id_status", table_name="profile_suggestions")
    op.drop_index(op.f("ix_profile_suggestions_org_id"), table_name="profile_suggestions")
    op.drop_table("profile_suggestions")
