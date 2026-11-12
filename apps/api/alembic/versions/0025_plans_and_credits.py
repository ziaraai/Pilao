"""plans and credits (lot 4): plans, action prices, a company's plan and credits ledger

Revision ID: 0025
Revises: 0024
Create Date: 2026-11-12 08:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0025"
down_revision: str | Sequence[str] | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _id() -> sa.Column[object]:
    return sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False)


def upgrade() -> None:
    op.create_table(
        "plans",
        _id(),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("modules", postgresql.ARRAY(sa.Text()), server_default="{}", nullable=False),
        sa.Column("monthly_credits", sa.Integer(), server_default="0", nullable=False),
        sa.Column("welcome_credits", sa.Integer(), server_default="0", nullable=False),
        sa.Column("price_note", sa.Text(), server_default="", nullable=False),
        sa.Column("is_default", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_plans")),
    )
    op.create_index("uq_plans_name_lower", "plans", [sa.text("lower(name)")], unique=True)
    op.create_index(
        "uq_plans_is_default",
        "plans",
        ["is_default"],
        unique=True,
        postgresql_where=sa.text("is_default"),
    )
    op.create_table(
        "credit_prices",
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("credits", sa.Integer(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("action", name=op.f("pk_credit_prices")),
    )
    op.execute("""
        INSERT INTO plans (name, description, modules, monthly_credits, welcome_credits, is_default)
        VALUES
          ('Pilote', 'Formule des entreprises du pilote.', '{veille,reponse}', 100, 0, false),
          ('Découverte', 'Pour découvrir Pilao : de quoi répondre à un appel d''offres.',
           '{veille,reponse}', 0, 7, true)
        """)
    op.add_column("organizations", sa.Column("plan_id", sa.UUID(), nullable=True))
    op.add_column(
        "organizations",
        sa.Column("welcome_credits_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute("UPDATE organizations SET plan_id = (SELECT id FROM plans WHERE name = 'Pilote')")
    op.alter_column("organizations", "plan_id", nullable=False)
    op.create_foreign_key(
        op.f("fk_organizations_plan_id_plans"),
        "organizations",
        "plans",
        ["plan_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_table(
        "credit_entries",
        _id(),
        sa.Column("org_id", sa.UUID(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("action", sa.Text(), nullable=True),
        sa.Column("monthly", sa.Integer(), server_default="0", nullable=False),
        sa.Column("extra", sa.Integer(), server_default="0", nullable=False),
        sa.Column("month", sa.Date(), nullable=True),
        sa.Column("bid_id", sa.UUID(), nullable=True),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("platform_admin_id", sa.UUID(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("ref_id", sa.UUID(), nullable=True),
        sa.Column("refund_of", sa.UUID(), nullable=True),
        sa.CheckConstraint(
            "kind IN ('charge', 'refund', 'grant', 'welcome')",
            name=op.f("ck_credit_entries_credit_entries_kind"),
        ),
        sa.ForeignKeyConstraint(
            ["org_id"],
            ["organizations.id"],
            name=op.f("fk_credit_entries_org_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["bid_id"], ["bids.id"], name=op.f("fk_credit_entries_bid_id_bids"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_credit_entries_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["platform_admin_id"],
            ["platform_admins.id"],
            name=op.f("fk_credit_entries_platform_admin_id_platform_admins"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["refund_of"],
            ["credit_entries.id"],
            name=op.f("fk_credit_entries_refund_of_credit_entries"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_credit_entries")),
        sa.UniqueConstraint("refund_of", name=op.f("uq_credit_entries_refund_of")),
    )
    op.create_index(op.f("ix_credit_entries_org_id"), "credit_entries", ["org_id"])
    op.create_index(op.f("ix_credit_entries_ref_id"), "credit_entries", ["ref_id"])
    op.create_index("ix_credit_entries_org_at", "credit_entries", ["org_id", "at"])
    op.create_index("ix_credit_entries_org_month", "credit_entries", ["org_id", "month"])


def downgrade() -> None:
    op.drop_table("credit_entries")
    op.drop_constraint(op.f("fk_organizations_plan_id_plans"), "organizations", type_="foreignkey")
    op.drop_column("organizations", "welcome_credits_at")
    op.drop_column("organizations", "plan_id")
    op.drop_table("credit_prices")
    op.drop_table("plans")
