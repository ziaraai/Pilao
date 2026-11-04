from app.domain.memoir_plan import (
    SECTOR_DEFAULT_OUTLINE,
    Criterion,
    assign_requirements,
    assign_word_budgets,
    build_outline,
    flatten_criteria,
    template_outline,
)

CRITERIA = flatten_criteria(
    [
        {
            "name": "Valeur technique",
            "weight_pct": 60,
            "subcriteria": [
                {"name": "Moyens humains et encadrement", "weight_pct": 20},
                {"name": "Méthodologie d'intervention", "weight_pct": 30},
                {"name": "Démarche environnementale", "weight_pct": 10},
            ],
        },
        {"name": "Prix", "weight_pct": 40},
    ]
)


def test_flatten_keeps_subcriteria_and_drops_price() -> None:
    assert [c.name for c in CRITERIA] == [
        "Moyens humains et encadrement",
        "Méthodologie d'intervention",
        "Démarche environnementale",
    ]
    assert flatten_criteria(
        [
            {"name": "Valeur technique", "weight_pct": 70},
            {"name": "Prix des prestations", "weight_pct": 30},
        ]
    ) == [Criterion("Valeur technique", 70.0)]


def test_imposed_outline_is_kept_word_for_word_and_in_order() -> None:
    imposed = ["3. Démarche environnementale", "1. Moyens humains et encadrement", "Annexe : CV"]
    source, sections = build_outline(imposed, ["Mon plan à moi"], CRITERIA)
    assert source == "rc_imposed" and [s.title for s in sections] == imposed  # never reordered
    assert sections[0].criterion == "Démarche environnementale" and sections[1].weight == 20.0


def test_template_outline_is_ordered_by_the_criteria() -> None:
    template = [
        "1. Notre démarche environnementale",
        "2. Présentation",
        "3. Méthodologie d'intervention",
        "4. Moyens humains",
    ]
    source, sections = build_outline([], template, CRITERIA)
    assert source == "org_template"
    assert [s.title for s in sections] == [
        "4. Moyens humains",
        "3. Méthodologie d'intervention",
        "1. Notre démarche environnementale",
        "2. Présentation",
    ]


def test_sector_default_when_nothing_else() -> None:
    source, sections = build_outline([], [], [])
    assert source == "sector_default" and tuple(s.title for s in sections) == SECTOR_DEFAULT_OUTLINE


def test_template_headings_keep_top_level_chapters() -> None:
    headings = [
        "1. Présentation",
        "1.1 Historique",
        "1.1 Historique",
        "2. Moyens",
        "2.1 Équipe",
        "II. Annexes",
    ]
    assert template_outline(headings) == [
        "1. Présentation",
        "2. Moyens",
        "II. Annexes",
    ]  # sub-titles left out
    assert template_outline(["Introduction", "Moyens"]) == [
        "Introduction",
        "Moyens",
    ]  # no numbering: all


def test_requirements_go_to_the_chapter_that_answers_them() -> None:
    _, sections = build_outline([], [], [])
    assign_requirements(
        sections,
        [
            ("CCTP-1", "staff", "Un chef d'équipe présent sur site"),
            ("CCTP-2", "frequency", "Nettoyage quotidien des bureaux"),
            ("CCTP-3", "product", "Produits écolabellisés"),
            ("CCTP-4", "quality", "Contrôle contradictoire mensuel"),
            ("CCTP-5", "environment", "Tri des déchets"),
            ("CCTP-6", "other", "Clause sans catégorie"),
        ],
    )
    where = {ref: s.title for s in sections for ref in s.requirement_refs}
    assert where["CCTP-1"].startswith("Organisation et moyens humains")
    assert where["CCTP-2"].startswith("Méthodologie")
    assert where["CCTP-3"].startswith("Moyens matériels et produits")
    assert where["CCTP-4"].startswith("Contrôle qualité")
    assert where["CCTP-5"].startswith("Démarche environnementale")
    assert where["CCTP-6"].startswith("Présentation") or where["CCTP-6"].startswith("Méthodologie")


def test_every_requirement_lands_somewhere_even_with_an_odd_imposed_outline() -> None:
    _, sections = build_outline(["A", "B"], [], [])
    assign_requirements(sections, [("CCTP-1", "staff", "x"), ("CCTP-2", "other", "y")])
    assert sum(len(s.requirement_refs) for s in sections) == 2


def test_word_budgets_follow_weights_and_page_limit() -> None:
    _, sections = build_outline(
        ["Moyens humains et encadrement", "Méthodologie d'intervention", "Présentation"],
        [],
        CRITERIA,
    )
    total = assign_word_budgets(sections, max_pages=10)
    budgets = [s.word_budget for s in sections]
    assert total == 4500 and sum(budgets) <= total + 100
    assert budgets[1] > budgets[0] > budgets[2]  # 30 % > 20 % > unweighted
    assert all(b % 50 == 0 and b >= 150 for b in budgets)
    _, equal = build_outline([], [], [])
    assign_word_budgets(equal, None)
    assert len({s.word_budget for s in equal}) == 1  # no criteria: equal split of 12 pages


def test_a_short_moyens_chapter_receives_staff_equipment_and_products() -> None:
    _, sections = build_outline(["1. Moyens", "2. Méthodologie"], [], [])
    assign_requirements(
        sections,
        [
            ("CCTP-1", "frequency", "Nettoyage quotidien"),
            ("CCTP-2", "product", "Produits écolabellisés"),
            ("CCTP-3", "staff", "Chef d'équipe"),
        ],
    )
    assert sections[0].requirement_refs == ["CCTP-2", "CCTP-3"] and sections[
        1
    ].requirement_refs == ["CCTP-1"]
