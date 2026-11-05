"""Phase 0 harness (docs/11, P0-02 to P0-06): two "models" on a synthetic DCE, end to end."""

import json
import zipfile
from pathlib import Path
from typing import Any

import pytest
from docx import Document
from openpyxl import load_workbook
from sqlalchemy import Connection, func, select

from app import cli
from app.ai import llm
from app.core.config import get_settings
from app.db.models import Organization
from app.evaluation import compare, run_evaluation, similar
from tests.api.test_analysis import CCTP, DEADLINE, RC, SRC_CCTP, SRC_RC
from tests.api.test_bids import zipped
from tests.api.test_memoir_drafting import WriterModel, quote_everything
from tests.conftest import _new_session
from tests.documents_helpers import make_docx

GOOD, BROKEN = "test/bon-modele", "test/modele-en-panne"


class TwoModels(WriterModel):
    """The extraction of ``FakeModel`` for both; ``BROKEN`` cannot write a chapter."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[str] = []
        self.matrix = quote_everything

    def __call__(
        self, model: str, messages: list[dict[str, Any]], max_tokens: int | None = None
    ) -> tuple[str, int, int, float]:
        self.calls.append(model)
        self.outage = model == BROKEN
        return super().__call__(model, messages, max_tokens)


def expected_sheet() -> dict[str, Any]:
    """The sheet the evaluator fills by hand (docs/11): one requirement the model misses."""
    return {
        "key_info": {
            "buyer_name": "Ville de Lyon",
            "title": "Nettoyage des bureaux",
            "submission_deadline": DEADLINE.isoformat(),
            "estimated_amount_eur_ht": None,
        },
        "site_visit": {"mandatory": False},
        "memoir_requirements": {"imposed_outline": ["1. Moyens", "2. Méthodologie"]},
        "award_criteria": [
            {"name": "Valeur technique", "weight_pct": 60},
            {"name": "Prix", "weight_pct": 40},
        ],
        "requirements": [
            {"text": "Nettoyage quotidien des bureaux avant 8h", "source": {"page": 1}},
            {"text": "Vitrerie intérieure trimestrielle", "source": {"page": 2}},
            {"text": "Désinfection des sanitaires deux fois par jour", "source": {"page": 2}},
        ],
    }


def samples(root: Path) -> Path:
    (root / "base").mkdir(parents=True)
    (root / "lyon" / "dce").mkdir(parents=True)
    (root / "notes").mkdir()  # no dce/ inside: not a DCE
    company = {
        "name": "Propreté Rhône",
        "city": "Lyon",
        "profile": {"trades": ["nettoyage_locaux"], "departments": ["69"]},
        "human_resources": [{"qualification": "Agent de propreté", "count": 12}],
        "equipment": [{"name": "Autolaveuse", "quantity": 2}],
        "certifications": [{"name": "ISO 14001"}],
        "references": [
            {"client_name": "Métropole", "client_type": "public", "title": "Bureaux, 4 000 m²"}
        ],
    }
    (root / "entreprise.json").write_text(json.dumps(company), encoding="utf-8")
    template = make_docx([("Heading 1", "Moyens humains"), ("Normal", "Nos équipes.")])
    (root / "base" / "modele-memoire.docx").write_bytes(template)
    past = make_docx([("Normal", "Méthode : passage quotidien avant l'arrivée des agents.")])
    (root / "base" / "memoire-2025.docx").write_bytes(past)
    dce = zipped({SRC_RC: RC, SRC_CCTP: CCTP})
    (root / "lyon" / "dce" / "DCE.zip").write_bytes(dce)
    (root / "lyon" / "dce" / "lisez-moi.txt").write_text("ignoré", encoding="utf-8")
    (root / "lyon" / "attendu.json").write_text(json.dumps(expected_sheet()), encoding="utf-8")
    (root / "vide" / "dce").mkdir(parents=True)  # nothing the pipeline reads: that run fails
    (root / "vide" / "dce" / "notes.txt").write_text("rien", encoding="utf-8")
    return root


def plain(path: Path) -> bytes:
    """A file as the rater can read it: Word and Excel files are ZIPs of XML."""
    if not zipfile.is_zipfile(path):
        return path.read_bytes()
    with zipfile.ZipFile(path) as zf:
        return b"".join(zf.read(name) for name in zf.namelist())


def docx_text(path: Path) -> str:
    doc = Document(str(path))
    cells = [c.text for t in doc.tables for row in t.rows for c in row.cells]
    heads = [p.text for s in doc.sections for p in (*s.header.paragraphs, *s.footer.paragraphs)]
    return "\n".join([*(p.text for p in doc.paragraphs), *cells, *heads])


def test_two_models_are_compared_blind_on_the_real_pipeline(
    conn: Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = TwoModels()
    monkeypatch.setattr(llm, "_call_provider", fake)
    configured = get_settings().llm_model_generation
    out = tmp_path / "resultats"

    runs = run_evaluation(
        samples(tmp_path / "samples"), [GOOD, BROKEN], out, lambda: _new_session(conn), seed=3
    )

    assert set(fake.calls) == {GOOD, BROKEN}  # every task with the model of its run
    assert get_settings().llm_model_generation == configured  # settings restored
    mapping = json.loads((out / "correspondance-a-garder.json").read_text(encoding="utf-8"))
    assert list(mapping) == ["lyon", "vide"] and set(mapping["lyon"].values()) == {GOOD, BROKEN}
    empty = [r for r in runs if r.dce == "vide"]
    assert [r.error for r in empty] == ["passage interrompu : Déposez au moins un fichier."] * 2
    assert all(r.chapters == 0 and set(r.cost_eur) == {"embedding"} for r in empty)
    runs = [r for r in runs if r.dce == "lyon"]
    letter = {model: x for x, model in mapping["lyon"].items()}
    assert sorted(letter.values()) == ["A", "B"]
    good, broken = sorted(runs, key=lambda r: r.model != GOOD)

    # what goes to the rater: the memoirs and the analyses, without the model's name
    for model in (GOOD, BROKEN):
        text = docx_text(out / "lyon" / f"memoire-{letter[model]}.docx")
        assert "Propreté Rhône" in text and "[lyon" not in text  # the company's real name
        analysis = json.loads(
            (out / "lyon" / f"analyse-{letter[model]}.json").read_text(encoding="utf-8")
        )
        assert analysis["key_info"]["buyer_name"]["value"] == "Ville de Lyon"
    sent = [*(out / "lyon").iterdir(), out / "grille-de-notation.xlsx"]
    for path in sent:
        raw = plain(path)
        assert b"test/" not in raw and b"modele-en-panne" not in raw, path.name
    good_text = docx_text(out / "lyon" / f"memoire-{letter[GOOD]}.docx")
    assert "nous assurons le nettoyage quotidien des bureaux avant 8h" in good_text

    # the product's own pipeline ran: chapters, [À COMPLÉTER], conformity matrix
    assert good.analysis_status == broken.analysis_status == "ready"
    assert good.chapters == good.drafted == 2 and good.to_complete >= 1
    assert good.conformity == {"covered": 2}
    assert broken.chapters == 2 and broken.drafted == 0 and broken.failed_calls >= 2
    assert good.cost_eur["dce_extraction"] > 0 and good.cost_eur["memoir_generation"] > 0
    assert good.failed_calls == 0 and good.error is None

    # extraction metrics against attendu.json
    assert good.metrics is not None
    assert all(good.metrics["champs"].values()) and good.metrics["champs_pct"] == 100
    assert set(good.metrics["champs"]) == {
        "acheteur",
        "objet",
        "date limite",
        "visite obligatoire",
        "plan imposé",
        "critères",
    }
    assert good.metrics["exigences_rappel_pct"] == 67  # 2 of the 3 expected
    assert good.metrics["sources_pct"] == 100

    # one organization per run, so the AI journal gives each run's own cost
    with _new_session(conn) as db:
        orgs = db.scalar(
            select(func.count())
            .select_from(Organization)
            .where(Organization.name.like("Propreté Rhône [lyon %"))
        )
    assert orgs == 2

    grid = load_workbook(out / "grille-de-notation.xlsx")
    rows = list(grid["Notation"].iter_rows(values_only=True))
    assert rows[0][:3] == ("DCE", "Mémoire", "Conformité au plan") and len(rows) == 5
    assert [(r[0], r[1]) for r in rows[1:3]] == [("lyon", "A"), ("lyon", "B")]
    assert rows[1][8] == '=IFERROR(AVERAGE(C2:H2),"")' and rows[1][2] is None
    assert grid["Consignes"]["A2"].value == "Conformité au plan"

    report = (out / "rapport.md").read_text(encoding="utf-8")
    assert f"| `{GOOD}` |" in report and f"| `{BROKEN}` |" in report
    assert "| 2/2 |" in report and "| 0/2 |" in report and "67 %" in report
    assert "**passage interrompu : Déposez au moins un fichier.**" in report


def test_the_run_is_refused_without_models_or_dce(conn: Connection, tmp_path: Path) -> None:
    root = samples(tmp_path / "samples")
    with pytest.raises(ValueError, match="de 1 à 6 modèles"):
        run_evaluation(root, [], tmp_path / "out", lambda: _new_session(conn))
    with pytest.raises(ValueError, match="aucun DCE"):
        run_evaluation(root / "base", ["m"], tmp_path / "out", lambda: _new_session(conn))
    company = json.loads((root / "entreprise.json").read_text(encoding="utf-8"))
    company["references"][0]["client_type"] = "inconnu"
    (root / "entreprise.json").write_text(json.dumps(company), encoding="utf-8")
    with pytest.raises(ValueError, match="entreprise.json invalide"):
        run_evaluation(root, ["m"], tmp_path / "out", lambda: _new_session(conn))
    assert not (tmp_path / "out").exists()  # refused before anything was written


def test_metrics_compare_values_amounts_dates_and_pages() -> None:
    assert similar("Ville de Lyon", "Ville de Lyon (69)") and not similar("Lyon", "Paris")
    expected = {
        "key_info": {
            "estimated_amount_eur_ht": 100_000,
            "submission_deadline": "2026-12-15T12:00",
        },
        "site_visit": {"mandatory": True},
        "requirements": [{"text": "Produits écolabellisés obligatoires", "source": {"page": 3}}],
    }
    got = {
        "key_info": {
            "estimated_amount_eur_ht": {"value": 100_900},
            "submission_deadline": {"value": "2026-12-15T12:00:00+00:00"},
        },
        "site_visit": {"mandatory": False},
        "requirements": [{"text": "Produits écolabellisés obligatoires", "source": {"page": 4}}],
    }
    result = compare(expected, got)
    assert result["champs"] == {
        "date limite": True,
        "montant estimé": True,  # within 1 %
        "visite obligatoire": False,
    }
    assert result["champs_pct"] == 67
    assert result["exigences_rappel_pct"] == 100 and result["sources_pct"] == 0
    got["key_info"]["estimated_amount_eur_ht"] = {"value": 102_000}
    assert compare(expected, got)["champs"]["montant estimé"] is False
    assert compare({}, got) == {
        "champs": {},
        "champs_pct": None,
        "exigences_rappel_pct": None,
        "sources_pct": None,
    }


def test_the_command_never_runs_on_production_or_on_a_shared_database(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    called: list[Any] = []
    monkeypatch.setattr("app.evaluation.run_evaluation", lambda *a: called.append(a) or [])
    argv = ["eval-models", "--models", "m", "--samples", str(tmp_path)]
    assert cli.main(argv) == 2  # the test database is not an *_eval one
    assert "ne finit pas par _eval" in capsys.readouterr().err
    assert cli.main([*argv, "--any-database"]) == 0 and len(called) == 1
    assert called[0][1] == ["m"]
    monkeypatch.setattr(get_settings(), "environment", "production")
    assert cli.main([*argv, "--any-database"]) == 2
    assert "jamais en production" in capsys.readouterr().err
    assert len(called) == 1
