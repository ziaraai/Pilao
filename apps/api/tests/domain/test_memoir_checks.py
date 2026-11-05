from app.domain.memoir_checks import check_chapter, flags_after_edit, force_title, numbers_in

CONTEXT = """Effectif : 12 agents. Autolaveuses : 3. Surface : 2 500 m². Chiffre d'affaires 1 250 000 €.
Exigence CCTP-1 : passage quotidien avant 8h."""


def kinds(flags):  # type: ignore[no-untyped-def]
    return [f.type for f in flags]


def test_title_is_forced_to_the_planned_one() -> None:
    assert force_title("## Un autre titre\n\nTexte.", "2. Méthodologie").startswith(
        "## 2. Méthodologie\n\nTexte."
    )
    assert force_title("Texte sans titre.", "Moyens") == "## Moyens\n\nTexte sans titre."


def test_numbers_are_normalized() -> None:
    assert numbers_in("2 500 m² et 1 250 000 € ou 3,50 €, avant 8h, 15min") == {
        "2500",
        "1250000",
        "3.5",
        "8",
        "15",
    }
    assert numbers_in("exigence CCTP-12, norme ISO9001") == set()  # references and codes in words


def test_numbers_from_the_inputs_are_fine_invented_ones_are_flagged() -> None:
    text = "## Moyens\n\nNous affectons 12 agents et 3 autolaveuses sur 2 500 m². Nous avons 45 salariés."
    flags = check_chapter(text, CONTEXT, [], 400)
    numbers = [f.text for f in flags if f.type == "number"]
    assert len(numbers) == 1 and numbers[0].startswith("45 — absent de vos données")


def test_to_complete_markers_and_commitments() -> None:
    text = (
        "## Qualité\n\nNous garantissons une intervention sous 2 heures. [À COMPLÉTER : nom du chef d'équipe]\n"
        "- Contrôle mensuel."
    )
    flags = check_chapter(text, CONTEXT, ["Réunion trimestrielle avec l'acheteur."], 400)
    assert ("to_complete", "nom du chef d'équipe") in [(f.type, f.text) for f in flags]
    commitments = [f.text for f in flags if f.type == "commitment"]
    assert commitments[0].startswith("Nous garantissons une intervention sous 2 heures")
    assert "Réunion trimestrielle avec l'acheteur." in commitments


def test_numbers_inside_to_complete_markers_are_not_flagged_twice() -> None:
    flags = check_chapter("## X\n\n[À COMPLÉTER : nombre d'agents, ex. 15]", CONTEXT, [], 400)
    assert kinds(flags) == ["to_complete"]


def test_length_warning() -> None:
    long_text = "## X\n\n" + "mot " * 600
    assert "length" in kinds(check_chapter(long_text, CONTEXT, [], 400))
    assert "length" not in kinds(check_chapter("## X\n\n" + "mot " * 400, CONTEXT, [], 400))


def test_an_invented_duration_glued_to_its_unit_is_flagged() -> None:
    flags = check_chapter("## X\n\nNous intervenons en 45min sur site.", CONTEXT, [], 400)
    assert any(f.type == "number" and f.text.startswith("45") for f in flags)


def test_proper_nouns_absent_from_the_inputs_are_flagged() -> None:
    context = CONTEXT + " Client : Ville de Lyon. Produits Ecolab."
    text = (
        "## Moyens\n\nNous travaillons avec Ecolab et la Ville de Lyon. "
        "Notre chef d'équipe Jean Dupont encadre le site, certifié MASE selon le CCTP.\n"
        "- Kärcher fournit les autolaveuses.\n"
        "| Zone | Produit |\n|---|---|\n| Hall | Diversey Taski |\n"
        "Objectif : Zéro réclamation (Voir annexe)."
    )
    flags = [f for f in check_chapter(text, context, [], 400) if f.type == "name"]
    # Known (context), sentence or cell starts, generic words and acronyms are not names.
    assert [(f.term, f.text.split(" — ")[0]) for f in flags] == [
        ("Jean Dupont", "Jean Dupont"),
        ("MASE", "MASE"),
        ("Taski", "Taski"),
    ]
    assert flags[0].text == (
        "Jean Dupont — absent de vos données : Notre chef d'équipe Jean Dupont encadre le site,"
        " certifié MASE selon le CCTP."
    )


def test_each_flag_says_what_to_highlight() -> None:
    text = "## X\n\nNous garantissons un passage sous 2 heures. Nous avons 45 salariés."
    flags = check_chapter(text, CONTEXT, ["Engagement absent du texte"], 400)
    assert [(f.type, f.term) for f in flags] == [
        ("commitment", "Nous garantissons un passage sous 2 heures."),
        ("commitment", None),
        ("number", "45"),
    ]


def test_after_an_edit_the_user_words_are_trusted() -> None:
    previous = [
        {"type": "number", "text": "45 — absent", "term": "45"},
        {"type": "number", "text": "37 — absent", "term": "37"},
        {"type": "name", "text": "Jean Dupont — absent", "term": "Jean Dupont"},
        {"type": "commitment", "text": "Ancien engagement", "term": None},
    ]
    edited = (
        "## X\n\nNous avons 45 salariés et 99 machines. Nous nous engageons à rappeler sous 4 h."
        " [À COMPLÉTER : nom du référent]"
    )
    flags = flags_after_edit(edited, previous, 400)
    assert [(f.type, f.term) for f in flags] == [
        ("to_complete", None),
        ("commitment", "Nous nous engageons à rappeler sous 4 h."),
        ("number", "45"),  # still there: still to check; 37 and Jean Dupont were removed
    ]  # 99 was typed by the user: not flagged
