from pipeline.theme_build import build, load_groups


def test_a_subject_in_a_curated_group_joins_the_group_theme():
    subjects = [("Atraso de vôo", 1), ("Cancelamento de vôo", 2)]
    groups = [{
        "aliases": ["Atraso de vôo", "Cancelamento de vôo"],
        "theme_name": "Voos", "subject_area": "CONSUMIDOR",
    }]

    themes = build(subjects, groups)

    assert themes == [
        {"theme_name": "Voos", "subject_area": "CONSUMIDOR", "subject_sks": [1, 2]}
    ]


def test_a_subject_outside_any_group_becomes_its_own_theme():
    subjects = [("Um Assunto Qualquer", 5)]

    themes = build(subjects, [])

    assert themes == [
        {"theme_name": "Um Assunto Qualquer", "subject_area": None, "subject_sks": [5]}
    ]


def test_a_group_with_only_some_aliases_present_still_forms_a_theme():
    subjects = [("Atraso de vôo", 1)]
    groups = [{
        "aliases": ["Atraso de vôo", "Cancelamento de vôo"],
        "theme_name": "Voos", "subject_area": "CONSUMIDOR",
    }]

    themes = build(subjects, groups)

    assert themes == [
        {"theme_name": "Voos", "subject_area": "CONSUMIDOR", "subject_sks": [1]}
    ]


def test_a_group_with_no_aliases_present_produces_no_theme():
    subjects = [("Outro Assunto", 9)]
    groups = [{"aliases": ["Atraso de vôo"], "theme_name": "Voos", "subject_area": "CONSUMIDOR"}]

    themes = build(subjects, groups)

    assert themes == [
        {"theme_name": "Outro Assunto", "subject_area": None, "subject_sks": [9]}
    ]


def test_a_subject_named_after_a_curated_theme_joins_it():
    subjects = [("Dano Moral Direto", 1), ("Dano", 2)]
    groups = [{"aliases": ["Dano Moral Direto"], "theme_name": "Dano", "subject_area": "CIVIL"}]

    themes = build(subjects, groups)

    assert themes == [{"theme_name": "Dano", "subject_area": "CIVIL", "subject_sks": [1, 2]}]


def test_subjects_with_the_same_name_become_one_theme():
    subjects = [("Plano de Saúde", 1), ("Plano de Saúde", 2)]

    themes = build(subjects, [])

    assert themes == [
        {"theme_name": "Plano de Saúde", "subject_area": "SAUDE", "subject_sks": [1, 2]}
    ]


def test_subjects_named_alike_but_for_case_and_accents_become_one_theme():
    subjects = [
        ("Desconsideração da Personalidade Jurídica", 1),
        ("Desconsideracao da personalidade juridica", 2),
    ]

    themes = build(subjects, [])

    assert [(theme["theme_name"], theme["subject_sks"]) for theme in themes] == [
        ("Desconsideração da Personalidade Jurídica", [1, 2])
    ]


def test_an_alias_takes_every_subject_with_its_name():
    subjects = [("Planos de Saúde", 1), ("Planos de Saúde", 2)]
    groups = [
        {"aliases": ["Planos de Saúde"], "theme_name": "Planos de saúde", "subject_area": "SAUDE"}
    ]

    themes = build(subjects, groups)

    assert themes == [
        {"theme_name": "Planos de saúde", "subject_area": "SAUDE", "subject_sks": [1, 2]}
    ]


def test_the_health_plan_subjects_form_a_single_curated_theme():
    group = next(group for group in load_groups() if group["theme_name"] == "Planos de saúde")

    assert "Plano de Saúde" in group["aliases"]
