"""A consultation read from its documents (25/11): the client's facts are kept only where the
cited page has them; nothing is guessed."""

from app.domain.consultation import (
    ConsultationReadOut,
    FactIn,
    check_facts,
    placeholder_title,
)

PAGE = """CCTB
Rue de l'orphelinat
42100 SAINT ETIENNE
Tél : 04 77 25 05 44
Fiche d'intervention établie depuis le devis n° : DE36594
Adresse du chantier
Monsieur DELBARRE Jean (fiche intervention cristallisation sols)
Adresse de facturation
7 rue du Général Leclerc
42100 Saint Etienne
Contact : achats@cctb-exemple.fr
1.1 Nettoyage et cristallisation du sol 89,83 M2"""
PAGES = {("FICHE.pdf", 1): PAGE}


def fact(value: str, file: str = "FICHE.pdf", page: int = 1) -> FactIn:
    return FactIn(value=value, file=file, page=page)


def test_facts_are_kept_only_where_the_page_has_them() -> None:
    read = ConsultationReadOut(
        facts={
            "title": fact("Nettoyage et cristallisation du sol"),
            "client_name": fact("CCTB"),
            "client_address": fact("Rue de l'orphelinat, 42100 Saint-Étienne"),
            "site_address": fact("M. DELBARRE Jean, 7 rue du Général Leclerc, 42100 Saint Etienne"),
            "contact_email": fact("ACHATS@cctb-exemple.fr"),
            "contact_phone": fact("04.77.25.05.44"),
            "reference": fact("DE36594"),
            # invented, or cited on a page not sent: dropped
            "contact_name": fact("Mme Martin"),
        },
        price_files=[],
    )
    kept = check_facts(read, PAGES)
    assert kept["client_name"] == ("CCTB", "FICHE.pdf", 1)
    assert kept["contact_email"][0] == "achats@cctb-exemple.fr"
    assert kept["contact_phone"][0] == "04 77 25 05 44"
    assert kept["reference"][0] == "DE36594"
    assert kept["site_address"][0].startswith("M. DELBARRE Jean")
    assert "contact_name" not in kept
    # a fact cited on a page that was not sent, an e-mail not written: dropped
    other = ConsultationReadOut(
        facts={
            "reference": fact("DE36594", page=3),
            "contact_email": fact("devis@ailleurs.fr"),
            "contact_phone": fact("06 12 34 56 78"),
        },
        price_files=[],
    )
    assert check_facts(other, PAGES) == {}


def test_an_unknown_field_or_a_bad_email_is_ignored() -> None:
    read = ConsultationReadOut.model_validate(
        {
            "facts": {
                "contact_email": {"value": "pas un e-mail", "file": "FICHE.pdf", "page": 1},
                "montant": {"value": "1 289,28 €", "file": "FICHE.pdf", "page": 1},
            },
            "price_files": [{"file": "FICHE.pdf", "reason": "lignes avec quantités"}],
        }
    )
    assert "montant" not in read.facts
    assert check_facts(read, PAGES) == {}
    assert read.price_files[0].file == "FICHE.pdf"


def test_a_consultation_without_title_has_a_dated_one() -> None:
    from datetime import date

    assert placeholder_title(date(2026, 11, 25)) == "Consultation du 25/11/2026"
