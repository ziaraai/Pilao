"""Phase 0 with the real credits (lot 4): the evaluated company is never stopped by its balance."""

from pathlib import Path

import pytest
from sqlalchemy import Connection

from app.ai import llm
from app.evaluation import run_evaluation
from tests.conftest import _new_session
from tests.test_evaluation import GOOD, TwoModels, samples

REAL_CREDITS = True  # the plans as seeded: the default « Découverte » has 0 monthly credits


def test_the_evaluated_company_has_credits_for_every_paid_step(
    conn: Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(llm, "_call_provider", TwoModels())

    runs = run_evaluation(
        samples(tmp_path / "samples"), [GOOD], tmp_path / "o", lambda: _new_session(conn), seed=3
    )

    [run] = [r for r in runs if r.dce == "lyon"]
    assert run.analysis_status == "ready", run.error
    assert run.error is None
    assert run.chapters > 0
