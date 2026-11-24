"""DCE e-mail address: the company's code and the e-mails received

Revision ID: 0035
Revises: 0034
Create Date: 2026-11-24 10:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0035"
down_revision: str | Sequence[str] | None = "0034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("organizations", sa.Column("dce_mail_code", sa.Text(), nullable=True))
    op.create_unique_constraint(
        op.f("uq_organizations_dce_mail_code"), "organizations", ["dce_mail_code"]
    )
    op.create_table(
        "inbound_mails",
        sa.Column("message_id", sa.Text(), nullable=False),
        sa.Column("sender", sa.Text(), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("bid_id", sa.UUID(), nullable=True),
        sa.Column("suggested_bid_id", sa.UUID(), nullable=True),
        sa.Column("file_ids", postgresql.ARRAY(sa.UUID()), nullable=False),
        sa.Column("attachment_names", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("skipped", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("links", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
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
        sa.CheckConstraint("kind in ('dce','notice')", name=op.f("ck_inbound_mails_kind")),
        sa.CheckConstraint(
            "status in ('to_sort','filed','ignored')", name=op.f("ck_inbound_mails_status")
        ),
        sa.ForeignKeyConstraint(
            ["bid_id"], ["bids.id"], name=op.f("fk_inbound_mails_bid_id_bids"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["suggested_bid_id"],
            ["bids.id"],
            name=op.f("fk_inbound_mails_suggested_bid_id_bids"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["org_id"],
            ["organizations.id"],
            name=op.f("fk_inbound_mails_org_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_inbound_mails")),
        sa.UniqueConstraint("org_id", "message_id", name="uq_inbound_mails_org_id_message_id"),
    )
    op.create_index(op.f("ix_inbound_mails_org_id"), "inbound_mails", ["org_id"], unique=False)
    op.create_index(op.f("ix_inbound_mails_bid_id"), "inbound_mails", ["bid_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_inbound_mails_bid_id"), table_name="inbound_mails")
    op.drop_index(op.f("ix_inbound_mails_org_id"), table_name="inbound_mails")
    op.drop_table("inbound_mails")
    op.drop_constraint(op.f("uq_organizations_dce_mail_code"), "organizations", type_="unique")
    op.drop_column("organizations", "dce_mail_code")
