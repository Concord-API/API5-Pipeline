from pipeline.theme_build import load_groups


def test_load_groups_reads_the_vendored_curation():
    groups = load_groups()

    assert len(groups) == 25
    assert all({"aliases", "theme_name", "subject_area"} <= set(g) for g in groups)


def test_load_groups_accepts_a_custom_path(tmp_path):
    path = tmp_path / "groups.json"
    path.write_text(
        '[{"aliases": ["A"], "theme_name": "Tema", "subject_area": "CIVIL"}]',
        encoding="utf-8",
    )

    groups = load_groups(str(path))

    assert groups == [{"aliases": ["A"], "theme_name": "Tema", "subject_area": "CIVIL"}]
