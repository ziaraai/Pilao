from datetime import UTC, datetime, timedelta

from app.domain.tender_filter import (
    CompanyFilter,
    TenderFacts,
    covered_codes,
    cpv_hits,
    keyword_hits,
    prefilter,
    same_buyer,
    similar_titles,
)

NOW = datetime(2026, 11, 5, 9, 0, tzinfo=UTC)
CLEANING = CompanyFilter(
    cpv_codes=["90910000"],
    keywords_include=["nettoyage", "vitrerie"],
    keywords_exclude=["désamiantage"],
    departments=["69", "01"],
    min_amount_cents=2_000_000,
    max_amount_cents=50_000_000,
)


def tender(**kw: object) -> TenderFacts:
    base: dict[str, object] = {
        "title": "Entretien des locaux de la mairie",
        "description": None,
        "lot_titles": [],
        "cpv_codes": ["90911200"],
        "departments": ["69"],
        "estimated_amount_cents": 12_000_000,
        "deadline_at": NOW + timedelta(days=20),
    }
    return TenderFacts(**{**base, **kw})  # type: ignore[arg-type]


def test_the_reason_names_the_notice_code_once() -> None:
    assert covered_codes(["90910000", "90911000", "90911200"], ["90911200-8", "72000000"]) == [
        "90911200"
    ]


def test_cpv_codes_cover_the_codes_below_them() -> None:
    assert cpv_hits(["90910000"], ["90911200-8"]) == ["90910000"]
    assert cpv_hits(["90911200"], ["90910000"]) == []  # a narrower code does not cover a wider one
    assert cpv_hits(["90910000", "45000000"], ["45261000"]) == ["45000000"]
    assert cpv_hits(["90910000"], ["90920000"]) == []


def test_keywords_are_whole_words_without_accents() -> None:
    text = "Prestations de PROPRETÉ et nettoyage-vitrerie"
    assert keyword_hits(["propreté", "vitrerie", "nettoyage"], text) == [
        "propreté",
        "vitrerie",
        "nettoyage",
    ]
    assert keyword_hits(["verre"], "vitrerie et verrerie") == []
    assert keyword_hits(["nettoyage", "bureau"], "Nettoyages des bureaux") == [
        "nettoyage",
        "bureau",
    ]
    assert keyword_hits(["vitre"], "vitres et vitrerie") == ["vitre"]
    assert keyword_hits(["remise en état"], "Remise en etat après chantier") == ["remise en état"]


def test_a_matching_notice_passes_with_its_reasons() -> None:
    decision = prefilter(CLEANING, tender(), NOW)
    assert decision.passed and decision.reasons == ["code CPV 90911200", "département 69"]
    by_word = prefilter(CLEANING, tender(cpv_codes=[], title="Nettoyage du gymnase"), NOW)
    assert by_word.reasons == ["mot-clé « nettoyage »", "département 69"]


def test_each_rule_can_reject() -> None:
    cases = {
        "ni code CPV ni mot-clé": tender(cpv_codes=["72000000"]),
        "mot-clé exclu : désamiantage": tender(description="Lot 2 : désamiantage"),
        "hors de vos départements": tender(departments=["75"]),
        "date limite dépassée": tender(deadline_at=NOW),
        "montant sous votre minimum": tender(estimated_amount_cents=1_000_000),
        "montant au-dessus de votre maximum": tender(estimated_amount_cents=90_000_000),
    }
    for reason, facts in cases.items():
        decision = prefilter(CLEANING, facts, NOW)
        assert (decision.passed, decision.rejected) == (False, reason)


def test_unknown_place_amount_or_deadline_does_not_reject() -> None:
    decision = prefilter(
        CLEANING, tender(departments=[], estimated_amount_cents=None, deadline_at=None), NOW
    )
    assert decision.passed and "lieu non précisé dans l'annonce" in decision.reasons
    anywhere = CompanyFilter(cpv_codes=["90910000"])  # no department: all of France
    assert prefilter(anywhere, tender(departments=["2A"]), NOW).passed


def test_an_empty_profile_watches_nothing() -> None:
    assert prefilter(CompanyFilter(), tender(), NOW).rejected == (
        "aucun code CPV ni mot-clé dans le profil"
    )


def test_duplicates_across_sources() -> None:
    assert similar_titles(
        "Nettoyage des locaux de la mairie de Lyon", "Lyon — nettoyage des locaux mairie"
    )
    assert not similar_titles("Nettoyage des locaux de la mairie", "Travaux de voirie")
    assert same_buyer("Ville de Lyon", "VILLE DE LYON (Direction de la commande publique)")
    assert not same_buyer("Ville de Lyon", "Métropole de Lyon")
