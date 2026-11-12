"""Phase 0 with lot 5: the model under evaluation wins over a model set in the administration
(final review)."""

from sqlalchemy.orm import Session

from app import evaluation
from app.ai import llm
from tests.core.test_runtime import put


def test_the_model_under_evaluation_wins_over_the_administration(db: Session) -> None:
    put(db, "model.dce_extraction", "openrouter/admin-choice")
    with evaluation.models("openrouter/under-evaluation"):
        for task in (
            "dce_extraction",
            "memoir_generation",
            "memoir_regeneration",
            "tender_scoring",
        ):
            assert llm.model_for(task) == "openrouter/under-evaluation"
    assert llm.model_for("dce_extraction") == "openrouter/admin-choice"
