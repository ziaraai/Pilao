"""The company's quote as a Word file (ADR-052)."""

import io
from datetime import date
from decimal import Decimal

from docx import Document

from app.domain.quote import QuoteRow, QuoteTable
from app.exports.quote_docx import Company, QuoteDocData, build_quote, money, quantity

ROWS = [
    QuoteRow("12.1 Nettoyage avant OPR", "Bâtiment A", "m²", Decimal(1250), 150, 187_500),
    QuoteRow("12.1 Nettoyage avant OPR", "Bâtiment B", "m²", Decimal("800.5"), 150, 120_075),
    QuoteRow("12.2 Nettoyage avant réception", "Ensemble", "forfait", Decimal(1), 90_000, 90_000),
]
INCLUSION = {
    "text": "Nettoyage des sols et des menuiseries avant les OPR.",
    "file": "CCTP lot 16.pdf",
    "page": 41,
}
OPTION = QuoteRow("Options", "Vitrerie haute", "m²", Decimal(100), 300, 30_000)


def data(**changes: object) -> QuoteDocData:
    base = QuoteDocData(
        number="D-2026-0001",
        issued=date(2026, 11, 17),
        validity_days=30,
        vat_bp=2000,
        company=Company(
            name="ENG PRO",
            legal_form="SAS",
            siret="12345678900012",
            address_line="20 boulevard Exemple",
            postal_code="42000",
            city="Saint-Étienne",
            phone="04 00 00 00 00",
            email="contact@exemple.fr",
            signatory_name="M. Exemple",
            signatory_role="gérant",
        ),
        client="Entreprise générale Exemple",
        contact="Mme Exemple — contact@eg-exemple.fr",
        subject="Annexe du lycée — nettoyage",
        reference="Lot 16 — Plâtrerie, peinture, plafonds",
        inclusions=[INCLUSION],
        table=QuoteTable(ROWS, [OPTION], 397_575, 30_000),
        brand_color=None,
        logo=None,
    )
    return base.__class__(**{**base.__dict__, **changes})


def text_of(content: bytes) -> str:
    doc = Document(io.BytesIO(content))
    parts = [p.text for p in doc.paragraphs]
    for table in doc.tables:
        for row in table.rows:
            parts.append(" | ".join(c.text for c in row.cells))
    return "\n".join(parts)


def test_money_and_quantities_are_written_the_french_way() -> None:
    assert money(187_500) == "1 875,00 €"
    assert money(5) == "0,05 €"
    assert money(-12_345) == "-123,45 €"
    assert quantity(Decimal(1250)) == "1 250"
    assert quantity(Decimal("800.50")) == "800,5"
    assert quantity(None) == "—"


def test_the_quote_says_who_what_how_much_and_where_it_comes_from() -> None:
    text = text_of(build_quote(data()).to_bytes())
    assert "Devis n° D-2026-0001" in text and "17 novembre 2026" in text
    assert "valable 30 jours, jusqu'au 17 décembre 2026" in text
    assert "ENG PRO" in text and "SIRET 123 456 789 00012" in text
    assert "Entreprise générale Exemple" in text and "Mme Exemple — contact@eg-exemple.fr" in text
    assert "Lot 16 — Plâtrerie, peinture, plafonds" in text
    assert "Nettoyage des sols et des menuiseries avant les OPR. (CCTP lot 16.pdf, p. 41)" in text
    assert "12.1 Nettoyage avant OPR" in text
    assert "Bâtiment B | m² | 800,5 | 1,50 € | 1 200,75 €" in text
    assert "Total HT | 3 975,75 €" in text
    assert "TVA 20 % | 795,15 €" in text
    assert "Total TTC | 4 770,90 €" in text
    assert "Vitrerie haute" in text and "non comprises dans le total" in text
    assert "Bon pour accord" in text and "M. Exemple, gérant" in text
    assert "[À COMPLÉTER" not in text


def test_what_is_missing_is_asked_for_never_guessed() -> None:
    company = data().company.__class__(
        name="ENG PRO", legal_form=None, siret="12345678900012", address_line=None,
        postal_code=None, city=None, phone=None, email=None, signatory_name=None,
        signatory_role=None,
    )  # fmt: skip
    built = build_quote(data(company=company, client=None, inclusions=[]))
    text = text_of(built.to_bytes())
    assert "[À COMPLÉTER : adresse de l'entreprise]" in text
    assert "[À COMPLÉTER : nom du client]" in text
    assert "telles que décrites dans le dossier du client" in text  # no bullet invented
    assert "[À COMPLÉTER : adresse de l'entreprise]" in "".join(
        f"[À COMPLÉTER : {t}]" for t in built.to_complete
    )


def test_unit_prices_only_give_no_totals() -> None:
    rows = [QuoteRow("Bordereau", "Heure de régie", "heure", None, 3500, None)]
    text = text_of(build_quote(data(table=QuoteTable(rows, [], 0, 0))).to_bytes())
    assert "Heure de régie | heure | — | 35,00 € | —" in text
    assert "Total TTC" not in text and "selon les quantités commandées" in text


def test_a_reduced_vat_rate_is_written_with_its_decimal() -> None:
    text = text_of(build_quote(data(vat_bp=550)).to_bytes())
    assert "TVA 5,5 % | 218,67 €" in text
