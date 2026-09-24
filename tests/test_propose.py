import psycopg2
import pytest

from pipeline.propose import MODEL, THRESHOLD, clusters, main, proposals

VECTORS = {
    "Indenização por Dano Moral": [1.0, 0.0, 0.0],
    "Dano Moral": [0.99, 0.05, 0.0],
    "Planos de Saúde": [0.0, 1.0, 0.0],
    "Plano de Saúde": [0.02, 0.99, 0.0],
    "Usucapião": [0.0, 0.0, 1.0],
}


def fake_encoder(names):
    return [VECTORS[name] for name in names]


def test_uses_the_local_multilingual_model_and_the_curated_threshold():
    assert MODEL == "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    assert THRESHOLD == 0.20


def test_clusters_close_names_and_keeps_distant_ones_apart():
    names = list(VECTORS)

    result = clusters(names, fake_encoder(names), THRESHOLD)

    assert sorted(sorted(group) for group in result) == [
        ["Dano Moral", "Indenização por Dano Moral"],
        ["Plano de Saúde", "Planos de Saúde"],
        ["Usucapião"],
    ]


def test_proposes_only_groups_with_a_subject_outside_the_curation():
    groups = [{"aliases": ["Indenização por Dano Moral", "Dano Moral"]}]
    counts = {name: 1 for name in VECTORS}

    result = proposals(VECTORS, groups, counts, encoder=fake_encoder)

    assert result == [{"total_cases": 2, "members": ["Plano de Saúde", "Planos de Saúde"]}]


def test_orders_the_proposals_by_case_volume():
    counts = {
        "Indenização por Dano Moral": 1, "Dano Moral": 1,
        "Planos de Saúde": 30, "Plano de Saúde": 5, "Usucapião": 99,
    }

    result = proposals(VECTORS, [], counts, encoder=fake_encoder)

    assert result == [
        {"total_cases": 35, "members": ["Planos de Saúde", "Plano de Saúde"]},
        {"total_cases": 2, "members": ["Dano Moral", "Indenização por Dano Moral"]},
    ]


def test_proposes_nothing_without_subjects():
    assert proposals([], [], {}, encoder=fake_encoder) == []


@pytest.fixture
def subjects(dw_ready, monkeypatch):
    with psycopg2.connect(dw_ready) as connection, connection.cursor() as cur:
        cur.execute("TRUNCATE dw.dim_subject RESTART IDENTITY CASCADE")
        cur.executemany(
            "INSERT INTO dw.dim_subject (subject_name, subject_code) VALUES (%s, %s)",
            [(name, code) for code, name in enumerate(VECTORS, start=1)],
        )
    monkeypatch.setenv("DATABASE_URL", dw_ready)
    return dw_ready


def test_main_prints_the_proposals_read_from_the_warehouse(subjects, capsys):
    exit_code = main(groups=[], encoder=fake_encoder)

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Plano de Saúde | Planos de Saúde" in output
    assert "Usucapião" not in output


def test_main_fails_clearly_without_the_database_url(monkeypatch, capsys):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    assert main(groups=[], encoder=fake_encoder) == 1
    assert "DATABASE_URL is not set" in capsys.readouterr().err
