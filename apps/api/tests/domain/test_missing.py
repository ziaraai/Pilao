import pytest

from app.domain.missing import answer, classify, marker_key, markers, remove, splice, units

SENT = (
    "## 2. Équipe\n\nNous intervenons tôt. Équipe : [À COMPLÉTER : nombre d'agents] agents"
    " formés. Le reste suit.\n"
)
KEY = marker_key("nombre d'agents")


def test_marker_key_normalizes() -> None:
    assert (
        marker_key("Nombre d'agents  affectés.")
        == marker_key("nombre d’agents affectes")
        == "nombre d agents affectes"
    )


@pytest.mark.parametrize(
    "text,kind",
    [
        ("nombre d'agents affectés au site", "staff"),
        ("nom du chef d'équipe", "staff"),
        ("autolaveuse pour les grandes surfaces", "equipment"),
        ("certification qualité", "certification"),
        ("références de chantiers similaires", "reference"),
        ("SIRET", "identity"),
        ("chiffre d'affaires 2025", "identity"),
        ("effectif total de l'entreprise", "identity"),
        ("horaires d'intervention sur ce site", "tender"),
    ],
)
def test_classify(text: str, kind: str) -> None:
    assert classify(text) == kind


def test_markers_lists_every_marker_with_its_key() -> None:
    found = markers(SENT + "Et [à compléter: Horaires].\n")
    assert [(m.key, m.text) for m in found] == [
        (KEY, "nombre d'agents"),
        ("horaires", "Horaires"),
    ]
    assert SENT[found[0].start : found[0].end] == "[À COMPLÉTER : nombre d'agents]"


def test_unit_is_the_sentence() -> None:
    [u] = units(SENT, KEY)
    assert u.shape == "sentence"
    assert u.text == "Équipe : [À COMPLÉTER : nombre d'agents] agents formés."


def test_abbreviation_is_not_a_sentence_end() -> None:
    md = "## T\n\nLe responsable M. Dupont encadre [À COMPLÉTER : nombre d'agents] agents. Fin.\n"
    assert units(md, KEY)[0].text == (
        "Le responsable M. Dupont encadre [À COMPLÉTER : nombre d'agents] agents."
    )


def test_list_line_and_table_cell() -> None:
    md = (
        "## T\n\n- [À COMPLÉTER : autolaveuse] pour les halls\n\n"
        "| Matériel | [À COMPLÉTER : autolaveuse] |\n|---|---|\n"
    )
    a, b = units(md, marker_key("autolaveuse"))
    assert (a.shape, a.text) == ("line", "[À COMPLÉTER : autolaveuse] pour les halls")
    assert (b.shape, b.text) == ("cell", "[À COMPLÉTER : autolaveuse]")


def test_variant_spelling_has_the_same_key() -> None:
    md = "## T\n\nA [à compléter: Nombre d’agents] b. C [À COMPLÉTER :  nombre d'agents] d.\n"
    assert len(units(md, KEY)) == 2


def test_same_sentence_twice_is_one_unit() -> None:
    md = "## T\n\nDe [À COMPLÉTER : nombre d'agents] à [À COMPLÉTER : nombre d'agents] agents.\n"
    assert len(units(md, KEY)) == 1


def test_splice_changes_only_the_unit() -> None:
    [u] = units(SENT, KEY)
    out = splice(SENT, u, "Équipe : 4 agents formés.")
    assert out == SENT.replace(u.text, "Équipe : 4 agents formés.")


def test_answer_replaces_every_marker_of_the_key_only() -> None:
    md = SENT + "Encore [À COMPLÉTER : nombre d'agents]. Et [À COMPLÉTER : horaires].\n"
    out = answer(md, KEY, "4")
    assert "[À COMPLÉTER : nombre d'agents]" not in out
    assert "Équipe : 4 agents formés." in out and "Encore 4." in out
    assert "[À COMPLÉTER : horaires]" in out


def test_remove_sentence_list_cell_heading() -> None:
    assert remove(SENT, KEY) == "## 2. Équipe\n\nNous intervenons tôt. Le reste suit.\n"
    md = (
        "## T\n\n- garder\n- [À COMPLÉTER : autolaveuse] pour les halls\n\n"
        "| Matériel | [À COMPLÉTER : autolaveuse] |\n|---|---|\n"
    )
    out = remove(md, marker_key("autolaveuse"))
    assert "- garder" in out and "pour les halls" not in out
    assert "| Matériel |  |" in out and "|---|---|" in out
    head = "## Équipe [À COMPLÉTER : nombre d'agents]\n\nTexte.\n"
    assert remove(head, KEY) == "## Équipe\n\nTexte.\n"


def test_remove_drops_an_emptied_paragraph() -> None:
    md = "## T\n\nAvant.\n\nSeule [À COMPLÉTER : nombre d'agents] phrase.\n\nAprès.\n"
    assert remove(md, KEY) == "## T\n\nAvant.\n\nAprès.\n"


def test_remove_last_sentence_of_a_paragraph() -> None:
    md = "## T\n\nPremière phrase. Équipe de [À COMPLÉTER : nombre d'agents] agents.\n\nFin.\n"
    assert remove(md, KEY) == "## T\n\nPremière phrase.\n\nFin.\n"


def test_unknown_key_changes_nothing() -> None:
    assert answer(SENT, "inconnu", "x") == SENT
    assert remove(SENT, "inconnu") == SENT
    assert units(SENT, "inconnu") == []
