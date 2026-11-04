"""Journal of AI calls (``ai_calls``): task, model, tokens, cost, latency."""

import uuid
from decimal import Decimal

from sqlalchemy.orm import Session

from app.ai.embeddings import EmbeddingResult
from app.db.models import AiCall


def log_embedding_call(
    db: Session,
    org_id: uuid.UUID,
    result: EmbeddingResult | None,
    latency_ms: int,
    model: str,
    error: str | None = None,
) -> None:
    db.add(
        AiCall(
            org_id=org_id,
            task="embedding",
            model=result.model if result else model,
            input_tokens=result.input_tokens if result else 0,
            output_tokens=0,
            cost_eur=Decimal(str(result.cost_eur)) if result else Decimal(0),
            latency_ms=latency_ms,
            success=error is None,
            error=error,
        )
    )
