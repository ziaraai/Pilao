"""The font the RC imposes on the memoir (« Police Times New Roman, taille 11 »)."""

import pytest

from app.domain.imposed_font import ImposedFont, from_analysis, read

RILLIEUX = (
    "10 pages maximum hors annexes légitimes et pertinentes (fiches techniques ou CV). Police "
    "Times New Roman, taille 11. Reprise obligatoire de la trame chronologique des critères de "
    "jugement technique."
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (RILLIEUX, ImposedFont("Times New Roman", 11)),
        ("Police Arial 10 minimum, interligne 1,5", ImposedFont("Arial", 10)),
        ("caractères de taille 12 points au moins", ImposedFont(None, 12)),
        ("Rédigé en Calibri corps 11", ImposedFont("Calibri", 11)),
        ("Police de type Arial ou équivalent", ImposedFont("Arial", None)),
        ("police Arial Narrow 9", ImposedFont("Arial Narrow", 9)),
        ("police Helvetica 10,5", ImposedFont("Arial", 10.5)),
        ("20 pages maximum, interligne simple", None),
        ("Police taille 40", None),  # not a body size: ignored
        (None, None),
    ],
)
def test_read(text: str | None, expected: ImposedFont | None) -> None:
    assert read(text) == expected


def test_from_analysis() -> None:
    data = {"memoir_requirements": {"format_constraints": RILLIEUX}}
    assert from_analysis(data) == ImposedFont("Times New Roman", 11)
    assert from_analysis({"memoir_requirements": {"format_constraints": None}}) is None
    assert from_analysis({}) is None
