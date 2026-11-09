"""Pre-filling the profile: the checks applied to what the model read (spec §5)."""

from app.domain.profile_prefill import (
    Located,
    Passage,
    clean,
    dedupe,
    key_of,
    locate,
    numbers_in,
)

# Lines of ENG PRO's 2017 memoir, as indexed.
P = [
    Passage("3 - MOYENS EN MATERIEL\n6 auto laveuses marque TENANTE 5400", 3, "Moyens en matériel"),
    Passage("AGENTS DE SERVICES\nResponsable M SAOUD Raouf", 2, "Organigramme"),
]


def test_locate_finds_the_passage_despite_typography() -> None:
    assert locate("6 auto  laveuses marque\nTENANTE 5400", P) == Located(3, "Moyens en matériel")
    assert locate("l’équipe", [Passage("l'équipe", None, None)]) == Located(None, None)
    assert locate("12 autolaveuses Kärcher", P) is None


def test_an_excerpt_across_two_passages_is_found_without_page() -> None:
    assert locate("TENANTE 5400 AGENTS DE SERVICES", P) == Located(None, None)


def test_numbers_must_be_written_in_the_excerpt() -> None:
    excerpt = "6 auto laveuses marque TENANTE 5400"
    c = clean("equipment", {"name": "Auto laveuse Tenante 5400", "quantity": 6}, excerpt)
    assert c is not None and c.data["quantity"] == 6 and c.missing == []
    c = clean("equipment", {"name": "Auto laveuse Tenante 5400", "quantity": 12}, excerpt)
    assert c is not None and c.data["quantity"] is None
    hr = clean(
        "human_resource", {"qualification": "Agent de service", "count": 25}, "AGENTS DE SERVICES"
    )
    assert hr is not None and hr.data["count"] is None and hr.missing == ["count"]
    assert numbers_in("85 000 € HT en 2016") >= {85000, 2016}
    assert numbers_in("85.000 et 1 200 000") >= {85000, 1200000}


def test_a_name_absent_from_the_excerpt_is_rejected() -> None:
    assert (
        clean("equipment", {"name": "Nettoyeur vapeur"}, "6 auto laveuses marque TENANTE") is None
    )
    assert clean("reference", {"client_name": ""}, "MERCIALYS") is None
    assert clean("certification", {"name": None}, "ISO 9001") is None


def test_person_names_are_removed() -> None:
    hr = clean(
        "human_resource",
        {"qualification": "Responsable M SAOUD Raouf", "count": None, "description": "Mme PERIFEL"},
        "Responsable M SAOUD Raouf",
    )
    assert hr is not None
    assert hr.data["qualification"] == "Responsable" and hr.data["description"] is None


def test_out_of_bounds_values_become_empty() -> None:
    r = clean(
        "reference",
        {
            "client_name": "Mercialys",
            "client_type": "privé",
            "title": None,
            "year": 1890,
            "amount_eur": 85000,
        },
        "MERCIALYS 1890",
    )
    assert r is not None
    assert r.data["client_type"] == "private"  # « privé » is understood
    assert r.data["year"] is None and r.data["amount_cents"] is None
    assert r.missing == ["title"]
    odd = clean("reference", {"client_name": "Mercialys", "client_type": "mixte"}, "MERCIALYS")
    assert odd is not None and odd.data["client_type"] is None
    assert odd.missing == ["client_type", "title"]


def test_a_sourced_amount_and_year_are_kept() -> None:
    r = clean(
        "reference",
        {
            "client_name": "Ville de Lyon",
            "client_type": "public",
            "title": "Nettoyage des écoles",
            "year": 2024,
            "amount_eur": 85000.0,
        },
        "Ville de Lyon - nettoyage des écoles - 85 000 € HT - 2024",
    )
    assert r is not None and r.missing == []
    assert r.data["amount_cents"] == 8_500_000 and r.data["year"] == 2024


def test_duplicates_are_kept_once() -> None:
    a = clean(
        "equipment",
        {"name": "Mono-brosses Nilfisk", "quantity": 14},
        "14 Mono-brosses de marque NILFISK",
    )
    b = clean(
        "equipment",
        {"name": "Mono-brosse Nilfisk", "quantity": 14},
        "14 Mono-brosses de marque NILFISK",
    )
    assert a is not None and b is not None
    assert dedupe([a, b], set()) == [a]
    assert dedupe([a], {key_of("equipment", {"name": "Mono brosses nilfisk"})}) == []
    ref = clean("reference", {"client_name": "Mercialys", "title": None}, "MERCIALYS")
    assert ref is not None
    known = {key_of("reference", {"client_name": "MERCIALYS", "title": "Galerie"})}
    assert dedupe([ref], known) == []
