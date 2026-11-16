"""The memoir written into the buyer's frame (ADR-051): a new kind of generated document

Revision ID: 0032
Revises: 0031
Create Date: 2026-11-16 08:00:00

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0032"
down_revision: str | Sequence[str] | None = "0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BEFORE = (
    "dc1", "dc2", "staff_list", "equipment_list", "references_list", "planning",
    "memoir_docx", "memoir_pdf", "bundle_zip",
)  # fmt: skip
AFTER = (*BEFORE, "memoir_frame_docx")


def _kinds(kinds: tuple[str, ...]) -> str:
    return "kind in (" + ",".join(f"'{k}'" for k in kinds) + ")"


def upgrade() -> None:
    op.drop_constraint(op.f("ck_generated_documents_kind"), "generated_documents", type_="check")
    op.create_check_constraint(
        op.f("ck_generated_documents_kind"), "generated_documents", _kinds(AFTER)
    )


def downgrade() -> None:
    op.execute("DELETE FROM generated_documents WHERE kind = 'memoir_frame_docx'")
    op.drop_constraint(op.f("ck_generated_documents_kind"), "generated_documents", type_="check")
    op.create_check_constraint(
        op.f("ck_generated_documents_kind"), "generated_documents", _kinds(BEFORE)
    )
