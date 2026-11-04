"""Pick the 3 to 5 company references closest to a tender (US-4.2 CA4, P2-02)."""

import hashlib
import math
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.calls import log_embedding_call
from app.ai.embeddings import Embedder, EmbeddingError
from app.ai.llm import LlmBudgetExceeded, ensure_budget
from app.db.models import CompanyReference

MAX_REFERENCES = 5
MIN_REFERENCES = 3
SELECT_SCORE = 0.25


def auto_selection(picks: "list[Pick]") -> "list[Pick]":
    """US-4.2 CA4: the 3 to 5 closest. The good ones (score >= SELECT_SCORE), at least 3 when
    the company has that many, at most 5; the others stay proposed."""
    good = [p for p in picks if p.score >= SELECT_SCORE]
    return (good if len(good) >= MIN_REFERENCES else picks[:MIN_REFERENCES])[:MAX_REFERENCES]


@dataclass(frozen=True)
class Pick:
    reference_id: str
    score: float
    reasons: list[str]


def _text(r: CompanyReference) -> str:
    return " — ".join(
        x for x in (r.title, r.description or "", r.client_name, r.location or "") if x
    )


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def _refresh_embeddings(
    db: Session, org_id: uuid.UUID, refs: list[CompanyReference], embedder: Embedder
) -> None:
    stale = [
        r for r in refs if r.embedding_text_hash != hashlib.sha256(_text(r).encode()).hexdigest()
    ]
    if not stale:
        return
    ensure_budget(db, org_id)
    began = time.monotonic()
    result = embedder.embed([_text(r) for r in stale])
    log_embedding_call(db, org_id, result, int((time.monotonic() - began) * 1000), result.model)
    for r, vector in zip(stale, result.vectors, strict=True):
        r.embedding, r.embedding_text_hash = vector, hashlib.sha256(_text(r).encode()).hexdigest()
    db.flush()


def select_references(
    db: Session,
    org_id: uuid.UUID,
    embedder: Embedder,
    tender_text: str,
    estimated_amount_cents: int | None,
) -> tuple[list[Pick], str | None]:
    """Best references, best first, with the reasons shown to the user. Never invents one:
    only the company's own references (tenant-filtered session). Returns (picks, warning)."""
    refs = list(db.scalars(select(CompanyReference)))
    if not refs:
        return [], "Aucune référence dans votre profil : ajoutez-en pour les citer dans le mémoire."
    warning = None
    similarity: dict[object, float] = {}
    try:
        _refresh_embeddings(db, org_id, refs, embedder)
        query = embedder.embed([tender_text]).vectors[0]
        similarity = {r.id: max(0.0, _cosine(query, [float(x) for x in r.embedding])) for r in refs}
    except (EmbeddingError, LlmBudgetExceeded):
        warning = "Proximité de contenu non calculée (service d'IA indisponible) : choix sur les autres critères."

    year_now = datetime.now(UTC).year
    picks = []
    for r in refs:
        score, reasons = 0.6 * similarity.get(r.id, 0.0), []
        if similarity.get(r.id, 0.0) >= 0.3:
            reasons.append("prestations proches de ce marché")
        if r.client_type == "public":
            score += 0.1
            reasons.append("client public")
        if estimated_amount_cents and r.amount_cents:
            closeness = 1 - min(1.0, abs(math.log10(r.amount_cents / estimated_amount_cents)))
            score += 0.2 * closeness
            if closeness >= 0.7:
                reasons.append("montant comparable")
        if r.year and r.year >= year_now - 5:
            score += 0.1
            reasons.append("récente")
        picks.append(Pick(str(r.id), round(score, 4), reasons))
    picks.sort(key=lambda p: p.score, reverse=True)
    return picks[:MAX_REFERENCES], warning
