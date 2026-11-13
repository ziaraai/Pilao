"""DCE retrieval: the robot's attempts, the company's mode and contact, the dossier's link and
watch, the origin of each DCE version

Revision ID: 0028
Revises: 0027
Create Date: 2026-11-13 17:22:39

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0028"
down_revision: str | Sequence[str] | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "dce_fetches",
        sa.Column("bid_id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("mode", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("outcome", sa.Text(), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("site", sa.Text(), nullable=False),
        sa.Column("size_label", sa.Text(), nullable=True),
        sa.Column("dce_version_id", sa.UUID(), nullable=True),
        sa.Column("requested_by", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("org_id", sa.UUID(), nullable=False),
        sa.CheckConstraint(
            "kind in ('retrieval','update','check')", name=op.f("ck_dce_fetches_kind")
        ),
        sa.CheckConstraint(
            "mode is null or mode in ('identified','anonymous')", name=op.f("ck_dce_fetches_mode")
        ),
        sa.CheckConstraint(
            "status in ('pending','running','done','error')", name=op.f("ck_dce_fetches_status")
        ),
        sa.ForeignKeyConstraint(
            ["bid_id"], ["bids.id"], name=op.f("fk_dce_fetches_bid_id_bids"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["dce_version_id"],
            ["dce_versions.id"],
            name=op.f("fk_dce_fetches_dce_version_id_dce_versions"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["org_id"],
            ["organizations.id"],
            name=op.f("fk_dce_fetches_org_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by"],
            ["users.id"],
            name=op.f("fk_dce_fetches_requested_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dce_fetches")),
    )
    op.create_index(
        "ix_dce_fetches_bid_created",
        "dce_fetches",
        ["bid_id", sa.literal_column("created_at DESC")],
        unique=False,
    )
    op.create_index(op.f("ix_dce_fetches_org_id"), "dce_fetches", ["org_id"], unique=False)
    op.create_index(
        "ix_dce_fetches_status_created", "dce_fetches", ["status", "created_at"], unique=False
    )
    op.create_index(
        "uq_dce_fetches_one_active_per_bid",
        "dce_fetches",
        ["bid_id"],
        unique=True,
        postgresql_where=sa.text(
            "status in ('pending','running') and kind in ('retrieval','update')"
        ),
    )
    op.add_column("bids", sa.Column("dce_url", sa.Text(), nullable=True))
    op.add_column(
        "bids", sa.Column("dce_watch", postgresql.JSONB(astext_type=sa.Text()), nullable=True)
    )
    op.add_column(
        "dce_versions", sa.Column("origin", sa.Text(), server_default="deposit", nullable=False)
    )
    op.add_column("dce_versions", sa.Column("source_url", sa.Text(), nullable=True))
    op.add_column("organizations", sa.Column("dce_retrieval_mode", sa.Text(), nullable=True))
    op.add_column("organizations", sa.Column("buyer_contact_first_name", sa.Text(), nullable=True))
    op.add_column("organizations", sa.Column("buyer_contact_last_name", sa.Text(), nullable=True))
    op.add_column("organizations", sa.Column("buyer_contact_email", sa.Text(), nullable=True))
    op.create_check_constraint(
        op.f("ck_dce_versions_origin"), "dce_versions", "origin in ('deposit','retrieval','update')"
    )
    op.create_check_constraint(
        op.f("ck_organizations_dce_retrieval_mode"),
        "organizations",
        "dce_retrieval_mode is null or dce_retrieval_mode in ('identified','anonymous')",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_organizations_dce_retrieval_mode"), "organizations", type_="check")
    op.drop_constraint(op.f("ck_dce_versions_origin"), "dce_versions", type_="check")
    op.drop_column("organizations", "buyer_contact_email")
    op.drop_column("organizations", "buyer_contact_last_name")
    op.drop_column("organizations", "buyer_contact_first_name")
    op.drop_column("organizations", "dce_retrieval_mode")
    op.drop_column("dce_versions", "source_url")
    op.drop_column("dce_versions", "origin")
    op.drop_column("bids", "dce_watch")
    op.drop_column("bids", "dce_url")
    op.drop_index(
        "uq_dce_fetches_one_active_per_bid",
        table_name="dce_fetches",
        postgresql_where=sa.text(
            "status in ('pending','running') and kind in ('retrieval','update')"
        ),
    )
    op.drop_index("ix_dce_fetches_status_created", table_name="dce_fetches")
    op.drop_index(op.f("ix_dce_fetches_org_id"), table_name="dce_fetches")
    op.drop_index("ix_dce_fetches_bid_created", table_name="dce_fetches")
    op.drop_table("dce_fetches")
