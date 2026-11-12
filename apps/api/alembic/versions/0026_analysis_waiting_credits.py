"""analysis waiting for credits (lot 4): a DCE deposited without enough credits

Revision ID: 0026
Revises: 0025
Create Date: 2026-11-12 09:00:00

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0026"
down_revision: str | Sequence[str] | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(op.f("ck_dce_analyses_status"), "dce_analyses", type_="check")
    op.create_check_constraint(
        op.f("ck_dce_analyses_status"),
        "dce_analyses",
        "status in ('pending','processing','ready','error','waiting_credits')",
    )


def downgrade() -> None:
    op.execute("UPDATE dce_analyses SET status = 'error' WHERE status = 'waiting_credits'")
    op.drop_constraint(op.f("ck_dce_analyses_status"), "dce_analyses", type_="check")
    op.create_check_constraint(
        op.f("ck_dce_analyses_status"),
        "dce_analyses",
        "status in ('pending','processing','ready','error')",
    )
