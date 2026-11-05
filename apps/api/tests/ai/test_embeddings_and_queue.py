import math
from types import SimpleNamespace
from typing import Any

import fakeredis
import pytest
from rq import Queue

from app.ai.embeddings import EmbeddingError, HashEmbedder, LiteLLMEmbedder, get_embedder
from app.core.config import get_settings
from app.workers.queue import RqJobQueue


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


def test_hash_embedder_is_deterministic_normalized_and_similarity_aware() -> None:
    e = HashEmbedder(256)
    r = e.embed(["Nettoyage des locaux", "nettoyage des LOCAUX", "Plomberie sanitaire"])
    a, b, c = r.vectors
    assert a == b  # case / accents normalized
    assert all(
        len(v) == 256 and abs(math.sqrt(sum(x * x for x in v)) - 1) < 1e-9 for v in r.vectors
    )
    assert cosine(a, b) > 0.99 and cosine(a, c) < 0.5
    assert e.embed(["Nettoyage des locaux"]).vectors[0] == a
    assert e.embed([""]).vectors[0] == [0.0] * 256  # empty text: zero vector, no crash


def test_litellm_embedder_batches_and_sums_usage(monkeypatch: pytest.MonkeyPatch) -> None:
    import litellm

    monkeypatch.setattr(get_settings(), "usd_eur_rate", 0.9)

    calls: list[list[str]] = []

    def fake_embedding(model: str, input: list[str], **kw: Any) -> Any:
        calls.append(input)
        return SimpleNamespace(
            data=[{"embedding": [float(len(t))] * 4} for t in input],
            usage=SimpleNamespace(prompt_tokens=len(input) * 10),
            _hidden_params={"response_cost": 0.001},
        )

    monkeypatch.setattr(litellm, "embedding", fake_embedding)
    result = LiteLLMEmbedder("some/model", 4, batch_size=2).embed(["a", "bb", "ccc", "dddd", "e"])
    assert [len(c) for c in calls] == [2, 2, 1]
    assert [v[0] for v in result.vectors] == [1.0, 2.0, 3.0, 4.0, 1.0]
    assert result.input_tokens == 50 and result.cost_eur == pytest.approx(0.0027)  # 0.003 $
    assert result.model == "some/model"


def test_litellm_errors_become_embedding_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    import litellm

    def boom(**kw: Any) -> Any:
        raise RuntimeError("401 unauthorized")

    monkeypatch.setattr(litellm, "embedding", boom)
    with pytest.raises(EmbeddingError, match="401"):
        LiteLLMEmbedder("m", 4).embed(["x"])


def test_get_embedder_selection(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    get_embedder.cache_clear()
    monkeypatch.setattr(settings, "embedding_model", "")
    assert isinstance(get_embedder(), HashEmbedder)
    get_embedder.cache_clear()
    monkeypatch.setattr(settings, "embedding_model", "openrouter/some-embedder")
    assert isinstance(get_embedder(), LiteLLMEmbedder)
    get_embedder.cache_clear()
    monkeypatch.setattr(settings, "embedding_model", "")
    monkeypatch.setattr(settings, "environment", "production")
    with pytest.raises(EmbeddingError):  # the fake model must never serve production traffic
        get_embedder()
    get_embedder.cache_clear()


def test_rq_enqueue_targets_the_job_with_retries() -> None:
    import uuid

    queue = Queue("default", connection=fakeredis.FakeRedis())
    doc_id = uuid.uuid4()
    RqJobQueue(queue).enqueue_index_document(doc_id)
    (job,) = queue.jobs
    assert job.func_name == "app.workers.jobs.index_document_job"
    assert job.args == (str(doc_id),) and job.timeout == 900
    assert job.retries_left == 2
