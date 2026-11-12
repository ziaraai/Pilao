"""Lot 5: the models offered for a task (spec §2)."""

from dataclasses import replace

from app.ai.openrouter import CatalogueModel
from app.domain.ai_catalogue import NEEDS_IMAGES, eur_per_million, usable

M = CatalogueModel(
    id="acme/small",
    name="Acme Small",
    prompt_usd=0.0000001,
    completion_usd=0.0000005,
    context_length=128000,
    json_output=True,
    reads_images=False,
)


def test_usable() -> None:
    assert usable(M, needs_images=False)
    assert not usable(replace(M, id="acme/small:free"), needs_images=False)  # keeps the texts
    assert not usable(replace(M, id="~acme/small-latest"), needs_images=False)  # moving alias
    assert not usable(replace(M, json_output=False), needs_images=False)
    assert not usable(replace(M, prompt_usd=-1.0), needs_images=False)
    assert not usable(replace(M, completion_usd=-1.0), needs_images=False)
    assert not usable(M, needs_images=True)
    assert usable(replace(M, reads_images=True), needs_images=True)
    assert NEEDS_IMAGES == {"compliance_reading"}


def test_eur_per_million() -> None:
    assert eur_per_million(0.0000001, 0.86) == 0.086
    assert eur_per_million(0.0000005, 0.86) == 0.43
    assert eur_per_million(0.0, 0.86) == 0.0
