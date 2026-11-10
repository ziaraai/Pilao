"""platform administration: super admin accounts, their sessions and their audit log

Revision ID: 0022
Revises: 0021
Create Date: 2026-11-10 10:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0022"
down_revision: str | Sequence[str] | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _admin_columns() -> list[sa.Column[object]]:
    return [
        sa.Column("full_name", sa.Text(), nullable=True),
        sa.Column("password_hash", sa.Text(), nullable=True),
        sa.Column("totp_secret_enc", sa.Text(), nullable=True),
        sa.Column("totp_confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("totp_last_step", sa.BigInteger(), nullable=True),
        sa.Column(
            "recovery_codes",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("setup_token_hash", sa.CHAR(length=64), nullable=True),
        sa.Column("setup_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
    ]


def upgrade() -> None:
    """A super admin account apart from any company account (ADR-040, US-6.1 to US-6.3)."""
    for column in _admin_columns():
        op.add_column("platform_admins", column)
    op.create_unique_constraint(
        op.f("uq_platform_admins_setup_token_hash"), "platform_admins", ["setup_token_hash"]
    )
    op.create_table(
        "platform_admin_sessions",
        sa.Column("admin_id", sa.UUID(), nullable=False),
        sa.Column("token_hash", sa.CHAR(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("ip", postgresql.INET(), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["admin_id"],
            ["platform_admins.id"],
            name=op.f("fk_platform_admin_sessions_admin_id_platform_admins"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_platform_admin_sessions")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_platform_admin_sessions_token_hash")),
    )
    op.create_index(
        op.f("ix_platform_admin_sessions_admin_id"),
        "platform_admin_sessions",
        ["admin_id"],
        unique=False,
    )
    op.create_table(
        "platform_audit_logs",
        sa.Column("admin_id", sa.UUID(), nullable=True),
        sa.Column("admin_email", sa.Text(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("org_id", sa.UUID(), nullable=True),
        sa.Column(
            "at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("ip", postgresql.INET(), nullable=True),
        sa.Column("meta", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["admin_id"],
            ["platform_admins.id"],
            name=op.f("fk_platform_audit_logs_admin_id_platform_admins"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_platform_audit_logs")),
    )
    op.create_index(
        "ix_platform_audit_logs_action_at", "platform_audit_logs", ["action", "at"], unique=False
    )
    op.create_index(
        op.f("ix_platform_audit_logs_org_id"), "platform_audit_logs", ["org_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_platform_audit_logs_org_id"), table_name="platform_audit_logs")
    op.drop_index("ix_platform_audit_logs_action_at", table_name="platform_audit_logs")
    op.drop_table("platform_audit_logs")
    op.drop_index(op.f("ix_platform_admin_sessions_admin_id"), table_name="platform_admin_sessions")
    op.drop_table("platform_admin_sessions")
    op.drop_constraint(
        op.f("uq_platform_admins_setup_token_hash"), "platform_admins", type_="unique"
    )
    for column in reversed(_admin_columns()):
        op.drop_column("platform_admins", column.name)
