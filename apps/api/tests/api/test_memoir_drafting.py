"""Chapter drafting (US-4.2, P2-03) and conformity matrix (US-4.3, P2-04)."""

import json
import re
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.ai import llm
from app.core.config import get_settings
from app.db.models import AiCall, MemoirSection
from tests.api.helpers import signed_in_client
from tests.api.test_analysis import SRC_CCTP, FakeModel
from tests.api.test_memoir import add_reference, analyzed_bid
from tests.conftest import FakeQueue, Outbox
from tests.documents_helpers import make_docx

Factory = Callable[[], TestClient]
Sections = dict[str, str]  # title -> section id, as the matrix prompt shows them
Matrix = Callable[[Sections, list[str]], list[dict[str, Any]]]


def _user(messages: list[dict[str, Any]]) -> str:
    return str(messages[1]["content"])  # the first user turn, also on a corrective retry


class WriterModel(FakeModel):
    """Extraction as ``FakeModel``; chapters and matrix answered from what the prompt shows."""

    def __init__(self) -> None:
        super().__init__()
        self.chapter_prompts: list[str] = []
        self.matrix_prompts: list[str] = []
        self.broken: set[str] = set()  # chapter titles answered with something that is not JSON
        self.words = 30
        self.sentence = ""  # added to every chapter
        self.matrix: Matrix | None = None  # None = the model returns invalid JSON
        self.outage = False

    def __call__(
        self, model: str, messages: list[dict[str, Any]], max_tokens: int | None = None
    ) -> tuple[str, int, int, float]:
        user = _user(messages)
        if "Chapitre à rédiger" in user:
            if self.outage:
                raise ConnectionError("provider down")
            self.chapter_prompts.append(user)
            return self._chapter(user), 800, 400, 0.01
        if "<memoir>" in user:
            self.matrix_prompts.append(user)
            if self.matrix is None:
                return "désolé, pas de JSON", 500, 10, 0.01
            shown = re.findall(r'<section id="([^"]+)" title="([^"]+)"', user)
            sections = {title: sid for sid, title in shown}
            refs = re.findall(r"^- \[(CCTP-\d+)\]", user, re.MULTILINE)
            return json.dumps({"items": self.matrix(sections, refs)}), 900, 300, 0.02
        return super().__call__(model, messages, max_tokens)

    def _chapter(self, user: str) -> str:
        title = re.search(r"Chapitre à rédiger : \*\*(.+?)\*\*", user).group(1)  # type: ignore[union-attr]
        if title in self.broken:
            return "Voici le chapitre demandé (sans JSON)."
        refs = re.findall(r"^- \[(CCTP-\d+)\]", user, re.MULTILINE)
        excerpts = re.findall(r'<excerpt id="([^"]+)"', user)
        filler = " ".join(["texte"] * self.words)
        markdown = (
            "## Un autre titre\n\n"
            f"Pour {title}, nous assurons le nettoyage quotidien des bureaux avant 8h. {filler}\n\n"
            "Nous nous engageons à intervenir sous 2 heures.\n\n"
            "Nous entretenons 4321 m² de vitrerie.\n\n"
            "[À COMPLÉTER : nombre d'agents affectés au site]"
            f"{self.sentence}"
        )
        return json.dumps(
            {
                "markdown": markdown,
                "covered_requirements": [*refs, "CCTP-99"],  # CCTP-99 is not in this chapter
                "sources": [
                    *({"excerpt_id": e, "used_for": "méthode de travail"} for e in excerpts[:1]),
                    {"excerpt_id": str(uuid.uuid4()), "used_for": "source inventée"},
                ],
                "to_complete": ["nombre d'agents affectés au site"],
                "commitments": ["Intervention sous 2 heures"],
            }
        )


@pytest.fixture
def model(monkeypatch: pytest.MonkeyPatch) -> WriterModel:
    fake = WriterModel()
    monkeypatch.setattr(get_settings(), "llm_model_extraction", "test/extraction")
    monkeypatch.setattr(get_settings(), "llm_model_generation", "test/generation")
    monkeypatch.setattr(llm, "_call_provider", fake)
    return fake


def quote_everything(sections: Sections, refs: list[str]) -> list[dict[str, Any]]:
    """A careful model: every requirement covered, quoting the chapter that answers it."""
    title = "2. Méthodologie"
    sentence = f"Pour {title}, nous assurons le nettoyage quotidien des bureaux avant 8h."
    return [
        {
            "requirement_ref": r,
            "status": "covered",
            "section_id": sections[title],
            "excerpt": sentence,
        }
        for r in refs
    ]


def add_knowledge(c: TestClient, queue: FakeQueue, title: str, text: str) -> None:
    res = c.post(
        "/knowledge",
        data={"kind": "past_memoir", "title": title},
        files={"file": ("m.docx", make_docx([("Normal", text)]), "application/octet-stream")},
    )
    assert res.status_code == 201, res.text
    queue.drain()


def prepared(c: TestClient, queue: FakeQueue) -> dict[str, Any]:
    res = c.post(f"/bids/{analyzed_bid(c, queue)}/memoir")
    assert res.status_code == 201, res.text
    return dict(res.json())


def drafted(c: TestClient, queue: FakeQueue) -> dict[str, Any]:
    m = prepared(c, queue)
    res = c.post(f"/memoirs/{m['id']}/generate")
    assert res.status_code == 202, res.text
    queue.drain_memoir()
    return latest(c, m["id"])


def latest(c: TestClient, memoir_id: str) -> dict[str, Any]:
    res = c.get(f"/memoirs/{memoir_id}")
    assert res.status_code == 200, res.text
    return dict(res.json())


def section(m: dict[str, Any], title: str) -> dict[str, Any]:
    return next(s for s in m["sections"] if s["title"] == title)


# ---------- drafting ----------------------------------------------------------------------


def test_every_chapter_is_drafted_in_its_own_job_then_the_matrix_runs(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, model: WriterModel, db: Session
) -> None:
    model.matrix = quote_everything
    c = signed_in_client(make_client, outbox)
    add_knowledge(c, queue, "Mémoire 2024", "Nos agents utilisent des produits écolabellisés.")
    add_reference(c, title="Nettoyage de la médiathèque", year=2025)
    m = prepared(c, queue)
    started = c.post(f"/memoirs/{m['id']}/generate").json()
    assert started["status"] == "generating"
    assert [s["status"] for s in started["sections"]] == ["pending", "pending"]
    assert len(queue.pending_sections) == 2  # one job per chapter: drafted in parallel (CA1)
    assert c.post(f"/memoirs/{m['id']}/generate").json()["error"]["code"] == "memoir_not_draft"

    queue.drain_memoir()
    done = latest(c, m["id"])
    assert done["status"] == "ready" and done["conformity_status"] == "ready"
    method = section(done, "2. Méthodologie")
    assert method["status"] == "ready" and method["requirement_refs"] == ["CCTP-1", "CCTP-2"]
    # The imposed title is kept whatever the model wrote; an unrelated ref is not "covered".
    assert method["content_md"].startswith("## 2. Méthodologie\n\nPour 2. Méthodologie, nous")
    assert method["covered_refs"] == ["CCTP-1", "CCTP-2"]
    assert section(done, "1. Moyens")["covered_refs"] == []
    # Sources: only excerpts really given to the model, with their document (CA2).
    assert [(s["document"], s["used_for"]) for s in method["sources"]] == [
        ("Mémoire 2024", "méthode de travail")
    ]
    flags = {(f["type"], f["text"]) for f in method["flags"]}
    assert ("to_complete", "nombre d'agents affectés au site") in flags  # CA3
    assert ("commitment", "Nous nous engageons à intervenir sous 2 heures.") in flags
    assert ("commitment", "Intervention sous 2 heures") in flags
    assert (
        "number",
        "4321 — absent de vos données : Nous entretenons 4321 m² de vitrerie.",
    ) in flags
    assert {f["type"] for f in method["flags"]} == {"to_complete", "commitment", "number"}

    prompt = next(p for p in model.chapter_prompts if "**2. Méthodologie**" in p)
    assert "- [CCTP-1] Nettoyage quotidien des bureaux avant 8h (source : DCE/CCTP.pdf p. 1)" in (
        prompt
    )
    assert "Nos agents utilisent des produits écolabellisés." in prompt
    assert "Nettoyage de la médiathèque" in prompt
    calls = db.scalars(select(AiCall).where(AiCall.task == "memoir_generation")).all()
    assert len(calls) == 3 and all(a.model == "test/generation" for a in calls)  # 2 + matrix

    matrix = c.get(f"/memoirs/{m['id']}/conformity").json()
    assert matrix["counts"] == {"missing": 0, "partial": 0, "covered": 2}
    first = matrix["items"][0]
    assert first["requirement_ref"] == "CCTP-1" and first["method"] == "ai"
    assert first["section_title"] == "2. Méthodologie"
    assert first["source"]["file"] == SRC_CCTP and first["source"]["page"] == 1


def test_drafting_never_sees_another_company_documents(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, model: WriterModel
) -> None:
    a, b = signed_in_client(make_client, outbox, 1), signed_in_client(make_client, outbox, 2)
    add_knowledge(a, queue, "Secret A", "Méthode confidentielle de la société A.")
    add_reference(a, title="Référence confidentielle de A")
    add_knowledge(b, queue, "Mémoire B", "Méthode publique de la société B.")
    drafted(b, queue)
    assert model.chapter_prompts and all(
        "société A" not in p and "confidentielle de A" not in p for p in model.chapter_prompts
    )
    assert all("Méthode publique de la société B." in p for p in model.chapter_prompts)


def test_a_failed_chapter_does_not_block_the_others_and_can_be_regenerated(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, model: WriterModel
) -> None:
    model.matrix, model.broken = quote_everything, {"1. Moyens"}
    c = signed_in_client(make_client, outbox)
    m = drafted(c, queue)
    broken = section(m, "1. Moyens")
    assert broken["status"] == "error" and broken["content_md"] is None
    assert broken["error"] == "Le modèle n'a pas produit de réponse exploitable."
    assert section(m, "2. Méthodologie")["status"] == "ready"
    # The memoir is readable, but the matrix waits for a complete memoir.
    assert m["status"] == "ready" and m["conformity_status"] == "none"

    model.broken = set()
    res = c.post(f"/memoir-sections/{broken['id']}/regenerate", json={})
    assert res.status_code == 202 and section(res.json(), "1. Moyens")["status"] == "pending"
    queue.drain_memoir()
    m = latest(c, m["id"])
    assert section(m, "1. Moyens")["status"] == "ready" and m["conformity_status"] == "ready"


def test_a_provider_outage_leaves_the_chapter_to_the_job_retry(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, model: WriterModel
) -> None:
    c = signed_in_client(make_client, outbox)
    m = prepared(c, queue)
    c.post(f"/memoirs/{m['id']}/generate")
    model.outage = True
    retried = list(queue.pending_sections)
    with pytest.raises(llm.LlmProviderError):
        queue.drain_memoir()  # RQ marks the job failed and schedules a retry
    queue.pending_sections.clear()
    waiting = latest(c, m["id"])
    assert waiting["status"] == "generating"
    assert section(waiting, "1. Moyens")["status"] == "generating"
    assert section(waiting, "1. Moyens")["error"] == (
        "Service d'IA indisponible, nouvelle tentative en cours."
    )
    model.outage = False
    queue.pending_sections.extend(retried)  # the retries run
    queue.drain_memoir()
    assert latest(c, m["id"])["status"] == "ready"


def test_an_unavailable_queue_marks_the_chapters_to_relaunch(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, model: WriterModel
) -> None:
    c = signed_in_client(make_client, outbox)
    m = prepared(c, queue)
    queue.down = True
    res = c.post(f"/memoirs/{m['id']}/generate").json()
    assert res["status"] == "ready" and res["conformity_status"] == "none"
    assert {s["status"] for s in res["sections"]} == {"error"}
    assert res["sections"][0]["error"] == "File d'attente indisponible : relancez ce chapitre."


def test_regeneration_with_an_instruction_and_a_requirement_to_complete(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, model: WriterModel, db: Session
) -> None:
    model.matrix = quote_everything
    c = signed_in_client(make_client, outbox)
    m = prepared(c, queue)
    first = section(m, "1. Moyens")
    assert (
        c.post(f"/memoir-sections/{first['id']}/regenerate", json={}).json()["error"]["code"]
        == "memoir_not_generated"
    )
    c.post(f"/memoirs/{m['id']}/generate")
    assert (
        c.post(f"/memoir-sections/{first['id']}/regenerate", json={}).json()["error"]["code"]
        == "section_busy"
    )
    queue.drain_memoir()
    before = section(latest(c, m["id"]), "1. Moyens")["content_md"]
    unknown = c.post(
        f"/memoir-sections/{first['id']}/regenerate", json={"add_requirement_refs": ["CCTP-42"]}
    )
    assert unknown.status_code == 422 and unknown.json()["error"]["code"] == "unknown_requirement"

    model.sentence = "\n\nNous mobilisons 12 agents."

    res = c.post(
        f"/memoir-sections/{first['id']}/regenerate",
        json={"instruction": "Précisez nos 12 agents.", "add_requirement_refs": ["CCTP-2"]},
    ).json()
    assert res["status"] == "generating" and res["conformity_status"] == "none"
    assert section(res, "1. Moyens")["requirement_refs"] == ["CCTP-2"]
    queue.drain_memoir()
    prompt = model.chapter_prompts[-1]
    assert "Consigne de l'entreprise : Précisez nos 12 agents." in prompt
    assert f"<previous>\n{before}\n</previous>" in prompt  # the previous version is improved
    assert "- [CCTP-2] Vitrerie intérieure trimestrielle" in prompt
    again = latest(c, m["id"])
    assert section(again, "1. Moyens")["covered_refs"] == ["CCTP-2"]
    numbers = [f["text"] for f in section(again, "1. Moyens")["flags"] if f["type"] == "number"]
    # 12 comes from the user's own instruction: not an invented number
    assert numbers == ["4321 — absent de vos données : Nous entretenons 4321 m² de vitrerie."]
    assert again["conformity_status"] == "ready" and len(model.matrix_prompts) == 2
    stored = db.get_one(MemoirSection, uuid.UUID(first["id"]))
    assert stored.instruction is None  # consumed by the new version


def test_a_chapter_stuck_by_a_killed_worker_can_be_relaunched(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, model: WriterModel, db: Session
) -> None:
    c = signed_in_client(make_client, outbox)
    m = prepared(c, queue)
    c.post(f"/memoirs/{m['id']}/generate")
    queue.pending_sections.clear()  # the worker died: nothing will finish these jobs
    first = section(m, "1. Moyens")["id"]
    db.execute(
        update(MemoirSection)
        .where(MemoirSection.id == uuid.UUID(first))
        .values(status="generating", updated_at=datetime.now(UTC) - timedelta(hours=2))
    )
    db.commit()
    assert c.post(f"/memoir-sections/{first}/regenerate", json={}).status_code == 202
    assert queue.pending_sections == [uuid.UUID(first)]


def test_page_limit_is_estimated(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, model: WriterModel
) -> None:
    model.extra = {
        "memoir_requirements": {
            "imposed_outline": ["1. Moyens", "2. Méthodologie"],
            "max_pages": 1,
            "source": {"file": "DCE/RC.pdf", "page": 2},
        }
    }
    model.words = 300
    c = signed_in_client(make_client, outbox)
    assert prepared(c, queue)["estimated_pages"] is None
    m = drafted(c, queue)
    assert m["drafted_words"] > 600 and m["estimated_pages"] == 2
    assert m["page_warning"] == (
        "Environ 2 pages pour 1 autorisées par le règlement : raccourcissez certains chapitres."
    )
    lengths = [f for s in m["sections"] for f in s["flags"] if f["type"] == "length"]
    assert len(lengths) == 2  # each chapter is far above its budget


# ---------- conformity matrix --------------------------------------------------------------

FOUR = [
    {
        "ref": f"CCTP-{i}",
        "text": text,
        "category": "other",
        "importance": "mandatory",
        "source": {"file": SRC_CCTP, "page": 1 + i % 2},
    }
    for i, text in enumerate(
        [
            "Nettoyage quotidien des bureaux avant 8h",
            "Vitrerie intérieure trimestrielle",
            "Produits écolabellisés",
            "Tri des déchets",
        ],
        start=1,
    )
]


def test_the_matrix_trusts_only_what_the_memoir_really_says(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, model: WriterModel
) -> None:
    def careless(sections: Sections, refs: list[str]) -> list[dict[str, Any]]:
        moyens, methode = sections["1. Moyens"], sections["2. Méthodologie"]
        return [
            {  # right quote, wrong chapter, other spacing and case: covered, in its real chapter
                "requirement_ref": "CCTP-1",
                "status": "covered",
                "section_id": moyens,
                "excerpt": "POUR 2. Méthodologie,   nous assurons\nle nettoyage quotidien",
            },
            {  # a "quote" the memoir does not contain
                "requirement_ref": "CCTP-2",
                "status": "covered",
                "section_id": methode,
                "excerpt": "Nous lavons les vitres chaque semaine.",
            },
            {"requirement_ref": "CCTP-2", "status": "missing"},  # duplicate: the first wins
            {"requirement_ref": "CCTP-3", "status": "covered", "section_id": "n'importe quoi"},
            {"requirement_ref": "CCTP-99", "status": "covered"},  # not a requirement
            # CCTP-4 forgotten by the model
        ]

    model.extra, model.matrix = {"requirements": FOUR}, careless
    c = signed_in_client(make_client, outbox)
    m = drafted(c, queue)
    method_id = section(m, "2. Méthodologie")["id"]
    matrix = c.get(f"/memoirs/{m['id']}/conformity").json()
    items = {i["requirement_ref"]: i for i in matrix["items"]}
    assert set(items) == {"CCTP-1", "CCTP-2", "CCTP-3", "CCTP-4"}
    assert items["CCTP-1"]["status"] == "covered" and items["CCTP-1"]["section_id"] == method_id
    assert items["CCTP-2"]["status"] == "partial" and items["CCTP-2"]["excerpt"] is None
    assert items["CCTP-2"]["comment"] == "Extrait cité introuvable : à vérifier."
    assert items["CCTP-3"]["status"] == "partial" and items["CCTP-3"]["section_id"] is None
    assert items["CCTP-3"]["comment"] == "Aucun extrait cité : à vérifier."
    # Forgotten by the model: what its chapter declares, never "covered" by default.
    assert (items["CCTP-4"]["status"], items["CCTP-4"]["method"]) == ("partial", "declared")
    assert items["CCTP-4"]["comment"] == "Déclarée traitée par le chapitre, non vérifiée."
    assert [i["requirement_ref"] for i in matrix["items"]] == [
        "CCTP-2",
        "CCTP-3",
        "CCTP-4",
        "CCTP-1",
    ]
    assert matrix["counts"] == {"missing": 0, "partial": 3, "covered": 1}


def test_missing_requirements_come_first_with_the_chapter_to_complete(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, model: WriterModel
) -> None:
    def strict(sections: Sections, refs: list[str]) -> list[dict[str, Any]]:
        return [
            (
                {"requirement_ref": r, "status": "missing", "comment": "Absent du mémoire."}
                if r == "CCTP-3"
                else quote_everything(sections, [r])[0]
            )
            for r in refs
        ]

    model.extra, model.matrix = {"requirements": FOUR}, strict
    c = signed_in_client(make_client, outbox)
    m = drafted(c, queue)
    matrix = c.get(f"/memoirs/{m['id']}/conformity").json()
    first = matrix["items"][0]
    assert first["requirement_ref"] == "CCTP-3" and first["status"] == "missing"
    assert first["section_id"] is None and first["comment"] == "Absent du mémoire."
    # "compléter ce point" regenerates the chapter the outline gave this requirement to
    home = next(s["id"] for s in m["sections"] if "CCTP-3" in s["requirement_refs"])
    assert first["target_section_id"] == home
    assert [i["requirement_ref"] for i in matrix["items"][1:]] == ["CCTP-1", "CCTP-2", "CCTP-4"]


def test_the_matrix_falls_back_on_the_chapters_declarations(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, model: WriterModel
) -> None:
    model.matrix = None  # the model never returns valid JSON
    c = signed_in_client(make_client, outbox)
    m = drafted(c, queue)
    matrix = c.get(f"/memoirs/{m['id']}/conformity").json()
    assert matrix["status"] == "ready"
    assert matrix["error"] == (
        "Vérification automatique impossible (Le modèle n'a pas produit de réponse exploitable.)"
        " : statuts déclarés par les chapitres."
    )
    assert [(i["requirement_ref"], i["status"], i["method"]) for i in matrix["items"]] == [
        ("CCTP-1", "partial", "declared"),
        ("CCTP-2", "partial", "declared"),
    ]
    assert matrix["items"][0]["comment"] == "Déclarée traitée par le chapitre, non vérifiée."


def test_the_matrix_can_be_run_again(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, model: WriterModel
) -> None:
    c = signed_in_client(make_client, outbox)
    m = prepared(c, queue)
    assert c.post(f"/memoirs/{m['id']}/conformity").json()["error"]["code"] == "memoir_busy"
    c.post(f"/memoirs/{m['id']}/generate")
    queue.drain_memoir()  # matrix model down: declarations
    model.matrix = quote_everything
    res = c.post(f"/memoirs/{m['id']}/conformity")
    assert res.status_code == 202 and res.json()["status"] == "pending"
    assert c.post(f"/memoirs/{m['id']}/conformity").json()["error"]["code"] == (
        "conformity_running"
    )
    queue.drain_memoir()
    matrix = c.get(f"/memoirs/{m['id']}/conformity").json()
    assert matrix["error"] is None and matrix["counts"]["covered"] == 2


# ---------- access -------------------------------------------------------------------------


def test_tenancy_isolation(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, model: WriterModel
) -> None:
    a, b = signed_in_client(make_client, outbox, 1), signed_in_client(make_client, outbox, 2)
    m = drafted(b, queue)
    sid = m["sections"][0]["id"]
    assert a.post(f"/memoirs/{m['id']}/generate").status_code == 404
    assert a.post(f"/memoir-sections/{sid}/regenerate", json={}).status_code == 404
    assert a.get(f"/memoirs/{m['id']}").status_code == 404
    assert a.get(f"/memoirs/{m['id']}/conformity").status_code == 404
    assert a.post(f"/memoirs/{m['id']}/conformity").status_code == 404


def test_requires_authentication(make_client: Factory) -> None:
    anon = make_client()
    some = uuid.uuid4()
    assert anon.get(f"/memoirs/{some}").status_code == 401
    assert anon.post(f"/memoirs/{some}/generate").status_code == 401
    assert anon.post(f"/memoir-sections/{some}/regenerate", json={}).status_code == 401
    assert anon.get(f"/memoirs/{some}/conformity").status_code == 401
