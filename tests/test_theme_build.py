from pipeline.theme_build import build


def test_a_subject_in_a_curated_group_joins_the_group_theme():
    subjects = [("Atraso de vôo", 1), ("Cancelamento de vôo", 2)]
    groups = [{"aliases": ["Atraso de vôo", "Cancelamento de vôo"], "theme_name": "Voos", "subject_area": "CONSUMIDOR"}]

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
    groups = [{"aliases": ["Atraso de vôo", "Cancelamento de vôo"], "theme_name": "Voos", "subject_area": "CONSUMIDOR"}]

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


def test_duplicate_theme_names_get_a_numbered_suffix():
    subjects = [("Dano Moral Direto", 1), ("Dano", 2)]
    groups = [{"aliases": ["Dano Moral Direto"], "theme_name": "Dano", "subject_area": "CIVIL"}]

    themes = build(subjects, groups)

    names = [t["theme_name"] for t in themes]
    assert names == ["Dano", "Dano (2)"]
