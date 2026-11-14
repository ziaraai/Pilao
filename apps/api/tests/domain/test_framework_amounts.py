"""The minimum and maximum of an accord-cadre, read from the DCE analysis."""

import pytest

from app.domain.framework_amounts import FrameworkAmounts, describe, from_analysis, parse

RILLIEUX = (
    "12 mois à compter de la notification, reconductible 3 fois tacitement pour des durées "
    "identiques (48 mois au total). Montant minimum annuel 80 000 € HT, maximum annuel "
    "170 000 € HT. Non-reconduction notifiée au plus tard 90 jours calendaires avant l'échéance."
)
SOURCE = {"file": "RC.pdf", "page": 2, "dce_file_id": "f1"}


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (RILLIEUX, (8_000_000, 17_000_000, True)),
        (
            (
                "Accord-cadre sans minimum, avec un montant maximum de 1 200 000 € HT pour toute "
                "la durée du marché."
            ),
            (None, 120_000_000, False),
        ),
        (
            "Montant minimum : 50.000 euros HT par an ; montant maximum : 200.000 euros HT par an",
            (5_000_000, 20_000_000, True),
        ),
        ("Maximum : 80\u202f000,50\u00a0€ HT", (None, 8_000_050, None)),
        ("Montant maximum annuel de 170 k€ HT", (None, 17_000_000, True)),
        ("Durée de 4 ans, reconductible.", None),
        ("Délai minimum de 10 jours avant la visite.", None),
        ("Minimum 900 000 € HT, maximum 100 000 € HT", None),  # inconsistent: not trusted
        (None, None),
    ],
)
def test_parse(text: str | None, expected: tuple[int | None, int | None, bool | None]) -> None:
    assert parse(text) == expected


def test_the_model_field_comes_first() -> None:
    data = {
        "key_info": {
            "framework_amounts": {
                "minimum_eur_ht": 80000,
                "maximum_eur_ht": 170000.0,
                "period": "year",
                "source": SOURCE,
            },
            "duration": {"value": "Montant maximum 1 € HT", "source": SOURCE},
        }
    }
    assert from_analysis(data) == FrameworkAmounts(8_000_000, 17_000_000, True, SOURCE)


def test_an_older_analysis_is_read_from_its_duration() -> None:
    data = {"key_info": {"duration": {"value": RILLIEUX, "source": SOURCE}}}
    assert from_analysis(data) == FrameworkAmounts(8_000_000, 17_000_000, True, SOURCE)


def test_nothing_to_read() -> None:
    assert from_analysis({}) is None
    assert from_analysis({"key_info": {"framework_amounts": None, "duration": None}}) is None
    empty = {"minimum_eur_ht": None, "maximum_eur_ht": None, "period": None, "source": SOURCE}
    assert from_analysis({"key_info": {"framework_amounts": empty}}) is None


@pytest.mark.parametrize(
    ("amounts", "phrase", "label"),
    [
        (
            FrameworkAmounts(8_000_000, 17_000_000, True, None),
            "de 80 000 € à 170 000 € HT par an",
            "De 80 000 € à 170 000 € HT par an",
        ),
        (
            FrameworkAmounts(None, 120_000_000, False, None),
            "jusqu'à 1 200 000 € HT sur toute la durée",
            "Jusqu'à 1 200 000 € HT sur toute la durée",
        ),
        (
            FrameworkAmounts(5_000_000, None, None, None),
            "d'au moins 50 000 € HT",
            "Au moins 50 000 € HT",
        ),
    ],
)
def test_describe(amounts: FrameworkAmounts, phrase: str, label: str) -> None:
    assert describe(amounts) == phrase
    assert describe(amounts, standalone=True) == label
