"""Same cases as apps/web/lib/markdown.test.ts: the page and the export read chapters alike."""

from app.domain.markdown import Heading, ListBlock, Paragraph, Run, Table, inline, parse


def t(text: str) -> Run:
    return Run("text", text)


def test_titles_paragraphs_lists_and_tables() -> None:
    blocks = parse(
        "## 2. Méthodologie\n"
        "\n"
        "Nous intervenons\n"
        "avant 8h.\n"
        "\n"
        "- quotidien\n"
        "* hebdomadaire\n"
        "1. Accueil\n"
        "2) Bureaux\n"
        "\n"
        "| Zone | Fréquence |\n"
        "|---|:---:|\n"
        "| Bureaux | **quotidienne** |\n"
        "Après le tableau."
    )
    assert blocks == [
        Heading(2, [t("2. Méthodologie")]),
        Paragraph([t("Nous intervenons avant 8h.")]),
        ListBlock(False, [[t("quotidien")], [t("hebdomadaire")]]),
        ListBlock(True, [[t("Accueil")], [t("Bureaux")]]),
        Table([[t("Zone")], [t("Fréquence")]], [[[t("Bureaux")], [Run("strong", "quotidienne")]]]),
        Paragraph([t("Après le tableau.")]),
    ]


def test_to_complete_markers_are_their_own_run() -> None:
    assert inline("Nous affectons [À COMPLÉTER : nombre d'agents] agents, *formés*.") == [
        t("Nous affectons "),
        Run("todo", "nombre d'agents"),
        t(" agents, "),
        Run("em", "formés"),
        t("."),
    ]
    assert inline("[à compléter: SIRET]") == [Run("todo", "SIRET")]


def test_html_and_odd_characters_stay_plain_text() -> None:
    assert parse("<script>alert(1)</script> 3 * 4 = 12_000_") == [
        Paragraph([t("<script>alert(1)</script> 3 * 4 = 12_000_")])
    ]
