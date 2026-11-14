from datetime import UTC, date, datetime, timedelta

import pytest

from app.domain.go_no_go import (
    DocumentCheck,
    Inputs,
    VaultEntry,
    check_documents,
    compliance_kind_for,
    opinion,
)
from app.services.dce_analysis import parse_datetime

NOW = datetime(2026, 11, 4, 10, 0, tzinfo=UTC)
DEADLINE = NOW + timedelta(days=30)


@pytest.mark.parametrize(
    ("name", "declared", "kind"),
    [
        ("Attestation de vigilance URSSAF de moins de 6 mois", None, "urssaf_vigilance"),
        ("Extrait Kbis", None, "kbis"),
        ("Attestation de régularité fiscale", None, "tax_compliance"),
        ("Attestation d'assurance décennale", None, "insurance_decennale"),
        ("Attestation d'assurance responsabilité civile", None, "insurance_rc_pro"),
        ("Certificat CIBTP", None, "cibtp_certificate"),
        ("DC1 - lettre de candidature", None, None),
        ("Mémoire technique", None, None),
        ("Peu importe", "tax_compliance", "tax_compliance"),  # the model's hint wins if valid
        ("Attestation URSSAF", "n'importe quoi", "urssaf_vigilance"),
    ],
)
def test_compliance_kind_for(name: str, declared: str | None, kind: str | None) -> None:
    assert compliance_kind_for(name, declared) == kind


def test_check_documents_statuses() -> None:
    vault = [
        VaultEntry("urssaf_vigilance", "valid", date(2027, 3, 1)),
        VaultEntry("tax_compliance", "valid", date(2026, 11, 20)),  # expires before the deadline
        VaultEntry("insurance_rc_pro", "expired", date(2026, 1, 1)),
        VaultEntry("insurance_rc_pro", "pending_review", None),  # a new one, not confirmed yet
        VaultEntry("rne_certificate", "valid", date(2027, 6, 1)),
    ]
    required = [
        ("Attestation URSSAF", "candidature", None),
        ("Attestation fiscale", "candidature", None),
        ("Assurance RC pro", "candidature", None),
        ("Extrait Kbis", "candidature", None),
        ("Assurance décennale", "candidature", None),
        ("DC1", "candidature", None),
    ]
    checks = {c.name: c for c in check_documents(required, vault, DEADLINE)}
    assert checks["Attestation URSSAF"].status == "available"
    assert checks["Attestation fiscale"].status == "expires_before_deadline"
    assert checks["Assurance RC pro"].status == "unconfirmed"  # best candidate, better than expired
    assert checks["Extrait Kbis"].status == "available" and "RNE" in checks["Extrait Kbis"].detail
    assert checks["Assurance décennale"].status == "missing"
    assert checks["DC1"].status == "to_prepare"


def inputs(**kw: object) -> Inputs:
    base = {
        "now": NOW,
        "deadline": DEADLINE,
        "estimated_amount_cents": 8_000_000,
        "min_amount_cents": 1_000_000,
        "max_amount_cents": 50_000_000,
        "profile_keywords": ["nettoyage", "vitrerie"],
        "excluded_keywords": ["désamiantage"],
        "tender_text": "Nettoyage des locaux de la mairie",
        "documents": [],
        "blocking_watch_points": [],
        "visit_mandatory": False,
        "visit_dates": [],
    }
    base.update(kw)
    return Inputs(**base)  # type: ignore[arg-type]


def test_good_tender_is_go_and_explained() -> None:
    o = opinion(inputs())
    assert (o.score, o.verdict) == (100, "go")
    assert {f.label: f.status for f in o.factors} == {
        "Métier": "ok",
        "Montant": "ok",
        "Délai": "ok",
    }
    assert "indicatif" in o.disclaimer


def test_each_rule() -> None:
    assert opinion(inputs(tender_text="Désamiantage du gymnase")).factors[0].status == "blocking"
    assert opinion(inputs(tender_text="Maintenance des ascenseurs")).score == 70
    assert opinion(inputs(profile_keywords=[])).factors[0].status == "unknown"
    assert opinion(inputs(estimated_amount_cents=None)).factors[1].status == "unknown"
    assert opinion(inputs(estimated_amount_cents=90_000_000)).score == 80
    assert opinion(inputs(deadline=NOW + timedelta(days=5))).score == 85
    assert (
        opinion(inputs(deadline=NOW + timedelta(days=1))).verdict == "to_study"
    )  # blocking factor
    late = opinion(inputs(deadline=NOW - timedelta(hours=1)))
    assert late.score == 0 and late.verdict == "no_go"
    past_visit = opinion(inputs(visit_mandatory=True, visit_dates=[NOW - timedelta(days=2)]))
    assert past_visit.score == 60 and any(
        f.label == "Visite" and f.status == "blocking" for f in past_visit.factors
    )
    missing = [DocumentCheck(f"P{i}", "candidature", "kbis", "missing", "") for i in range(5)]
    assert opinion(inputs(documents=missing)).score == 70  # capped at -30
    assert opinion(inputs(blocking_watch_points=["Groupement interdit"])).verdict == "to_study"


def test_parse_datetime() -> None:
    assert parse_datetime("2026-12-15T12:00:00+01:00") == datetime(2026, 12, 15, 11, 0, tzinfo=UTC)
    assert parse_datetime("2026-12-15T12:00:00Z") == datetime(2026, 12, 15, 12, 0, tzinfo=UTC)
    day = parse_datetime("2026-12-15")
    assert (
        day is not None
        and (day.hour, day.minute) == (23, 59)
        and day.utcoffset() == timedelta(hours=1)
    )
    assert parse_datetime("15 décembre") is None and parse_datetime(None) is None


def test_a_keyword_from_profile_and_trade_is_listed_once() -> None:
    o = opinion(inputs(profile_keywords=["nettoyage", "Nettoyage", "vitrerie"]))
    assert o.factors[0].detail == "Correspond à votre activité (nettoyage)."


# ---------- accord-cadre bounded by a minimum and a maximum ---------------------------------


def test_a_framework_range_stands_in_for_a_missing_estimate() -> None:
    from app.domain.framework_amounts import FrameworkAmounts

    fa = FrameworkAmounts(8_000_000, 17_000_000, True, None)

    def amount(**kw: object) -> tuple[int, str, str]:
        o = opinion(inputs(estimated_amount_cents=None, framework=fa, **kw))
        [f] = [f for f in o.factors if f.label == "Montant"]
        return o.score, f.status, f.detail

    assert amount() == (
        100,
        "ok",
        "Accord-cadre de 80 000 € à 170 000 € HT par an : dans votre fourchette.",
    )
    assert amount(min_amount_cents=20_000_000) == (
        85,
        "warning",
        "Accord-cadre de 80 000 € à 170 000 € HT par an : sous votre minimum.",
    )
    assert amount(max_amount_cents=5_000_000) == (
        80,
        "warning",
        "Accord-cadre de 80 000 € à 170 000 € HT par an : au-dessus de votre maximum.",
    )
    # only a maximum: never « above your maximum », the orders may stay small
    only_max = FrameworkAmounts(None, 17_000_000, None, None)
    o = opinion(inputs(estimated_amount_cents=None, framework=only_max, max_amount_cents=1))
    assert [f.status for f in o.factors if f.label == "Montant"] == ["ok"]
    # an estimated amount still wins
    o = opinion(inputs(framework=fa, min_amount_cents=20_000_000))
    assert [f.detail for f in o.factors if f.label == "Montant"] == [
        "80 000 € HT : sous votre minimum."
    ]
